"""CI check against a running VERITAS engine (standard library only).

    python .github/scripts/check_api.py http://127.0.0.1:8000 <install-dir>/web/samples/lab [--faceswap fp32|int8|b7]

Checks /api/health (ok + all four models), that .js files are served as text/javascript (the Windows MIME fix), and
POSTs Evidence-locker samples to /api/analyze/{image,audio,video}: each verdict must equal the verdict of the
engine_score recorded in web/samples/lab/manifest.json. Samples whose recorded score is within 3 points of a
threshold (35 / 65) are reported but not asserted (scores may move by a point or two across platforms).
--faceswap MODE also asserts which face-swap detector the engine loaded (e.g. the one "auto" picked).
Lines starting with "TIMING" are collected for the guide / README.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

SUSPICIOUS, SYNTHETIC = 35, 65
FACESWAP_NAMES = {"fp32": "GenD CLIP ViT-L/14 + DFDC-B7", "int8": "GenD CLIP ViT-L/14 (int8) + DFDC-B7", "b7": "DFDC-B7"}
MIME = {".jpg": "image/jpeg", ".webp": "image/webp", ".png": "image/png", ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp4": "video/mp4"}


def verdict(score: int) -> str:
    return "synthetic" if score >= SYNTHETIC else "suspicious" if score >= SUSPICIOUS else "authentic"


def get(url: str, timeout: float = 30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def post_file(url: str, path: Path) -> dict:
    b = uuid.uuid4().hex
    head = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f'Content-Type: {MIME.get(path.suffix.lower(), "application/octet-stream")}\r\n\r\n').encode()
    body = head + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def main() -> int:
    args = sys.argv[1:]
    want_fs = None
    if "--faceswap" in args:
        i = args.index("--faceswap")
        want_fs = args[i + 1]
        del args[i:i + 2]
    base, samples = args[0].rstrip("/"), Path(args[1])
    bad = 0
    st, _, raw = get(base + "/api/health")
    h = json.loads(raw)
    print("health:", json.dumps({k: h.get(k) for k in ("ok", "version", "models")}))
    if not h.get("ok") or not all(h.get("models", {}).values()):
        print("FAIL  health is not ok or a model is missing:", h.get("detail"))
        bad += 1
    fs_name = (h.get("detail") or {}).get("model_names", {}).get("face_swap")
    if want_fs:
        ok = fs_name == FACESWAP_NAMES.get(want_fs)
        print(f"{'PASS' if ok else 'FAIL'}  face-swap detector loaded: {fs_name} (expected {want_fs})")
        bad += not ok
    else:
        print(f"INFO  face-swap detector loaded: {fs_name}")
    st, ctype, page = get(base + "/")
    ok = st == 200 and "text/html" in ctype and b"<html" in page.lower()
    print(f"{'PASS' if ok else 'FAIL'}  GET /  -> {st} {ctype}")
    bad += not ok
    js = next((p for p in sorted((samples.parents[1] / "js").rglob("*.js"))), None)
    if js:
        rel = js.relative_to(samples.parents[1]).as_posix()
        st, ctype, _ = get(f"{base}/{rel}")
        ok = st == 200 and ctype.startswith("text/javascript")
        print(f"{'PASS' if ok else 'FAIL'}  GET /{rel} -> {ctype}")
        bad += not ok
    manifest = json.loads((samples / "manifest.json").read_text(encoding="utf-8"))
    first_video = True
    for it in manifest:
        exp_score = it.get("engine_score")
        if exp_score is None:
            continue
        exp = verdict(exp_score)
        border = min(abs(exp_score - SUSPICIOUS), abs(exp_score - SYNTHETIC)) <= 3
        t = time.perf_counter()
        try:
            rep = post_file(f"{base}/api/analyze/{it['kind']}", samples / it["file"])
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {it['kind']:5s} {it['file']:26s} request failed: {e}")
            bad += 1
            continue
        secs = time.perf_counter() - t
        ok = rep.get("verdict") == exp
        tag = "PASS" if ok else ("INFO" if border else "FAIL")
        print(f"{tag}  {it['kind']:5s} {it['file']:26s} -> {rep.get('verdict'):10s} {rep.get('score'):3d} "
              f"(manifest {exp_score} = {exp}{', borderline: not asserted' if border else ''})"
              f"  {secs:5.1f} s")
        if it["kind"] == "video" and first_video:
            first_video = False
            print(f"TIMING first-video-analysis: {it['file']} took {secs:.1f} s (face-swap: {fs_name})")
        bad += (not ok) and not border
    print("API CHECK:", "ALL PASS" if not bad else f"{bad} FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
