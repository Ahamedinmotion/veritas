"""Video decoding with PyAV (bundled FFmpeg libraries - no system ffmpeg needed, works on Windows).

One pass over the first <= 20 s produces:
  * dense frames (~12 fps, <= 480 px) for the landmark-based tests (blink, jitter, flicker)
  * sampled frames (<= 48, <= 1280 px) for the neural detectors, timeline and keyframes
"""
from __future__ import annotations

import io

import numpy as np

from . import config
from .util import AnalysisError


def _rotation(frame, stream) -> int:
    rot = 0
    try:
        rot = int(getattr(frame, "rotation", 0) or 0)
    except Exception:  # noqa: BLE001
        rot = 0
    if not rot:
        try:
            rot = int(stream.metadata.get("rotate", 0))
        except Exception:  # noqa: BLE001
            rot = 0
    return rot % 360


def _to_rgb(frame, max_side: int, rot: int) -> np.ndarray:
    w, h = frame.width, frame.height
    s = min(1.0, max_side / max(w, h))
    tw, th = max(2, int(w * s) // 2 * 2), max(2, int(h * s) // 2 * 2)
    a = frame.to_ndarray(format="rgb24", width=tw, height=th)
    if rot in (90, -270):
        a = np.rot90(a, k=1)
    elif rot in (270, -90):
        a = np.rot90(a, k=3)
    elif rot in (180, -180):
        a = np.rot90(a, k=2)
    return np.ascontiguousarray(a)


def _format_name(container, tags: dict, name: str) -> str:
    """'mov,mp4,m4a,3gp,3g2,mj2' / 'matroska,webm' -> a name people recognise (MP4, MOV, WEBM, MKV ...)."""
    names = (container.format.name or "video").lower().split(",")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if "mp4" in names or "mov" in names:
        brand = str(tags.get("major_brand", "")).strip().lower()
        if brand == "qt" or (not brand and ext == "mov"):
            return "MOV"
        return "M4V" if ext == "m4v" else "MP4"
    if "webm" in names or "matroska" in names:
        return "WEBM" if ext == "webm" or str(tags.get("DOCTYPE", tags.get("doctype", ""))).lower() == "webm" else "MKV"
    return names[0].upper()


def read_video(data: bytes, max_s: float = config.VIDEO_MAX_SECONDS, dense_fps: float = config.VIDEO_DENSE_FPS,
               max_sampled: int | None = None, sample_side: int = 1280, dense_side: int = 480, name: str = "") -> dict:
    import av

    if max_sampled is None:
        max_sampled = config.video_sampled_frames()
    try:
        container = av.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise AnalysisError("Could not read this file as a video (supported: MP4, MOV, WebM, MKV, AVI).") from e
    with container:
        vs = [s for s in container.streams if s.type == "video"]
        if not vs:
            raise AnalysisError("This file has no video track.")
        st = vs[0]
        st.thread_type = "AUTO"
        fps = float(st.average_rate) if st.average_rate else 25.0
        total = None
        if st.duration and st.time_base:
            total = float(st.duration * st.time_base)
        elif container.duration:
            total = float(container.duration / 1e6)
        analysed = min(max_s, total) if total else max_s
        n_samp = int(min(max_sampled, max(8, round(analysed * 2.4))))
        samp_times = list(np.linspace(0.15, max(0.2, analysed - 0.15), n_samp))
        tags = {k: str(v)[:120] for k, v in (container.metadata or {}).items()}
        tags.update({f"video.{k}": str(v)[:120] for k, v in (st.metadata or {}).items()})
        codec = st.codec_context.name if st.codec_context else "?"
        fmt = _format_name(container, tags, name)
        dense, sampled = [], []
        next_dense, si = 0.0, 0
        t0 = None
        n_decoded = 0
        ow = oh = None
        try:
            for frame in container.decode(st):
                if frame.time is None:
                    t = n_decoded / fps
                else:
                    if t0 is None:
                        t0 = frame.time
                    t = frame.time - t0
                n_decoded += 1
                if t > analysed + 0.05:
                    break
                rot = _rotation(frame, st)
                if n_decoded == 1:
                    ow, oh = (frame.height, frame.width) if rot in (90, 270) else (frame.width, frame.height)
                if t + 1e-6 >= next_dense:
                    dense.append((t, _to_rgb(frame, dense_side, rot)))
                    next_dense += 1.0 / dense_fps
                    while next_dense <= t:
                        next_dense += 1.0 / dense_fps
                if si < len(samp_times) and t + 0.5 / fps >= samp_times[si]:
                    sampled.append((t, _to_rgb(frame, sample_side, rot)))
                    while si < len(samp_times) and samp_times[si] <= t + 0.5 / fps:
                        si += 1
        except av.error.InvalidDataError:
            pass  # truncated tail - keep what decoded
        except Exception as e:  # noqa: BLE001
            if not dense:
                raise AnalysisError("The video stream could not be decoded.") from e
    if not dense:
        raise AnalysisError("No frames could be decoded from this video.")
    if len(dense) < 6 or dense[-1][0] < 0.5:
        raise AnalysisError("Video is too short to analyse - it needs at least one second of footage.")
    if total is None:
        total = dense[-1][0] + 1.0 / fps
    h, w = (sampled or dense)[0][1].shape[:2]
    if ow and oh:
        w, h = ow, oh
    return {"dense": dense, "sampled": sampled or dense[:: max(1, len(dense) // 24)], "fps": fps,
            "duration": float(total), "analysed": float(min(analysed, dense[-1][0] + 1.0 / dense_fps)),
            "width": int(w), "height": int(h), "format": fmt, "codec": codec, "tags": tags}
