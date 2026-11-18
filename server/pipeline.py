"""Analysis pipelines: bytes in -> contract-shaped report dict out."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

from . import fusion
from .forensics import ai_face, ai_generated, ela, fft, jpeg_quant, metadata, noise
from .forensics.base import make_test, safe_run
from .util import AnalysisError, Timer, case_id, detail_level, is_grayscale, jpeg_uri, open_image, sha256, to_rgb

log = logging.getLogger("veritas.pipeline")
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="forensic")

IMAGE_ORDER = ["ai_generated", "ai_face", "ela", "noise", "fft", "jpeg_quant", "metadata"]
# The lab's Live Cam names its captures "live-capture-HHMMSS.jpg". A webcam frame is smoothed by the camera's own
# noise reduction and re-encoded by the browser, so the tests that look for edits, sensor grain, spectrum
# statistics, JPEG tables or EXIF cannot say anything about it - only the two AI detectors are scored.
LIVE_PREFIX = "live-capture"
LIVE_SKIP = {"ela", "noise", "fft", "jpeg_quant", "metadata"}
LIVE_NOTE = "Webcam frame: the camera smooths and re-encodes it, so this test does not apply."
GRAY_NOTE = ("Black-and-white image: the colour fingerprints our AI detectors rely on are gone, "
             "so the result is inconclusive.")
LARGE_PIXELS = 24_000_000


class _Pick:
    """Future-like view of one key of a future that returns a dict (used for the large-photo serial path)."""

    def __init__(self, fut, key):
        self._fut, self._key = fut, key

    def result(self):
        return self._fut.result()[self._key]


def _base_report(kind: str, name: str, data: bytes) -> dict:
    return {
        "kind": kind, "case_id": case_id(), "elapsed_ms": 0,
        "file": {"name": name or f"upload.{kind}", "size": len(data), "sha256": sha256(data), "format": None,
                 "width": None, "height": None, "duration": None},
        "verdict": "suspicious", "score": 50, "confidence": 0.0, "summary": "", "preview": None,
        "faces": [], "tests": [], "timeline": [], "keyframes": [], "waveform": [],
        "metadata": {"exif": {}, "flags": []},
    }


def analyze_image(data: bytes, name: str = "", keep_private: bool = False) -> dict:
    timer = Timer()
    if not data:
        raise AnalysisError("Empty upload.")
    img_raw = open_image(data)
    fmt = (img_raw.format or (name.rsplit(".", 1)[-1] if "." in name else "IMAGE")).upper()
    img = to_rgb(img_raw)
    if detail_level(img) < 2.0:
        raise AnalysisError("This image is almost blank (one flat colour), so there is no detail to analyse.")
    live = os.path.basename(name or "").lower().startswith(LIVE_PREFIX)
    gray = is_grayscale(img)
    rep = _base_report("image", name, data)
    rep["file"].update(format=fmt, width=img.width, height=img.height)

    # classic tests run on worker threads while the neural nets run here. On very large photos (> 24 MP) they run
    # one after another instead: each holds full-resolution float copies, and three at once can push an 8 GB laptop
    # into paging. The results are identical either way.
    classic = [("ela", ela, "compression"), ("noise", noise, "noise"), ("fft", fft, "frequency")]
    if img.width * img.height > LARGE_PIXELS:
        def _serial():
            return {k: safe_run(m.run, k, m.NAME, cat, m.EXPLAIN, img) for k, m, cat in classic}
        serial = _pool.submit(_serial)
        futs = {k: _Pick(serial, k) for k, _, _ in classic}
    else:
        futs = {k: _pool.submit(safe_run, m.run, k, m.NAME, cat, m.EXPLAIN, img) for k, m, cat in classic}
    tests: dict[str, dict] = {}
    tests["ai_generated"] = safe_run(ai_generated.run, "ai_generated", ai_generated.NAME, "ai_model",
                                     ai_generated.EXPLAIN, img)
    faces = []
    try:
        tests["ai_face"], faces = ai_face.run(img)
    except Exception as e:  # noqa: BLE001
        log.warning("ai_face failed: %s", e)
        tests["ai_face"] = make_test("ai_face", ai_face.NAME, "ai_model", status="error",
                                     finding="Face analysis could not run.", explain=ai_face.EXPLAIN)
    tests["jpeg_quant"] = safe_run(jpeg_quant.run, "jpeg_quant", jpeg_quant.NAME, "compression",
                                   jpeg_quant.EXPLAIN, img_raw, fmt)
    md_report = {"exif": {}, "flags": [], "ai_marker": False}
    try:
        tests["metadata"], md_report = metadata.run(img_raw, data)
    except Exception as e:  # noqa: BLE001
        log.warning("metadata failed: %s", e)
        tests["metadata"] = make_test("metadata", metadata.NAME, "metadata", status="error",
                                      finding="Metadata could not be read.", explain=metadata.EXPLAIN)
    for k, f in futs.items():
        tests[k] = f.result()
    flags = list(md_report.get("flags", []))
    if live:
        for k in LIVE_SKIP:
            t = tests[k]
            if t["status"] == "ok":
                t.update(status="skipped", score=None, finding=LIVE_NOTE)
                t.pop("_amplify", None)
        md_report["ai_marker"] = False
        flags.insert(0, "Live webcam capture: only the two AI detectors are scored")
    if gray:
        flags.insert(0, "Black-and-white image: AI detectors are less reliable")
    rep["tests"] = [tests[k] for k in IMAGE_ORDER]
    rep["faces"] = faces
    rep["metadata"] = {"exif": md_report.get("exif", {}), "flags": flags}
    rep["preview"] = jpeg_uri(img, 960)
    rep.update(fusion.fuse("image", rep["tests"], hard_ai_marker=md_report.get("ai_marker", False)))
    if gray and rep["score"] < fusion.config.THRESH_SUSPICIOUS:
        # removing colour is a known way to hide generator fingerprints: never call a grey picture 'authentic'
        rep.update(score=40, verdict="suspicious", confidence=min(rep["confidence"], 0.3), summary=GRAY_NOTE)
    rep["elapsed_ms"] = timer.ms
    return rep if keep_private else fusion.strip_private(rep)


def analyze_video(data: bytes, name: str = "") -> dict:
    from . import video_pipeline

    return fusion.strip_private(video_pipeline.analyze_video(data, name, _base_report("video", name, data)))


def analyze_audio(data: bytes, name: str = "") -> dict:
    from . import audio_pipeline

    return fusion.strip_private(audio_pipeline.analyze_audio(data, name, _base_report("audio", name, data)))
