"""Shared helpers for compare_models.py and evaluate.py: dataset listing, the calibration/test split,
and the 'laundering' transform (identical JPEG re-encode so file format can't give the answer away)."""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / "eval_data"
CALIB_FRACTION = 0.4

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
AUD_EXT = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".webm", ".aiff"}
VID_EXT = {".mp4", ".webm", ".mov", ".mkv", ".ogv", ".avi"}


def load_items(kind: str) -> list[dict]:
    src = json.loads((EVAL / "sources.json").read_text()) if (EVAL / "sources.json").exists() else {}
    exts = {"images": IMG_EXT, "audio": AUD_EXT, "video": VID_EXT}[kind]
    items = []
    for lab in ("real", "fake"):
        d = EVAL / kind / lab
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in exts:
                continue
            meta = src.get(str(p.relative_to(EVAL)), {})
            items.append({
                "path": p, "name": p.name, "y": 1 if lab == "fake" else 0,
                "group": meta.get("group", "unknown"), "generator": meta.get("generator", ""),
                "source": meta.get("source", ""), "licence": meta.get("licence", ""), "speaker": meta.get("speaker"),
            })
    assign_split(items)
    return items


def split_key(it: dict) -> str:
    """Files that share a person, a voice or a prompt must land on the SAME side of the split, otherwise the
    held-out test would partly measure 'have I seen this speaker / this prompt before'."""
    n = it["name"].rsplit(".", 1)[0]
    if it.get("speaker"):
        return f"spk:{it['speaker']}"
    if n.startswith("unidata_"):                       # unidata_UK_female_1_original / _synthetic_2
        return "spk:" + "_".join(n.split("_")[1:4])
    if n.startswith("tts_mms_vits"):
        return "spk:mms_vits"                          # one MMS voice for all clips
    if n.startswith("diff_"):                          # diff_<model>_<prompt id>_<k>
        return "prompt:" + n.split("_")[-2]
    return "file:" + n


def _union_groups(items: list[dict]) -> dict[str, str]:
    """Union-find: a face-swap shares a group with its real target photo and its GAN donor face."""
    parent: dict[str, str] = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    names = {it["name"].rsplit(".", 1)[0]: split_key(it) for it in items}
    for k in names.values():
        find(k)
    for n, k in names.items():
        if n.startswith("swap_") and "__" in n:
            target, donor = n[5:].split("__", 1)
            for other in (target, donor):
                if other in names:
                    union(k, names[other])
    return {n: find(k) for n, k in names.items()}


def assign_split(items: list[dict]):
    """Deterministic GROUP-aware split: every group (speaker, prompt, face-swap + its source photos) goes wholly to
    the CALIBRATION side (~40%) or the HELD-OUT side (~60%). Group sides are decided by md5(salt + group); the salt
    is the first one (searched deterministically) that keeps every (label, category) bucket close to 40%."""
    groups = _union_groups(items)
    for it in items:
        it["split_group"] = groups[it["name"].rsplit(".", 1)[0]]
    buckets: dict[tuple, list] = {}
    for it in items:
        buckets.setdefault((it["y"], it["group"]), []).append(it)
    gkeys = sorted({it["split_group"] for it in items})

    def side(salt: int) -> dict[str, bool]:
        return {g: int(hashlib.md5(f"{salt}:{g}".encode()).hexdigest(), 16) / 16 ** 32 < CALIB_FRACTION for g in gkeys}

    best = None
    for salt in range(300):
        sd = side(salt)
        dev = max((abs(sum(sd[it["split_group"]] for it in lst) / len(lst) - CALIB_FRACTION)
                   for lst in buckets.values() if len(lst) >= 4), default=0.0)
        if best is None or dev < best[0] - 1e-9:
            best = (dev, salt, sd)
    _, salt, sd = best
    for it in items:
        it["split"] = "calib" if sd[it["split_group"]] else "test"


def launder(data: bytes, quality: int = 90, max_side: int | None = None) -> bytes:
    """Re-encode as baseline JPEG with no metadata (what a messaging app does)."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max_side and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, subsampling=2)
    return buf.getvalue()


def roc_auc(y, s) -> float:
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    ok = ~np.isnan(s)
    y, s = y[ok], s[ok]
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    # Mann-Whitney U with ties
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv))
    ranks[order] = np.arange(1, len(allv) + 1)
    for v in np.unique(allv):
        m = allv == v
        ranks[m] = ranks[m].mean()
    rp = ranks[: len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def roc_points(y, s, max_points: int = 50) -> list[list[float]]:
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    thr = np.unique(np.concatenate([[np.inf], np.sort(s)[::-1], [-np.inf]]))[::-1]
    P, N = max(1, (y == 1).sum()), max(1, (y == 0).sum())
    pts = []
    for t in thr:
        pred = s >= t
        pts.append([float((pred & (y == 0)).sum() / N), float((pred & (y == 1)).sum() / P)])
    pts = sorted({(round(a, 4), round(b, 4)) for a, b in pts})
    if len(pts) > max_points:
        idx = np.linspace(0, len(pts) - 1, max_points).round().astype(int)
        pts = [pts[i] for i in sorted(set(idx))]
    return [list(p) for p in pts]


# ---------------------------------------------------------------------------- real-world degradations
# How REAL photos actually reach the booth. Used (a) on the calibration split, so the calibration curves learn
# that a smoothed webcam frame of a real person is still real, and (b) on the held-out split as robustness checks.
def _fit(im: Image.Image, side: int) -> Image.Image:
    im = im.copy()
    im.thumbnail((side, side), Image.Resampling.LANCZOS)
    return im


def _jpg(im: Image.Image, q: int) -> bytes:
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q, subsampling=2)
    return b.getvalue()


def degrade(data: bytes, kind: str, seed: int = 0) -> bytes:
    import cv2
    from PIL import ImageFilter

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if kind == "webcam":      # soft optics + sensor noise + in-camera denoise/sharpen, 720p, browser JPEG 0.92
        rng = np.random.default_rng(seed)
        im = _fit(im, 1280).filter(ImageFilter.GaussianBlur(1.1))
        a = np.asarray(im).astype(np.float32) + rng.normal(0, 3.0, (im.height, im.width, 1))
        a = cv2.bilateralFilter(np.clip(a, 0, 255).astype(np.uint8), 5, 25, 5)
        return _jpg(_fit(Image.fromarray(a).filter(ImageFilter.UnsharpMask(1.5, 60, 2)), 960), 92)
    if kind == "denoise":     # phone 'beauty' / night-mode noise reduction
        return _jpg(Image.fromarray(cv2.bilateralFilter(np.asarray(_fit(im, 1280)), 9, 40, 9)), 88)
    if kind == "h264":        # a still from a streamed video (H.264, crf 28, <= 854 px)
        import av

        im = _fit(im, 854)
        w, h = im.width // 2 * 2, im.height // 2 * 2
        im = im.crop((0, 0, w, h))
        buf = io.BytesIO()
        with av.open(buf, "w", format="mp4") as c:
            st = c.add_stream("libx264", rate=25)
            st.width, st.height, st.pix_fmt = w, h, "yuv420p"
            st.options = {"crf": "28", "preset": "veryfast"}
            for _ in range(3):
                for pk in st.encode(av.VideoFrame.from_image(im)):
                    c.mux(pk)
            for pk in st.encode():
                c.mux(pk)
        buf.seek(0)
        with av.open(buf) as c:
            fr = next(c.decode(video=0)).to_image()
        return _jpg(fr, 95)
    if kind == "small":       # thumbnail-sized web copy
        return _jpg(_fit(im, 640), 75)
    if kind == "whatsapp":    # messaging-app recompression
        return launder(data, quality=75, max_side=1600)
    raise ValueError(kind)


DEGRADATIONS = ("webcam", "denoise", "h264", "small")
