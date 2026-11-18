"""Landmark jitter: frame-to-frame instability of facial landmarks after removing head motion.

Real faces move smoothly - bone does not wobble. Face-swap and talking-head generators synthesise each frame
semi-independently, so the facial geometry 'boils': eye corners, brows and nose shift by a few pixels from
frame to frame even when the head is still. We align each frame's landmarks to the previous frame with a
similarity transform (removing head motion), then measure the leftover acceleration, normalised by the
distance between the eyes so that face size does not matter.
"""
from __future__ import annotations

import cv2
import numpy as np

from .. import charts
from ..util import ramp
from .base import calibrated, make_test
from .face_track import STABLE

NAME = "Landmark Jitter"
EXPLAIN = ("We track 478 facial landmarks about 12 times a second, cancel out normal head movement with a similarity "
           "transform, and measure how much the remaining points shake. Bone does not wobble, so strong jitter "
           "points to frame-by-frame synthesis - while zero movement means a still photo is being animated.")


def run(track: dict) -> dict:
    pts, iod, t = track["pts"], track["iod"], track["t"]
    idx = [i for i in range(len(pts)) if pts[i] is not None]
    if len(idx) < 8:
        return make_test("landmark_jitter", NAME, "temporal", status="skipped", score=None,
                         finding="Face not visible long enough to measure landmark stability.", explain=EXPLAIN)
    jit_t, jit_v = [], []
    for a, b, c in zip(idx, idx[1:], idx[2:]):
        if c - a != 2:  # need three consecutive frames
            continue
        P0, P1, P2 = pts[a][STABLE], pts[b][STABLE], pts[c][STABLE]
        # align previous and next frames onto the middle one (removes rotation, scale, translation)
        M0, _ = cv2.estimateAffinePartial2D(P0, P1)
        M2, _ = cv2.estimateAffinePartial2D(P2, P1)
        if M0 is None or M2 is None:
            continue
        A0 = P0 @ M0[:, :2].T + M0[:, 2]
        A2 = P2 @ M2[:, :2].T + M2[:, 2]
        acc = np.linalg.norm(A0 + A2 - 2 * P1, axis=1)  # second difference = non-rigid 'shake'
        d = iod[b]
        if not np.isfinite(d) or d < 8:
            continue
        jit_t.append(t[b])
        jit_v.append(float(np.median(acc) / d * 100))  # % of inter-ocular distance
    if len(jit_v) < 5:
        return make_test("landmark_jitter", NAME, "temporal", status="skipped", score=None,
                         finding="Too few consecutive face frames to measure jitter.", explain=EXPLAIN)
    jv = np.array(jit_v)
    med = float(np.median(jv))
    p90 = float(np.percentile(jv, 90))
    face_px = float(np.nanmedian(iod))
    # small faces -> landmark noise dominates; soften the evidence
    # too much shake = frame-by-frame synthesis; essentially ZERO shake = a frozen photograph being moved around
    frozen = ramp(med, 0.15, 0.06, 0, 62)
    raw = 12 + max(ramp(med, 0.9, 2.6, 0, 68) + ramp(p90, 2.5, 6.0, 0, 15), frozen)
    if face_px < 40:
        raw = 50 + (raw - 50) * 0.5
    score = calibrated("landmark_jitter", raw)
    visual = charts.line_chart(np.array(jit_t), [{"y": jv, "color": charts.EVID if score > 50 else charts.SCAN,
                                                  "label": "non-rigid jitter", "fill": True}],
                               xlabel="time (s)", ylabel="% eye distance",
                               hlines=[(1.8, charts.FAINT, "typical limit")], legend=False, ylim=(0, max(4.0, p90 * 1.3)))
    if score > 65 and frozen > 30:
        finding = f"Face geometry is frozen ({med:.2f}% movement) - like a moving photograph."
    elif score > 65:
        finding = f"Facial geometry shakes {med:.1f}% of eye distance per frame - unnatural."
    elif score >= 35:
        finding = f"Moderate landmark wobble ({med:.1f}%); could be compression or synthesis."
    else:
        finding = f"Landmarks move smoothly ({med:.1f}% jitter), like real bone structure."
    return make_test("landmark_jitter", NAME, "temporal", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"jitter_median_pct": med, "jitter_p90_pct": p90, "eye_distance_px": face_px,
                              "frames": len(jv), "raw": raw})
