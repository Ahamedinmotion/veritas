"""Blink-rate test using the Eye Aspect Ratio (EAR).

EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|)  - eye height over eye width from six eye landmarks.
It stays roughly constant while the eye is open and dips sharply during a blink. People blink about 15-20
times a minute at rest; early deepfakes rarely blinked because their training photos almost never showed closed eyes.
Modern deepfakes blink normally: in our video test this score sat at its floor (15) on every research clip.
We turn the count into a probability with a Poisson model of normal blinking.
"""
from __future__ import annotations

import math

import numpy as np

from .. import charts
from ..util import ramp
from .base import calibrated, make_test

NAME = "Blink Rate (Eye Aspect Ratio)"
EXPLAIN = ("The Eye Aspect Ratio divides the eye's height by its width using six landmarks; it drops sharply "
           "when the eyelid closes. Humans blink about 15-20 times a minute at rest, fewer when reading or "
           "concentrating, and modern deepfakes blink normally, so very few blinks is weak evidence and a normal "
           "rate proves nothing.")

HUMAN_RATE = 17.0  # mean resting rate (Bentivoglio 1997); ~26/min while talking, ~4.5/min while reading


def poisson_cdf(k: int, lam: float) -> float:
    return float(sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(0, k + 1)))


def detect_blinks(t: np.ndarray, e: np.ndarray, fps: float) -> tuple[list[tuple[float, float]], float]:
    """Adaptive threshold: a blink is a dip below 72% of the open-eye EAR lasting <= 0.6 s."""
    ok = ~np.isnan(e)
    if ok.sum() < 5:
        return [], float("nan")
    base = float(np.nanpercentile(e, 75))
    thr = base * 0.72
    closed = ok & (e < thr)
    blinks = []
    i, n = 0, len(e)
    while i < n:
        if closed[i]:
            j = i
            while j + 1 < n and (closed[j + 1] or (np.isnan(e[j + 1]) and j + 2 < n and closed[j + 2])):
                j += 1
            dur = t[j] - t[i] + 1.0 / fps
            # must re-open afterwards (or end of clip) and be short
            if dur <= 0.6:
                blinks.append((float(t[i]), float(np.nanmin(e[i:j + 1]))))
            i = j + 1
        else:
            i += 1
    return blinks, thr


def run(track: dict, fps: float) -> dict:
    t, e = track["t"], track["ear"]
    present = ~np.isnan(e)
    face_time = present.sum() / max(fps, 1e-6)
    if face_time < 5.0:
        return make_test("blink", NAME, "biometric", status="skipped", score=None,
                         finding="Not enough clear face time to count blinks.", explain=EXPLAIN,
                         metrics={"face_seconds": face_time})
    # light smoothing (3-tap median) to suppress landmark noise
    es = e.copy()
    for i in range(1, len(e) - 1):
        w = e[i - 1:i + 2]
        if not np.isnan(w).any():
            es[i] = np.median(w)
    blinks, thr = detect_blinks(t, es, fps)
    k = len(blinks)
    rate = k / face_time * 60.0
    lam = HUMAN_RATE / 60.0 * face_time
    p_low = poisson_cdf(k, lam)                       # chance a real person blinks this little
    s_low = ramp(-math.log10(max(p_low, 1e-9)), 0.7, 2.6, 0, 70)
    s_high = ramp(rate, 45, 80, 0, 45) if face_time >= 10 else 0.0   # flutter / implausibly frequent dips
    raw = 15 + max(s_low, s_high)
    if face_time < 8:                                 # short clips carry little evidence
        raw = 50 + (raw - 50) * (face_time / 8.0)
    score = calibrated("blink", raw)
    bs = track.get("blink_bs")
    bs_blinks = int(np.sum((bs[1:] > 0.5) & (bs[:-1] <= 0.5))) if bs is not None and np.isfinite(bs).any() else None

    x = t
    visual = charts.line_chart(
        x, [{"y": np.where(np.isnan(es), np.nan, es), "color": charts.SCAN, "label": "eye aspect ratio", "width": 1.7}],
        xlabel="time (s)", ylabel="EAR", hlines=[(thr, charts.EVID, "blink threshold")] if np.isfinite(thr) else [],
        markers=[(bt, bv, charts.AUTH) for bt, bv in blinks], legend=False,
        ylim=(max(0.0, min(thr if np.isfinite(thr) else np.inf, float(np.nanmin(es))) - 0.03), np.nanmax(es) + 0.03))
    if score > 65:
        finding = f"Only {k} blink{'s' if k != 1 else ''} in {face_time:.0f} s ({rate:.0f}/min); humans average ~17/min."
    elif rate > 45:
        finding = f"{rate:.0f} blinks/min - unusually frequent eye-closure flicker."
    elif score >= 35:
        finding = f"{k} blinks in {face_time:.0f} s ({rate:.0f}/min): a little low, short clip."
    else:
        finding = f"{k} blinks in {face_time:.0f} s ({rate:.0f}/min) - a natural human rate."
    return make_test("blink", NAME, "biometric", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"blinks": k, "blinks_per_min": rate, "face_seconds": face_time,
                              "p_this_few_if_human": p_low, "ear_open": float(np.nanpercentile(e, 75)),
                              "ear_threshold": thr, "blendshape_blinks": bs_blinks, "raw": raw})
