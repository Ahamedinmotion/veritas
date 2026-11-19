"""Should the face-swap detector (GenD + DFDC-B7, built for VIDEO) also score faces in still images and Live Cam
captures? Decided by measurement, not by hope. Writes eval_data/faceswap_images.json and prints a summary.

    uv run python scripts/evaluate_faceswap_images.py        # ~15 min on the M4

The detector's thresholds were chosen for the mean of 8 video frames on FaceForensics++; a single still has no such
average, so it is scored here exactly as one frame (same face detectors, same crops, same formula; score >= 50 =
"fires"). What we check:
  1. False alarms on REAL faces - the deal-breaker:
       * the image held-out split (FFHQ / COCO people / our 7 phone photos), as laundered JPEGs and after the
         webcam, phone-denoise, H.264-still and WhatsApp degradations (evalcommon.degrade),
       * 105 frames of real people from the 35 real research videos of the 75-clip benchmark (FF++ test originals,
         Celeb-DF real, Google DFD originals), as saved by Live Cam (JPEG 0.92) and after the webcam degradation,
       * stills of the real demo clips (the "Real video stills" set of the Results chapter).
  2. What it would add: the held-out face-swap stills (our own GAN-face pastes; the engine catches 2 of 9) and
     the fake research-video frames.
  3. The verdict effect: the held-out images re-fused with the detector added one-sided (like video) at weight
     W_IMAGE, counting real images whose verdict would change.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evalcommon import EVAL, ROOT, degrade, launder, load_items  # noqa: E402

INCOMING = ROOT.parent / "_incoming" / "media" / "video"
FS_DIR = EVAL / "video_faceswap"
OUT = EVAL / "faceswap_images.json"
CONDS = ("laundered", "webcam", "denoise", "h264", "whatsapp")
W_IMAGE = 1.25        # the video weight, for the "what if" fusion (image weights also sum to 1.0)


def module_score(rgb: np.ndarray) -> dict:
    from server.models import INFER_LOCK, REGISTRY

    with INFER_LOCK:
        r = REGISTRY.face_swap.analyze([rgb])
    return {"score": None if r["score"] is None else round(r["score"], 1),
            "gend_p": r["clip_p"].get("gend"), "dfdc_p": r["clip_p"].get("dfdc")}


def rgb_of(data: bytes) -> np.ndarray:
    from PIL import ImageOps
    return np.asarray(ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB"))


def refuse_image(rep: dict, fs: dict) -> int:
    """Fused image score with the face-swap test added one-sided at weight W_IMAGE (what-if)."""
    import copy

    from server import config, fusion

    tests = [copy.deepcopy(t) for t in rep["tests"]]
    if fs["score"] is not None:
        tests.append({"id": "face_swap", "name": "Face-Swap Detector", "category": "ai_model", "status": "ok",
                      "score": int(round(fs["score"])), "weight": 0.0, "_onesided": True, "metrics": {}})
    marker = any(t["id"] == "metadata" and t["status"] == "ok" and (t["metrics"].get("ai_markers") or 0) > 0
                 for t in tests)
    old = config.DEFAULT_WEIGHTS["image"].get("face_swap")
    config.DEFAULT_WEIGHTS["image"]["face_swap"] = W_IMAGE
    try:
        return fusion.fuse("image", tests, hard_ai_marker=marker)["score"]
    finally:
        if old is None:
            config.DEFAULT_WEIGHTS["image"].pop("face_swap", None)


def frames_at(path: Path, times=(1.0, 5.0, 9.0)) -> list[Image.Image]:
    import av

    out, want = [], list(times)
    with av.open(str(path)) as c:
        for fr in c.decode(video=0):
            if want and fr.time is not None and fr.time >= want[0]:
                out.append(fr.to_image())
                want.pop(0)
            if not want:
                break
    return out


def jpeg92(im: Image.Image) -> bytes:
    im = im.copy()
    im.thumbnail((1280, 1280))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=92)
    return b.getvalue()


def summary(rows, key="score"):
    sc = [r[key] for r in rows if r.get(key) is not None]
    return {"n": len(rows), "with_face": len(sc), "fires": int(sum(s >= 50 for s in sc)),
            "fires_pct": round(100 * sum(s >= 50 for s in sc) / max(1, len(sc)), 1),
            "max": None if not sc else max(sc), "median": None if not sc else float(np.median(sc))}


def main():
    from server import pipeline
    from server.models import REGISTRY

    t0 = time.perf_counter()
    REGISTRY.load()
    REGISTRY.warmup()
    assert REGISTRY.face_swap is not None, REGISTRY.errors
    res = {"note": __doc__.strip().splitlines()[0], "weight_what_if": W_IMAGE}

    # 1+3. image held-out split, 5 conditions, module score + what-if fusion
    items = [it for it in load_items("images") if it["split"] == "test"]
    rows = []
    for it in items:
        raw = it["path"].read_bytes()
        for i, c in enumerate(CONDS):
            data = launder(raw) if c == "laundered" else degrade(raw, c, seed=i)
            rep = pipeline.analyze_image(data, it["name"], keep_private=True)
            fs = module_score(rgb_of(data))
            rows.append({"file": it["name"], "label": "fake" if it["y"] else "real", "group": it["group"], "cond": c,
                         "engine": rep["score"], "with_fs": refuse_image(rep, fs), **fs})
        print(f"  {it['name']:40s} {'fake' if it['y'] else 'real'} {[r['score'] for r in rows[-len(CONDS):]]}", flush=True)
    res["image_heldout"] = {"rows": rows}
    agg = {}
    for lab in ("real", "fake"):
        for c in CONDS:
            rr = [r for r in rows if r["label"] == lab and r["cond"] == c]
            s = summary(rr)
            s["engine_flagged"] = int(sum(r["engine"] > 50 for r in rr))
            s["with_fs_flagged"] = int(sum(r["with_fs"] > 50 for r in rr))
            s["engine_synthetic"] = int(sum(r["engine"] > 65 for r in rr))
            s["with_fs_synthetic"] = int(sum(r["with_fs"] > 65 for r in rr))
            s["verdict_changed"] = int(sum((r["engine"] > 65) != (r["with_fs"] > 65) or (r["engine"] < 35) != (r["with_fs"] < 35)
                                           for r in rr))
            agg[f"{lab}_{c}"] = s
    fsw = [r for r in rows if r["group"] == "face_swap"]
    for c in CONDS:
        rr = [r for r in fsw if r["cond"] == c]
        agg[f"face_swap_stills_{c}"] = {**summary(rr), "engine_flagged": int(sum(r["engine"] > 50 for r in rr)),
                                         "with_fs_flagged": int(sum(r["with_fs"] > 50 for r in rr))}
    res["image_heldout"]["summary"] = agg

    # 2. frames of real (and fake) people from the 75 research clips, Live-Cam JPEG and webcam-degraded
    vrows = []
    man = json.loads((FS_DIR / "manifest.json").read_text()) if (FS_DIR / "manifest.json").exists() else []
    for m in man:
        for k, im in enumerate(frames_at(FS_DIR / m["file"])):
            data = jpeg92(im)
            for c, d in (("live_jpeg", data), ("webcam", degrade(data, "webcam", seed=k))):
                vrows.append({"clip": m["file"], "label": m["label"], "dataset": m["dataset"], "cond": c, **module_score(rgb_of(d))})
    res["video_frames"] = {"rows": vrows, "summary": {
        f"{lab}_{c}": summary([r for r in vrows if r["label"] == lab and r["cond"] == c])
        for lab in ("real", "fake") for c in ("live_jpeg", "webcam")}}
    print("  research-video frames:", res["video_frames"]["summary"], flush=True)

    # demo-clip stills (1 / 3 / 5 s, the Results chapter's "Real video stills")
    srows = []
    if (INCOMING / "manifest.json").exists():
        for m in json.loads((INCOMING / "manifest.json").read_text()):
            f = INCOMING / m["file"].split("/", 1)[-1]
            lab = "fake" if m["label"] == "synthetic" else "real"
            for k, im in enumerate(frames_at(f, (1.0, 3.0, 5.0))):
                data = jpeg92(im)
                rep = pipeline.analyze_image(data, f"live-capture-{f.stem}_{k}.jpg", keep_private=True)
                fs = module_score(rgb_of(data))
                srows.append({"clip": f.stem, "label": lab, "engine_live": rep["score"], "with_fs": refuse_image(rep, fs), **fs})
    res["demo_stills"] = {"rows": srows, "summary": {lab: {**summary([r for r in srows if r["label"] == lab]),
                                                           "engine_flagged": sum(r["engine_live"] > 50 for r in srows if r["label"] == lab),
                                                           "with_fs_flagged": sum(r["with_fs"] > 50 for r in srows if r["label"] == lab)}
                                                     for lab in ("real", "fake")}}
    print("  demo stills:", res["demo_stills"]["summary"], flush=True)

    # lab samples
    lab_rows = []
    for it in json.loads((ROOT / "web/samples/lab/manifest.json").read_text()):
        if it["kind"] != "image":
            continue
        data = (ROOT / "web/samples/lab" / it["file"]).read_bytes()
        rep = pipeline.analyze_image(data, it["file"], keep_private=True)
        fs = module_score(rgb_of(data))
        lab_rows.append({"file": it["file"], "label": it["label"], "engine": rep["score"], "with_fs": refuse_image(rep, fs), **fs})
    res["lab_samples"] = lab_rows
    print("  lab samples:", lab_rows, flush=True)

    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res["image_heldout"]["summary"], indent=1))
    print(f"wrote {OUT.relative_to(ROOT)} in {(time.perf_counter() - t0) / 60:.1f} min")


def merge(res: dict | None = None):
    """Write the short summary into web/data/results.json -> image_details.faceswap_on_stills."""
    res = res or json.loads(OUT.read_text())
    S = res["image_heldout"]["summary"]
    real = {c: {k: S[f"real_{c}"][k] for k in ("with_face", "fires", "engine_flagged", "with_fs_flagged",
                                                 "engine_synthetic", "with_fs_synthetic", "verdict_changed")} for c in CONDS}
    swaps = {c: {k: S[f"face_swap_stills_{c}"][k] for k in ("n", "fires", "engine_flagged", "with_fs_flagged")} for c in CONDS}
    vf = res["video_frames"]["summary"]
    ds = res["demo_stills"]["summary"]
    block = {
        "decision": "video-only",
        "why": "On single stills the detector raised false alarms on real faces (more real photos flagged after "
               "webcam / H.264 / denoise degradations, and it fired on about 1 in 5 frames of real people from "
               "research videos), so photos and Live Cam captures do not use it.",
        "weight_what_if": res.get("weight_what_if"),
        "real_heldout_photos": real,
        "face_swap_stills": swaps,
        "real_video_frames": {k: vf[k] for k in ("real_live_jpeg", "real_webcam")},
        "fake_video_frames": {k: vf[k] for k in ("fake_live_jpeg", "fake_webcam")},
        "demo_stills": ds,
    }
    R = ROOT / "web" / "data" / "results.json"
    d = json.loads(R.read_text())
    d.setdefault("image_details", {})["faceswap_on_stills"] = block
    R.write_text(json.dumps(d, indent=1))
    print("merged into", R.relative_to(ROOT))


if __name__ == "__main__":
    if sys.argv[1:] == ["--merge"]:
        merge()
    else:
        main()
        merge()
