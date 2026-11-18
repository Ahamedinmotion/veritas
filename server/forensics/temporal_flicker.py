"""Temporal flicker: does the face's brightness/colour flicker independently of the rest of the scene?

In a real video, lighting changes hit the face and the background together. A swapped or generated face is
rendered frame by frame, so its brightness and skin tone pulse slightly on their own. We compare the fast
(frame-to-frame) luminance and chroma changes inside the face with those of the background.
"""
from __future__ import annotations

import numpy as np

from .. import charts
from ..util import ramp
from .base import calibrated, make_test

NAME = "Temporal Flicker"
EXPLAIN = ("We record the average brightness and colour of the face and of the background in every frame, "
           "remove slow changes, and compare the fast flicker. Real lighting affects both together; a face "
           "synthesised frame by frame flickers on its own, giving a high face-to-background flicker ratio.")


def _detrend(x: np.ndarray, k: int = 9) -> np.ndarray:
    """Subtract a centred moving average (removes slow lighting / motion changes)."""
    pad = np.pad(x, (k // 2, k // 2), mode="edge")
    ma = np.convolve(pad, np.ones(k) / k, mode="valid")
    return x - ma


def _fill(x: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    if ok.sum() < 2:
        return x
    idx = np.arange(len(x))
    return np.interp(idx, idx[ok], x[ok])


def run(track: dict) -> dict:
    fy, by, fc, bc, t = track["face_y"], track["bg_y"], track["face_c"], track["bg_c"], track["t"]
    ok = np.isfinite(fy) & np.isfinite(by)
    if ok.sum() < 12:
        return make_test("temporal_flicker", NAME, "temporal", status="skipped", score=None,
                         finding="Face not visible long enough to measure flicker.", explain=EXPLAIN)
    sl = slice(int(np.argmax(ok)), len(ok) - int(np.argmax(ok[::-1])))
    fy, by, fc, bc, t = _fill(fy[sl]), _fill(by[sl]), _fill(fc[sl]), _fill(bc[sl]), t[sl]
    dfy, dby = _detrend(fy), _detrend(by)
    dfc, dbc = _detrend(fc), _detrend(bc)
    f_flick = float(np.std(np.diff(dfy)))
    b_flick = float(np.std(np.diff(dby)))
    fc_flick = float(np.std(np.diff(dfc)))
    bc_flick = float(np.std(np.diff(dbc)))
    floor = 0.35  # ~ quantisation / sensor noise level of a mean over thousands of pixels
    ratio_y = f_flick / (b_flick + floor)
    ratio_c = fc_flick / (bc_flick + floor)
    corr = float(np.corrcoef(dfy, dby)[0, 1]) if np.std(dfy) > 1e-6 and np.std(dby) > 1e-6 else 0.0
    ratio = max(ratio_y, ratio_c * 0.8)
    raw = 12 + ramp(ratio, 1.6, 4.0, 0, 62) + ramp(f_flick, 1.0, 3.0, 0, 14) - ramp(corr, 0.4, 0.8, 0, 8)
    score = calibrated("temporal_flicker", raw)
    visual = charts.line_chart(t, [
        {"y": dby, "color": charts.FAINT, "label": "background", "width": 1.3},
        {"y": dfy, "color": charts.EVID if score > 50 else charts.AUTH, "label": "face", "width": 1.7},
    ], xlabel="time (s)", ylabel="fast luminance change")
    if score > 65:
        finding = f"Face brightness flickers {ratio:.1f}x more than the background."
    elif score >= 35:
        finding = f"Face flickers somewhat more than the scene ({ratio:.1f}x)."
    else:
        finding = f"Face and background light change together ({ratio:.1f}x ratio) - natural."
    return make_test("temporal_flicker", NAME, "temporal", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"flicker_ratio_luma": ratio_y, "flicker_ratio_chroma": ratio_c, "face_flicker": f_flick,
                              "background_flicker": b_flick, "face_bg_correlation": corr, "raw": raw})
