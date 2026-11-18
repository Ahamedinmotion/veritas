"""Audio analysis: neural voice detector + classic acoustic forensics."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from . import fusion
from .audio_io import load_audio
from .forensics import ai_voice, audio_tests as at
from .forensics.base import make_test, safe_run
from .util import Timer

log = logging.getLogger("veritas.audio")
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="acoustic")


def analyze_audio(data: bytes, name: str, rep: dict) -> dict:
    timer = Timer()
    a = load_audio(data, name)
    timer.mark("decode")
    wav, sr, wav16 = a["wav"], a["sr"], a["wav16"]
    rep["file"].update(format=a["format"], duration=round(a["duration_total"], 2))
    vad = at.speech_activity(wav16)
    if vad["speech_s"] < at.MIN_SPEECH_S:
        return _no_speech(rep, a, vad, timer)
    futs = {
        "spectral_cutoff": _pool.submit(safe_run, at.spectral_cutoff, "spectral_cutoff", at.CUT_NAME, "acoustic",
                                        at.CUT_EXPLAIN, wav, sr),
        "prosody": _pool.submit(safe_run, at.prosody, "prosody", at.PROS_NAME, "acoustic", at.PROS_EXPLAIN, wav16),
        "breath_silence": _pool.submit(safe_run, at.breath_silence, "breath_silence", at.BR_NAME, "acoustic",
                                       at.BR_EXPLAIN, wav16, a["peak"]),
    }
    tests = {"ai_voice": safe_run(ai_voice.run, "ai_voice", ai_voice.NAME, "ai_model", ai_voice.EXPLAIN, wav16)}
    timer.mark("model")
    for k, f in futs.items():
        tests[k] = f.result()
    cut = tests["spectral_cutoff"].get("metrics", {}).get("cutoff_hz")
    tests["spectrogram"] = safe_run(at.spectrogram, "spectrogram", at.SPEC_NAME, "acoustic", at.SPEC_EXPLAIN, wav, sr, cut)
    rep["tests"] = [tests[k] for k in ("ai_voice", "spectral_cutoff", "prosody", "breath_silence", "spectrogram")]
    rep["waveform"] = at.waveform_peaks(wav)
    rep["metadata"] = {"exif": {"sample_rate": f"{sr} Hz", "analysed_seconds": f"{a['duration']:.1f}",
                                "format": a["format"]},
                       "flags": [f"Sample rate {sr / 1000:g} kHz"] + (["Only the first 30 s analysed"] if a["duration_total"] > a["duration"] + 0.5 else [])}
    rep.update(fusion.fuse("audio", rep["tests"]))
    rep["elapsed_ms"] = timer.ms
    rep["timing_ms"] = timer.marks
    return rep


def _no_speech(rep: dict, a: dict, vad: dict, timer: Timer) -> dict:
    """Silence, a tone, noise or a clip shorter than a word: no voice test can judge it, so say so plainly."""
    wav, sr = a["wav"], a["sr"]
    note = f"Only {vad['speech_s']:.1f} s of speech found; at least {at.MIN_SPEECH_S:g} s is needed."
    tests = {
        "ai_voice": make_test("ai_voice", ai_voice.NAME, "ai_model", status="skipped", finding=note,
                              explain=ai_voice.EXPLAIN, metrics={"speech_seconds": vad["speech_s"]}),
        "spectral_cutoff": safe_run(at.spectral_cutoff, "spectral_cutoff", at.CUT_NAME, "acoustic", at.CUT_EXPLAIN, wav, sr),
        "prosody": make_test("prosody", at.PROS_NAME, "acoustic", status="skipped", finding=note, explain=at.PROS_EXPLAIN),
        "breath_silence": make_test("breath_silence", at.BR_NAME, "acoustic", status="skipped", finding=note,
                                    explain=at.BR_EXPLAIN),
    }
    cut = tests["spectral_cutoff"].get("metrics", {}).get("cutoff_hz")
    tests["spectrogram"] = safe_run(at.spectrogram, "spectrogram", at.SPEC_NAME, "acoustic", at.SPEC_EXPLAIN, wav, sr, cut)
    rep["tests"] = [tests[k] for k in ("ai_voice", "spectral_cutoff", "prosody", "breath_silence", "spectrogram")]
    for t in rep["tests"]:
        t["weight"] = 0.0
    rep["waveform"] = at.waveform_peaks(wav)
    rep["metadata"] = {"exif": {"sample_rate": f"{sr} Hz", "analysed_seconds": f"{a['duration']:.1f}",
                                "speech_seconds": f"{vad['speech_s']:.1f}", "format": a["format"]},
                       "flags": [f"Sample rate {sr / 1000:g} kHz", "Not enough speech to judge"]}
    rep.update(score=50, verdict="suspicious", confidence=0.05,
               summary="Not enough clear speech to judge this recording - try a longer clip of someone talking.")
    rep["elapsed_ms"] = timer.ms
    rep["timing_ms"] = timer.marks
    return rep
