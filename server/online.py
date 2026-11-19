"""Online mode (VERITAS_ONLINE=1): the public engine on the Hugging Face Space.

The booth laptop never sets VERITAS_ONLINE, so nothing here changes booth behaviour or any score. Online only:
  * upload limits from the contract (the lab checks the same numbers before uploading):
        image <= 15 MB;  audio <= 20 MB and <= 60 s;  video <= 40 MB and <= 30 s
    (MB = MiB here, so a client that counts 1 MB as 1,000,000 or as 1,048,576 bytes is never refused by the server;
    durations get 0.5 s of slack for container rounding). Too big -> HTTP 413, too long -> HTTP 422, JSON {"error"}.
  * one analysis at a time with a short queue: if the expected wait is too long the request is refused at once with
    HTTP 503 {"error", "busy": true, "retry_after": seconds} instead of hanging.
  * uploads are never persisted: the engine works on in-memory bytes only, and the multipart spool file (an
    anonymous, already-unlinked temp file) is closed straight after reading.
"""
from __future__ import annotations

import io
import os
import threading
import time
from contextlib import contextmanager

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from .util import AnalysisError


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().strip("\"'").strip().lower() in ("1", "true", "yes", "on")


ONLINE = _env_on("VERITAS_ONLINE")

MiB = 1024 * 1024
LIMITS = {   # the contract shared with web/js/lab (client-side checks)
    "image": {"max_mb": 15, "max_seconds": None},
    "audio": {"max_mb": 20, "max_seconds": 60},
    "video": {"max_mb": 40, "max_seconds": 30},
}
DURATION_SLACK_S = 0.5
MULTIPART_OVERHEAD = 256 * 1024          # form boundary + headers around the file part
NOUNS = {"image": "Photos", "audio": "Voice clips", "video": "Videos"}

# queue: refuse at once when the expected wait is longer than MAX_WAIT_S or MAX_WAITING requests already wait
MAX_WAIT_S = float(os.environ.get("VERITAS_ONLINE_MAX_WAIT", "150"))
MAX_WAITING = int(os.environ.get("VERITAS_ONLINE_MAX_QUEUE", "3"))
_TYPICAL_S = {"image": 8.0, "audio": 10.0, "video": 75.0}   # first guesses; replaced by measured averages


def max_bytes(kind: str) -> int:
    return LIMITS[kind]["max_mb"] * MiB


def public_limits() -> dict:
    return {k: {"max_mb": v["max_mb"], "max_bytes": max_bytes(k), "max_seconds": v["max_seconds"]}
            for k, v in LIMITS.items()}


def _too_big_msg(kind: str) -> str:
    return f"{NOUNS[kind]} up to {LIMITS[kind]['max_mb']} MB can be analysed online - this file is larger."


class UploadTooLarge(StarletteHTTPException):
    """An HTTPException, so FastAPI's body parser re-raises it instead of turning it into a 400."""

    def __init__(self, kind: str):
        super().__init__(status_code=413, detail=_too_big_msg(kind))


def _kind_of(path: str) -> str | None:
    p = path.rstrip("/")
    for k in LIMITS:
        if p == f"/api/analyze/{k}":
            return k
    return None


class UploadLimitMiddleware:
    """Pure ASGI: refuse an oversized upload BEFORE its body is read (Content-Length), and stop reading a body
    without Content-Length as soon as it passes the limit - so a huge upload never fills RAM or disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        kind = _kind_of(scope.get("path", ""))
        if kind is None:
            return await self.app(scope, receive, send)
        cap = max_bytes(kind) + MULTIPART_OVERHEAD
        cl = dict(scope.get("headers") or []).get(b"content-length")
        if cl is not None and cl.strip().isdigit() and int(cl) > cap:
            resp = JSONResponse({"error": _too_big_msg(kind), "limit_mb": LIMITS[kind]["max_mb"]}, status_code=413,
                                headers={"Connection": "close"})
            return await resp(scope, receive, send)
        seen = 0

        async def counted_receive():
            nonlocal seen
            msg = await receive()
            if msg.get("type") == "http.request":
                seen += len(msg.get("body", b""))
                if seen > cap:
                    raise UploadTooLarge(kind)
            return msg

        return await self.app(scope, counted_receive, send)


def check_size(kind: str, n: int) -> None:
    if n > max_bytes(kind):
        raise AnalysisError(_too_big_msg(kind), 413)


def probe_duration(data: bytes) -> float | None:
    """Container duration in seconds from the header (no decoding); None if the file does not say (e.g. a
    MediaRecorder WebM). Unknown durations are allowed: the engine itself only analyses the first 20 s of a video
    and 30 s of a voice clip."""
    try:
        import av

        with av.open(io.BytesIO(data)) as c:
            if c.duration:
                return float(c.duration) / 1e6
            for s in c.streams:
                if s.duration and s.time_base:
                    return float(s.duration * s.time_base)
    except Exception:  # noqa: BLE001  (unreadable files get the engine's own clear error later)
        return None
    return None


def check_duration(kind: str, data: bytes) -> None:
    lim = LIMITS[kind]["max_seconds"]
    if not lim:
        return
    d = probe_duration(data)
    if d is not None and d > lim + DURATION_SLACK_S:
        raise AnalysisError(f"{NOUNS[kind]} up to {lim} seconds can be analysed online - this one is {d:.0f} s. "
                            f"Trim it and try again.", 422)


class AnalysisGate:
    """One analysis at a time (shares the app's lock, so the start-up warm-up queues too) with a short queue."""

    def __init__(self, lock: threading.Lock):
        self.lock = lock
        self._mu = threading.Lock()
        self._waiting: list[str] = []
        self._running: tuple[str, float] | None = None
        self._avg = dict(_TYPICAL_S)

    def expected_wait(self) -> float:
        with self._mu:
            w = 0.0
            if self._running:
                k, t0 = self._running
                w += max(2.0, self._avg[k] - (time.monotonic() - t0))
            elif self.lock.locked():
                w += self._avg["video"] / 2   # warm-up in progress
            w += sum(self._avg[k] for k in self._waiting)
            return w

    def status(self) -> dict:
        with self._mu:
            return {"busy": self.lock.locked(), "waiting": len(self._waiting)}

    def _busy(self, wait: float) -> AnalysisError:
        retry = int(min(300, max(10, wait)))
        e = AnalysisError(f"The online engine is busy with other visitors (about {retry} s queue). Try again in a "
                          f"minute - or open an Evidence-locker exhibit, whose saved report opens instantly.", 503)
        e.busy, e.retry_after = True, retry
        return e

    @contextmanager
    def slot(self, kind: str):
        wait = self.expected_wait()
        with self._mu:
            n_wait = len(self._waiting)
        if self.lock.locked() and (n_wait >= MAX_WAITING or wait > MAX_WAIT_S):
            raise self._busy(wait)
        with self._mu:
            self._waiting.append(kind)
        try:
            got = self.lock.acquire(timeout=MAX_WAIT_S)
        finally:
            with self._mu:
                self._waiting.remove(kind)
        if not got:
            raise self._busy(self.expected_wait())
        t0 = time.monotonic()
        with self._mu:
            self._running = (kind, t0)
        try:
            yield
        finally:
            dt = time.monotonic() - t0
            with self._mu:
                self._running = None
                self._avg[kind] = 0.7 * self._avg[kind] + 0.3 * dt
            self.lock.release()
