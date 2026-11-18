"""Frequency-domain analysis (2-D FFT).

Natural photos have a smooth power spectrum that falls off roughly as 1/f^2 with frequency. Neural generators
build images by repeatedly up-sampling small feature maps; that leaves faint periodic "checkerboard" patterns
that appear as isolated bright peaks in the spectrum, and often an unnatural excess or deficit of the highest
frequencies. We look for both.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .. import charts
from ..util import ramp
from .base import calibrated, feature_score, make_test

NAME = "Frequency Spectrum (FFT)"
EXPLAIN = ("The Fourier transform splits an image into waves of different spatial frequency. Camera photos keep "
           "fine detail and sensor grain right up to the highest frequencies, while generators tend to be too "
           "smooth there; their up-sampling layers can also leave periodic grid peaks in the spectrum.")

TILE = 256


def _azimuthal(power: np.ndarray, nbins: int = 96):
    h, w = power.shape
    yy, xx = np.indices((h, w))
    rr = np.hypot((yy - h / 2) / h, (xx - w / 2) / w)  # cycles / pixel, 0 .. ~0.707
    bins = np.linspace(0, 0.5, nbins + 1)
    idx = np.digitize(rr.ravel(), bins) - 1
    v = power.ravel()
    ok = (idx >= 0) & (idx < nbins)
    sums = np.bincount(idx[ok], weights=v[ok], minlength=nbins)
    cnt = np.bincount(idx[ok], minlength=nbins)
    prof = sums / np.maximum(cnt, 1)
    return (bins[:-1] + bins[1:]) / 2, prof


def run(img: Image.Image) -> dict:
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    H, W = gray.shape
    if min(H, W) < 128:
        return make_test("fft", NAME, "frequency", status="skipped", score=None,
                         finding="Image too small for spectral analysis.", explain=EXPLAIN)
    # ---- display spectrum: centred square crop with a Hann window
    side = int(min(1024, 2 ** int(np.log2(min(H, W)))))
    y0, x0 = (H - side) // 2, (W - side) // 2
    crop = gray[y0:y0 + side, x0:x0 + side]
    win = np.outer(np.hanning(side), np.hanning(side)).astype(np.float32)
    F = np.fft.fftshift(np.fft.fft2((crop - crop.mean()) * win))
    logmag = np.log1p(np.abs(F))
    freqs, prof = _azimuthal(np.abs(F) ** 2)
    lp = np.log10(prof + 1e-9)
    # power-law fit on mid frequencies
    fit_m = (freqs > 0.03) & (freqs < 0.25)
    coef = np.polyfit(np.log10(freqs[fit_m]), lp[fit_m], 1)
    fit = np.polyval(coef, np.log10(np.maximum(freqs, 1e-3)))
    hi = freqs > 0.3
    hf_excess = float(np.mean(lp[hi] - fit[hi]))     # >0: more high-freq energy than a 1/f trend predicts
    slope = float(coef[0])

    # ---- periodic artefacts: average power spectrum of high-pass residual tiles (Welch-style)
    resid = gray - cv2.GaussianBlur(gray, (0, 0), 1.2)
    tiles = []
    for ty in range(0, H - TILE + 1, TILE):
        for tx in range(0, W - TILE + 1, TILE):
            tiles.append(resid[ty:ty + TILE, tx:tx + TILE])
    if len(tiles) > 24:
        sel = np.linspace(0, len(tiles) - 1, 24).round().astype(int)
        tiles = [tiles[i] for i in sel]
    if not tiles:
        tiles = [cv2.resize(resid, (TILE, TILE), interpolation=cv2.INTER_AREA)]
    w2 = np.outer(np.hanning(TILE), np.hanning(TILE)).astype(np.float32)
    P = np.mean([np.abs(np.fft.fftshift(np.fft.fft2((t - t.mean()) * w2))) ** 2 for t in tiles], axis=0)
    lP = np.log(P + 1e-6)
    bg = cv2.medianBlur(lP.astype(np.float32), 5)
    ex = lP - bg  # log-ratio over local background
    c = TILE // 2
    yy, xx = np.indices(P.shape)
    rad = np.hypot(yy - c, xx - c) / TILE
    # off-axis periodic peaks on the k/8 grid (2-D checkerboards). Axis lines (u=0 or v=0) are excluded
    # because JPEG block edges and image borders put energy there in every photo.
    peaks = []
    for ky in range(-4, 5):
        for kx in range(-4, 5):
            if ky == 0 or kx == 0:
                continue
            py, px = c + ky * TILE // 8, c + kx * TILE // 8
            py, px = int(np.clip(py, 1, TILE - 2)), int(np.clip(px, 1, TILE - 2))
            v = float(ex[py - 1:py + 2, px - 1:px + 2].max())
            peaks.append((v, py, px))
    peaks.sort(reverse=True)
    grid_peak = float(np.mean([p[0] for p in peaks[:4]]))
    # generic isolated peaks anywhere outside the low-frequency core and the axes
    m = (rad > 0.12) & (np.abs(yy - c) > 2) & (np.abs(xx - c) > 2)
    iso_peak = float(np.percentile(ex[m], 99.9))

    # (a) strong periodic peaks = up-sampling checkerboard (GANs); far above anything JPEG produces
    periodic = 6 + ramp(grid_peak, 2.2, 4.0, 0, 80)
    # (b) missing fine detail: camera photos carry sharp micro-texture and grain up to the highest frequencies;
    #     generated images fall off too smoothly. Logistic model fitted on the calibration split.
    feats = {"grid_peak": grid_peak, "isolated_peak": iso_peak, "hf_excess": hf_excess}
    smooth = feature_score("fft", feats)
    if smooth is None:
        smooth = 10 + ramp(iso_peak, 1.3, 0.9, 0, 45) + ramp(-hf_excess, 0.2, 0.6, 0, 25)
    # the statistical model alone is weak evidence (camera JPEGs with gentle compression look 'smooth' to it);
    # it may only call the image clearly synthetic when the measured curve really falls below the 1/f trend
    if hf_excess > -0.4:
        smooth = min(smooth, 55.0)
    raw = max(periodic, smooth)
    score = calibrated("fft", raw)

    # map the strongest tile peaks into the display spectrum coordinates for circling
    circ = [(c + (py - c) * side / TILE, c + (px - c) * side / TILE) for v, py, px in peaks[:6] if v > 1.2]
    circ = [(y + side / 2 - c, x + side / 2 - c) for y, x in circ]
    disp = logmag
    if side > 512:
        disp = cv2.resize(disp, (512, 512), interpolation=cv2.INTER_AREA)
        circ = [(y * 512 / side, x * 512 / side) for y, x in circ]
    visual = charts.spectrum_figure(disp, freqs, lp, fit, circ)

    if score >= 60 and periodic >= smooth:
        finding = "Periodic grid peaks in the spectrum, typical of AI up-sampling."
    elif score >= 60:
        finding = "Fine detail falls below the natural 1/f trend: unusually smooth."
    elif score >= 35:
        finding = "Spectrum close to the natural trend; its statistics lean slightly AI-like."
    else:
        finding = "Natural spectrum with camera-like fine detail; no grid artefacts."
    t = make_test("fft", NAME, "frequency", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"grid_peak": grid_peak, "isolated_peak": iso_peak, "hf_excess": hf_excess,
                              "spectral_slope": slope, "crop_px": side, "periodic_score": periodic,
                              "smoothness_score": smooth, "raw": raw})
    t["_amplify"] = bool(periodic >= smooth and periodic > 65)   # a periodic grid is specific; smoothness is not
    return t
