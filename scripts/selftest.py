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
REGISTRY.load()
h = REGISTRY.health()
print(f"models: {h}   (loaded in {time.perf_counter() - t0:.1f} s)")
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
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"FAIL  {it['kind']:5s} {it['file']:28s} {type(e).__name__}: {e}")
    bad += not ok
print(f"\n{'ALL PASS' if not bad and all(h.values()) else f'{bad} FAILED'}  ({time.perf_counter() - t0:.0f} s total)")
sys.exit(1 if bad or not all(h.values()) else 0)
