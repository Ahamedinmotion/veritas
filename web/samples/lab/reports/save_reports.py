"""Save the REAL engine report for every Evidence-locker exhibit (showcase mode of the lab).

When no forensic engine is reachable (the website on a static host with the online engine asleep or down), the lab
opens these files instead of analysing: each one is the engine's unedited /api/analyze answer for that exhibit.
The only change: PNG charts inside the report are re-encoded as LOSSLESS WebP (pixel-identical, ~30% smaller).
A "_showcase" block records when and where the report was made.

Usage (engine running, e.g. ./scripts/start_mac.sh):
    .venv/bin/python web/samples/lab/reports/save_reports.py --api http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import mimetypes
import platform
import sys
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
LAB = HERE.parent


def post_file(url: str, path: Path) -> dict:
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))


def png_to_webp(data_url: str) -> str:
    head, b64 = data_url.split(",", 1)
    if "image/png" not in head:
        return data_url
    im = Image.open(io.BytesIO(base64.b64decode(b64)))
    out = io.BytesIO()
    im.save(out, "WEBP", lossless=True, method=6)
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--where", default="our development laptop")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    health = json.loads(urllib.request.urlopen(f"{api}/api/health", timeout=30).read())
    if not health.get("ok") or health.get("online"):
        print("Use the full booth engine (not the online one) with every model loaded.", file=sys.stderr)
        return 1
    items = json.loads((LAB / "manifest.json").read_text(encoding="utf-8"))
    bad = 0
    for it in items:
        src = LAB / it["file"]
        rep = post_file(f"{api}/api/analyze/{it['kind']}", src)
        for t in rep.get("tests", []):
            if isinstance(t.get("visual"), str) and t["visual"].startswith("data:image/png"):
                t["visual"] = png_to_webp(t["visual"])
        rep["_showcase"] = {
            "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "engine_version": health.get("version"),
            "where": a.where,
            "machine": f"{platform.system()} {platform.machine()}, CPU",
            "note": "Unedited engine report for this exhibit; PNG charts stored as lossless WebP.",
        }
        out = HERE / f"{src.name}.json"
        out.write_text(json.dumps(rep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        same = rep.get("score") == it.get("engine_score")
        bad += not same
        print(f"{src.name:28s} {rep.get('verdict'):10s} {rep.get('score'):>3}  manifest {it.get('engine_score'):>3}"
              f"  {'ok' if same else 'DIFFERS'}  {out.stat().st_size / 1e6:.2f} MB")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
