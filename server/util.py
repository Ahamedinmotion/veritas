"""Small shared helpers: errors, data-URIs, case ids, image I/O."""
from __future__ import annotations

import base64
import hashlib
import io
import itertools
import logging
import random
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageOps

from . import config

log = logging.getLogger("veritas")

Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
MIN_IMAGE_SIDE = 128

try:  # iPhone photos (HEIC/HEIF); optional so the engine still starts if the wheel is missing
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # noqa: BLE001
    log.info("pillow-heif not available: HEIC uploads will be refused")


class AnalysisError(Exception):
    """Raised for bad input; becomes an HTTP 4xx with {"error": message}."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_case_counter = itertools.count(random.randint(1, 400))


def case_id() -> str:
    return f"VX-{datetime.now():%Y%m%d}-{next(_case_counter) % 10000:04d}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_uri(img: Image.Image | np.ndarray) -> str:
    if isinstance(img, np.ndarray):
        img = Image.fromarray(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def jpeg_uri(img: Image.Image | np.ndarray, max_side: int = 960, quality: int = 84) -> str:
    if isinstance(img, np.ndarray):
        img = Image.fromarray(img)
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def open_image(data: bytes) -> Image.Image:
    """Decode an uploaded image, refusing anything that is not a real raster image."""
    try:
        img = Image.open(io.BytesIO(data))
        # Pillow only raises DecompressionBombError at 2x MAX_IMAGE_PIXELS, so check the header size ourselves
        if img.width * img.height > config.MAX_IMAGE_PIXELS:
            raise Image.DecompressionBombError("too many pixels")
        img.load()
    except Image.DecompressionBombError as e:
        raise AnalysisError("Image is too large to analyse (over 60 megapixels).", 413) from e
    except Exception as e:  # noqa: BLE001
        raise AnalysisError("Could not read this file as an image (supported: JPEG, PNG, WebP, HEIC, BMP, GIF, TIFF).") from e
    if min(img.width, img.height) < MIN_IMAGE_SIDE:
        raise AnalysisError(f"Image is too small to analyse (the shorter side must be at least {MIN_IMAGE_SIDE} pixels).")
    return img


def to_rgb(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation, bring 16-bit / float images down to 8 bits, flatten alpha onto neutral grey."""
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001
        pass
    if img.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        # convert('RGB') would clip 16-bit values to white; rescale to 0-255 first
        a = np.asarray(img, dtype=np.float64)
        hi = 65535.0 if (img.mode.startswith("I;16") or a.max() > 255) else 255.0
        if img.mode == "F" and a.max() <= 1.0:
            hi = 1.0
        img = Image.fromarray(np.clip(a / hi * 255.0 + 0.5, 0, 255).astype(np.uint8), "L")
    if img.mode in ("RGBA", "LA", "P", "PA") or (img.mode == "L" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (128, 128, 128))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def is_grayscale(img: Image.Image, tol: float = 2.0) -> bool:
    """True when the three colour channels are (almost) identical - a black-and-white picture."""
    small = img.copy()
    small.thumbnail((256, 256))
    a = np.asarray(small, dtype=np.int16)
    return bool(np.abs(a[..., 0] - a[..., 1]).mean() < tol and np.abs(a[..., 1] - a[..., 2]).mean() < tol)


def detail_level(img: Image.Image) -> float:
    """Standard deviation of brightness on a 512 px copy; ~0 for a blank / single-colour picture."""
    small = img.copy()
    small.thumbnail((512, 512))
    return float(np.asarray(small.convert("L"), dtype=np.float32).std())


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def ramp(x: float, x0: float, x1: float, y0: float = 0.0, y1: float = 100.0) -> float:
    """Linear map x in [x0, x1] -> [y0, y1], clamped."""
    if x1 == x0:
        return y1 if x >= x1 else y0
    t = (x - x0) / (x1 - x0)
    t = max(0.0, min(1.0, t))
    return float(y0 + t * (y1 - y0))


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.marks: dict[str, float] = {}

    def mark(self, name: str):
        self.marks[name] = round((time.perf_counter() - self.t0) * 1000)

    @property
    def ms(self) -> int:
        return int(round((time.perf_counter() - self.t0) * 1000))


def r(x, nd=3):
    """Round for JSON metrics; handles numpy scalars and None."""
    if x is None:
        return None
    try:
        xf = float(x)
    except Exception:  # noqa: BLE001
        return x
    if not np.isfinite(xf):
        return None
    return round(xf, nd)
