"""Model registry: loads every neural network ONCE at start-up from the local models/ folder.

* face_deepfake  - image classifier run on face crops        (models/face_deepfake/)
* ai_generated   - whole-image AI-generation detector        (models/ai_generated/)
* audio_deepfake - wav2vec2-style synthetic-speech detector  (models/audio_deepfake/)
* face detector  - OpenCV YuNet ONNX (fallback: Haar cascade bundled with OpenCV)
* face landmarker- MediaPipe FaceLandmarker .task (478 landmarks, used for blink / jitter / flicker)
* face_swap      - GenD (CLIP ViT-L/14) + DFDC-winner EfficientNet-B7, ONNX Runtime, each with its own face
                   detector (SCRFD / MTCNN)                  (models/face_swap/, server/forensics/face_swap.py)

Everything is loaded with local_files_only=True and HF_HUB_OFFLINE=1 - no network at runtime.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("veritas.models")

INFER_LOCK = threading.Lock()   # one forward pass at a time keeps RAM flat on an 8 GB laptop
_torch = None

FAKE_WORDS = ("fake", "ai", "artificial", "synthetic", "deepfake", "spoof", "generated", "sdxl", "machine")
REAL_WORDS = ("real", "human", "bona", "authentic", "genuine", "natural", "realism")


def torch():
    global _torch
    if _torch is None:
        import torch as _t

        _t.set_num_threads(config.torch_threads())
        try:
            _t.set_num_interop_threads(1)
        except RuntimeError:
            pass
        _torch = _t
    return _torch


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _fake_index(id2label: dict, override: str | None) -> int | None:
    labels = {int(k): str(v) for k, v in id2label.items()}
    if override is not None:
        for k, v in labels.items():
            if v.lower() == override.lower():
                return k
    for k, v in labels.items():
        lv = v.lower()
        if any(w in lv for w in REAL_WORDS):
            continue
        if any(w == lv or w in lv.replace("-", " ").split() or lv.startswith(w) for w in FAKE_WORDS):
            return k
    # two-class model with one recognisable 'real' label -> the other one is fake
    if len(labels) == 2:
        for k, v in labels.items():
            if any(w in v.lower() for w in REAL_WORDS):
                return 1 - k
    return None


class ImageClassifier:
    """Hugging Face image-classification model with hand-rolled preprocessing (no processor-version surprises)."""

    def __init__(self, folder: Path, role: str):
        from transformers import AutoModelForImageClassification

        self.role = role
        self.folder = folder
        meta = _read_json(folder / "veritas.json")
        self.repo = meta.get("repo", folder.name)
        self.model = AutoModelForImageClassification.from_pretrained(str(folder), local_files_only=True).eval()
        cfg = self.model.config
        self.num_labels = int(getattr(cfg, "num_labels", 2))
        self.fake_idx = None if self.num_labels == 1 else _fake_index(cfg.id2label, meta.get("fake_label"))
        if self.num_labels > 1 and self.fake_idx is None:
            raise RuntimeError(f"{role}: cannot tell which label means 'fake' in {cfg.id2label}")
        pp = _read_json(folder / "preprocessor_config.json")
        self.mean = np.array(pp.get("image_mean", [0.5, 0.5, 0.5]), dtype=np.float32)
        self.std = np.array(pp.get("image_std", [0.5, 0.5, 0.5]), dtype=np.float32)
        self.rescale = float(pp.get("rescale_factor", 1 / 255)) if pp.get("do_rescale", True) else 1.0
        self.normalize = bool(pp.get("do_normalize", True))
        self.resample = int(pp.get("resample", 2))
        size = pp.get("size", {"height": 224, "width": 224})
        if isinstance(size, int):
            size = {"height": size, "width": size}
        self.size = size
        self.do_crop = bool(pp.get("do_center_crop", False))
        crop = pp.get("crop_size", size)
        if isinstance(crop, int):
            crop = {"height": crop, "width": crop}
        self.crop = crop
        self.labels = {int(k): v for k, v in cfg.id2label.items()} if self.num_labels > 1 else {0: "fake"}
        log.info("loaded %-14s %s  labels=%s fake_idx=%s", role, self.repo, self.labels, self.fake_idx)

    def _prep(self, img: Image.Image) -> np.ndarray:
        img = img.convert("RGB")
        if "shortest_edge" in self.size:
            se = int(self.size["shortest_edge"])
            w, h = img.size
            s = se / min(w, h)
            img = img.resize((max(1, round(w * s)), max(1, round(h * s))), self.resample)
        else:
            img = img.resize((int(self.size["width"]), int(self.size["height"])), self.resample)
        if self.do_crop:
            cw, ch = int(self.crop["width"]), int(self.crop["height"])
            w, h = img.size
            left, top = max(0, (w - cw) // 2), max(0, (h - ch) // 2)
            img = img.crop((left, top, left + cw, top + ch))
        a = np.asarray(img, dtype=np.float32) * self.rescale
        if self.normalize:
            a = (a - self.mean) / self.std
        return a.transpose(2, 0, 1)

    def predict(self, images: list[Image.Image], batch: int = 8) -> list[float]:
        """Return P(fake) for each image."""
        t = torch()
        out: list[float] = []
        for i in range(0, len(images), batch):
            x = t.from_numpy(np.stack([self._prep(im) for im in images[i:i + batch]]))
            with INFER_LOCK, t.inference_mode():
                logits = self.model(pixel_values=x).logits.float()
            if self.num_labels == 1:
                p = t.sigmoid(logits[:, 0])
            else:
                p = t.softmax(logits, dim=-1)[:, self.fake_idx]
            out += [float(v) for v in p]
        return out


class AudioClassifier:
    def __init__(self, folder: Path):
        from transformers import AutoModelForAudioClassification

        meta = _read_json(folder / "veritas.json")
        self.repo = meta.get("repo", folder.name)
        self.model = AutoModelForAudioClassification.from_pretrained(str(folder), local_files_only=True).eval()
        cfg = self.model.config
        self.fake_idx = _fake_index(cfg.id2label, meta.get("fake_label"))
        if self.fake_idx is None:
            raise RuntimeError(f"audio: cannot tell which label is fake in {cfg.id2label}")
        fe = _read_json(folder / "preprocessor_config.json")
        self.sr = int(fe.get("sampling_rate", 16000))
        self.normalize = bool(fe.get("do_normalize", True))
        self.labels = {int(k): v for k, v in cfg.id2label.items()}
        log.info("loaded %-14s %s  labels=%s fake_idx=%s", "audio_deepfake", self.repo, self.labels, self.fake_idx)

    def predict_windows(self, wav16: np.ndarray, win_s: float = 4.0, hop_s: float = 2.0, batch: int = 4,
                        embed_layer: int | None = None):
        """Score overlapping windows. Returns (centres_s, P(fake) per window) - plus, when embed_layer is given,
        the time-averaged hidden state of that transformer layer for every window (n_windows x 768)."""
        t = torch()
        n, w, h = len(wav16), int(win_s * self.sr), int(hop_s * self.sr)
        starts = [0] if n <= w else list(range(0, n - w + 1, h))
        if n > w and starts[-1] + w < n:
            starts.append(n - w)
        chunks = []
        for s in starts:
            c = wav16[s:s + w].astype(np.float32)
            if len(c) < self.sr // 2:
                c = np.pad(c, (0, self.sr // 2 - len(c)))
            if self.normalize:
                c = (c - c.mean()) / np.sqrt(c.var() + 1e-7)
            chunks.append(c)
        probs: list[float] = []
        embs: list[np.ndarray] = []
        for i in range(0, len(chunks), batch):
            group = chunks[i:i + batch]
            L = max(len(c) for c in group)
            x = np.zeros((len(group), L), dtype=np.float32)
            mask = np.zeros((len(group), L), dtype=np.int64)
            for j, c in enumerate(group):
                x[j, :len(c)] = c
                mask[j, :len(c)] = 1
            with INFER_LOCK, t.inference_mode():
                kw = {"input_values": t.from_numpy(x)}
                if getattr(self.model.config, "feat_extract_norm", "group") == "layer":
                    kw["attention_mask"] = t.from_numpy(mask)
                out = self.model(**kw, output_hidden_states=embed_layer is not None)
                logits = out.logits.float()
                if embed_layer is not None:
                    hs = out.hidden_states[embed_layer].float().numpy()
                    for j, c in enumerate(group):
                        frames = max(1, min(hs.shape[1], int(round(hs.shape[1] * len(c) / L))))
                        embs.append(hs[j, :frames].mean(axis=0))
            probs += [float(v) for v in t.softmax(logits, dim=-1)[:, self.fake_idx]]
        centres = [(s + min(w, n) / 2) / self.sr for s in starts]
        if embed_layer is not None:
            return centres, probs, np.stack(embs)
        return centres, probs


class FaceDetector:
    """YuNet (OpenCV DNN, 230 kB ONNX). Returns boxes in pixel coords, largest first."""

    def __init__(self):
        self.kind = None
        p = config.FACE_DETECTOR_ONNX
        if p.exists() and hasattr(cv2, "FaceDetectorYN"):
            self.det = cv2.FaceDetectorYN.create(str(p), "", (320, 320), 0.72, 0.3, 50)
            self.kind = "yunet"
        else:
            self.det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            self.kind = "haar"
        self._lock = threading.Lock()
        log.info("face detector: %s", self.kind)

    def _detect_at(self, rgb: np.ndarray, scale: float) -> list[dict]:
        H, W = rgb.shape[:2]
        small = cv2.resize(rgb, (max(1, int(W * scale)), max(1, int(H * scale))), interpolation=cv2.INTER_AREA) \
            if scale < 1 else rgb
        bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        out = []
        if self.kind == "yunet":
            self.det.setInputSize((bgr.shape[1], bgr.shape[0]))
            _, faces = self.det.detect(bgr)
            for f in ([] if faces is None else faces):
                out.append({"box": (f[:4] / scale).tolist(), "conf": float(f[14]),
                            "landmarks": (f[4:14].reshape(5, 2) / scale).tolist()})
        else:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            for (x, y, w, h) in self.det.detectMultiScale(gray, 1.1, 6, minSize=(40, 40)):
                out.append({"box": [x / scale, y / scale, w / scale, h / scale], "conf": 0.8, "landmarks": None})
        return out

    def detect(self, rgb: np.ndarray, max_faces: int = 6, min_rel: float = 0.04, sides=(960, 320)) -> list[dict]:
        """Two scales: YuNet is tuned for faces up to ~300 px, so close-up portraits are found on a 320 px copy and
        small background faces on a 960 px copy; duplicates are merged by overlap (non-maximum suppression).
        Video frames use a single 480 px pass (talking-head faces are large; this halves the face-pass time)."""
        H, W = rgb.shape[:2]
        scales = sorted({min(1.0, s / max(H, W)) for s in sides}, reverse=True)
        cands = []
        with self._lock:
            for sc in scales:
                cands += self._detect_at(rgb, sc)
        cands.sort(key=lambda f: f["conf"], reverse=True)
        out = []
        for f in cands:
            if all(_iou(f["box"], g["box"]) < 0.35 for g in out):
                out.append(f)
        # clip to image, drop tiny faces
        res = []
        for f in out:
            x, y, w, h = f["box"]
            x0, y0 = max(0.0, x), max(0.0, y)
            x1, y1 = min(W, x + w), min(H, y + h)
            if x1 - x0 < 24 or y1 - y0 < 24 or max(x1 - x0, y1 - y0) < min_rel * min(W, H):
                continue
            f["box"] = [x0, y0, x1 - x0, y1 - y0]
            res.append(f)
        res.sort(key=lambda f: f["box"][2] * f["box"][3], reverse=True)
        return res[:max_faces]


def _iou(a, b) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    return inter / max(1e-6, aw * ah + bw * bh - inter)


def face_crop(rgb: np.ndarray, box, margin: float = 0.30) -> np.ndarray:
    """Square crop around a face box with context margin (classifiers were trained on loose face crops).
    Near the picture edge the square slides inwards (and, if it must, shrinks) instead of mirroring pixels:
    mirrored padding invents symmetric shapes that the classifier could mistake for artefacts."""
    H, W = rgb.shape[:2]
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    side = max(w, h) * (1 + 2 * margin)
    side = min(side, float(min(W, H)))           # never larger than the picture
    side = max(side, min(float(max(w, h)), float(min(W, H))))
    x0 = int(round(min(max(cx - side / 2, 0), W - side)))
    y0 = int(round(min(max(cy - side / 2, 0), H - side)))
    s = int(round(side))
    crop = rgb[max(0, y0):max(0, y0) + s, max(0, x0):max(0, x0) + s]
    ch, cw = crop.shape[:2]
    if ch != cw:  # face larger than the short side of the picture: pad the short way with the edge colour
        d = max(ch, cw)
        crop = cv2.copyMakeBorder(crop, 0, d - ch, 0, d - cw, cv2.BORDER_REPLICATE)
    return np.ascontiguousarray(crop)


def landmarker_bytes() -> bytes | None:
    for p in (config.FACE_LANDMARKER_TASK, config.FACE_LANDMARKER_FALLBACK):
        if p.exists():
            return p.read_bytes()
    return None


def new_landmarker(video: bool = True):
    """A fresh MediaPipe FaceLandmarker (VIDEO mode needs monotonic timestamps, so one per request)."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision

    data = REGISTRY.landmarker_model
    if data is None:
        return None
    opts = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_buffer=data),
        running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
        num_faces=1, min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5, output_face_blendshapes=True)
    _ = mp
    return vision.FaceLandmarker.create_from_options(opts)


class Registry:
    def __init__(self):
        self.face_deepfake: ImageClassifier | None = None
        self.ai_generated: ImageClassifier | None = None
        self.audio_deepfake: AudioClassifier | None = None
        self.face_detector: FaceDetector | None = None
        self.face_swap = None   # forensics.face_swap.FaceSwapDetector (video only)
        self.landmarker_model: bytes | None = None
        self.errors: dict[str, str] = {}
        self.loaded = False

    def load(self):
        t0 = time.perf_counter()
        torch()
        for role in ("ai_generated", "face_deepfake"):
            folder = config.MODEL_DIRS[role]
            try:
                if not (folder / "config.json").exists():
                    raise FileNotFoundError(f"{folder} is missing - run scripts/download_models.py")
                meta = _read_json(folder / "veritas.json")
                other = self.ai_generated
                if role == "face_deepfake" and other is not None and meta.get("repo") == other.repo:
                    self.face_deepfake = other  # same network used on face crops: share one copy in RAM
                    log.info("face_deepfake shares the ai_generated network (%s)", other.repo)
                    continue
                setattr(self, role, ImageClassifier(folder, role))
            except Exception as e:  # noqa: BLE001
                self.errors[role] = str(e)
                log.error("could not load %s: %s", role, e)
        try:
            folder = config.MODEL_DIRS["audio_deepfake"]
            if not (folder / "config.json").exists():
                raise FileNotFoundError(f"{folder} is missing - run scripts/download_models.py")
            self.audio_deepfake = AudioClassifier(folder)
        except Exception as e:  # noqa: BLE001
            self.errors["audio_deepfake"] = str(e)
            log.error("could not load audio_deepfake: %s", e)
        try:
            self.face_detector = FaceDetector()
        except Exception as e:  # noqa: BLE001
            self.errors["face_detector"] = str(e)
            log.error("could not load face detector: %s", e)
        self.landmarker_model = landmarker_bytes()
        if self.landmarker_model is None:
            self.errors["face_landmarker"] = "face_landmarker.task not found"
        self.load_face_swap()
        self.loaded = True
        log.info("models ready in %.1fs", time.perf_counter() - t0)

    def load_face_swap(self):
        """GenD + DFDC-B7 face-swap detector (video). VERITAS_FACESWAP=fp32 (default) | int8 | b7 | off."""
        mode = config.faceswap_mode()
        if mode == "off":
            log.info("face-swap detector switched off (VERITAS_FACESWAP=off)")
            return
        try:
            from .forensics.face_swap import FaceSwapDetector

            use = config.FACESWAP_MODES[mode][0]
            need = {"gend": "gend_clip.onnx", "gend_int8": "gend_clip_int8.onnx", "dfdc": "dfdc_b7.onnx"}
            files = [need[k] for k in use] + (["det_10g.onnx", "clip_preprocessor/preprocessor_config.json"]
                                              if any(k.startswith("gend") for k in use) else [])
            missing = [f for f in files if not (config.FACE_SWAP_DIR / f).exists()]
            if missing:
                raise FileNotFoundError(f"models/face_swap/{', '.join(missing)} missing - run scripts/download_models.py")
            self.face_swap = FaceSwapDetector(config.FACE_SWAP_DIR, use=use, threads=config.torch_threads())
            self.face_swap.mode = mode
        except Exception as e:  # noqa: BLE001
            self.face_swap = None
            self.errors["face_swap"] = str(e)
            log.error("could not load the face-swap detector: %s", e)

    def warmup(self):
        t0 = time.perf_counter()
        img = Image.fromarray((np.random.default_rng(0).random((256, 256, 3)) * 255).astype(np.uint8))
        for m in (self.face_deepfake, self.ai_generated):
            if m:
                m.predict([img])
        if self.audio_deepfake:
            self.audio_deepfake.predict_windows(np.zeros(16000 * 2, dtype=np.float32) + 1e-4)
        if self.face_detector:
            self.face_detector.detect(np.asarray(img))
        if self.face_swap:
            try:
                with INFER_LOCK:
                    self.face_swap.warmup()
            except Exception as e:  # noqa: BLE001
                log.warning("face-swap warm-up failed: %s", e)
        try:
            lm = new_landmarker(video=False)
            if lm:
                import mediapipe as mp

                lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(img)))
                lm.close()
        except Exception as e:  # noqa: BLE001
            self.errors["face_landmarker"] = str(e)
            log.error("face landmarker failed: %s", e)
        log.info("warm-up done in %.1fs", time.perf_counter() - t0)

    def health(self) -> dict:
        return {
            "face_deepfake": self.face_deepfake is not None,
            "ai_generated": self.ai_generated is not None,
            "audio_deepfake": self.audio_deepfake is not None,
            "face_detector": self.face_detector is not None,
            "face_landmarker": self.landmarker_model is not None and "face_landmarker" not in self.errors,
            # the face-swap test is required unless it was switched off on purpose (VERITAS_FACESWAP=off)
            "face_swap": self.face_swap is not None or config.faceswap_mode() == "off",
        }


REGISTRY = Registry()
