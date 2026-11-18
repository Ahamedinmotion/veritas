"""Error Level Analysis (ELA).

Re-save the image as JPEG at a known quality and look at how much every pixel changes. Regions with the same
compression history change by similar amounts (after allowing for texture - busy areas always change more).
A pasted or retouched region has a different history and stands out as a coherent blob of unusual error.
The score comes from that *regional inconsistency*, not from the raw mean error.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from .. import charts
from ..util import ramp
from .base import calibrated, make_test

NAME = "Error Level Analysis"
EXPLAIN = ("ELA re-saves the picture as a JPEG at a fixed quality and measures how much each pixel changes. "
           "Brighter areas changed more: fine detail and edges always glow, but a region with a different "
           "compression history can glow too. It is a map for human eyes; on its own it rarely proves an edit.")

BLOCK = 16
RESAVE_Q = 90


def _robust_z(x: np.ndarray, mask: np.ndarray, floor: float = 0.12) -> np.ndarray:
    """Robust z-score. The MAD floor stops near-identical blocks (e.g. an already-q90 JPEG) from exploding."""
    v = x[mask]
    med = np.median(v)
    mad = max(np.median(np.abs(v - med)) * 1.4826, floor)
    return (x - med) / mad


def _expected_by_texture(val: np.ndarray, tex: np.ndarray, mask: np.ndarray, bins: int = 12) -> np.ndarray:
    """Median of `val` as a function of texture (binned by texture quantiles) -> expected value per block."""
    t = tex[mask]
    edges = np.unique(np.quantile(t, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return np.full_like(val, np.median(val[mask]))
    centers, meds = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = mask & (tex >= a) & (tex <= b)
        if m.sum() >= 4:
            centers.append(np.median(tex[m]))
            meds.append(np.median(val[m]))
    if len(centers) < 2:
        return np.full_like(val, np.median(val[mask]))
    return np.interp(tex, centers, meds)


def cluster_inconsistency(z: np.ndarray, mask: np.ndarray, thr: float = 2.5) -> tuple[float, float, np.ndarray]:
    """Largest spatially coherent cluster of |z| > thr blocks. Returns (area fraction, mean |z| in it, cluster mask)."""
    hot = ((np.abs(z) > thr) & mask).astype(np.uint8)
    if hot.sum() == 0:
        return 0.0, 0.0, hot
    hot = cv2.morphologyEx(hot, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hot, connectivity=8)
    if n <= 1:
        return 0.0, 0.0, hot
    areas = stats[1:, cv2.CC_STAT_AREA]
    k = int(np.argmax(areas)) + 1
    comp = lab == k
    frac = float(comp.sum() / max(1, mask.sum()))
    return frac, float(np.abs(z[comp & mask]).mean()) if (comp & mask).any() else 0.0, comp


def run(img: Image.Image) -> dict:
    work = img
    if max(work.size) > 3000:
        work = work.copy()
        work.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
    orig = np.asarray(work, dtype=np.float32)
    buf = io.BytesIO()
    work.save(buf, "JPEG", quality=RESAVE_Q)
    resaved = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"), dtype=np.float32)
    diff = np.abs(orig - resaved).max(axis=2)

    H, W = diff.shape
    hb, wb = H // BLOCK, W // BLOCK
    if hb < 4 or wb < 4:
        return make_test("ela", NAME, "compression", status="skipped", score=None,
                         finding="Image too small for error level analysis.", explain=EXPLAIN)
    d = diff[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean(axis=(1, 3))
    gray = cv2.cvtColor(orig.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    tex = lap[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean(axis=(1, 3))
    g = gray[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK)
    bmean = g.mean(axis=(1, 3))
    # ignore clipped / perfectly flat blocks: they cannot carry compression error
    mask = (bmean > 6) & (bmean < 249) & (tex > 0.3)
    if mask.sum() < 16:
        mask = np.ones_like(mask, dtype=bool)
    ld, lt = np.log(d + 0.05), np.log(tex + 0.05)
    resid = ld - _expected_by_texture(ld, lt, mask)
    z = _robust_z(resid, mask)
    frac, zc, comp = cluster_inconsistency(z, mask, thr=3.0)
    # a splice is a COMPACT blob of strongly deviating error: both size and strength must be convincing
    strength = ramp(zc, 3.5, 7.0, 0, 1)
    size = ramp(frac, 0.01, 0.08, 0, 1)
    raw = 10 + 80 * strength * size + 8 * strength
    score = calibrated("ela", raw)

    # visual: amplified error map (sqrt for dynamic range), downsized with area averaging
    vis = np.sqrt(diff)
    if max(H, W) > 900:
        s = 900 / max(H, W)
        vis = cv2.resize(vis, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    visual = charts.heatmap_uri(vis, charts.CMAP_EVIDENCE, vmin=0, vmax=max(1e-3, float(np.percentile(vis, 99.7))))

    if score >= 60:
        finding = "A compact area has unusual error levels - an edit, or just fine detail?"
    elif score >= 35:
        finding = "Some patches show unusual error levels; often texture, sometimes editing."
    else:
        finding = "Error levels look even across the image; no area stands out."
    return make_test("ela", NAME, "compression", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"mean_error": float(diff.mean()), "p99_error": float(np.percentile(diff, 99)),
                              "inconsistent_area_pct": frac * 100, "cluster_z": zc, "resave_quality": RESAVE_Q,
                              "raw": raw})
