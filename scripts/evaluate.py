"""VERITAS evaluation: calibrate on the CALIBRATION split, report HELD-OUT numbers only.

    uv run python scripts/evaluate.py                 # images + audio (+ videos if present)
    uv run python scripts/evaluate.py --kind images

Pass 1 runs the real analysis pipeline on every calibration file and fits:
  * a calibration curve for each neural detector (logistic regression on the log-odds of its raw probability),
  * the fusion gain/bias (logistic regression on the weighted mean log-odds).
These are saved to server/calibration.json (the live server loads them at start-up).
Pass 2 re-runs the pipeline - now calibrated - on the held-out TEST files that pass 1 never touched, and writes
web/data/results.json (accuracy, precision, recall, F1, ROC AUC, confusion matrix, ROC curve, per-test AUC, latency).

Images are evaluated in two conditions:
  laundered - every file re-encoded identically (JPEG q90, metadata stripped) so file type can't give the answer away
              (this is the HEADLINE number), and
  as_found  - the original files, metadata included.
Calibration also sees every calibration image after realistic degradations (webcam, phone denoise, H.264 video
still, small web copy - evalcommon.degrade), so a smoothed webcam frame of a real person is not mistaken for AI.
The held-out files are then tested under the same degradations plus WhatsApp-style recompression (robustness
table), and - when ../_incoming/media is present - on stills from real research videos (external check).
The split is GROUP-aware (speaker / prompt / face-swap sources never straddle it), see evalcommon.assign_split.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import time
from datetime import datetime, timezone

import numpy as np

from evalcommon import DEGRADATIONS, EVAL, ROOT, degrade, launder, load_items, roc_auc, roc_points

INCOMING = ROOT.parent / "_incoming" / "media"
REUSE_PASS1 = False

CAL_FILE = ROOT / "server" / "calibration.json"
RESULTS = ROOT / "web" / "data" / "results.json"
DETAILS = EVAL / "eval_details.json"

NEURAL = {"images": ["ai_generated", "ai_face"], "audio": ["ai_voice"]}
# classic tests whose "missing camera fingerprint" part is a tiny logistic model fitted on the calibration split
FEATURE_MODELS = {
    "images": {"noise": {"log_sigma": lambda m: math.log(m["noise_sigma"] + 1e-3), "spread": lambda m: m["residual_spread"]},
               "fft": {"grid_peak": lambda m: m["grid_peak"], "isolated_peak": lambda m: m["isolated_peak"],
                       "hf_excess": lambda m: m["hf_excess"]}},
}


def fit_feature_model(X: np.ndarray, y: np.ndarray, names: list[str]) -> dict:
    from sklearn.linear_model import LogisticRegression

    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    lr = LogisticRegression(C=0.3, class_weight="balanced").fit((X - mu) / sd, y)
    return {"features": names, "coef": [round(float(c), 4) for c in lr.coef_[0]],
            "intercept": round(float(lr.intercept_[0]), 4), "mean": [round(float(v), 5) for v in mu],
            "std": [round(float(v), 5) for v in sd], "n": int(len(y))}


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-5, 1 - 1e-5)
    return np.log(p / (1 - p))


def fit_curve(raw: list[float], y: list[int], constrain: bool = False) -> dict | None:
    """Logistic calibration of a detector's raw probability (0-100) -> calibrated score (0-100).
    constrain=True (image detectors): the curve may not call something 'synthetic' (> 65) unless the network's own
    probability is at least 25%, nor push a raw 0.5% above 20 - a guard against over-confident calibration when the
    real calibration photos are much cleaner than what the booth will see."""
    from sklearn.linear_model import LogisticRegression

    raw, y = np.asarray(raw, dtype=float), np.asarray(y)
    ok = np.isfinite(raw)
    raw, y = raw[ok], y[ok]
    if len(set(y.tolist())) < 2 or len(y) < 8:
        return None
    X = _logit(raw / 100).reshape(-1, 1)
    lr = LogisticRegression(C=0.5, class_weight="balanced").fit(X, y)
    a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    a = float(np.clip(a, 0.15, 3.0))
    fitted = (round(a, 4), round(b, 4))
    if constrain:
        a = max(a, 0.5)
        l = lambda q: math.log(q / (1 - q))  # noqa: E731
        b = min(b, l(0.65) - a * l(0.25), l(0.20) - a * l(0.005))
    xs = np.unique(np.concatenate([np.logspace(-3, np.log10(50), 40), 100 - np.logspace(np.log10(50), -3, 40)]))
    ys = 100 / (1 + np.exp(-(a * _logit(xs / 100) + b)))
    return {"x": [round(float(v), 5) for v in xs], "y": [round(float(v), 3) for v in ys], "a": round(a, 4), "b": round(b, 4),
            "fitted_a_b": list(fitted), "constrained": constrain}


def fit_fusion(reports: list[dict], y: list[int], kind: str) -> dict:
    from sklearn.linear_model import LogisticRegression

    Z = []
    for rep in reports:
        z = 0.0
        for t in rep["tests"]:
            if t["status"] == "ok" and t["score"] is not None and t["weight"] > 0:
                p = min(0.985, max(0.015, t["score"] / 100))
                z += t["weight"] * math.log(p / (1 - p))
        Z.append(z)
    lr = LogisticRegression(C=1.0, class_weight="balanced").fit(np.array(Z).reshape(-1, 1), np.array(y))
    gain = float(np.clip(lr.coef_[0, 0], 0.7, 3.0))
    # The bias is kept small on purpose. Calibration includes degraded fakes whose fingerprints are destroyed;
    # an unconstrained fit lowers the decision line to 'catch' them, which pushes ordinary compressed REAL photos
    # (webcam frames, video stills) over 50. |bias| <= 0.5 keeps the verdict a sharpened version of the tests' vote.
    bias = float(np.clip(lr.intercept_[0], -0.5, 0.5))
    return {"gain": round(gain, 4), "bias": round(bias, 4), "fitted_bias": round(float(lr.intercept_[0]), 4)}


def run_pipeline(kind: str, data: bytes, name: str, keep_private: bool = False) -> dict:
    from server import pipeline

    fn = {"images": pipeline.analyze_image, "audio": pipeline.analyze_audio, "video": pipeline.analyze_video}[kind]
    t0 = time.perf_counter()
    rep = fn(data, name, keep_private=True) if keep_private else fn(data, name)
    rep["_ms"] = (time.perf_counter() - t0) * 1000
    return rep


def rescore_image(rep: dict) -> dict:
    """Apply the (new) calibration curves to a pass-1 image report and fuse again (same maths as the pipeline)."""
    import copy

    from server import fusion
    from server.forensics import ai_face
    from server.forensics.base import calibrated

    rep = copy.deepcopy(rep)
    for t in rep["tests"]:
        if t["status"] != "ok":
            continue
        if t["id"] == "ai_generated" and t["metrics"].get("raw") is not None:
            t["score"] = int(round(calibrated("ai_generated", t["metrics"]["raw"])))
        elif t["id"] == "ai_face" and t.get("_faces_raw"):
            faces = [{"score": calibrated("ai_face", p * 100), "box": [0, 0, a, 1]} for p, a in t["_faces_raw"]]
            t["score"] = int(round(ai_face.summarise(faces)))
    marker = any(t["id"] == "metadata" and t["status"] == "ok" and (t["metrics"].get("ai_markers") or 0) > 0
                 for t in rep["tests"])
    rep.update(fusion.fuse("image", rep["tests"], hard_ai_marker=marker))
    return rep


def slim(rep: dict) -> dict:
    return {"score": rep["score"], "verdict": rep["verdict"], "confidence": rep["confidence"], "ms": round(rep["_ms"]),
            "tests": {t["id"]: {"score": t["score"], "status": t["status"], "raw": t["metrics"].get("raw"),
                                "weight": t["weight"]} for t in rep["tests"]}}


def binary_metrics(y, s, ms) -> dict:
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    pred = s > 50
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    tn = int((~pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    return {
        "metrics": {"accuracy": round((tp + tn) / max(1, len(y)), 4), "precision": round(prec, 4),
                    "recall": round(rec, 4), "f1": round(2 * prec * rec / max(1e-9, prec + rec), 4),
                    "auc": round(roc_auc(y, s), 4), "mean_latency_ms": int(round(float(np.mean(ms))))},
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "roc": roc_points(y, s, 50),
        "verdicts": {"authentic": int((s < 35).sum()), "suspicious": int(((s >= 35) & (s <= 65)).sum()),
                     "synthetic": int((s > 65).sum())},
    }


def per_test_auc(rows: list[dict], y: list[int], names: dict) -> list[dict]:
    out = []
    ids = list(rows[0]["tests"].keys()) if rows else []
    for tid in ids:
        ys, ss = [], []
        for r, yy in zip(rows, y):
            t = r["tests"][tid]
            if t["status"] == "ok" and t["score"] is not None:
                ys.append(yy)
                ss.append(t["score"])
        if not ss or len(set(ys)) < 2:
            continue
        out.append({"id": tid, "name": names.get(tid, tid), "auc": round(roc_auc(ys, ss), 4), "n": len(ss)})
    return out


def by_group(items, rows) -> list[dict]:
    g = {}
    for it, r in zip(items, rows):
        k = (it["group"], "fake" if it["y"] else "real")
        g.setdefault(k, []).append(r["score"])
    out = []
    for (grp, lab), sc in sorted(g.items()):
        sc = np.array(sc)
        out.append({"group": grp, "label": lab, "n": len(sc), "flagged_pct": round(float((sc > 50).mean() * 100), 1),
                    "mean_score": round(float(sc.mean()), 1)})
    return out


def evaluate_kind(kind: str, details: dict) -> dict | None:
    from server import config
    from server.models import REGISTRY

    items = load_items(kind)
    if not items:
        print(f"[{kind}] no files")
        return None
    calib = [it for it in items if it["split"] == "calib"]
    test = [it for it in items if it["split"] == "test"]
    print(f"[{kind}] {len(items)} files: calib {len(calib)} / held-out {len(test)}")
    if not REGISTRY.loaded:
        REGISTRY.load()
        REGISTRY.warmup()
    cal = json.loads(CAL_FILE.read_text()) if CAL_FILE.exists() else {}
    # ---------------- pass 1: raw scores on the calibration split (no calibration applied)
    saved_curves = {k: v for k, v in cal.get("curves", {}).items()}
    for tid in NEURAL.get(kind, []) + (["ai_generated", "ai_face"] if kind == "images" else []):
        cal.setdefault("curves", {}).pop(tid, None)
    cal.setdefault("fusion", {}).pop({"images": "image"}.get(kind, kind), None)
    for tid in FEATURE_MODELS.get(kind, {}):
        cal.setdefault("feature_models", {}).pop(tid, None)
    config.CALIBRATION.clear()
    config.CALIBRATION.update(cal)

    conds = ["laundered", "as_found"] if kind == "images" else ["as_found"]
    cal_conds = conds + list(DEGRADATIONS) if kind == "images" else conds
    generalisation = None
    if kind == "audio":
        generalisation = fit_voice_probe(items, cal)
        NEURAL["audio"] = []          # the ai_voice curve was fitted inside fit_voice_probe (out-of-fold)
        config.CALIBRATION.clear()
        config.CALIBRATION.update(cal)

    def variants(it, which=None):
        raw = it["path"].read_bytes()
        out = {}
        for i, c in enumerate(which or conds):
            out[c] = launder(raw) if c == "laundered" else raw if c == "as_found" else degrade(raw, c, seed=i)
        return out

    cal_reports, cal_y = [], []
    raw_by_test: dict[str, list] = {t: [] for t in NEURAL.get(kind, [])}
    raw_y: dict[str, list] = {t: [] for t in NEURAL.get(kind, [])}
    feat_rows: dict[str, list] = {t: [] for t in FEATURE_MODELS.get(kind, {})}
    cache_file = EVAL / f"_pass1_{kind}.pkl"
    cache = {}
    if REUSE_PASS1 and cache_file.exists():
        import pickle

        cache = pickle.loads(cache_file.read_bytes())
        print(f"  reusing {len(cache)} cached pass-1 reports from {cache_file.name}")
    for i, it in enumerate(calib):
        for c in cal_conds:
            key = (it["name"], c)
            if key in cache:
                rep = cache[key]
            else:
                rep = run_pipeline(kind, variants(it, [c])[c], it["name"], keep_private=kind == "images")
                for t in rep["tests"]:
                    t["visual"] = None
                rep["preview"] = None
                cache[key] = rep
            cal_reports.append(rep)
            cal_y.append(it["y"])
            for t in rep["tests"]:
                if t["id"] in raw_by_test and t["status"] == "ok" and t["metrics"].get("raw") is not None:
                    raw_by_test[t["id"]].append(t["metrics"]["raw"])
                    raw_y[t["id"]].append(it["y"])
                if t["id"] in feat_rows and t["status"] == "ok":
                    try:
                        feat_rows[t["id"]].append(([f(t["metrics"]) for f in FEATURE_MODELS[kind][t["id"]].values()], it["y"]))
                    except Exception:  # noqa: BLE001
                        pass
        if i % 10 == 0:
            print(f"  calib {i + 1}/{len(calib)}", flush=True)
    if kind == "images":
        import pickle

        cache_file.write_bytes(pickle.dumps(cache))
    curves = {}
    for tid in raw_by_test:
        c = fit_curve(raw_by_test[tid], raw_y[tid], constrain=kind == "images")
        if c:
            curves[tid] = c
            print(f"  curve {tid}: a={c['a']} b={c['b']}  (n={len(raw_y[tid])}, raw AUC={roc_auc(raw_y[tid], raw_by_test[tid]):.3f})")
    for tid, rowsf in feat_rows.items():
        if len(rowsf) >= 10:
            X = np.array([r[0] for r in rowsf], dtype=float)
            yy = np.array([r[1] for r in rowsf])
            fm = fit_feature_model(X, yy, list(FEATURE_MODELS[kind][tid].keys()))
            cal.setdefault("feature_models", {})[tid] = fm
            print(f"  feature model {tid}: {dict(zip(fm['features'], fm['coef']))} b={fm['intercept']}")
    # re-score calibration reports with the curves to fit the fusion gain/bias
    cal.setdefault("curves", {}).update(curves)
    for k, v in saved_curves.items():
        cal["curves"].setdefault(k, v)
    config.CALIBRATION.clear()
    config.CALIBRATION.update(cal)
    if kind == "images":
        # re-score pass 1 with the new curves WITHOUT re-running the slow pipeline: only the two neural scores change
        rescored = [rescore_image(rep) for rep in cal_reports]
    else:
        rescored = [run_pipeline(kind, data, it["name"]) for it in calib for c, data in variants(it, cal_conds).items()]
    fk = {"images": "image"}.get(kind, kind)
    if kind == "audio":
        # the probe was fitted on these same calibration clips, so its outputs here are over-confident;
        # fitting the fusion on them would be circular -> keep the neutral default
        cal.setdefault("fusion", {})[fk] = {"gain": 1.0, "bias": 0.0}
    else:
        cal.setdefault("fusion", {})[fk] = fit_fusion(rescored, cal_y, fk)
    print(f"  fusion {fk}: {cal['fusion'][fk]}")
    cal["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cal.setdefault("notes", "Fitted by scripts/evaluate.py on the calibration split only.")
    CAL_FILE.write_text(json.dumps(cal, indent=1))
    config.CALIBRATION.clear()
    config.CALIBRATION.update(cal)

    # ---------------- pass 2: held-out test split with the final calibration
    res_by_cond = {}
    names = {}
    for c in conds:
        rows, ys, ms = [], [], []
        for i, it in enumerate(test):
            data = variants(it)[c]
            rep = run_pipeline(kind, data, it["name"])
            for t in rep["tests"]:
                names[t["id"]] = t["name"]
            row = slim(rep)
            rows.append(row)
            ys.append(it["y"])
            ms.append(rep["_ms"])
            details.setdefault(kind, {}).setdefault(c, {})[it["name"]] = dict(row, y=it["y"], group=it["group"])
        bm = binary_metrics(ys, [r["score"] for r in rows], ms)
        bm["per_test"] = per_test_auc(rows, ys, names)
        bm["by_group"] = by_group(test, rows)
        res_by_cond[c] = bm
        print(f"  [{c}] held-out: {bm['metrics']}  confusion={bm['confusion']}  verdicts={bm['verdicts']}")
        for pt in bm["per_test"]:
            print(f"      {pt['id']:18s} AUC {pt['auc']:.3f} (n={pt['n']})")
    # robustness: the held-out files after real-world degradations (never seen in this form during calibration)
    robust, wa = None, None
    if kind == "images":
        robust = []
        for c in list(DEGRADATIONS) + ["whatsapp"]:
            ys, ss = [], []
            for it in test:
                ys.append(it["y"])
                ss.append(run_pipeline(kind, variants(it, [c])[c], it["name"])["score"])
            ys, ss = np.array(ys), np.array(ss)
            r, f = ss[ys == 0], ss[ys == 1]
            robust.append({"condition": c, "n_real": int(len(r)), "n_fake": int(len(f)),
                           "real_flagged": int((r > 50).sum()), "real_synthetic_verdict": int((r > 65).sum()),
                           "fake_caught": int((f > 50).sum()), "auc": round(roc_auc(ys, ss), 4),
                           "accuracy": round(float(((ss > 50) == (ys == 1)).mean()), 4)})
            print(f"  robustness {c:9s}: real flagged {robust[-1]['real_flagged']}/{len(r)} "
                  f"(synthetic verdict {robust[-1]['real_synthetic_verdict']}), fakes caught {robust[-1]['fake_caught']}/{len(f)}, "
                  f"AUC {robust[-1]['auc']}")
        # WhatsApp-style check for the HELD-OUT real phone photos only (calibration phones would flatter it)
        phones = [it for it in test if it["group"] == "phone"]
        if phones:
            scores = [run_pipeline(kind, degrade(it["path"].read_bytes(), "whatsapp"), it["name"])["score"] for it in phones]
            wa = {"n": len(phones), "flagged": int(sum(sc > 50 for sc in scores)), "max_score": int(max(scores)),
                  "mean_score": round(float(np.mean(scores)), 1), "split": "held-out phone photos only"}
            print(f"  WhatsApp-style phone photos (held-out): {wa}")
    head = res_by_cond[conds[0]]
    out = {"dataset": {"real": sum(1 for i in items if i["y"] == 0), "fake": sum(1 for i in items if i["y"] == 1),
                       "held_out_real": sum(1 for i in test if i["y"] == 0), "held_out_fake": sum(1 for i in test if i["y"] == 1)},
           **{k: head[k] for k in ("metrics", "confusion", "roc", "per_test", "verdicts", "by_group")},
           "condition": conds[0]}
    if len(conds) > 1:
        out["as_found"] = {k: res_by_cond["as_found"][k] for k in ("metrics", "confusion", "per_test", "verdicts")}
    if wa:
        out["whatsapp_phone_photos"] = wa
    if robust:
        out["robustness"] = robust
    if kind == "images":
        ext = external_video_stills()
        if ext:
            out["external_video_stills"] = ext
    if generalisation:
        out["generalisation"] = generalisation
    if kind == "audio":
        ext = external_audio()
        if ext:
            out["external"] = ext
    return out


FAMILIES = {"vctk_bonafide": "ASVspoof 2019 (VCTK speakers vs 13 TTS/VC systems)",
            "asvspoof_tts_vc": "ASVspoof 2019 (VCTK speakers vs 13 TTS/VC systems)",
            "original_voice": "UniData (real voices vs their AI clones)",
            "voice_clone": "UniData (real voices vs their AI clones)",
            "read_speech": "LibriSpeech vs our own TTS (MMS, SpeechT5, macOS say)",
            "neural_tts": "LibriSpeech vs our own TTS (MMS, SpeechT5, macOS say)",
            "classic_tts": "LibriSpeech vs our own TTS (MMS, SpeechT5, macOS say)",
            "vocoded_speech": "LibriSpeech vs our own TTS (MMS, SpeechT5, macOS say)",
            "everyday_speech": "FLEURS everyday speech (real only)"}
PROBE_C = 0.01


def fit_voice_probe(items: list[dict], cal: dict) -> list[dict]:
    """Transfer learning for the voice test: layer-4 wav2vec2 features -> logistic regression, fitted on the
    calibration clips only. Also measures generalisation to a source family the probe never saw."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    from server.audio_io import load_audio
    from server.forensics.ai_voice import PROBE_LAYER, clip_embedding

    print("  computing wav2vec2 layer-4 features ...", flush=True)
    feats = {}
    for it in items:
        feats[it["name"]] = clip_embedding(load_audio(it["path"].read_bytes(), it["name"])["wav16"], PROBE_LAYER)

    def fit(train):
        X = np.stack([feats[i["name"]] for i in train])
        y = np.array([i["y"] for i in train])
        mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-6
        lr = LogisticRegression(C=PROBE_C, max_iter=5000, class_weight="balanced").fit((X - mu) / sd, y)
        return mu, sd, lr

    calib = [i for i in items if i["split"] == "calib"]
    mu, sd, lr = fit(calib)
    cal["voice_probe"] = {"layer": PROBE_LAYER, "mean": [round(float(v), 6) for v in mu],
                          "std": [round(float(v), 6) for v in sd], "coef": [round(float(v), 6) for v in lr.coef_[0]],
                          "intercept": round(float(lr.intercept_[0]), 6), "n_train": len(calib), "C": PROBE_C}
    print(f"  voice probe fitted on {len(calib)} calibration clips")
    # calibration curve from OUT-OF-FOLD predictions, folds grouped by SPEAKER (a speaker's clips never sit on both
    # sides of a fold), so the curve is not fitted on the probe's own training clips or voices
    yc = np.array([i["y"] for i in calib])
    groups = [i["split_group"] for i in calib]
    oof = np.zeros(len(calib))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(np.zeros(len(yc)), yc, groups):
        m2, s2, lr2 = fit([calib[k] for k in tr])
        X = np.stack([feats[calib[k]["name"]] for k in te])
        oof[te] = lr2.predict_proba((X - m2) / s2)[:, 1]
    curve = fit_curve(list(oof * 100), list(yc))
    if curve:
        cal.setdefault("curves", {})["ai_voice"] = curve
        print(f"  ai_voice curve from speaker-grouped out-of-fold outputs: a={curve['a']} b={curve['b']} (OOF AUC {roc_auc(yc, oof):.3f})")
    # leave-one-family-out: train on the other families' calibration clips, test on this family's held-out clips
    out = []
    for fam in sorted(set(FAMILIES.values())):
        train = [i for i in calib if FAMILIES.get(i["group"]) != fam]
        test = [i for i in items if i["split"] == "test" and FAMILIES.get(i["group"]) == fam]
        if len({i["y"] for i in train}) < 2 or not test:
            continue
        m2, s2, lr2 = fit(train)
        X = np.stack([feats[i["name"]] for i in test])
        p = lr2.predict_proba((X - m2) / s2)[:, 1]
        y = np.array([i["y"] for i in test])
        row = {"unseen_family": fam, "n": len(test), "accuracy": round(float(((p > 0.5) == y).mean()), 3)}
        if len(set(y.tolist())) == 2:
            row["auc"] = round(roc_auc(y, p), 3)
        else:  # a real-only corpus: all we can measure is how many real voices it would wrongly flag
            row["false_alarm_rate"] = round(float((p > 0.5).mean()), 3)
        out.append(row)
        print(f"  unseen family {fam}: {row}")
    return out


EXTERNAL_AUDIO_NOTE = ("Generators never used for tuning: F5-TTS, Chatterbox, WaveGlow and ASVspoof attack A10. Not fully "
                       "unseen: LibriSpeech speaker 260 (4 of these clips) and the HiFi-GAN vocoder type were in our "
                       "tuning set. Only 10 clips: a spot check, not a statistic.")
VIDEO_EXTERNAL_NOTE = ("Headline clips are real research deepfakes made by other people (FaceForensics++, Google DFD, "
                       "Celeb-DF, Wav2Lip). No number was fitted on them, though an earlier run on stills from these "
                       "clips led us to change the calibration. The video thresholds were set by hand on our own 6 "
                       "'tuning clips' (3 NASA, 3 animated GAN faces), which are therefore not a test. Our image network "
                       "was not trained on face-swaps, reenactment or lip-sync, so it misses most of them.")


def clopper_pearson(k: int, n: int, a: float = 0.05) -> tuple[float, float]:
    """Exact 95% binomial confidence interval for k successes out of n."""
    from scipy.stats import beta

    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return lo, hi


def external_audio() -> dict | None:
    """The ../_incoming voice pairs: real speakers and generators (F5-TTS, Chatterbox, WaveFake HiFi-GAN/WaveGlow,
    ASVspoof A10) that are NOT in eval_data - the most honest test of the voice detector."""
    d = INCOMING / "audio"
    if not (d / "manifest.json").exists():
        return None
    man = json.loads((d / "manifest.json").read_text())
    rows = []
    for m in man:
        f = d / m["file"].split("/", 1)[-1]
        if not f.exists():
            continue
        rep = run_pipeline("audio", f.read_bytes(), f.name)
        rows.append({"file": f.name, "label": "fake" if m["label"] == "synthetic" else "real", "score": rep["score"],
                     "verdict": rep["verdict"], "ai_voice": next(t["score"] for t in rep["tests"] if t["id"] == "ai_voice"),
                     "method": m.get("method", "")[:90]})
        print(f"  external voice {f.name:52s} {rows[-1]['label']:4s} -> {rep['score']:3d} {rep['verdict']}")
    y = np.array([r["label"] == "fake" for r in rows], dtype=int)
    sc = np.array([r["score"] for r in rows], dtype=float)
    return {"clips": rows, "n": len(rows), "correct": int(((sc > 50) == (y == 1)).sum()),
            "auc": round(roc_auc(y, sc), 3) if len(set(y.tolist())) == 2 else None,
            "note": EXTERNAL_AUDIO_NOTE}


def external_video_stills() -> dict | None:
    """Stills from the ../_incoming research videos (FaceForensics++, Google DFD, Celeb-DF), saved the way the lab's
    Live Cam saves a frame (JPEG 0.92). Real people on ordinary video: the hardest false-alarm test we have."""
    d = INCOMING / "video"
    if not (d / "manifest.json").exists():
        return None
    import av
    from PIL import Image

    man = json.loads((d / "manifest.json").read_text())
    rows = []
    for m in man:
        f = d / m["file"].split("/", 1)[-1]
        if not f.exists():
            continue
        lab = "fake" if m["label"] == "synthetic" else "real"
        with av.open(str(f)) as c:
            frames, want = [], [1.0, 3.0, 5.0]
            for fr in c.decode(video=0):
                if want and fr.time is not None and fr.time >= want[0]:
                    frames.append(fr.to_image())
                    want.pop(0)
                if not want:
                    break
        for k, im in enumerate(frames):
            im.thumbnail((1280, 1280))
            b = io.BytesIO()
            im.convert("RGB").save(b, "JPEG", quality=92)
            photo = run_pipeline("images", b.getvalue(), f"still_{f.stem}_{k}.jpg")["score"]
            live = run_pipeline("images", b.getvalue(), f"live-capture-{f.stem}_{k}.jpg")["score"]
            rows.append({"clip": f.stem, "label": lab, "as_photo": photo, "as_live_capture": live})
    out = {"frames": len(rows), "note": "3 stills per clip from the incoming research videos; never used for tuning."}
    for lab in ("real", "fake"):
        rr = [r for r in rows if r["label"] == lab]
        if not rr:
            continue
        for mode in ("as_photo", "as_live_capture"):
            sc = np.array([r[mode] for r in rr])
            out[f"{lab}_{mode}"] = {"n": len(rr), "flagged": int((sc > 50).sum()), "synthetic_verdict": int((sc > 65).sum()),
                                     "suspicious_verdict": int(((sc >= 35) & (sc <= 65)).sum()), "mean_score": round(float(sc.mean()), 1)}
    print("  external video stills:", {k: v for k, v in out.items() if isinstance(v, dict)})
    out["stills"] = rows
    return out


def evaluate_video() -> dict | None:
    """Videos (scripts/evaluate_video.py does the work):
      * benchmark    - the FULL engine on 75 leak-free research clips (eval_data/video_faceswap: FF++ test split,
                       Celeb-DF test list, Google DFD), before vs after the face-swap detector, with 95% CIs.
      * clips        - the 10 booth demo clips in ../_incoming/media/video (FF++ 069 is in GenD's training split).
      * tuning_clips - our own 6 clips (3 NASA, 3 animated GAN faces). The hand-set video thresholds were chosen while
                       looking at these, so they are NOT a test."""
    import evaluate_video as ev
    from server.models import REGISTRY

    if not REGISTRY.loaded:
        REGISTRY.load()
        REGISTRY.warmup()
    bench = ev.evaluate_benchmark()
    dt = ev.evaluate_demo_and_tuning()
    if bench is not None:
        bench["webcam_reals"] = ev.evaluate_webcam_reals()
    return ev.build_video_block(bench, dt)


def sources_summary(_unused=None) -> list[str]:
    src = json.loads((EVAL / "sources.json").read_text())
    agg: dict[tuple, dict] = {}
    for k, v in src.items():
        if not (EVAL / k).exists():
            continue
        key = (k.split("/")[0], v.get("label"), v.get("group"))
        srcs = v.get("source", "")
        srcs = srcs.split("/")[2] if srcs.startswith("http") else srcs.split(" via ")[0].split(":")[0]
        a = agg.setdefault(key, {"n": 0, "gens": set(), "src": srcs[:60],
                                 "lic": v.get("licence", "")[:48]})
        a["n"] += 1
        if v.get("label") == "fake" and v.get("generator"):
            a["gens"].add(v["generator"].split(" (")[0].replace("ASVspoof2019 attack ", "A"))
    out = []
    for (kind, lab, grp), a in sorted(agg.items()):
        gens = sorted(a["gens"])
        g = (", ".join(gens) if len(gens) <= 5 else f"{len(gens)} systems") if gens else ""
        out.append(f"{kind}: {a['n']} {lab} - {grp}{' (' + g + ')' if g else ''} - {a['src']} [{a['lic']}]")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="all")
    ap.add_argument("--notes-only", action="store_true", help="rebuild sources + notes in results.json only")
    ap.add_argument("--reuse-pass1", action="store_true", help="images: reuse cached pass-1 calibration reports")
    a = ap.parse_args()
    global REUSE_PASS1
    REUSE_PASS1 = a.reuse_pass1
    if a.notes_only:
        res = json.loads(RESULTS.read_text())
        res.setdefault("dataset", {})["sources"] = sources_summary()
        res["notes"] = build_notes(res)
        RESULTS.write_text(json.dumps(res, indent=1))
        print("\n".join(res["notes"]))
        return
    kinds = ["images", "audio", "video"] if a.kind == "all" else [a.kind]
    details = json.loads(DETAILS.read_text()) if DETAILS.exists() else {}
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    for k in kinds:
        if k == "video":
            v = evaluate_video()
            if v:
                results["video"] = v
            continue
        r = evaluate_kind(k, details)
        if r is None:
            continue
        if k == "images":
            results.update({kk: r[kk] for kk in ("metrics", "confusion", "roc", "per_test")})
            results["dataset"] = {"real": r["dataset"]["real"], "fake": r["dataset"]["fake"], "sources": [],
                                  "split": f"group-aware ~40% calibration / ~60% held-out test (no prompt, person or "
                                           f"face-swap source on both sides); held-out = "
                                           f"{r['dataset']['held_out_real']} real + {r['dataset']['held_out_fake']} fake; "
                                           f"headline numbers are on laundered files (JPEG q90 re-encode, metadata stripped)"}
            results["image_details"] = {kk: r[kk] for kk in ("verdicts", "by_group", "as_found", "whatsapp_phone_photos",
                                                              "condition", "robustness", "external_video_stills") if kk in r}
        else:
            results[k] = {kk: r[kk] for kk in ("metrics", "confusion", "roc", "per_test", "verdicts", "by_group", "generalisation",
                                               "external") if kk in r}
            results[k]["dataset"] = r["dataset"]
    results["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results.setdefault("dataset", {})["sources"] = sources_summary({})
    results["notes"] = build_notes(results)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=1))
    DETAILS.write_text(json.dumps(details, indent=1))
    print("wrote", RESULTS.relative_to(ROOT), "and", CAL_FILE.relative_to(ROOT))


def build_notes(res: dict) -> list[str]:
    n = []
    m = res.get("metrics", {})
    if m:
        n.append(f"Image numbers are on {res['dataset'].get('split', 'held-out files')}. Calibration curves and the fusion "
                 f"gain/bias were fitted on the calibration split only (plus degraded copies of it: webcam, phone "
                 f"denoise, H.264 video still, small web copy). No number was fitted on the held-out files, but we looked "
                 f"at earlier test runs while improving the system, so treat these results as slightly optimistic.")
    det = res.get("image_details", {})
    if det.get("as_found"):
        af = det["as_found"]["metrics"]
        n.append(f"On the original files (metadata intact) held-out accuracy was {af['accuracy'] * 100:.1f}% and AUC {af['auc']:.3f}.")
    for rb in det.get("robustness", []):
        if rb["condition"] in ("webcam", "denoise", "h264", "whatsapp"):
            label = {"webcam": "webcam-like copies", "denoise": "phone 'beauty/denoise' copies",
                     "h264": "H.264 video-still copies", "whatsapp": "WhatsApp-style copies"}[rb["condition"]]
            n.append(f"Robustness, held-out {label}: {rb['real_flagged']} of {rb['n_real']} real images flagged "
                     f"({rb['real_synthetic_verdict']} with a 'synthetic' verdict); {rb['fake_caught']} of {rb['n_fake']} "
                     f"fakes still caught; AUC {rb['auc']:.2f}.")
    ev = det.get("external_video_stills")
    if ev and ev.get("real_as_photo"):
        r1, r2 = ev["real_as_photo"], ev.get("real_as_live_capture", {})
        n.append(f"External false-alarm check: stills of REAL people from research videos (never used to fit any number): "
                 f"{r1['flagged']} of {r1['n']} flagged as an uploaded photo, {r2.get('flagged', '?')} of {r2.get('n', '?')} "
                 f"in Live Cam mode. Compressed video frames remain the engine's weakest spot for false alarms.")
    fsi = det.get("faceswap_on_stills")
    if fsi:
        rw = fsi["real_heldout_photos"]["webcam"]
        vf = fsi["real_video_frames"]["real_live_jpeg"]
        n.append(f"The face-swap detector is video-only. Scored on single stills it fired on {vf['fires']} of {vf['n']} "
                 f"frames of real people from research videos saved like a Live Cam capture, and adding it to photos would "
                 f"have raised real webcam-style photos flagged from {rw['engine_flagged']} to {rw['with_fs_flagged']} of 49, "
                 f"so photos and Live Cam captures do not use it (their numbers above are unchanged).")
    if det.get("whatsapp_phone_photos"):
        w = det["whatsapp_phone_photos"]
        n.append(f"False-alarm check: {w['flagged']} of {w['n']} held-out real smartphone photos were flagged after "
                 f"WhatsApp-style recompression (1600 px, JPEG q75); highest fused score {w['max_score']}.")
    n.append("The AI-image network (CommunityForensics ViT, Park & Owens, CVPR 2025; pretrained, not trained by us) was "
             "trained on millions of images from thousands of generators. FFHQ and COCO are listed among its training "
             "datasets (Community Forensics dataset card), so the real-photo numbers are optimistic; our 7 phone photos "
             "(0 flagged) are the fairest real-photo test. Real-world accuracy on brand-new generators will be lower "
             "than these numbers. It is a general AI-image detector: it was not trained on face-swaps, reenactment or "
             "lip-sync.")
    cf = res.get("confusion") or {}
    if all(k in cf for k in ("tp", "fp", "tn", "fn")):
        tp, fp, tn, fn = cf["tp"], cf["fp"], cf["tn"], cf["fn"]
        a = clopper_pearson(tp + tn, tp + fp + tn + fn)
        r = clopper_pearson(tp, tp + fn)
        f = clopper_pearson(fp, fp + tn)
        n.append(f"95% confidence ranges (exact binomial): accuracy {a[0] * 100:.0f}-{a[1] * 100:.0f}%, fakes caught "
                 f"{r[0] * 100:.0f}-{r[1] * 100:.0f}%, false-alarm rate {f[0] * 100:.0f}-{f[1] * 100:.1f}%.")
    n_img = res.get("dataset", {}).get("real", 0) + res.get("dataset", {}).get("fake", 0)
    n_aud = sum(res.get("audio", {}).get("dataset", {}).get(k, 0) for k in ("real", "fake"))
    n.append(f"The dataset is small ({n_img} images, {n_aud} voice clips): one file changing class moves held-out "
             f"accuracy by about 1 percentage point. Treat the numbers as a school-scale experiment, not a benchmark.")
    classic = [t for t in res.get("per_test", []) if t["id"] in ("ela", "noise", "fft", "jpeg_quant", "metadata")]
    if classic:
        rng = f"{min(t['auc'] for t in classic):.2f}-{max(t['auc'] for t in classic):.2f}"
        n.append(f"Classic forensic tests (ELA, noise, FFT, JPEG tables, metadata) are weak on whole AI-generated images "
                 f"(held-out AUC {rng}) and carry small weights. We also tried them on a hand-made splice (an AI region "
                 f"pasted into a real phone photo): the ELA map shows the pasted square to the eye, but no test's score "
                 f"caught it. Their thresholds and the fusion weights were set by hand, not fitted. Part of the JPEG-table "
                 f"signal is a dataset artefact: our real FFHQ faces were PNG originals.")
    if res.get("audio"):
        am = res["audio"]["metrics"]
        gen = res["audio"].get("generalisation") or []
        ext = res["audio"].get("external") or {}
        if ext.get("n"):
            xc = ext.get("clips", [])
            fk = [c for c in xc if c["label"] == "fake"]
            rl = [c for c in xc if c["label"] == "real"]
            n.append(f"Voice, outside clips (generators never used for tuning: F5-TTS, Chatterbox, WaveGlow, ASVspoof A10; "
                     f"not fully unseen: LibriSpeech speaker 260, in 4 clips, and the HiFi-GAN vocoder type were in our "
                     f"tuning set): fakes caught {sum(c['score'] > 50 for c in fk)} of {len(fk)}, real voices cleared "
                     f"{sum(c['score'] <= 50 for c in rl)} of {len(rl)}"
                     + (f", AUC {ext['auc']:.2f} from only {len(rl)} real and {len(fk)} fake clips" if ext.get("auc") is not None else "")
                     + f". In the lab none of the fakes gets a 'synthetic' verdict ({sum(c['score'] > 65 for c in fk)} of "
                     f"{len(fk)} above 65). Only 10 clips - a spot check.")
        if gen:
            parts = "; ".join(f"{g['unseen_family'].split(' (')[0]}: " + (f"AUC {g['auc']:.2f}" if "auc" in g else
                              f"{g['false_alarm_rate'] * 100:.0f}% of real voices flagged") for g in gen)
            n.append(f"Voice stress test - a whole source family left out of training: {parts}. An AUC near 0.5 on a "
                     f"left-out dataset means what the probe learned does not transfer: it partly learned dataset quirks "
                     f"(microphones, rooms) rather than signs of synthesis.")
        n.append(f"Voice, in-distribution (held-out speakers, but the SAME datasets and generators as tuning): accuracy "
                 f"{am['accuracy'] * 100:.1f}%, AUC {am['auc']:.3f}. This is the optimistic number. The voice test is a "
                 f"pretrained wav2vec2 network's layer-4 features plus a logistic-regression probe trained on our "
                 f"calibration clips; speakers never appear on both sides of the split.")
    if res.get("video"):
        v = res["video"]
        b = v.get("benchmark") or {}
        x = (b.get("parts") or {}).get("cross")
        if x:
            xb, xa = x["before"], x["after"]
            g = b.get("cross_gain") or {}
            cb = xb.get("auc_ci95_newcombe") or xb["auc_ci95"]
            ca = xa.get("auc_ci95_newcombe") or xa["auc_ci95"]
            n.append(f"Video benchmark, datasets neither face-swap network was trained on (Celeb-DF + Google DFD, "
                     f"{xa['n_real']} real + {xa['n_fake']} fake clips; no threshold or weight was chosen on them, but the "
                     f"detectors were ranked by their AUC on these clips and the pair was chosen after seeing them, so "
                     f"this AUC is optimistic): AUC of the engine's verdict score {xb['auc']:.2f} "
                     f"[95% CI {cb[0]:.2f}-{cb[1]:.2f}] before the face-swap detector, {xa['auc']:.3f} "
                     f"[{ca[0]:.2f}-{ca[1]:.2f}] after"
                     + (f" (paired bootstrap gain +{g['gain']:.2f}, CI {g['ci95'][0]:+.2f} to {g['ci95'][1]:+.2f})" if g else "")
                     + f". AUC intervals are Newcombe's Wilson-type intervals: with only {xa['n_real']} + {xa['n_fake']} "
                     f"clips a bootstrap at the ceiling ({xa['auc_ci95'][0]:.2f}-{xa['auc_ci95'][1]:.2f}) is far too narrow. "
                     f"Fakes called synthetic {xb['fakes']['synthetic']} -> {xa['fakes']['synthetic']} of {xa['n_fake']}; "
                     f"reals called synthetic {xb['reals']['synthetic']} -> {xa['reals']['synthetic']}, reals called "
                     f"suspicious {xb['reals']['suspicious']} -> {xa['reals']['suspicious']} of {xa['n_real']}. Caveat: GenD's "
                     f"authors chose their checkpoint using Celeb-DF++ validation videos, so Celeb-DF is unseen in training "
                     f"but not in model selection; Google DFD (5 real + 5 fake) is the only fully unseen part.")
            f = (b.get("parts") or {}).get("ffpp")
            if f:
                fx = (b.get("per_method") or [])
                pm = "; ".join(f"{m['method']} {m['before']['auc']:.2f} -> {m['after']['auc']:.2f}" for m in fx)
                n.append(f"Video benchmark, FaceForensics++ test split (20 real + 25 fake): AUC {f['before']['auc']:.3f} -> "
                         f"{f['after']['auc']:.3f}; fakes called synthetic {f['before']['fakes']['synthetic']} -> "
                         f"{f['after']['fakes']['synthetic']} of 25" + (f" (per method, 5 fakes each vs 20 reals: {pm})" if pm else "")
                         + ". In-sample for the face-swap detector: its thresholds were chosen on these 45 clips, and GenD "
                         "was trained on other FF++ videos of the same methods (FaceShifter excepted).")
            w = b.get("webcam_reals")
            if w and w.get("n"):
                wb, wa = w["before"], w["after"]
                n.append(f"Video false-alarm check: {w['n']} real clips re-encoded like a cheap webcam (360p, blur, noise, "
                         f"denoise, H.264 CRF 30): verdicts authentic/suspicious/synthetic {wb['authentic']}/{wb['suspicious']}/"
                         f"{wb['synthetic']} before the face-swap detector, {wa['authentic']}/{wa['suspicious']}/{wa['synthetic']} "
                         f"after (it fired on {w['face_swap_fired']} of {w['n']}). Grainy, heavily compressed real video is "
                         f"its weak spot.")
            ft = (b.get("face_swap_test") or {}).get("cross") or {}
            if ft.get("n"):
                n.append(f"The face-swap test on its own (its 50 = the pair threshold chosen on FF++): AUC {ft['auc']:.2f} "
                         f"on Celeb-DF + DFD, but it fired on {ft['fired_on_reals']} of {xa['n_real']} real clips there "
                         + (f"and on {w['face_swap_fired']} of {w['n']} webcam-quality real clips" if w and w.get('n') else "")
                         + ". Its threshold was set on FaceForensics++, the dataset GenD was trained on, where it is "
                         "overconfident about real faces; the fusion turns most of these alarms into 'suspicious', not "
                         "'synthetic'.")
            n.append("The face-swap detector (GenD + the DFDC-winning EfficientNet-B7) is pretrained, not trained by us. We "
                     "benchmarked 6 published detectors; our pre-registered rule (best cross-dataset AUC) picked the DFDC "
                     "winner alone, and we added GenD after seeing the cross-dataset and demo results because it also catches "
                     "reenactment. On those clips the pair is statistically tied with the DFDC winner alone (+0.03 AUC, 95% "
                     "CI 0.00-0.09). The 8-frame setting was chosen for speed after all results were known; with 4 or 16 "
                     "frames the benchmark simulation called one real Celeb-DF/DFD clip synthetic. Only 2019-2020 "
                     "manipulation methods were tested.")
        if v.get("summary"):
            sm = v["summary"]
            sb = v.get("summary_before") or {}
            n.append(f"Video, the 10 booth demo clips (FF++ 069 is in GenD's training split, the Celeb-DF id2 pair is "
                     f"from Celeb-DF's training portion, and these clips were looked at when the pair was chosen, so they "
                     f"are a demonstration; only the Wav2Lip lip-sync we made from a Google DFD clip is a fully unseen "
                     f"catch): "
                     f"{sm['deepfakes_synthetic_verdict']} of {sm['deepfakes']} fakes get a 'synthetic' verdict"
                     + (f" ({sb['deepfakes_synthetic_verdict']} before the face-swap detector)" if sb else "")
                     + f"; {sm['reals_authentic_verdict']} of {sm['reals']} real clips are called authentic.")
        n.append(f"Video tuning clips (our 6, thresholds set by hand while looking at them - not a test): "
                 f"{v.get('tuning_correct', v.get('correct'))} of {len(v.get('tuning_clips', v.get('clips', [])))} correct.")
    n.append("Threshold for accuracy/precision/recall: fused score above 50 counts as 'synthetic'. In the lab, scores "
             "35-65 are shown as 'suspicious' rather than forcing a yes/no answer.")
    return n


if __name__ == "__main__":
    main()
