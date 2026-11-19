"""VERITAS server - serves the web app (web/) and the forensic API.

Run from the veritas/ folder:
    uv run uvicorn server.app:app --port 8000
"""
from __future__ import annotations

import logging
import mimetypes
import os
import threading
import time
from contextlib import asynccontextmanager

from . import config  # noqa: F401  (sets HF offline env vars before anything imports transformers)

from fastapi import FastAPI, File, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from . import online  # noqa: E402
from .models import REGISTRY  # noqa: E402
from .util import AnalysisError  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-5s  %(name)-18s %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "urllib3", "matplotlib", "PIL", "transformers", "absl"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("veritas")

_analysis_lock = threading.Lock()  # one analysis at a time: predictable RAM on an 8 GB laptop
_gate = online.AnalysisGate(_analysis_lock) if online.ONLINE else None   # online: same lock + a short queue


def _warm_media() -> None:
    """First voice / video analysis after a fresh install pays one-time costs (numba JIT for the pitch tracker,
    matplotlib font cache, codec start-up): 10-30 s on a slow laptop. Pay them now, not on the first visitor.
    Video runs in the background while holding the analysis lock, so an early visitor simply queues behind it."""
    from .pipeline import analyze_audio, analyze_video

    lab = config.WEB_DIR / "samples" / "lab"
    voice, video = lab / "synthetic-voice.wav", lab / "synthetic-video.mp4"
    try:
        if voice.exists():
            t0 = time.perf_counter()
            analyze_audio(voice.read_bytes(), "warmup.wav")
            log.info("voice warm-up done in %.1f s", time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001
        log.warning("voice warm-up failed: %s", e)

    def _video():
        with _analysis_lock:
            try:
                t0 = time.perf_counter()
                analyze_video(video.read_bytes(), "warmup.mp4")
                log.info("video warm-up done in %.1f s", time.perf_counter() - t0)
            except Exception as e:  # noqa: BLE001
                log.warning("video warm-up failed: %s", e)

    if video.exists():
        threading.Thread(target=_video, name="video-warmup", daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("VERITAS %s starting - loading models from %s (threads=%d)", config.VERSION, config.MODELS_DIR,
             config.torch_threads())
    if online.ONLINE:
        log.info("ONLINE mode: upload limits %s, one analysis at a time, face-swap mode %s, %d video frames",
                 {k: v["max_mb"] for k, v in online.LIMITS.items()}, config.faceswap_mode(),
                 config.video_sampled_frames())
    REGISTRY.load()
    REGISTRY.warmup()
    try:  # run one complete tiny analysis so fonts, charts and codecs are loaded before the first visitor
        import io

        import numpy as np
        from PIL import Image

        from .pipeline import analyze_image

        buf = io.BytesIO()
        Image.fromarray((np.random.default_rng(1).random((256, 256, 3)) * 255).astype(np.uint8)).save(buf, "JPEG")
        analyze_image(buf.getvalue(), "warmup.jpg")
    except Exception as e:  # noqa: BLE001
        log.warning("pipeline warm-up failed: %s", e)
    if os.environ.get("VERITAS_SKIP_WARMUP") != "1":
        _warm_media()
    h = REGISTRY.health()
    missing = [k for k, v in h.items() if not v]
    if missing:
        log.warning("NOT AVAILABLE: %s  -> run scripts/download_models.py (with internet) and restart", ", ".join(missing))
    log.info("models loaded - starting the web server on http://127.0.0.1:%s/", os.environ.get("VERITAS_PORT", "8000"))
    yield


app = FastAPI(title="VERITAS Deepfake Forensics Lab", version=config.VERSION, lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
if online.ONLINE:   # added BEFORE CORS = runs inside it, so even an early 413 carries the CORS headers
    app.add_middleware(online.UploadLimitMiddleware)
# Permissive CORS (any origin, no credentials) so the lab hosted elsewhere (ChatGPT site, GitHub Pages) can call the
# online engine on the Hugging Face Space. Nothing is cookie- or login-protected, so this exposes nothing extra.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Retry-After"], max_age=600)


# ------------------------------------------------------------------------------------------ errors
@app.exception_handler(AnalysisError)
async def _analysis_error(_: Request, exc: AnalysisError):
    body, headers = {"error": str(exc)}, {}
    if getattr(exc, "busy", False):
        body.update(busy=True, retry_after=exc.retry_after)
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(body, status_code=exc.status, headers=headers)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Upload a file in the multipart form field named 'file'."}, status_code=400)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else "Request failed."
    if exc.status_code == 404:
        msg = f"Not found: {request.url.path}"
    elif exc.status_code == 405:
        msg = "Method not allowed (use POST with a multipart 'file' field)."
    return JSONResponse({"error": msg}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse({"error": "Internal error while analysing this file. Try another file."}, status_code=500)


# --------------------------------------------------------------------------------------------- API
@app.get("/api/health")
def health():
    h = REGISTRY.health()
    out = {"ok": REGISTRY.loaded, "version": config.VERSION,
           "models": {"face_deepfake": h["face_deepfake"], "ai_generated": h["ai_generated"],
                      "audio_deepfake": h["audio_deepfake"], "face_swap": h["face_swap"]},
           "device": "cpu",
           "detail": {"face_detector": h["face_detector"], "face_landmarker": h["face_landmarker"],
                      "errors": REGISTRY.errors,
                      "model_names": {**{k: getattr(getattr(REGISTRY, k), "repo", None)
                                         for k in ("face_deepfake", "ai_generated", "audio_deepfake")},
                                      "face_swap": FACESWAP_NAMES.get(getattr(REGISTRY.face_swap, "mode", None))}}}
    if online.ONLINE:   # the booth's health answer is unchanged
        out["online"] = {"limits": online.public_limits(), "faceswap_mode": config.faceswap_mode(),
                         "video_frames": config.video_sampled_frames(), **_gate.status()}
    return out


FACESWAP_NAMES = {"fp32": "GenD CLIP ViT-L/14 + DFDC-B7", "int8": "GenD CLIP ViT-L/14 (int8) + DFDC-B7",
                  "b7": "DFDC-B7"}


async def _read_upload(request: Request, file: UploadFile, kind: str = "") -> tuple[bytes, str]:
    try:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > config.MAX_UPLOAD_BYTES + 1_000_000:
            raise AnalysisError("File too large - the limit is 200 MB.", 413)
        chunks, total = [], 0
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > config.MAX_UPLOAD_BYTES:
                raise AnalysisError("File too large - the limit is 200 MB.", 413)
            if online.ONLINE and kind:
                online.check_size(kind, total)
            chunks.append(chunk)
    finally:
        await file.close()   # the multipart spool (an anonymous temp file) is released now, not at end of request
    data = b"".join(chunks)
    if not data:
        raise AnalysisError("The uploaded file is empty.")
    if online.ONLINE and kind:
        online.check_duration(kind, data)
    return data, os.path.basename(file.filename or "upload")


def _run(kind: str, fn, data: bytes, name: str) -> dict:
    t0 = time.perf_counter()
    if _gate is not None:   # online: one at a time, refuse at once if the queue is too long
        with _gate.slot(kind):
            rep = fn(data, name)
    else:
        if not _analysis_lock.acquire(timeout=120):
            raise AnalysisError("The lab is busy with another analysis - try again in a moment.", 503)
        try:
            rep = fn(data, name)
        finally:
            _analysis_lock.release()
    log.info("%-5s %-28s %7.1f kB  -> %-10s %3d  (conf %.2f)  %5d ms", kind,
             "(upload)" if online.ONLINE else name[:28], len(data) / 1024,
             rep["verdict"], rep["score"], rep["confidence"], (time.perf_counter() - t0) * 1000)
    return rep


@app.post("/api/analyze/image")
async def analyze_image(request: Request, file: UploadFile = File(...)):
    from starlette.concurrency import run_in_threadpool

    from .pipeline import analyze_image as fn

    data, name = await _read_upload(request, file, "image")
    return await run_in_threadpool(_run, "image", fn, data, name)


@app.post("/api/analyze/video")
async def analyze_video(request: Request, file: UploadFile = File(...)):
    from starlette.concurrency import run_in_threadpool

    from .pipeline import analyze_video as fn

    data, name = await _read_upload(request, file, "video")
    return await run_in_threadpool(_run, "video", fn, data, name)


@app.post("/api/analyze/audio")
async def analyze_audio(request: Request, file: UploadFile = File(...)):
    from starlette.concurrency import run_in_threadpool

    from .pipeline import analyze_audio as fn

    data, name = await _read_upload(request, file, "audio")
    return await run_in_threadpool(_run, "audio", fn, data, name)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def api_404(request: Request, rest: str):
    if rest.rstrip("/") in ("analyze/image", "analyze/video", "analyze/audio"):
        return JSONResponse({"error": "Use POST with a multipart form field named 'file'."}, status_code=405)
    return JSONResponse({"error": f"Unknown API endpoint: /api/{rest}"}, status_code=404)


# ----------------------------------------------------------------------------------- static web app
# Windows reads MIME types from the registry (HKCR\.js "Content Type"), which is often text/plain on school laptops;
# Chrome/Edge then refuse every ES module and both pages stay blank. Pin the types the web app needs.
for _ext, _typ in {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html",
                   ".json": "application/json", ".wasm": "application/wasm", ".svg": "image/svg+xml",
                   ".woff2": "font/woff2", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
                   ".flac": "audio/flac", ".wav": "audio/wav", ".mp4": "video/mp4",
                   ".task": "application/octet-stream"}.items():
    mimetypes.add_type(_typ, _ext)
app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
