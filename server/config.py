"""Central configuration: paths, limits, model roles, fusion weights.

Calibrated numbers (per-test calibration curves, fusion weights) are written by
scripts/evaluate.py into server/calibration.json and loaded here at start-up. If that file is
missing the hand-set defaults below are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

VERSION = "1.0.0"

# Windows: a click inside the black server window puts the classic console into QuickEdit "Select" mode, and from
# then on every log write blocks - analyses finish but never answer. Turn QuickEdit off for this console.
# (Does nothing on macOS/Linux or when there is no console.)
if os.name == "nt":
    try:
        import ctypes

        _k = ctypes.windll.kernel32
        _h = _k.GetStdHandle(-10)  # STD_INPUT_HANDLE
        _m = ctypes.c_uint32()
        if _k.GetConsoleMode(_h, ctypes.byref(_m)):
            _k.SetConsoleMode(_h, (_m.value & ~0x0040) | 0x0080)  # clear ENABLE_QUICK_EDIT_MODE, set EXTENDED_FLAGS
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
MODELS_DIR = Path(os.environ.get("VERITAS_MODELS", ROOT / "models"))
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
CALIBRATION_FILE = Path(__file__).resolve().parent / "calibration.json"

# Offline at runtime: never let transformers / huggingface_hub reach the network.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ---- upload / analysis limits -----------------------------------------------------------------
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_IMAGE_PIXELS = 60_000_000          # ~ 60 MP; bigger images are refused (decompression bombs)
VIDEO_MAX_SECONDS = 20.0
VIDEO_MAX_SAMPLED_FRAMES = 48
VIDEO_DENSE_FPS = 12.0                 # landmark pass for blink / jitter / flicker
AUDIO_MAX_SECONDS = 30.0

# ---- model roles -> folder in models/ ----------------------------------------------------------
MODEL_DIRS = {
    "face_deepfake": MODELS_DIR / "face_deepfake",
    "ai_generated": MODELS_DIR / "ai_generated",
    "audio_deepfake": MODELS_DIR / "audio_deepfake",
}
FACE_DETECTOR_ONNX = MODELS_DIR / "face_detector" / "face_detection_yunet_2023mar.onnx"
FACE_SWAP_DIR = MODELS_DIR / "face_swap"   # GenD + DFDC-B7 face-swap detector (server/forensics/face_swap.py)
FACE_LANDMARKER_TASK = MODELS_DIR / "face_landmarker" / "face_landmarker.task"
# The web app vendors the same landmarker model; use it as a fallback location.
FACE_LANDMARKER_FALLBACK = WEB_DIR / "vendor" / "mediapipe" / "face_landmarker.task"

# ---- verdict thresholds (contract) -------------------------------------------------------------
THRESH_SUSPICIOUS = 35
THRESH_SYNTHETIC = 65

# ---- default fusion weights (overridden by calibration.json) ----------------------------------
DEFAULT_WEIGHTS = {
    "image": {
        "ai_generated": 0.42, "ai_face": 0.30, "ela": 0.06, "noise": 0.06,
        "fft": 0.06, "jpeg_quant": 0.03, "metadata": 0.07,
    },
    "video": {
        "ai_face": 0.40, "ai_generated": 0.20, "blink": 0.14, "landmark_jitter": 0.10,
        "temporal_flicker": 0.10, "metadata": 0.06,
        # one-sided face-swap test (counts only when its score >= 50); weight set per mode by faceswap_weight()
        "face_swap": 1.25,
    },
    "audio": {
        # spectral_cutoff and prosody are shown as visual evidence only (held-out AUC 0.42 / 0.52 = chance)
        "ai_voice": 0.85, "spectral_cutoff": 0.0, "prosody": 0.0, "breath_silence": 0.15, "spectrogram": 0.0,
    },
}


def load_calibration() -> dict:
    if CALIBRATION_FILE.exists():
        try:
            return json.loads(CALIBRATION_FILE.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


CALIBRATION = load_calibration()


def weights_for(kind: str) -> dict:
    w = dict(DEFAULT_WEIGHTS[kind])
    w.update(CALIBRATION.get("weights", {}).get(kind, {}))
    if kind == "video":
        w["face_swap"] = faceswap_weight()
    return w


# ---- face-swap detector (video) -----------------------------------------------------------------
# Mode -> (models, fusion weight). All weights and thresholds were chosen on FaceForensics++ only (BENCHMARK.md).
#   auto : the default - fp32 on a machine with >= 12 GB of RAM (identical scores to fp32), int8 below that
#          (an 8 GB booth laptop) when models/face_swap/gend_clip_int8.onnx is installed, otherwise fp32
#   fp32 : GenD fp32 + DFDC-B7 (the verified recommendation; ~1.5 GB files, +1.5-2.2 GB RAM)
#   int8 : GenD int8 + DFDC-B7 (RAM fallback, ~0.5-1 GB less; borderline clips jitter)
#   b7   : DFDC-B7 alone (smallest; catches far fewer reenactments)
#   off  : no face-swap test (the engine as it was before 19 Nov 2026)
FACESWAP_MODES = {"fp32": (("gend", "dfdc"), 1.25), "int8": (("gend_int8", "dfdc"), 1.5), "b7": (("dfdc",), 2.0)}
AUTO_INT8_BELOW_GB = 12.0   # "auto" picks int8 when the machine has less total RAM than this


_WARNED_MODE: set = set()
_AUTO: dict = {}


def total_ram_gb() -> float | None:
    """Total physical RAM in GB (1024^3), or None if it cannot be read. No extra dependency (no psutil)."""
    try:
        if os.name == "nt":
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None
            return st.ullTotalPhys / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:  # noqa: BLE001
        return None


def _auto_mode() -> str:
    """fp32 unless the machine has < AUTO_INT8_BELOW_GB of RAM and the int8 file is installed. Decided once."""
    if "mode" not in _AUTO:
        ram = total_ram_gb()
        has_int8 = (FACE_SWAP_DIR / "gend_clip_int8.onnx").exists()
        if ram is not None and ram < AUTO_INT8_BELOW_GB and has_int8:
            _AUTO["mode"], _AUTO["why"] = "int8", f"auto: {ram:.1f} GB RAM is under {AUTO_INT8_BELOW_GB:.0f} GB"
        elif ram is not None and ram < AUTO_INT8_BELOW_GB:
            _AUTO["mode"], _AUTO["why"] = "fp32", f"auto: {ram:.1f} GB RAM, but the int8 file is not installed"
        else:
            _AUTO["mode"] = "fp32"
            _AUTO["why"] = f"auto: {ram:.1f} GB RAM" if ram is not None else "auto: RAM size unknown"
    return _AUTO["mode"]


def faceswap_mode() -> str:
    # cmd keeps quotes in `set VERITAS_FACESWAP="int8"`, so strip them as well as spaces
    raw = os.environ.get("VERITAS_FACESWAP", "auto")
    m = raw.strip().strip("\"'").strip().lower() or "auto"
    if m in FACESWAP_MODES or m == "off":
        return m
    if m != "auto" and raw not in _WARNED_MODE:
        _WARNED_MODE.add(raw)
        import logging

        logging.getLogger("veritas").warning("VERITAS_FACESWAP=%r is not one of auto, fp32, int8, b7, off - using auto",
                                             raw)
    return _auto_mode()


def faceswap_mode_note() -> str:
    """Human-readable mode with the reason, e.g. 'int8 (auto: 7.8 GB RAM is under 12 GB)'."""
    m = faceswap_mode()
    raw = os.environ.get("VERITAS_FACESWAP", "auto").strip().strip("\"'").strip().lower()
    if raw in FACESWAP_MODES or raw == "off":
        return f"{m} (set by VERITAS_FACESWAP)"
    return f"{m} ({_AUTO.get('why', 'auto')})"


def faceswap_weight() -> float:
    m = faceswap_mode()
    return FACESWAP_MODES[m][1] if m in FACESWAP_MODES else 0.0


def video_sampled_frames() -> int:
    """Face frames per video: 48 on a fast machine (>= 10 CPU threads), otherwise 32 - the face pass dominates video
    time. Never fewer than 32 by default: at 24 frames (the old <= 4-thread setting) the face-swap test sees different
    frames and published demo scores move (Wav2Lip 70 -> 64, a real Celeb-DF clip 34 -> 38), while at 32 all 40 checked
    clips keep their verdict. The face-swap "auto" mode never changes this. VERITAS_VIDEO_FRAMES overrides it (for
    experiments only: below 32 the published demo scores move)."""
    env = os.environ.get("VERITAS_VIDEO_FRAMES", "").strip().strip("\"'")
    if env.isdigit():
        return max(8, min(VIDEO_MAX_SAMPLED_FRAMES, int(env)))
    n = os.cpu_count() or 4
    return VIDEO_MAX_SAMPLED_FRAMES if n >= 10 else 32


def torch_threads() -> int:
    n = os.cpu_count() or 4
    env = os.environ.get("VERITAS_THREADS")
    if env and env.isdigit():
        return max(1, int(env))
    return max(1, min(6, n - 1 if n > 2 else n))
