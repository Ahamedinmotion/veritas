"""VERITAS video experiment: the FULL engine on 75 leak-free research clips, before vs after the face-swap detector.

    uv run python scripts/evaluate_video.py            # ~10 min on the M4; updates web/data/results.json -> "video"
    uv run python scripts/evaluate_video.py --restat   # seconds: recompute intervals + notes from the saved rows
    uv run python scripts/evaluate.py --kind video     # same thing, through the main evaluation script

Clip sets (none of them was used to choose a threshold for the ENGINE; see BENCHMARK.md / docs/MODEL_SELECTION.md):
  * eval_data/video_faceswap/  75 clips (gitignored; manifest.json + SPLITS.md explain why they are leak-free):
      FaceForensics++ c23 official TEST split: 20 real + 25 fake (Deepfakes, FaceSwap, Face2Face, NeuralTextures,
      FaceShifter x 5), Celeb-DF v2 official test list: 10 + 10, Google DFD: 5 + 5.
      The face-swap detector's three thresholds were chosen on the 45 FF++ clips ONLY, so FF++ accuracy at those
      thresholds is in-sample; Celeb-DF + DFD ("cross-dataset", 15 real + 15 fake) are the honest, out-of-sample test.
  * ../_incoming/media/video/  the 10 booth demo clips (FF++ 069 is in GenD's TRAINING split - reported separately)
  * eval_data/video/           our 6 tuning clips (3 NASA, 3 animated GAN faces) - the engine's video thresholds were
                               set by hand on these, so they are a no-regression check, not a test.

"Before" = the same report fused WITHOUT the face_swap test (exactly the engine as shipped on 19 Nov: every other test
is unchanged). "After" = the engine's own fused score. Score > 50 counts as "fake" for accuracy/AUC; verdict bands:
< 35 authentic, 35-65 suspicious, > 65 synthetic.
"""
from __future__ import annotations

import copy
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evalcommon import EVAL, ROOT, load_items, roc_auc  # noqa: E402

INCOMING = ROOT.parent / "_incoming" / "media" / "video"
FS_DIR = EVAL / "video_faceswap"
RESULTS = ROOT / "web" / "data" / "results.json"
DETAILS = FS_DIR / "eval_results.json"
SEED = 20261121
N_BOOT = 2000

METHOD_SHORT = {"Deepfakes": "Deepfakes", "FaceSwap": "FaceSwap", "Face2Face": "Face2Face",
                "NeuralTextures": "NeuralTextures", "FaceShifter": "FaceShifter"}
PART = {"FaceForensics++ (c23)": "ffpp", "Celeb-DF v2": "celebdf", "Google DFD": "dfd"}


def run_clip(path: Path | bytes, name: str) -> dict:
    """Full engine on one clip; returns the private report (face_swap one-sided hint intact)."""
    from server import pipeline, video_pipeline

    data = path if isinstance(path, bytes) else path.read_bytes()
    t0 = time.perf_counter()
    rep = video_pipeline.analyze_video(data, name, pipeline._base_report("video", name, data))
    rep["_ms"] = (time.perf_counter() - t0) * 1000
    return rep


def before_score(rep: dict) -> tuple[int, str]:
    """The engine as shipped before the face-swap detector: same tests, fused without face_swap."""
    from server import fusion

    tests = [copy.deepcopy(t) for t in rep["tests"] if t["id"] != "face_swap"]
    marker = any(str(f).lower().startswith("ai marker") for f in rep.get("metadata", {}).get("flags", []))
    f = fusion.fuse("video", tests, hard_ai_marker=marker)
    return f["score"], f["verdict"]


def row(rep: dict, name: str, label: str, **extra) -> dict:
    b, bv = before_score(rep)
    fs = next((t for t in rep["tests"] if t["id"] == "face_swap"), None)
    r = {"file": name, "label": label, "score": rep["score"], "verdict": rep["verdict"], "before": b,
         "before_verdict": bv, "ms": round(rep["_ms"]), "timing_ms": rep.get("timing_ms", {}),
         "tests": {t["id"]: t["score"] for t in rep["tests"]}}
    if fs is not None:
        m = fs.get("metrics", {})
        r["face_swap"] = {"score": fs["score"], "status": fs["status"], "z": m.get("z"),
                          "fired": bool(fs["score"] is not None and fs["score"] >= 50),
                          "gend_p": m.get("GenD_mean_P(fake)", m.get("GenD_int8_mean_P(fake)")), "dfdc_p": m.get("B7_mean_P(fake)"),
                          "weight": fs["weight"]}
    r.update(extra)
    return r


# ------------------------------------------------------------------------------------------- statistics
def boot_auc(y, s, n=N_BOOT, seed=SEED):
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    rng = np.random.default_rng(seed)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    out = []
    for _ in range(n):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        out.append(roc_auc(y[idx], s[idx]))
    return [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)]


def newcombe_auc_ci(auc: float, n_pos: int, n_neg: int, z: float = 1.959964) -> list[float]:
    """Newcombe (2006, Stat Med 25:543, method 5): Wilson-type score interval for an AUC (Hanley-McNeil variance with
    N* = (m + n)/2 - 1). Unlike the percentile bootstrap it stays honest when the AUC sits at the ceiling on few clips
    (0.998 on 15 + 15 clips: bootstrap 0.99-1.00, Newcombe 0.87-1.00)."""
    m, n = n_pos, n_neg
    ns = (m + n) / 2 - 1

    def var(t):
        return 0.0 if t <= 0 or t >= 1 else t * (1 - t) / (m * n) * (1 + (ns - 1) * ((1 - t) / (2 - t) + t / (1 + t)))

    def f(t):
        return (auc - t) ** 2 - z * z * var(t)

    def root(a, b):
        fa = f(a)
        for _ in range(100):
            c = (a + b) / 2
            if (f(c) > 0) == (fa > 0):
                a, fa = c, f(c)
            else:
                b = c
        return (a + b) / 2

    lo = 0.0 if f(0.0) <= 0 else root(0.0, auc)
    hi = 1.0 if f(1.0) <= 0 else root(auc, 1.0)
    return [round(lo, 3), round(hi, 3)]


def boot_gain(y, a, b, n=N_BOOT, seed=SEED):
    """Paired stratified bootstrap of AUC(a) - AUC(b) on the same clips."""
    y, a, b = np.asarray(y), np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    d = []
    for _ in range(n):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        d.append(roc_auc(y[idx], a[idx]) - roc_auc(y[idx], b[idx]))
    d = np.asarray(d)
    return {"gain": round(float(roc_auc(y, a) - roc_auc(y, b)), 3),
            "ci95": [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)],
            "p_gain_le_0": round(float((d <= 0).mean()), 3)}


def bands(scores) -> dict:
    s = np.asarray(scores, dtype=float)
    return {"authentic": int((s < 35).sum()), "suspicious": int(((s >= 35) & (s <= 65)).sum()),
            "synthetic": int((s > 65).sum())}


def part_stats(rows: list[dict], key: str) -> dict:
    y = np.array([r["label"] == "fake" for r in rows], dtype=int)
    s = np.array([r[key] for r in rows], dtype=float)
    out = {"n_real": int((y == 0).sum()), "n_fake": int((y == 1).sum())}
    if len(set(y.tolist())) == 2:
        out["auc"] = round(roc_auc(y, s), 3)
        out["auc_ci95"] = boot_auc(y, s)                       # stratified percentile bootstrap (too narrow at 1.0)
        out["auc_ci95_newcombe"] = newcombe_auc_ci(roc_auc(y, s), int((y == 1).sum()), int((y == 0).sum()))
    out["accuracy_at_50"] = round(float(((s > 50) == (y == 1)).mean()), 3)
    out["fakes_flagged"] = int(((s > 50) & (y == 1)).sum())
    out["reals_flagged"] = int(((s > 50) & (y == 0)).sum())
    out["reals"] = bands(s[y == 0])
    out["fakes"] = bands(s[y == 1])
    return out


def fs_stats(rows: list[dict]) -> dict:
    """The face-swap test on its own: its 50 = the pair threshold chosen on FF++ (z = 0)."""
    rr = [r for r in rows if r.get("face_swap") and r["face_swap"]["z"] is not None]
    y = np.array([r["label"] == "fake" for r in rr], dtype=int)
    z = np.array([r["face_swap"]["z"] for r in rr], dtype=float)
    out = {"n": len(rr)}
    if len(set(y.tolist())) == 2:
        out["auc"] = round(roc_auc(y, z), 3)
        out["auc_ci95"] = boot_auc(y, z)
        out["auc_ci95_newcombe"] = newcombe_auc_ci(roc_auc(y, z), int((y == 1).sum()), int((y == 0).sum()))
    pred = z >= 0
    out["accuracy_at_ffpp_threshold"] = round(float((pred == (y == 1)).mean()), 3)
    out["recall"] = round(float(pred[y == 1].mean()), 3) if (y == 1).any() else None
    out["specificity"] = round(float((~pred[y == 0]).mean()), 3) if (y == 0).any() else None
    out["fired_on_reals"] = int(pred[y == 0].sum())
    out["fired_on_fakes"] = int(pred[y == 1].sum())
    return out


def evaluate_benchmark(log=print) -> dict | None:
    man_p = FS_DIR / "manifest.json"
    if not man_p.exists():
        log(f"  (no {man_p.relative_to(ROOT)} - skipping the 75-clip video benchmark)")
        return None
    man = json.loads(man_p.read_text())
    rows = []
    for m in man:
        f = FS_DIR / m["file"]
        if not f.exists():
            continue
        rep = run_clip(f, f.name)
        r = row(rep, f.name, m["label"], part=PART.get(m["dataset"], m["dataset"]), method=m.get("method"))
        rows.append(r)
        log(f"  {f.name:58s} {m['label']:4s} before {r['before']:3d} -> after {r['score']:3d} {r['verdict']:10s} "
            f"face_swap {r['face_swap']['score'] if r.get('face_swap') else None}  {r['ms'] / 1000:.1f}s")
    out = bench_stats(rows)
    DETAILS.write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                   "rows": rows}, indent=1))
    return out


def bench_stats(rows: list[dict]) -> dict:
    ff = [r for r in rows if r["part"] == "ffpp"]
    cdf = [r for r in rows if r["part"] == "celebdf"]
    dfd = [r for r in rows if r["part"] == "dfd"]
    cross = cdf + dfd
    out = {"n": len(rows), "parts": {}, "per_method": [], "face_swap_test": {}}
    for name, rr in (("ffpp", ff), ("celebdf", cdf), ("dfd", dfd), ("cross", cross), ("all", rows)):
        if not rr:
            continue
        out["parts"][name] = {"before": part_stats(rr, "before"), "after": part_stats(rr, "score")}
        out["face_swap_test"][name] = fs_stats(rr)
    reals = [r for r in ff if r["label"] == "real"]
    for meth in METHOD_SHORT:
        fk = [r for r in ff if r["method"] == meth]
        if not fk:
            continue
        rr = reals + fk
        y = [r["label"] == "fake" for r in rr]
        out["per_method"].append({
            "method": meth, "n_fake": len(fk),
            "before": {"auc": round(roc_auc(y, [r["before"] for r in rr]), 3),
                       "flagged": sum(r["before"] > 50 for r in fk), "synthetic": sum(r["before"] > 65 for r in fk)},
            "after": {"auc": round(roc_auc(y, [r["score"] for r in rr]), 3),
                      "flagged": sum(r["score"] > 50 for r in fk), "synthetic": sum(r["score"] > 65 for r in fk)},
            "face_swap_auc": round(roc_auc(y, [r["face_swap"]["z"] for r in rr]), 3),
            "seen_in_training": "GenD: this method's TRAIN videos (not these test clips)" if meth != "FaceShifter"
                                else "no (FaceShifter is in neither model's training data)"})
    if cross:
        y = [r["label"] == "fake" for r in cross]
        out["cross_gain"] = boot_gain(y, [r["score"] for r in cross], [r["before"] for r in cross])
    out["mean_latency_ms"] = int(np.mean([r["ms"] for r in rows])) if rows else None
    out["clips"] = [{k: r[k] for k in ("file", "label", "part", "method", "before", "score", "verdict")} |
                    {"face_swap": r["face_swap"]["score"] if r.get("face_swap") else None} for r in rows]
    return out


def restat() -> None:
    """Rebuild video.benchmark statistics, the notes and the demo provenance flags in results.json from the per-clip
    rows saved by the last full run (eval_data/video_faceswap/eval_results.json). No clip is re-analysed, so every score
    stays exactly as measured; only derived numbers (intervals) and wording change."""
    res = json.loads(RESULTS.read_text())
    v = res["video"]
    old = v["benchmark"]
    rows = json.loads(DETAILS.read_text())["rows"]
    new = bench_stats(rows)
    for k in ("n", "parts", "per_method", "face_swap_test", "cross_gain", "clips"):   # same rows -> same numbers
        a, b = json.loads(json.dumps(old[k])), json.loads(json.dumps(new[k]))
        if k in ("parts", "face_swap_test"):
            for d in (a, b):
                for part in d.values():
                    for blk in ([part["before"], part["after"]] if "before" in part else [part]):
                        blk.pop("auc_ci95_newcombe", None)
        if a != b:
            raise SystemExit(f"restat: {k} differs from results.json - run the full evaluation instead")
    new["mean_latency_ms"] = old.get("mean_latency_ms")
    new["webcam_reals"] = old.get("webcam_reals")
    new["note"] = VIDEO_NOTE
    new["dataset"] = old.get("dataset")
    v["benchmark"] = new
    for c in v.get("clips", []):
        c["celebdf_train_portion"] = str(c.get("file", "")).startswith("celebdf_")
    v["note"] = ("Demo clips: research deepfakes made by other people (FaceForensics++, Google DFD, Celeb-DF) plus a "
                 "Wav2Lip lip-sync we made from a Google DFD clip, never used to fit any number, but looked at when the "
                 "face-swap pair was chosen. FF++ 069 (3 of the 6 fakes and 1 real) is in the face-swap detector's TRAINING "
                 "split, and the Celeb-DF id2 pair comes from Celeb-DF's training portion, so these are a demonstration; "
                 "the 75-clip benchmark is the test. Scores measured at 48 sampled frames on the development Mac; at 32 "
                 "frames (the booth default) the same 10 clips keep their verdicts (DFD face-swap 41 -> 44). The video "
                 "thresholds of the older tests were set by hand on our own 6 tuning clips, which are therefore not a test.")
    from evaluate import build_notes
    res["notes"] = build_notes(res)
    RESULTS.write_text(json.dumps(res, indent=1))
    x = new["parts"]["cross"]
    print("cross AUC", x["before"]["auc"], x["before"]["auc_ci95_newcombe"], "->", x["after"]["auc"],
          x["after"]["auc_ci95_newcombe"], "(bootstrap", x["after"]["auc_ci95"], ")")
    print("wrote", RESULTS.relative_to(ROOT))


def evaluate_demo_and_tuning(log=print) -> dict:
    """The 10 booth demo clips (separately: FF++ 069 is in GenD's training split) + our 6 tuning clips."""
    tuning = []
    for it in load_items("video"):
        rep = run_clip(it["path"], it["name"])
        r = row(rep, it["name"], "fake" if it["y"] else "real", group=it["group"])
        tuning.append(r)
        log(f"  tuning {it['name']:40s} before {r['before']:3d} -> after {r['score']:3d} {r['verdict']}")
    demo = []
    if (INCOMING / "manifest.json").exists():
        for m in json.loads((INCOMING / "manifest.json").read_text()):
            f = INCOMING / m["file"].split("/", 1)[-1]
            if not f.exists():
                continue
            method = m.get("method", "")
            group = ("lip-sync" if "lip" in method.lower() else "reenactment" if "reenact" in method.lower()
                     else "face-swap" if "swap" in method.lower() else "real recording")
            rep = run_clip(f, f.name)
            r = row(rep, f.name, "fake" if m["label"] == "synthetic" else "real", group=group, method=method[:90],
                    in_gend_training=f.name.startswith("ffpp_"),
                    celebdf_train_portion=f.name.startswith("celebdf_"))
            demo.append(r)
            log(f"  demo {f.name:40s} {r['label']:4s} before {r['before']:3d} -> after {r['score']:3d} {r['verdict']}")
    return {"demo": demo, "tuning": tuning}


def webcam_copy(path: Path, seed: int = 0) -> bytes:
    """A real video as a cheap webcam / video call would deliver it: 360p, soft optics, sensor noise, in-camera
    denoise, strong H.264 compression (CRF 30). Same spirit as evalcommon.degrade('webcam') for photos."""
    import io

    import av
    import cv2

    rng = np.random.default_rng(seed)
    out = io.BytesIO()
    with av.open(str(path)) as cin, av.open(out, "w", format="mp4") as cout:
        vin = cin.streams.video[0]
        fps = vin.average_rate or 25
        st = None
        for fr in cin.decode(video=0):
            a = fr.to_ndarray(format="rgb24")
            h, w = a.shape[:2]
            nh = 360
            nw = int(round(w * nh / h / 2)) * 2
            a = cv2.resize(a, (nw, nh), interpolation=cv2.INTER_AREA)
            a = cv2.GaussianBlur(a, (0, 0), 0.9)
            a = np.clip(a.astype(np.float32) + rng.normal(0, 3.0, (nh, nw, 1)), 0, 255).astype(np.uint8)
            a = cv2.bilateralFilter(a, 5, 25, 5)
            if st is None:
                st = cout.add_stream("libx264", rate=fps)
                st.width, st.height, st.pix_fmt = nw, nh, "yuv420p"
                st.options = {"crf": "30", "preset": "veryfast"}
            for pk in st.encode(av.VideoFrame.from_ndarray(a, format="rgb24")):
                cout.mux(pk)
        if st is not None:
            for pk in st.encode():
                cout.mux(pk)
    return out.getvalue()


def evaluate_webcam_reals(log=print) -> dict | None:
    """False-alarm check: every REAL clip of the benchmark (and the real demo clips) re-encoded like a cheap webcam."""
    man_p = FS_DIR / "manifest.json"
    if not man_p.exists():
        return None
    srcs = [(FS_DIR / m["file"], m["file"]) for m in json.loads(man_p.read_text()) if m["label"] == "real"]
    if (INCOMING / "manifest.json").exists():
        srcs += [(INCOMING / m["file"].split("/", 1)[-1], m["file"].split("/", 1)[-1])
                 for m in json.loads((INCOMING / "manifest.json").read_text()) if m["label"] != "synthetic"]
    rows = []
    for i, (f, name) in enumerate(srcs):
        if not f.exists():
            continue
        rep = run_clip(webcam_copy(f, seed=i), "webcam_" + name)
        r = row(rep, name, "real")
        rows.append({k: r[k] for k in ("file", "before", "score", "verdict")} | {"face_swap": r["face_swap"]["score"]})
        log(f"  webcam-real {name:58s} before {r['before']:3d} -> after {r['score']:3d} {r['verdict']}  face_swap {r['face_swap']['score']}")
    b = np.array([r["before"] for r in rows]); a = np.array([r["score"] for r in rows])
    fs = np.array([r["face_swap"] if r["face_swap"] is not None else 0 for r in rows])
    return {"n": len(rows), "before": bands(b), "after": bands(a), "flagged_before": int((b > 50).sum()),
            "flagged_after": int((a > 50).sum()), "face_swap_fired": int((fs >= 50).sum()), "clips": rows,
            "note": "35 real benchmark clips + 4 real demo clips, re-encoded like a cheap webcam (360p, blur, noise, "
                    "denoise, H.264 CRF 30), full engine before vs after the face-swap detector."}


VIDEO_NOTE = ("Video = the FULL engine (every video test + fusion). 'Before' is the engine as shipped on 19 Nov (the same "
              "report fused without the face-swap test); 'after' adds the face-swap detector: two PRETRAINED published "
              "networks (GenD CLIP ViT-L/14, WACV 2026, trained on FaceForensics++; the DFDC-winning EfficientNet-B7, "
              "trained on DFDC) that we benchmarked, chose and integrated - we did not train them. Its three thresholds "
              "were chosen on the 45 FaceForensics++ test clips only, so FF++ accuracy is in-sample. Celeb-DF + Google DFD "
              "(15 real + 15 fake) are the out-of-sample test: no threshold or weight was chosen on them and neither network "
              "was trained on them, but the 6 candidates were ranked by their AUC on them (pre-registered rule) and the pair "
              "was preferred over the rule's winner (B7 alone) after looking at them, so their AUC is optimistic; GenD's authors chose their checkpoint using Celeb-DF++ validation videos, so only Google DFD (5 + 5) "
              "is fully unseen. On these clips the pair and B7 alone are statistically tied. AUC intervals: auc_ci95 = "
              "stratified percentile bootstrap (too narrow near 1.0 with so few clips), auc_ci95_newcombe = Newcombe's "
              "Wilson-type interval (use this one). The demo clips FF++ 069 are in GenD's training split, and the Celeb-DF "
              "id2 pair is from Celeb-DF's training portion.")


def build_video_block(bench: dict | None, dt: dict, old: dict | None = None) -> dict:
    ok = lambda c: (c["score"] > 50) == (c["label"] == "fake")  # noqa: E731
    demo, tuning = dt["demo"], dt["tuning"]
    slim = lambda r: {k: r[k] for k in ("file", "label", "group", "score", "verdict", "before", "before_verdict", "ms",  # noqa: E731
                                        "tests", "method", "in_gend_training", "celebdf_train_portion") if k in r}
    head = demo or tuning
    out = {"clips": [slim(r) for r in head], "correct": sum(ok(c) for c in head), "n": len(head),
           "mean_latency_ms": int(np.mean([c["ms"] for c in head])) if head else None,
           "tuning_clips": [slim(r) for r in tuning], "tuning_correct": sum(ok(c) for c in tuning)}
    if demo:
        fk = [c for c in demo if c["label"] == "fake"]
        rl = [c for c in demo if c["label"] == "real"]
        out["summary"] = {"deepfakes": len(fk), "deepfakes_synthetic_verdict": sum(c["score"] > 65 for c in fk),
                          "deepfakes_flagged": sum(c["score"] > 50 for c in fk), "reals": len(rl),
                          "reals_authentic_verdict": sum(c["score"] < 35 for c in rl),
                          "reals_flagged": sum(c["score"] > 50 for c in rl)}
        out["summary_before"] = {"deepfakes_synthetic_verdict": sum(c["before"] > 65 for c in fk),
                                 "deepfakes_flagged": sum(c["before"] > 50 for c in fk),
                                 "reals_authentic_verdict": sum(c["before"] < 35 for c in rl),
                                 "reals_flagged": sum(c["before"] > 50 for c in rl),
                                 "correct": sum((c["before"] > 50) == (c["label"] == "fake") for c in demo)}
    out["note"] = ("Demo clips: research deepfakes made by other people (FaceForensics++, Google DFD, Celeb-DF) plus a "
                   "Wav2Lip lip-sync we made from a Google DFD clip, never used to fit any number, but looked at when the "
                   "face-swap pair was chosen. FF++ 069 (3 of the 6 fakes and 1 real) is in the face-swap detector's "
                   "TRAINING split, and the Celeb-DF id2 pair comes from Celeb-DF's training portion, so these are a "
                   "demonstration; the 75-clip benchmark is the test. The video thresholds of the older tests were set by "
                   "hand on our own 6 tuning clips, which are therefore not a test.")
    if bench:
        out["benchmark"] = bench
        out["benchmark"]["note"] = VIDEO_NOTE
        out["benchmark"]["dataset"] = ("75 leak-free clips: FaceForensics++ c23 official test split (20 real + 25 fake: "
                                       "Deepfakes, FaceSwap, Face2Face, NeuralTextures, FaceShifter x 5), Celeb-DF v2 "
                                       "official test list (10 + 10), Google DFD (5 + 5; actors not in any training "
                                       "set). No overlap with the demo clips (whole identities excluded).")
    return out


def main():
    if sys.argv[1:] == ["--restat"]:   # recompute the statistics from the saved per-clip rows; no engine run
        restat()
        return
    from server import config
    from server.models import REGISTRY

    t0 = time.perf_counter()
    if not REGISTRY.loaded:
        REGISTRY.load()
        REGISTRY.warmup()
    if REGISTRY.face_swap is None:
        raise SystemExit("face-swap detector not loaded: " + str(REGISTRY.errors.get("face_swap")))
    print(f"face-swap mode {config.faceswap_mode()}, {config.video_sampled_frames()} sampled frames, "
          f"{config.torch_threads()} threads")
    if sys.argv[1:] == ["--webcam-reals"]:   # only the webcam false-alarm check, merged into the existing block
        wr = evaluate_webcam_reals()
        res = json.loads(RESULTS.read_text())
        res["video"].setdefault("benchmark", {})["webcam_reals"] = wr
        RESULTS.write_text(json.dumps(res, indent=1))
        print("webcam reals:", {k: v for k, v in wr.items() if k not in ("clips", "note")})
        return
    bench = evaluate_benchmark()
    dt = evaluate_demo_and_tuning()
    if bench is not None:
        bench["webcam_reals"] = evaluate_webcam_reals()
    res = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    res["video"] = build_video_block(bench, dt, res.get("video"))
    res["generated_video"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        from evaluate import build_notes
        res["notes"] = build_notes(res)
    except Exception as e:  # noqa: BLE001
        print("notes not rebuilt:", e)
    RESULTS.write_text(json.dumps(res, indent=1))
    b = bench or {}
    for part in ("ffpp", "cross", "celebdf", "dfd"):
        if part in b.get("parts", {}):
            pb, pa = b["parts"][part]["before"], b["parts"][part]["after"]
            print(f"{part:8s} AUC before {pb.get('auc')} {pb.get('auc_ci95')} -> after {pa.get('auc')} {pa.get('auc_ci95')}; "
                  f"fakes {pb['fakes']} -> {pa['fakes']}; reals {pb['reals']} -> {pa['reals']}")
    if b.get("cross_gain"):
        print("cross gain", b["cross_gain"])
    print(f"wrote {RESULTS.relative_to(ROOT)} and {DETAILS.relative_to(ROOT)} in {(time.perf_counter() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
