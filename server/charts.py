"""Forensic charts & heatmaps rendered with matplotlib in the VERITAS palette.

Palette (fixed meanings, matches web/css/tokens.css):
  bg #04060a, text #e8e6df, authentic #3ef2c4, synthetic #ff3b5c, evidence #ffb020, scan #6aa8ff
"""
from __future__ import annotations

import io
import math
import threading
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from PIL import Image  # noqa: E402

from . import config  # noqa: E402
from .util import jpeg_uri, png_uri  # noqa: E402

BG = "#04060a"
PANEL = "#0a0e15"
TEXT = "#e8e6df"
DIM = "#a9a79f"
FAINT = "#6b6a64"
GRID = "#1a2230"
AUTH = "#3ef2c4"
SYN = "#ff3b5c"
EVID = "#ffb020"
SCAN = "#6aa8ff"

_lock = threading.Lock()  # pyplot is not thread-safe

# Local fonts (converted from the site's woff2 files) - no system font dependency on Windows.
_FONT_MONO = "DejaVu Sans Mono"
_FONT_HEAD = "DejaVu Sans"
for ttf in sorted(Path(config.ASSETS_DIR / "fonts").glob("*.ttf")):
    try:
        font_manager.fontManager.addfont(str(ttf))
    except Exception:  # noqa: BLE001
        pass
_names = {f.name for f in font_manager.fontManager.ttflist}
if "IBM Plex Mono" in _names:
    _FONT_MONO = "IBM Plex Mono"
if "IBM Plex Sans Condensed" in _names:
    _FONT_HEAD = "IBM Plex Sans Condensed"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "axes.edgecolor": GRID, "axes.labelcolor": DIM, "axes.titlecolor": TEXT,
    "xtick.color": FAINT, "ytick.color": FAINT, "text.color": TEXT,
    "font.family": _FONT_MONO, "font.size": 10.5,
    "axes.titlesize": 12, "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.alpha": 0.9,
    "legend.frameon": False, "legend.fontsize": 9, "legend.labelcolor": DIM,
    "lines.solid_capstyle": "round", "axes.titlelocation": "left", "axes.titlepad": 10,
})

# dark -> amber -> white : "evidence heat"
CMAP_EVIDENCE = LinearSegmentedColormap.from_list(
    "evidence", [(0.0, BG), (0.18, "#2a1a04"), (0.5, "#b8740f"), (0.75, EVID), (1.0, "#fffaf0")])
# dark -> blue -> white : neutral analysis
CMAP_SCAN = LinearSegmentedColormap.from_list(
    "scan", [(0.0, BG), (0.25, "#0d2142"), (0.6, "#3f78d0"), (0.82, SCAN), (1.0, "#f4f8ff")])
# spectrogram: dark -> blue -> amber -> white
CMAP_SPEC = LinearSegmentedColormap.from_list(
    "spec", [(0.0, BG), (0.3, "#132a52"), (0.55, "#3f6fc0"), (0.78, EVID), (1.0, "#fff7e6")])


def score_color(score: float | None) -> str:
    if score is None:
        return FAINT
    if score < config.THRESH_SUSPICIOUS:
        return AUTH
    if score <= config.THRESH_SYNTHETIC:
        return EVID
    return SYN


def colorize(arr: np.ndarray, cmap=CMAP_EVIDENCE, vmin: float | None = None, vmax: float | None = None) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float32)
    lo = np.nanpercentile(a, 1) if vmin is None else vmin
    hi = np.nanpercentile(a, 99.5) if vmax is None else vmax
    if hi <= lo:
        hi = lo + 1e-6
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    rgb = (cmap(t)[..., :3] * 255).astype(np.uint8)
    return rgb


def heatmap_uri(arr: np.ndarray, cmap=CMAP_EVIDENCE, max_side: int = 900, vmin=None, vmax=None) -> str:
    """Photographic heatmaps compress badly as PNG (1-2 MB); a high-quality JPEG keeps responses small."""
    rgb = colorize(arr, cmap, vmin, vmax)
    img = Image.fromarray(rgb)
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return jpeg_uri(img, max_side, 90)


def _finish(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    img = Image.open(io.BytesIO(buf.getvalue()))
    return png_uri(img)


def _style_axes(ax, xlabel=None, ylabel=None, title=None):
    if xlabel:
        ax.set_xlabel(xlabel.upper(), labelpad=6, fontsize=8.5, color=FAINT)
    if ylabel:
        ax.set_ylabel(ylabel.upper(), labelpad=6, fontsize=8.5, color=FAINT)
    if title:
        ax.set_title(title, fontfamily=_FONT_HEAD, fontsize=12.5, color=TEXT, fontweight="medium")
    ax.tick_params(length=0, pad=5)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)


def line_chart(x, series: list[dict], *, xlabel=None, ylabel=None, title=None, hlines=(), vspans=(),
               markers=(), ylim=None, size=(8.0, 3.0), legend=True) -> str:
    """series: [{label, y, color, fill?, width?}], hlines: [(y, color, label)], vspans: [(x0, x1, color, alpha)],
    markers: [(x, y, color)]"""
    with _lock:
        fig, ax = plt.subplots(figsize=size)
        for x0, x1, c, a in vspans:
            ax.axvspan(x0, x1, color=c, alpha=a, lw=0)
        for s in series:
            y = np.asarray(s["y"], dtype=float)
            c = s.get("color", SCAN)
            ax.plot(x if s.get("x") is None else s["x"], y, color=c, lw=s.get("width", 1.6), label=s.get("label"),
                    alpha=s.get("alpha", 1.0))
            if s.get("fill"):
                ax.fill_between(x if s.get("x") is None else s["x"], y, np.nanmin(y) if ylim is None else ylim[0],
                                color=c, alpha=0.10, lw=0)
        for yv, c, lab in hlines:
            ax.axhline(yv, color=c, lw=1.0, ls=(0, (4, 4)), alpha=0.9)
            if lab:
                ax.text(1.0, yv, f" {lab}", color=c, fontsize=8.5, va="center", ha="left",
                        transform=ax.get_yaxis_transform(), clip_on=False)
        for xm, ym, c in markers:
            ax.scatter([xm], [ym], s=34, color=c, zorder=5, edgecolors=BG, linewidths=1.2)
        if ylim:
            ax.set_ylim(*ylim)
        ax.margins(x=0.01)
        _style_axes(ax, xlabel, ylabel, title)
        if legend and any(s.get("label") for s in series):
            ax.legend(loc="upper left", ncol=len(series), bbox_to_anchor=(0, 1.02, 1, 0.1), mode=None)
        return _finish(fig)


def bar_chart(x, heights, colors, *, xlabel=None, ylabel=None, title=None, hlines=(), ylim=(0, 100),
              size=(8.0, 2.8), width=None) -> str:
    with _lock:
        fig, ax = plt.subplots(figsize=size)
        ax.bar(x, heights, color=colors, width=width or (0.8 * (x[1] - x[0]) if len(x) > 1 else 0.8), lw=0)
        for yv, c, lab in hlines:
            ax.axhline(yv, color=c, lw=1.0, ls=(0, (4, 4)))
            if lab:
                ax.text(1.0, yv, f" {lab}", color=c, fontsize=8.5, va="center", ha="left",
                        transform=ax.get_yaxis_transform(), clip_on=False)
        ax.set_ylim(*ylim)
        ax.grid(axis="x", visible=False)
        _style_axes(ax, xlabel, ylabel, title)
        return _finish(fig)


def spectrum_figure(log_spec: np.ndarray, freqs: np.ndarray, radial: np.ndarray, fit: np.ndarray | None,
                    peaks: list[tuple[float, float]] | None = None) -> str:
    """Left: 2-D log-magnitude spectrum. Right: azimuthal average with power-law fit."""
    with _lock:
        fig = plt.figure(figsize=(9.0, 3.6))
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.55], wspace=0.22)
        a0 = fig.add_subplot(gs[0])
        a0.imshow(colorize(log_spec, CMAP_SCAN), interpolation="bilinear")
        a0.set_xticks([])
        a0.set_yticks([])
        a0.grid(False)
        for s in a0.spines.values():
            s.set_visible(False)
        a0.set_title("2-D SPECTRUM", fontfamily=_FONT_HEAD, fontsize=10, color=DIM)
        if peaks:
            h, w = log_spec.shape
            for (py, px) in peaks[:12]:
                a0.add_patch(plt.Circle((px, py), radius=max(4, w * 0.025), fill=False, ec=EVID, lw=1.2))
        a1 = fig.add_subplot(gs[1])
        a1.plot(freqs, radial, color=SCAN, lw=1.7, label="measured")
        if fit is not None:
            a1.plot(freqs, fit, color=FAINT, lw=1.1, ls=(0, (4, 4)), label="natural 1/f trend")
            dev = radial - fit
            hi = freqs > 0.25
            a1.fill_between(freqs[hi], fit[hi], radial[hi], where=dev[hi] > 0, color=EVID, alpha=0.25, lw=0)
        _style_axes(a1, "spatial frequency (cycles / pixel)", "log power")
        a1.set_title("AZIMUTHAL AVERAGE", fontfamily=_FONT_HEAD, fontsize=10, color=DIM)
        a1.legend(loc="upper right")
        return _finish(fig)


def image_with_colorbar(rgb: np.ndarray, label: str) -> str:
    with _lock:
        h, w = rgb.shape[:2]
        fig, ax = plt.subplots(figsize=(8.0, 8.0 * h / w))
        ax.imshow(rgb)
        ax.axis("off")
        ax.text(0.01, 0.985, label.upper(), transform=ax.transAxes, color=TEXT, fontsize=9, va="top",
                bbox=dict(facecolor=BG, alpha=0.7, lw=0, pad=4))
        return _finish(fig)


def spectrogram_figure(S_db: np.ndarray, sr: int, hop: int, fmax: float, mel: bool = True,
                       cutoff_hz: float | None = None) -> str:
    """Mel spectrogram. The rows are mel bands (equally spaced in pitch perception, NOT in Hz), so the y-axis ticks
    are placed where each frequency actually falls on the mel scale and labelled in kHz."""
    with _lock:
        fig, ax = plt.subplots(figsize=(9.0, 3.2))
        dur = S_db.shape[1] * hop / sr
        n = S_db.shape[0]
        top = float(n) if mel else fmax / 1000.0
        ax.imshow(colorize(S_db, CMAP_SPEC, vmin=S_db.max() - 80, vmax=S_db.max()), aspect="auto", origin="lower",
                  extent=[0, dur, 0, top], interpolation="bilinear")
        ax.grid(False)

        def ypos(hz: float) -> float:
            if not mel:
                return hz / 1000.0
            import librosa

            m0, m1 = librosa.hz_to_mel(0.0), librosa.hz_to_mel(fmax)
            return float((librosa.hz_to_mel(hz) - m0) / (m1 - m0) * n)

        ticks = [f for f in (500, 1000, 2000, 4000, 8000) if f < fmax * 0.9] + [fmax]
        ax.set_yticks([0.0] + [ypos(f) for f in ticks])
        ax.set_yticklabels(["0"] + [f"{f / 1000:g}" for f in ticks])
        if cutoff_hz:
            ax.axhline(ypos(cutoff_hz), color=EVID, lw=1, ls=(0, (4, 4)))
        _style_axes(ax, "time (s)", "frequency (kHz)" + (", mel scale" if mel else ""))
        return _finish(fig)


def face_strip(crops: list[np.ndarray], scores: list[float | None], size: int = 220) -> str:
    """Face crops side by side, framed by their verdict colour with the score underneath."""
    with _lock:
        n = max(1, len(crops))
        fig, axes = plt.subplots(1, n, figsize=(2.3 * n, 2.75))
        axes = np.atleast_1d(axes)
        for ax, crop, sc in zip(axes, crops, scores):
            ax.imshow(np.asarray(Image.fromarray(crop).resize((size, size), Image.Resampling.LANCZOS)))
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            col = score_color(sc)
            for s in ax.spines.values():
                s.set_visible(True)
                s.set_color(col)
                s.set_linewidth(2.2)
            ax.set_xlabel("n/a" if sc is None else f"{sc:.0f}% synthetic", color=col, fontsize=10, labelpad=6)
        return _finish(fig)


def faceswap_figure(crops: list, frame_scores: list, times: list, size: int = 200, silent: bool = False) -> str:
    """The aligned faces the face-swap detector judged (2 x 4 grid), framed by each frame's score; a frame where no
    face was found is shown as an empty tile. silent=True (the one-sided test stayed below 50): every frame and label
    is drawn in neutral grey, because a silent test never vouches that a face is real."""
    with _lock:
        n = max(1, len(crops))
        cols = min(4, n)
        rows = int(math.ceil(n / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(2.15 * cols, 2.45 * rows))
        axes = np.atleast_1d(axes).ravel()
        for k, ax in enumerate(axes):
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            if k >= n:
                ax.axis("off")
                continue
            crop, sc = crops[k], frame_scores[k]
            t = times[k] if k < len(times) else None
            if crop is not None:
                ax.imshow(np.asarray(Image.fromarray(crop).resize((size, size), Image.Resampling.LANCZOS)))
            else:
                ax.imshow(np.zeros((size, size, 3), dtype=np.uint8) + 10)
                ax.text(0.5, 0.5, "NO FACE", color=FAINT, fontsize=9, ha="center", va="center", transform=ax.transAxes)
            col = FAINT if silent else score_color(sc)
            for s in ax.spines.values():
                s.set_visible(True)
                s.set_color(col)
                s.set_linewidth(2.2)
            ts = "" if t is None else f"{t:.1f} s · "
            ax.set_xlabel(f"{ts}{'n/a' if sc is None else f'{sc:.0f}'}", color=col, fontsize=9.5, labelpad=5)
        fig.subplots_adjust(wspace=0.08, hspace=0.32)
        return _finish(fig)
