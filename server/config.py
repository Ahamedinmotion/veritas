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
#   fp32 : GenD fp32 + DFDC-B7 (default, the verified recommendation; ~1.5 GB files, +1.5-2.2 GB RAM)
#   int8 : GenD int8 + DFDC-B7 (RAM fallback, ~0.5-1 GB less; borderline clips jitter)
#   b7   : DFDC-B7 alone (smallest; catches far fewer reenactments)
#   off  : no face-swap test (the engine as it was before 19 Nov 2026)
FACESWAP_MODES = {"fp32": (("gend", "dfdc"), 1.25), "int8": (("gend_int8", "dfdc"), 1.5), "b7": (("dfdc",), 2.0)}


_WARNED_MODE: set = set()


def faceswap_mode() -> str:
    # cmd keeps quotes in `set VERITAS_FACESWAP="int8"`, so strip them as well as spaces
    raw = os.environ.get("VERITAS_FACESWAP", "fp32")
    m = raw.strip().strip("\"'").strip().lower() or "fp32"
    if m in FACESWAP_MODES or m == "off":
        return m
    if raw not in _WARNED_MODE:
        _WARNED_MODE.add(raw)
        import logging

        logging.getLogger("veritas").warning("VERITAS_FACESWAP=%r is not one of fp32, int8, b7, off - using fp32", raw)
    return "fp32"


def faceswap_weight() -> float:
    m = faceswap_mode()
    return FACESWAP_MODES[m][1] if m in FACESWAP_MODES else 0.0


def video_sampled_frames() -> int:
    """Face frames per video: 48 on a fast machine (>= 10 CPU threads), otherwise 32 - the face pass dominates video
    time. Never fewer than 32 by default: at 24 frames (the old <= 4-thread setting) the face-swap test sees different
    frames and published demo scores move (Wav2Lip 70 -> 64, a real Celeb-DF clip 34 -> 38), while at 32 all 40 checked
    clips keep their verdict. Override with the VERITAS_VIDEO_FRAMES environment variable (e.g. 24 if too slow)."""
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
