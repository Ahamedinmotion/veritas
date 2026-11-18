"""Sensor-noise consistency.

Every camera sensor adds a faint, fairly uniform grain whose strength depends mostly on brightness.
We isolate it (noise residual = image - denoised image, via the finest wavelet band), estimate the local noise
level in 32 px blocks, remove the expected brightness dependence, and look for regions whose grain is
inconsistent with the rest - the fingerprint of splicing, cloning, local blurring or synthetic patches.
"""
from __future__ import annotations

import cv2
import numpy as np
import pywt
from PIL import Image

from .. import charts
from ..util import ramp
from .base import calibrated, feature_score, make_test
from .ela import _expected_by_texture, _robust_z, cluster_inconsistency

NAME = "Noise Residual Consistency"
EXPLAIN = ("A real camera sensor leaves a fine, even grain over the whole picture. Subtracting a denoised copy "
           "isolates that grain; we measure its strength block by block. Generated images often have too little "
           "grain - but so do phone photos after noise reduction, webcams and video stills, so that is weak evidence.")


def run(img: Image.Image) -> dict:
    work = img
    if max(work.size) > 2048:
        work = work.copy()
        work.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    gray = cv2.cvtColor(np.asarray(work), cv2.COLOR_RGB2GRAY).astype(np.float32)
    H, W = gray.shape
    # finest diagonal wavelet sub-band = mostly noise (Donoho's estimator)
    _, (_, _, hh) = pywt.dwt2(gray, "db2")
    B = 16  # 16 coefficients = 32 image pixels
    hb, wb = hh.shape[0] // B, hh.shape[1] // B
    if hb < 4 or wb < 4:
        return make_test("noise", NAME, "noise", status="skipped", score=None,
                         finding="Image too small to map sensor noise.", explain=EXPLAIN)
    blocks = np.abs(hh[: hb * B, : wb * B]).reshape(hb, B, wb, B)
    sigma = np.median(blocks, axis=(1, 3)) / 0.6745
    g2 = cv2.resize(gray, (wb, hb), interpolation=cv2.INTER_AREA)
    # local texture: high texture inflates the estimate, so condition on it as well as brightness
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    tex = cv2.resize(lap, (wb, hb), interpolation=cv2.INTER_AREA)
    mask = (g2 > 12) & (g2 < 243)
    if mask.sum() < 12:
        mask = np.ones_like(mask, dtype=bool)
    ls = np.log(sigma + 0.05)
    exp_b = _expected_by_texture(ls, g2, mask, bins=8)
    r1 = ls - exp_b
    exp_t = _expected_by_texture(r1, np.log(tex + 0.05), mask, bins=8)
    resid = r1 - exp_t
    z = _robust_z(resid, mask)
    frac, zc, comp = cluster_inconsistency(z, mask, thr=3.0)
    global_sigma = float(np.median(sigma[mask]))
    spread = float(np.std(resid[mask]))

    # (a) splice evidence: a compact region whose grain disagrees strongly with the rest
    splice = 8 + 80 * ramp(zc, 3.5, 7.0, 0, 1) * ramp(frac, 0.015, 0.10, 0, 1)
    # (b) missing camera grain: generators do not simulate a sensor, so their noise is weak and uneven.
    #     A 2-feature logistic model fitted on the calibration split (scripts/evaluate.py) turns the
    #     measured noise level and its unevenness into a probability.
    feats = {"log_sigma": float(np.log(global_sigma + 1e-3)), "spread": spread}
    clean = feature_score("noise", feats)
    if clean is None:
        clean = 10 + ramp(-feats["log_sigma"], np.log(1 / 0.9), np.log(1 / 0.3), 0, 45) + ramp(spread, 0.35, 0.8, 0, 25)
    raw = max(splice, clean)
    score = calibrated("noise", raw)

    vis = cv2.resize(np.log(sigma + 0.05), (min(900, W), int(min(900, W) * H / W)), interpolation=cv2.INTER_CUBIC)
    visual = charts.heatmap_uri(vis, charts.CMAP_SCAN)

    if score >= 60 and splice >= clean:
        finding = "One region's sensor grain doesn't match the rest of the photo."
    elif score >= 60:
        finding = "Very little sensor grain: AI-like, but phone denoising does this too."
    elif score >= 35:
        finding = "Weak or uneven grain; phones, apps and generators all smooth it."
    else:
        finding = "Camera-like sensor grain, consistent across the whole image."
    t = make_test("noise", NAME, "noise", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"noise_sigma": global_sigma, "residual_spread": spread,
                              "inconsistent_area_pct": frac * 100, "cluster_z": zc, "splice_score": splice,
                              "missing_grain_score": clean, "raw": raw})
    # only a localised grain mismatch is specific enough to be amplified in the fusion
    t["_amplify"] = bool(splice >= clean and splice > 65)
    return t
