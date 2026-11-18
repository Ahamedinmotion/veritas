"""Whole-image AI-generation detector (pretrained vision transformer).

The network looks at the whole picture plus a 3x3 grid of overlapping patches; the patch scores become a
'where does it look synthetic' map. Raw probabilities are mapped through a calibration curve learnt on our
calibration split (scripts/evaluate.py) so that 50 means 'on the fence'.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import charts, config
from ..models import REGISTRY
from ..util import jpeg_uri
from .base import calibrated, make_test

NAME = "AI-Generated Image Detector"
EXPLAIN = ("A vision transformer trained on millions of real photos and images from thousands of generators "
           "(GANs, diffusion models, commercial apps) has learnt the tiny statistical fingerprints generators leave "
           "in texture and colour. It outputs a probability; we also scan 9 overlapping patches to see where it reacts.")


def patch_grid(img: Image.Image, n: int = 3) -> list[tuple[tuple[int, int, int, int], Image.Image]]:
    W, H = img.size
    side = int(min(W, H) * 0.6)
    out = []
    for gy in range(n):
        for gx in range(n):
            x0 = int((W - side) * gx / (n - 1))
            y0 = int((H - side) * gy / (n - 1))
            box = (x0, y0, x0 + side, y0 + side)
            out.append((box, img.crop(box)))
    return out


def _font(size: int):
    for p in sorted((config.ASSETS_DIR / "fonts").glob("IBMPlexMono-Medium.ttf")):
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:  # noqa: BLE001
            pass
    return ImageFont.load_default()


def overlay(img: Image.Image, cells: list[tuple[tuple[int, int, int, int], float]], max_side: int = 900) -> str:
    base = img.copy()
    base.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    s = base.width / img.width
    g = np.asarray(base.convert("L"), dtype=np.float32)
    dark = np.stack([g * 0.55] * 3, axis=-1)
    heat = np.zeros_like(dark)
    wsum = np.zeros(dark.shape[:2], dtype=np.float32)
    for (x0, y0, x1, y1), p in cells:
        X0, Y0, X1, Y1 = int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)
        col = np.array(Image.new("RGB", (1, 1), charts.score_color(p)).getpixel((0, 0)), dtype=np.float32)
        heat[Y0:Y1, X0:X1] += col * (0.15 + 0.85 * p / 100)
        wsum[Y0:Y1, X0:X1] += 1
    heat /= np.maximum(wsum, 1)[..., None]
    out = np.clip(dark * 0.75 + heat * 0.55, 0, 255).astype(np.uint8)
    im = Image.fromarray(out)
    d = ImageDraw.Draw(im)
    f = _font(max(12, base.width // 34))
    for (x0, y0, x1, y1), p in cells:
        cx, cy = (x0 + x1) / 2 * s, (y0 + y1) / 2 * s
        txt = f"{p:.0f}"
        d.text((cx, cy), txt, fill=charts.score_color(p), font=f, anchor="mm", stroke_width=3, stroke_fill="#04060a")
    return jpeg_uri(im, max_side, 88)


def run(img: Image.Image) -> dict:
    model = REGISTRY.ai_generated
    if model is None:
        return make_test("ai_generated", NAME, "ai_model", status="error", score=None,
                         finding="AI-image model is not installed on this computer.", explain=EXPLAIN)
    grid = patch_grid(img) if min(img.size) >= 160 else []
    probs = model.predict([img] + [c for _, c in grid])
    p_full = probs[0]
    p_cells = probs[1:]
    # whole image dominates; patches add robustness for crops / large photos
    p = 0.6 * p_full + 0.4 * float(np.mean(p_cells)) if p_cells else p_full
    score = calibrated("ai_generated", p * 100)
    cells_scaled = [(box, calibrated("ai_generated", q * 100)) for (box, _), q in zip(grid, p_cells)]
    visual = overlay(img, cells_scaled) if grid else None
    hot = sum(1 for _, q in cells_scaled if q > config.THRESH_SYNTHETIC)
    if score > config.THRESH_SYNTHETIC:
        finding = (f"Generator fingerprints detected; {hot} of {len(cells_scaled)} patches look synthetic."
                   if cells_scaled else "Generator fingerprints detected in the whole image.")
    elif score >= config.THRESH_SUSPICIOUS:
        finding = "Mixed signal: some patches resemble AI output, others look camera-made."
    else:
        finding = "Texture statistics match real camera photos, not a known generator."
    return make_test("ai_generated", NAME, "ai_model", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                     metrics={"p_fake_full": p_full, "p_fake_patches_mean": float(np.mean(p_cells)) if p_cells else None,
                              "p_fake_patches_max": float(np.max(p_cells)) if p_cells else None,
                              "model": model.repo.split("/")[-1], "raw": p * 100})
