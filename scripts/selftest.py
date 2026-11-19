"""VERITAS self-test: run every Evidence-locker exhibit through the real engine (no browser, no network) and compare
with the score recorded in web/samples/lab/manifest.json.  Also warms the one-time caches (numba JIT, matplotlib
fonts, .pyc files) so the first visitor is not the one who waits.

    .venv\\Scripts\\python.exe scripts\\selftest.py        (Windows)
    .venv/bin/python scripts/selftest.py                  (macOS)
Exit code 0 = all PASS.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

t0 = time.perf_counter()
try:
    import torch  # noqa: F401  (fails here with a clear message if the VC++ runtime is missing on Windows)
    from server.models import REGISTRY
    from server import pipeline
    import server.app  # noqa: F401  (pins the MIME types the web pages need)
except Exception as e:  # noqa: BLE001
    print(f"FAIL  could not import the engine libraries: {e}")
    print("      Windows: install the Microsoft Visual C++ 2015-2022 Redistributable (x64), then run setup again.")
    sys.exit(2)
import mimetypes  # noqa: E402

js_type = mimetypes.guess_type("main.js")[0]
print(f"{'PASS' if js_type == 'text/javascript' else 'FAIL'}  .js is served as {js_type}")
from server import config  # noqa: E402

REGISTRY.load()
h = REGISTRY.health()
print(f"models: {h}   (loaded in {time.perf_counter() - t0:.1f} s)")
FS_MODE = config.faceswap_mode()
print(f"face-swap detector mode: {FS_MODE}   video frames per clip: {config.video_sampled_frames()}"
      f"   threads: {config.torch_threads()}")
# The face-swap detector stays silent (< 50) on both locker videos, so their final scores cannot show whether it ran.
# Check it directly: status ok, its score (fp32 mode, measured on the dev Mac at 48 and 32 frames) and how many of its
# 8 frames each network found a face in. A missing DLL or a Windows numerics problem would show up here.
FACE_SWAP_EXPECT = {  # file: (score in fp32 mode, {network: frames with a face})
    "real-video.mp4": (16, {"GenD": 8, "B7": 8}),
    "synthetic-video.mp4": (0, {"GenD": 0, "B7": 8}),   # SCRFD finds no face in the animated GAN still
}


def check_face_swap(name: str, rep: dict) -> bool:
    if FS_MODE == "off":
        return True
    exp = FACE_SWAP_EXPECT.get(name)
    if exp is None:
        return True
    fs = next((t for t in rep["tests"] if t["id"] == "face_swap"), None)
    if fs is None or fs["status"] != "ok" or fs["score"] is None:
        print(f"FAIL  face-swap detector on {name}: "
              f"{'missing' if fs is None else fs['status'] + ' - ' + str(fs.get('finding'))}")
        return False
    m = fs.get("metrics", {})
    frames = {k: m.get(f"{k}_frames_with_face", m.get(f"{k}_int8_frames_with_face")) for k in exp[1]}
    frames = {k: v for k, v in frames.items() if v is not None}
    ok_frames = all(v == exp[1][k] for k, v in frames.items()) and frames
    ok_score = FS_MODE != "fp32" or abs(fs["score"] - exp[0]) <= 5
    ok = bool(ok_frames and ok_score)
    frames = {k: int(v) for k, v in frames.items()}
    print(f"{'PASS' if ok else 'FAIL'}  face-swap {name:24s} score {fs['score']:3d}"
          f"{f' (expected {exp[0]})' if FS_MODE == 'fp32' else f' ({FS_MODE} mode, score not compared)'}"
          f"   frames with a face {frames} (expected {exp[1]})")
    return ok


fn = {"image": pipeline.analyze_image, "video": pipeline.analyze_video, "audio": pipeline.analyze_audio}
items = json.loads((ROOT / "web" / "samples" / "lab" / "manifest.json").read_text(encoding="utf-8"))
bad = int(js_type != "text/javascript")
for it in items:
    p = ROOT / "web" / "samples" / "lab" / it["file"]
    t = time.perf_counter()
    try:
        rep = fn[it["kind"]](p.read_bytes(), p.name)
        ok = abs(rep["score"] - it.get("engine_score", rep["score"])) <= 5
        print(f"{'PASS' if ok else 'FAIL'}  {it['kind']:5s} {it['file']:28s} score {rep['score']:3d} (expected {it.get('engine_score')})"
              f"  {time.perf_counter() - t:5.1f} s")
        if it["kind"] == "video":
            ok = check_face_swap(it["file"], rep) and ok
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"FAIL  {it['kind']:5s} {it['file']:28s} {type(e).__name__}: {e}")
    bad += not ok
print(f"\n{'ALL PASS' if not bad and all(h.values()) else f'{bad} FAILED'}  ({time.perf_counter() - t0:.0f} s total)")
sys.exit(1 if bad or not all(h.values()) else 0)
