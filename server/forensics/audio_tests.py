"""Classic acoustic forensics: spectral cut-off, prosody (pitch), breaths & silence, spectrogram, waveform."""
from __future__ import annotations

import numpy as np

from .. import charts
from ..util import ramp
from .base import calibrated, make_test

# ------------------------------------------------------------------------------------- speech gate
MIN_SPEECH_S = 1.0   # less active speech than this and no voice test can say anything


def speech_activity(wav16: np.ndarray) -> dict:
    """Seconds of active sound that rises clearly above the clip's own background (20 ms frames).
    Silence, a steady tone or constant noise have no frames above their own floor, so they count as no speech."""
    import librosa

    hop, win = 320, 640
    if len(wav16) < win:
        return {"speech_s": 0.0, "active_frac": 0.0}
    rms = librosa.feature.rms(y=wav16, frame_length=win, hop_length=hop, center=True)[0]
    db = 20 * np.log10(rms + 1e-10)
    floor, peak = float(np.percentile(db, 10)), float(np.percentile(db, 99))
    act = (db > floor + 12) & (db > -50) & (db > peak - 35)
    return {"speech_s": float(act.sum() * hop / 16000), "active_frac": float(act.mean()), "floor_db": floor, "peak_db": peak}


# ------------------------------------------------------------------------------------ spectral cut-off
CUT_NAME = "Spectral Cut-off"
CUT_EXPLAIN = ("Microphones record up to about 20 kHz, but many voice generators work at 16-24 kHz sample rates, "
               "so above 8-12 kHz their output can be an empty 'brick wall'. The chart shows where the long-term "
               "spectrum falls off. Phone calls, codecs and cheap mics cut off too, so in our experiment it did not "
               "separate real from fake: it is shown as evidence for your eyes, not scored.")


def spectral_cutoff(wav: np.ndarray, sr: int) -> dict:
    import scipy.signal as ss

    nyq = sr / 2
    if sr < 22000:
        return make_test("spectral_cutoff", CUT_NAME, "acoustic", status="skipped", score=None,
                         finding=f"Recorded at {sr / 1000:g} kHz - too low to see above {nyq / 1000:g} kHz.",
                         explain=CUT_EXPLAIN, metrics={"sample_rate": sr})
    f, P = ss.welch(wav, sr, nperseg=4096, noverlap=2048)
    db = 10 * np.log10(P + 1e-14)
    speech = (f > 300) & (f < 3000)
    ref = np.percentile(db[speech], 90)
    rel = db - ref
    # cut-off = highest frequency where the smoothed spectrum is still within 60 dB of the speech band
    sm = np.convolve(rel, np.ones(9) / 9, mode="same")
    above = np.where(sm > -60)[0]
    cutoff = float(f[above[-1]]) if len(above) else 4000.0
    # steepness of the edge: drop over the 1 kHz above the cut-off
    j = np.searchsorted(f, cutoff)
    j2 = np.searchsorted(f, min(nyq - 1, cutoff + 1000))
    steep = float(sm[j] - sm[min(j2, len(sm) - 1)]) if j2 > j else 0.0
    e_tot = P[f > 100].sum()
    hf_ratio = float(P[f > 8000].sum() / (e_tot + 1e-20))
    hf_db = 10 * np.log10(hf_ratio + 1e-12)
    headroom = nyq - cutoff
    raw = 15.0
    if headroom > 2500:
        # the spectrum stops well short of what the file could hold
        raw += ramp(cutoff, 15500, 8500, 0, 55) + ramp(steep, 12, 35, 0, 20)
    raw -= ramp(hf_db, -35, -22, 0, 10)
    keep = f <= nyq
    visual = charts.line_chart(f[keep] / 1000, [{"y": rel[keep], "color": charts.SCAN, "label": "long-term spectrum", "fill": True}],
                               xlabel="frequency (kHz)", ylabel="dB re speech", ylim=(-100, 8), legend=False,
                               vspans=[(cutoff / 1000, nyq / 1000, charts.EVID, 0.10)] if headroom > 1500 else [],
                               hlines=[(-60, charts.FAINT, "-60 dB")])
    if headroom > 2500 and steep > 12:
        finding = f"Energy stops sharply at {cutoff / 1000:.1f} kHz (shown, not scored)."
    elif headroom > 2500:
        finding = f"Spectrum fades out near {cutoff / 1000:.1f} kHz (shown, not scored)."
    else:
        finding = f"Energy reaches {cutoff / 1000:.1f} kHz, near the file's limit (shown, not scored)."
    return make_test("spectral_cutoff", CUT_NAME, "acoustic", score=None, finding=finding, explain=CUT_EXPLAIN,
                     visual=visual, metrics={"cutoff_hz": cutoff, "edge_steepness_db": steep, "energy_above_8k_db": hf_db,
                                             "sample_rate": sr, "raw": raw})


# ------------------------------------------------------------------------------------------- prosody
PROS_NAME = "Prosody & Pitch"
PROS_EXPLAIN = ("Pitch (F0) is how fast the vocal folds vibrate. We track it every 20 ms with the pYIN algorithm and "
                "plot its range and smoothness: flat, robotic intonation gave away older text-to-speech. Modern "
                "voice generators copy natural intonation, so in our experiment pitch did not separate real from "
                "fake; it is shown, not scored.")


def prosody(wav16: np.ndarray) -> dict:
    import librosa

    y = wav16[: 16000 * 30]
    f0, vflag, vprob = librosa.pyin(y, fmin=65, fmax=420, sr=16000, frame_length=1024, hop_length=320, fill_na=np.nan,
                                    max_transition_rate=40, n_thresholds=50)
    t = np.arange(len(f0)) * 320 / 16000
    v = np.isfinite(f0)
    if v.sum() < 25:
        return make_test("prosody", PROS_NAME, "acoustic", status="skipped", score=None,
                         finding="Too little voiced speech to measure pitch.", explain=PROS_EXPLAIN)
    semis = 12 * np.log2(f0[v] / np.nanmedian(f0))
    pitch_sd = float(np.std(semis))
    voiced_frac = float(v.mean())
    visual = charts.line_chart(t, [{"y": np.where(v, f0, np.nan), "color": charts.SCAN, "label": "F0", "width": 2.0}],
                               xlabel="time (s)", ylabel="pitch (Hz)", legend=False,
                               ylim=(max(50, np.nanmin(f0) * 0.85), np.nanmax(f0) * 1.12))
    if pitch_sd < 1.2:
        finding = f"Very flat pitch ({pitch_sd:.1f} semitone spread); shown, not scored."
    else:
        finding = f"Pitch spread {pitch_sd:.1f} semitones around {np.nanmedian(f0):.0f} Hz; shown, not scored."
    return make_test("prosody", PROS_NAME, "acoustic", score=None, finding=finding, explain=PROS_EXPLAIN, visual=visual,
                     metrics={"f0_median_hz": float(np.nanmedian(f0)), "pitch_sd_semitones": pitch_sd,
                              "voiced_fraction": voiced_frac})


# ----------------------------------------------------------------------------------- breath & silence
BR_NAME = "Breaths & Silence"
BR_EXPLAIN = ("Unprocessed microphone recordings rarely contain true digital silence: between words there is room "
              "noise, and speakers take audible breaths. Many synthetic voices stitch words together over perfect "
              "zeros or a suspiciously clean noise floor, with no breaths. But call and voice-note apps often gate "
              "pauses to silence, so this is weak evidence (AUC 0.53 in our test). We map energy every 20 ms to find "
              "pauses, breaths and the noise floor.")


def breath_silence(wav16: np.ndarray, peak: float) -> dict:
    import librosa

    y = wav16
    hop, win = 320, 640
    rms = librosa.feature.rms(y=y, frame_length=win, hop_length=hop, center=True)[0]
    db = 20 * np.log10(rms + 1e-10)
    flat = librosa.feature.spectral_flatness(y=y, n_fft=win, hop_length=hop)[0][: len(db)]
    t = np.arange(len(db)) * hop / 16000
    speech_level = float(np.percentile(db, 90))
    floor = float(np.percentile(db, 5))
    pause = db < speech_level - 28
    # pauses >= 150 ms
    runs, i = [], 0
    while i < len(pause):
        if pause[i]:
            j = i
            while j + 1 < len(pause) and pause[j + 1]:
                j += 1
            if (j - i + 1) * hop / 16000 >= 0.15:
                runs.append((i, j))
            i = j + 1
        else:
            i += 1
    # digital silence = exact zeros / below -90 dBFS for >= 40 ms
    zero = np.abs(y) < 1e-5
    zrun = 0
    max_zero = 0
    for z in zero[::16]:
        zrun = zrun + 1 if z else 0
        max_zero = max(max_zero, zrun)
    max_zero_ms = max_zero * 16 / 16
    digital_frac = float((db < -90).mean())
    # breaths: noisy (high flatness), quiet but not silent segments 120-700 ms just before speech
    breathy = (db > floor + 6) & (db < speech_level - 14) & (flat > 0.05)
    breaths, i = 0, 0
    while i < len(breathy):
        if breathy[i]:
            j = i
            while j + 1 < len(breathy) and breathy[j + 1]:
                j += 1
            dur = (j - i + 1) * hop / 16000
            if 0.12 <= dur <= 0.7:
                breaths += 1
            i = j + 1
        else:
            i += 1
    dur_s = len(y) / 16000
    raw = 15.0
    raw += ramp(max_zero_ms, 30, 200, 0, 40)            # stretches of perfect digital zeros
    raw += ramp(floor, -75, -95, 0, 25)                 # unnaturally clean noise floor
    if len(runs) >= 2 and breaths == 0 and dur_s > 6:
        raw += 12                                       # pauses but never a breath
    raw -= ramp(breaths / max(dur_s, 1) * 60, 2, 8, 0, 10)
    score = calibrated("breath_silence", raw)
    spans = [(t[a], t[b] + hop / 16000, charts.FAINT, 0.18) for a, b in runs]
    visual = charts.line_chart(t, [{"y": db, "color": charts.SCAN, "label": "energy", "width": 1.1}],
                               xlabel="time (s)", ylabel="level (dBFS)", legend=False, vspans=spans,
                               hlines=[(floor, charts.EVID, "noise floor")], ylim=(max(-110, floor - 12), max(db.max() + 4, -10)))
    if score > 65:
        finding = "Pauses drop to digital silence and no breaths are heard."
    elif score >= 35:
        finding = f"Very clean pauses (floor {floor:.0f} dB); few or no breaths detected."
    else:
        finding = f"Natural room noise in pauses ({floor:.0f} dB) and {breaths} breath-like sounds."
    return make_test("breath_silence", BR_NAME, "acoustic", score=score, finding=finding, explain=BR_EXPLAIN, visual=visual,
                     metrics={"pauses": len(runs), "breaths": breaths, "noise_floor_db": floor,
                              "longest_digital_silence_ms": max_zero_ms, "digital_silence_frac": digital_frac, "raw": raw})


# ------------------------------------------------------------------------------------- spectrogram
SPEC_NAME = "Spectrogram"
SPEC_EXPLAIN = ("A spectrogram shows which frequencies are present at each moment: time runs left to right, pitch "
                "bottom to top (on the mel scale, which stretches low frequencies like our ears do), brightness is "
                "loudness. Harmonics appear as stacked bands, consonants as bursts of noise. It is a picture, not a score.")


def spectrogram(wav: np.ndarray, sr: int, cutoff_hz: float | None) -> dict:
    import librosa

    sr_use = min(sr, 32000)
    y = wav if sr == sr_use else librosa.resample(wav, orig_sr=sr, target_sr=sr_use, res_type="soxr_hq")
    hop = 256 if len(y) < sr_use * 12 else 512
    S = librosa.feature.melspectrogram(y=y, sr=sr_use, n_fft=2048, hop_length=hop, n_mels=128, fmax=sr_use / 2)
    S_db = librosa.power_to_db(S, ref=np.max)
    visual = charts.spectrogram_figure(S_db, sr_use, hop, sr_use / 2, mel=True, cutoff_hz=None)
    return make_test("spectrogram", SPEC_NAME, "acoustic", score=None, status="ok",
                     finding="Visual map of frequencies over time (not scored).", explain=SPEC_EXPLAIN, visual=visual,
                     metrics={"display_sr": sr_use, "mel_bands": 128})


def waveform_peaks(wav: np.ndarray, n: int = 600) -> list[float]:
    if len(wav) == 0:
        return []
    k = int(np.ceil(len(wav) / n))
    pad = np.pad(np.abs(wav), (0, k * n - len(wav)))
    peaks = pad.reshape(n, k).max(axis=1)
    m = peaks.max() or 1.0
    return [round(float(v / m), 3) for v in peaks]
