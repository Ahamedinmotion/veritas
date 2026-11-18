"""JPEG quantisation-table forensics.

A JPEG stores 8x8 'quantisation tables' that say how coarsely each frequency was rounded. Cameras and phones
use their own tuned tables; editing software, web services and AI tools usually re-save with the standard
libjpeg (IJG) tables scaled to a quality setting. We (1) estimate the quality, (2) check whether the tables are
the standard software ones or a camera-specific set, and (3) look for double-compression traces in the
histogram of DCT coefficients (periodic gaps that appear when a JPEG is decoded and re-saved).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..util import ramp
from .base import calibrated, make_test

NAME = "JPEG Quantisation Tables"
EXPLAIN = ("JPEG compression rounds each 8x8 block's frequency components by amounts listed in quantisation "
           "tables. Phone cameras use their own tables, whereas editors, apps and AI tools re-save with "
           "standard tables; re-saving an already-compressed JPEG also leaves periodic gaps in the DCT histogram.")

STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=np.float64)
STD_CHROMA = np.array([
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99] + [99] * 32, dtype=np.float64)
ZIGZAG = np.array([
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21,
    28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61,
    54, 47, 55, 62, 63])


def ijg_table(base: np.ndarray, q: int) -> np.ndarray:
    q = max(1, min(100, q))
    s = 5000 / q if q < 50 else 200 - 2 * q
    return np.clip(np.floor((base * s + 50) / 100), 1, 255)


def estimate_quality(table: np.ndarray, base: np.ndarray) -> tuple[int, float]:
    """Best IJG quality and the mean absolute mismatch (0 = exactly a standard libjpeg table)."""
    best = (50, 1e9)
    for q in range(1, 101):
        err = float(np.mean(np.abs(ijg_table(base, q) - table)))
        if err < best[1]:
            best = (q, err)
    return best


def _natural(t: list[int]) -> np.ndarray:
    """Pillow returns tables in natural order on recent versions; accept zigzag too by testing both."""
    a = np.asarray(t, dtype=np.float64)
    z = np.empty(64)
    z[ZIGZAG] = a
    return a, z


def double_compression(img: Image.Image, qtable: np.ndarray) -> float:
    """Periodicity of DCT-coefficient histograms (luma, low-frequency AC). ~0 for single compression."""
    import cv2

    y = np.asarray(img.convert("YCbCr"))[..., 0].astype(np.float32) - 128.0
    H, W = y.shape
    H8, W8 = (H // 8) * 8, (W // 8) * 8
    if H8 < 64 or W8 < 64:
        return 0.0
    y = y[:H8, :W8]
    if H8 * W8 > 4_000_000:  # sub-sample block rows for speed on 12 MP photos
        step = int(np.ceil(H8 * W8 / 4_000_000))
        rows = np.arange(0, H8 // 8, step)
        y = np.concatenate([y[r * 8:(r + 1) * 8] for r in rows], axis=0)
        H8 = y.shape[0]
    blocks = y.reshape(H8 // 8, 8, W8 // 8, 8).transpose(0, 2, 1, 3).reshape(-1, 8, 8)
    dct = np.stack([cv2.dct(b) for b in blocks[:60000]])
    rough = []
    for (u, v) in [(0, 1), (1, 0), (1, 1), (0, 2), (2, 0), (1, 2), (2, 1)]:
        qstep = qtable[u * 8 + v]
        if qstep < 2:
            continue
        k = np.round(dct[:, u, v] / qstep).astype(int)
        h = np.bincount(np.abs(k[(k != 0) & (np.abs(k) <= 24)]), minlength=25)[1:].astype(float)
        if h.sum() < 400:
            continue
        lh = np.log(h + 1)
        sec = np.abs(lh[1:-1] - 0.5 * (lh[:-2] + lh[2:]))
        valid = h[1:-1] > 8
        if valid.sum() >= 4:
            rough.append(float(np.median(sec[valid])))
    return float(np.mean(rough)) if rough else 0.0


def run(img_raw: Image.Image, fmt: str) -> dict:
    if fmt.upper() not in ("JPEG", "JPG", "MPO") or not getattr(img_raw, "quantization", None):
        return make_test("jpeg_quant", NAME, "compression", status="skipped", score=None,
                         finding=f"{fmt.upper() or 'This'} file is not a JPEG; no quantisation tables to read.",
                         explain=EXPLAIN)
    qt = img_raw.quantization
    luma = qt.get(0)
    chroma = qt.get(1)
    a, z = _natural(luma)
    qa, ea = estimate_quality(a, STD_LUMA)
    qz, ez = estimate_quality(z, STD_LUMA)
    natural_tbl, (q, err) = (a, (qa, ea)) if ea <= ez else (z, (qz, ez))
    if chroma is not None:
        ca, cz = _natural(chroma)
        cerr = min(estimate_quality(ca, STD_CHROMA)[1], estimate_quality(cz, STD_CHROMA)[1])
    else:
        cerr = 0.0
    standard = err < 0.6 and cerr < 0.6
    try:
        dq = double_compression(img_raw, natural_tbl)
    except Exception:  # noqa: BLE001
        dq = 0.0
    n_tables = len(qt)

    raw = 12.0 if not standard else 26.0
    if standard and q >= 97:
        raw += 6
    raw += ramp(dq, 0.18, 0.6, 0, 34)
    score = calibrated("jpeg_quant", raw)

    kind = "standard software tables" if standard else "camera-specific tables"
    if dq > 0.35:
        finding = f"Quality {q}, {kind}; DCT histogram shows signs of double compression."
    elif standard:
        finding = f"Quality {q} with standard software tables; re-saved by an app or editor."
    else:
        finding = f"Quality about {q} with camera-style custom tables; single compression."
    return make_test("jpeg_quant", NAME, "compression", score=score, finding=finding, explain=EXPLAIN,
                     metrics={"quality_est": q, "table_mismatch": err, "standard_tables": bool(standard),
                              "double_compression_index": dq, "tables": n_tables, "raw": raw})
