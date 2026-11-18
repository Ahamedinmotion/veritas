"""Audio decoding without system ffmpeg: soundfile (wav/flac/ogg-vorbis/aiff) first, PyAV (mp3/m4a/aac/opus/webm/
video soundtracks) as fallback. Returns mono float32 at the native rate AND resampled to 16 kHz for the model."""
from __future__ import annotations

import io

import numpy as np

from . import config
from .util import AnalysisError


def _decode_soundfile(data: bytes, max_s: float):
    """Decode only the first max_s (+1) seconds: a 2-hour FLAC must not be expanded into RAM."""
    import soundfile as sf

    with sf.SoundFile(io.BytesIO(data)) as f:
        sr, total, fmt = int(f.samplerate), (f.frames / f.samplerate if f.frames else 0.0), f.format
        wav = f.read(frames=int((max_s + 1.0) * sr), dtype="float32", always_2d=True)
    return wav.mean(axis=1), sr, total or len(wav) / sr, fmt


def _decode_av(data: bytes, max_s: float):
    import av

    try:
        container = av.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise AnalysisError("Could not read this file as audio (supported: WAV, MP3, M4A, OGG, WebM, FLAC).") from e
    with container:
        streams = [s for s in container.streams if s.type == "audio"]
        if not streams:
            raise AnalysisError("This file has no audio track.")
        st = streams[0]
        sr = int(st.rate or st.codec_context.sample_rate or 16000)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sr)
        chunks, n = [], 0
        total = float(container.duration / 1e6) if container.duration else None
        for frame in container.decode(st):
            for f in resampler.resample(frame):
                a = f.to_ndarray().reshape(-1)
                chunks.append(a)
                n += len(a)
            if n >= (max_s + 0.5) * sr:
                break
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
        fmt = (container.format.name or "audio").split(",")[0].upper()
    if not chunks:
        raise AnalysisError("No audio samples could be decoded.")
    wav = np.concatenate(chunks).astype(np.float32)
    return wav, sr, total if total else len(wav) / sr, fmt


def load_audio(data: bytes, name: str = "", max_s: float = config.AUDIO_MAX_SECONDS) -> dict:
    try:
        wav, sr, total, fmt = _decode_soundfile(data, max_s)
    except Exception:  # noqa: BLE001
        wav, sr, total, fmt = _decode_av(data, max_s)
    if wav.size == 0 or not np.isfinite(wav).all():
        raise AnalysisError("Audio is empty or corrupt.")
    wav = wav[: int(max_s * sr)]
    if len(wav) < 0.5 * sr:
        raise AnalysisError("Audio is too short to analyse (need at least half a second).")
    peak = float(np.abs(wav).max())
    if sr != 16000:
        import soxr

        wav16 = soxr.resample(wav, sr, 16000).astype(np.float32)
    else:
        wav16 = wav.astype(np.float32)
    return {"wav": wav.astype(np.float32), "sr": sr, "wav16": wav16, "duration_total": float(total),
            "duration": len(wav) / sr, "format": fmt, "peak": peak}
