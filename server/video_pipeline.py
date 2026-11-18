"""Video analysis: neural detectors on sampled frames + biometric/temporal tests on a dense landmark track."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw

from . import charts, config, fusion
from .forensics import ai_face, blink, face_track, landmark_jitter, temporal_flicker, video_meta
from .forensics.base import calibrated, make_test, safe_run
from .models import REGISTRY
from .util import Timer, jpeg_uri
from .video_io import read_video

log = logging.getLogger("veritas.video")
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="track")

AIGEN_NAME = "AI-Generated Frames"
AIGEN_EXPLAIN = ("The same whole-image AI detector used for photos is run on frames spread across the clip. "
                 "Fully generated videos and animated AI faces carry generator fingerprints in every frame. It was "
                 "not trained on face-swaps or lip-sync, and heavy video compression can fool it either way.")
FACE_EXPLAIN = ("Faces are found in up to 48 frames spread across the clip and the general AI-image detector scores "
                "each face crop; averaging many frames is steadier than one still. It catches generated (GAN or "
                "diffusion) faces but misses most face-swaps and lip-syncs, which keep a real face's texture.")


def video_face_score(p: float) -> float:
    """Per-frame face score for VIDEO. Video frames are compressed (and often small), so the image calibration curve
    is too trigger-happy on them. With only 6 test videos we could not fit a curve statistically, so this is a
    hand-set logistic: 50 at P(fake) = 0.15, slope 1 in log-odds (documented as a limitation)."""
    vf = config.CALIBRATION.get("video_face", {"mid": 0.15, "a": 1.0})
    p = min(1 - 1e-6, max(1e-6, float(p)))
    z = vf["a"] * (np.log(p / (1 - p)) - np.log(vf["mid"] / (1 - vf["mid"])))
    return float(100 / (1 + np.exp(-z)))


def _thumb(rgb: np.ndarray, box_norm, score: float) -> str:
    im = Image.fromarray(rgb)
    im.thumbnail((360, 360), Image.Resampling.LANCZOS)
    if box_norm:
        d = ImageDraw.Draw(im)
        x, y, w, h = box_norm
        W, H = im.size
        d.rectangle([x * W, y * H, (x + w) * W, (y + h) * H], outline=charts.score_color(score), width=3)
    return jpeg_uri(im, 360, 80)


def analyze_video(data: bytes, name: str, rep: dict) -> dict:
    timer = Timer()
    vid = read_video(data, name=name)
    timer.mark("decode")
    dense, sampled = vid["dense"], vid["sampled"]
    dense_fps = len(dense) / max(vid["analysed"], 1e-3)
    rep["file"].update(format=vid["format"], width=vid["width"], height=vid["height"], duration=round(vid["duration"], 2))

    # landmark track runs on a worker thread while the neural nets score sampled frames here
    fut = _pool.submit(face_track.track, dense)

    # ---- faces on sampled frames
    per_frame = []
    det, clf = REGISTRY.face_detector, REGISTRY.face_deepfake
    crops, owners = [], []
    for i, (t, rgb) in enumerate(sampled):
        faces = det.detect(rgb, max_faces=1, sides=(480,)) if det else []
        if faces:
            f = faces[0]
            H, W = rgb.shape[:2]
            x, y, w, h = f["box"]
            from .models import face_crop

            crops.append(Image.fromarray(face_crop(rgb, f["box"])))
            owners.append(i)
            per_frame.append({"t": t, "box": [x / W, y / H, w / W, h / H], "face": None, "frame": None})
        else:
            per_frame.append({"t": t, "box": None, "face": None, "frame": None})
    if crops and clf:
        probs = clf.predict(crops)
        for i, p in zip(owners, probs):
            per_frame[i]["face"] = video_face_score(p)
            per_frame[i]["p"] = p
    timer.mark("faces")
    # ---- whole-frame AI detector on up to 12 frames
    gen = REGISTRY.ai_generated
    k = min(12, len(sampled))
    sel = sorted(set(np.linspace(0, len(sampled) - 1, k).round().astype(int).tolist())) if k else []
    if gen and sel:
        probs = gen.predict([Image.fromarray(sampled[i][1]) for i in sel])
        for i, p in zip(sel, probs):
            per_frame[i]["frame"] = calibrated("ai_generated", p * 100)
    timer.mark("frames")

    tests = {}
    face_scores = [f["face"] for f in per_frame if f["face"] is not None]
    if face_scores and clf:
        arr = np.array(face_scores)
        fs = float(0.7 * arr.mean() + 0.3 * np.percentile(arr, 90))
        frac_fake = float((arr > config.THRESH_SYNTHETIC).mean())
        if fs > config.THRESH_SYNTHETIC:
            finding = f"Face looks synthetic in {frac_fake * 100:.0f}% of {len(arr)} sampled frames."
        elif fs >= config.THRESH_SUSPICIOUS:
            finding = f"Mixed: {frac_fake * 100:.0f}% of {len(arr)} face frames look synthetic."
        else:
            finding = f"Face looks real across {len(arr)} sampled frames."
        xs = [f["t"] for f in per_frame if f["face"] is not None]
        visual = charts.bar_chart(np.array(xs), arr, [charts.score_color(s) for s in arr], xlabel="time (s)",
                                  ylabel="synthetic %", hlines=[(config.THRESH_SYNTHETIC, charts.SYN, "synthetic"),
                                                                (config.THRESH_SUSPICIOUS, charts.AUTH, "authentic")],
                                  width=max(0.08, 0.7 * (xs[1] - xs[0])) if len(xs) > 1 else 0.3)
        tests["ai_face"] = make_test("ai_face", "AI Face Analysis (per-frame)", "ai_model", score=fs, finding=finding,
                                     explain=FACE_EXPLAIN, visual=visual,
                                     metrics={"face_frames": len(arr), "sampled_frames": len(per_frame),
                                              "mean_face_score": float(arr.mean()), "frames_synthetic_pct": frac_fake * 100,
                                              "raw": float(np.mean([f["p"] for f in per_frame if f.get("p") is not None]) * 100)})
    else:
        tests["ai_face"] = make_test("ai_face", "AI Face Analysis (per-frame)", "ai_model", status="skipped", score=None,
                                     finding="No clear face in the sampled frames.", explain=FACE_EXPLAIN,
                                     metrics={"face_frames": 0, "sampled_frames": len(per_frame)})
    fr = [f["frame"] for f in per_frame if f["frame"] is not None]
    if fr:
        fa = np.array(fr)
        s = float(0.7 * fa.mean() + 0.3 * fa.max())
        finding = ("Generator fingerprints in the frames themselves." if s > config.THRESH_SYNTHETIC else
                   "Some frames resemble AI-generated imagery." if s >= config.THRESH_SUSPICIOUS else
                   "Frames look like real camera footage.")
        tests["ai_generated"] = make_test("ai_generated", AIGEN_NAME, "ai_model", score=s, finding=finding,
                                          explain=AIGEN_EXPLAIN, metrics={"frames_scored": len(fa), "mean": float(fa.mean()),
                                                                          "max": float(fa.max())})
    else:
        tests["ai_generated"] = make_test("ai_generated", AIGEN_NAME, "ai_model", status="error", score=None,
                                          finding="Frame detector unavailable.", explain=AIGEN_EXPLAIN)

    # ---- dense landmark tests
    try:
        trk = fut.result()
    except Exception as e:  # noqa: BLE001
        log.warning("face tracking failed: %s", e)
        trk = None
    timer.mark("track")
    if trk is not None and "error" not in trk:
        tests["blink"] = safe_run(blink.run, "blink", blink.NAME, "biometric", blink.EXPLAIN, trk, dense_fps)
        tests["landmark_jitter"] = safe_run(landmark_jitter.run, "landmark_jitter", landmark_jitter.NAME, "temporal",
                                            landmark_jitter.EXPLAIN, trk)
        tests["temporal_flicker"] = safe_run(temporal_flicker.run, "temporal_flicker", temporal_flicker.NAME, "temporal",
                                             temporal_flicker.EXPLAIN, trk)
    else:
        for tid, mod, cat in (("blink", blink, "biometric"), ("landmark_jitter", landmark_jitter, "temporal"),
                              ("temporal_flicker", temporal_flicker, "temporal")):
            tests[tid] = make_test(tid, mod.NAME, cat, status="error", score=None,
                                   finding="Face landmark tracker unavailable.", explain=mod.EXPLAIN)
    tests["metadata"], md = video_meta.run(vid["tags"], data, vid["codec"])

    order = ["ai_face", "ai_generated", "blink", "landmark_jitter", "temporal_flicker", "metadata"]
    rep["tests"] = [tests[k] for k in order]

    # ---- timeline + keyframes (frame score = face score where a face exists, else frame detector)
    frame_scores = [f["frame"] for f in per_frame]
    filled = np.array([np.nan if v is None else v for v in frame_scores], dtype=float)
    if np.isfinite(filled).any():
        idx = np.arange(len(filled))
        ok = np.isfinite(filled)
        filled = np.interp(idx, idx[ok], filled[ok])
    timeline = []
    for i, f in enumerate(per_frame):
        if f["face"] is not None:
            v = f["face"]
        elif np.isfinite(filled[i]) if len(filled) else False:
            v = float(filled[i])
        else:
            continue
        f["score"] = v
        timeline.append({"t": round(float(f["t"]), 2), "score": int(round(v))})
    rep["timeline"] = timeline
    ranked = sorted([i for i, f in enumerate(per_frame) if "score" in f], key=lambda i: per_frame[i]["score"], reverse=True)
    picks = []
    for i in ranked:  # spread keyframes out in time
        if all(abs(per_frame[i]["t"] - per_frame[j]["t"]) > max(0.6, vid["analysed"] / 12) for j in picks):
            picks.append(i)
        if len(picks) == 4:
            break
    rep["keyframes"] = [{"t": round(float(per_frame[i]["t"]), 2), "score": int(round(per_frame[i]["score"])),
                         "thumb": _thumb(sampled[i][1], per_frame[i]["box"], per_frame[i]["score"])}
                        for i in sorted(picks, key=lambda i: per_frame[i]["t"])]
    # poster: first sampled frame with a face (or the middle frame)
    pi = next((i for i, f in enumerate(per_frame) if f["box"] is not None), len(sampled) // 2)
    rep["preview"] = jpeg_uri(sampled[pi][1], 960)
    if per_frame and per_frame[pi]["box"] is not None and per_frame[pi]["face"] is not None:
        rep["faces"] = [{"box": [round(v, 4) for v in per_frame[pi]["box"]],
                         "score": int(round(tests["ai_face"]["score"] or per_frame[pi]["face"]))}]
    rep["metadata"] = {"exif": md["exif"], "flags": md["flags"]}
    rep.update(fusion.fuse("video", rep["tests"], hard_ai_marker=md.get("ai_marker", False)))
    rep["elapsed_ms"] = timer.ms
    rep["timing_ms"] = timer.marks
    log.info("video %s: %d dense / %d sampled frames, timings %s", name, len(dense), len(sampled), timer.marks)
    return rep
