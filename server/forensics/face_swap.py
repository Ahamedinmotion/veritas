"""Face-Swap Detector (video): two PRETRAINED published detectors, chosen by our own benchmark.

We did not train these networks. We benchmarked six published face-swap detectors on 75 leak-free research clips
(FaceForensics++ test split, Celeb-DF v2 test list, Google DFD) and integrated a pair of them, exactly as verified
(../_incoming/detector/BENCHMARK.md, "Verification"). Our pre-registered rule picked the DFDC winner alone; we added
GenD after seeing the results because it also catches reenactment (Face2Face / NeuralTextures). On the clips from
datasets neither network was trained on (Celeb-DF + Google DFD), the pair and B7 alone are statistically tied.
Caveat: GenD's authors chose its checkpoint using Celeb-DF++ validation videos, so Celeb-DF is unseen in training
but not in model selection; Google DFD is the only fully unseen part. The two networks:

  * GenD  - CLIP ViT-L/14 fine-tuned for deepfake detection ("Deepfake Detection that Generalizes Across Benchmarks",
            Yermakov, Cech, Matas, Fritz, WACV 2026; MIT). Exact published fp32 weights as ONNX (logits == PyTorch
            within 2.4e-6). Its own face detector: SCRFD-10G (InsightFace buffalo_l det_10g.onnx, non-commercial
            research licence), 5-point alignment, scale 1.3, CLIP preprocessing. Trained on FaceForensics++ (train).
  * B7    - the DFDC (Deepfake Detection Challenge, 2020) first-place EfficientNet-B7 by Selim Seferbekov (MIT), one of
            its 7 checkpoints, as ONNX (== PyTorch within 5e-7). Its own face detector: MTCNN (facenet-pytorch, MIT,
            vendored in server/vendor). Trained on the DFDC training set only.

Each model scores 8 evenly spaced frames with its own face crop (feeding the engine's YuNet crops moved scores by up to
0.22 in the benchmark). Clip score, a fixed rule with nothing fitted except three thresholds chosen on the 45
FaceForensics++ test clips ONLY (never on Celeb-DF, DFD or the demo clips):
    pG, pB = mean P(fake) over the frames where that model found a face
    z      = 0.5*(logit pG - logit tG) + 0.5*(logit pB - logit tB) - logit t_pair        (both models found a face)
    z      = logit p - logit t                                                           (only one model did)
    score  = 100 * sigmoid(z)          -> the pair's FF++ threshold sits exactly at 50
The engine uses it ONE-SIDED (server/fusion.py): it may raise an alarm (score >= 50) but never vouches that a face is
real, because both networks call fully generated (GAN) faces "real" - they were trained on face-swaps only.

Modes (VERITAS_FACESWAP): "fp32" (default; GenD fp32 + B7, ~1.5 GB of files, +1.5-2.2 GB RAM), "int8" (GenD int8 + B7;
RAM fallback - its decisions jitter on borderline clips), "b7" (B7 alone; smallest), "off".
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("veritas.face_swap")

NAME = "Face-Swap Detector"
EXPLAIN = ("Two pretrained deepfake detectors that we benchmarked and chose, not trained ourselves: GenD (a CLIP "
           "vision transformer tuned on FaceForensics++, WACV 2026) and the Deepfake Detection Challenge winner "
           "(EfficientNet-B7). Each finds the face in 8 frames (GenD also aligns it) and gives the probability that it "
           "was swapped or re-animated; such detectors are trained to pick up blending seams and texture mismatches. "
           "Thresholds chosen on FaceForensics++ only. It can only raise an alarm: it never vouches that a face is real.")

# FF++-chosen clip thresholds (mean of frame probabilities over N = 8 evenly spaced frames), bench_results.json
# metrics[<scorer>]["8"]["mean"]["threshold_ffpp"]; models/face_swap/thresholds.json carries the same values.
DEFAULT_THRESHOLDS = {"gend": 0.812141, "gend_int8": 0.673306, "dfdc": 0.6968,
                      "pair_gend+dfdc": 0.117826,       # fp32 GenD + DFDC B7 (the verified recommendation)
                      "pair_gend_int8+dfdc": 0.193495}  # int8 GenD + DFDC B7 (RAM fallback)
N_FRAMES = 8          # never fewer: the thresholds were chosen for 8-frame means
MODES = {"fp32": ("gend", "dfdc"), "int8": ("gend_int8", "dfdc"), "b7": ("dfdc",)}
MODEL_LABEL = {"gend": "GenD CLIP ViT-L/14", "gend_int8": "GenD CLIP ViT-L/14 (int8)", "dfdc": "DFDC-winner EfficientNet-B7"}


def _logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, float(p)))
    return math.log(p / (1 - p))


def _ort_session(path: Path, threads: int):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


# ============================================================================== SCRFD-10G (GenD's face detector)
def _distance2bbox(points, distance):
    return np.stack([points[:, 0] - distance[:, 0], points[:, 1] - distance[:, 1],
                     points[:, 0] + distance[:, 2], points[:, 1] + distance[:, 3]], axis=-1)


def _distance2kps(points, distance):
    preds = []
    for i in range(0, distance.shape[1], 2):
        preds.append(points[:, i % 2] + distance[:, i])
        preds.append(points[:, i % 2 + 1] + distance[:, i + 1])
    return np.stack(preds, axis=-1)


class SCRFD:
    """InsightFace det_10g.onnx: 640x640 letterbox, det_thresh 0.5, NMS 0.4, BGR input (GenD detector.py)."""

    def __init__(self, path: Path, threads: int = 4, det_thresh=0.5, nms_thresh=0.4, input_size=(640, 640)):
        self.session = _ort_session(path, threads)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.fmc, self.strides, self.num_anchors = 3, [8, 16, 32], 2
        self.det_thresh, self.nms_thresh, self.input_size = det_thresh, nms_thresh, input_size
        self.center_cache = {}

    def _forward(self, img, threshold):
        scores_list, bboxes_list, kpss_list = [], [], []
        blob = cv2.dnn.blobFromImage(img, 1.0 / 128.0, tuple(img.shape[0:2][::-1]), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.session.run(self.output_names, {self.input_name: blob})
        ih, iw = blob.shape[2], blob.shape[3]
        for idx, stride in enumerate(self.strides):
            scores = outs[idx]
            bbox_preds = outs[idx + self.fmc] * stride
            kps_preds = outs[idx + self.fmc * 2] * stride
            h, w = ih // stride, iw // stride
            key = (h, w, stride)
            if key not in self.center_cache:
                ac = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
                ac = (ac * stride).reshape((-1, 2))
                ac = np.stack([ac] * self.num_anchors, axis=1).reshape((-1, 2))
                self.center_cache[key] = ac
            ac = self.center_cache[key]
            pos = np.where(scores >= threshold)[0]
            scores_list.append(scores[pos])
            bboxes_list.append(_distance2bbox(ac, bbox_preds)[pos])
            kpss_list.append(_distance2kps(ac, kps_preds).reshape((-1, 5, 2))[pos])
        return scores_list, bboxes_list, kpss_list

    def _nms(self, dets):
        x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])
            xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
            ovr = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[np.where(ovr <= self.nms_thresh)[0] + 1]
        return keep

    def detect(self, img_bgr):
        iw_, ih_ = self.input_size
        im_ratio = float(img_bgr.shape[0]) / img_bgr.shape[1]
        if im_ratio > float(ih_) / iw_:
            nh, nw = ih_, int(ih_ / im_ratio)
        else:
            nw, nh = iw_, int(iw_ * im_ratio)
        det_scale = float(nh) / img_bgr.shape[0]
        det_img = np.zeros((ih_, iw_, 3), dtype=np.uint8)
        det_img[:nh, :nw, :] = cv2.resize(img_bgr, (nw, nh))
        scores_list, bboxes_list, kpss_list = self._forward(det_img, self.det_thresh)
        scores = np.vstack(scores_list)
        order = scores.ravel().argsort()[::-1]
        bboxes = np.vstack(bboxes_list) / det_scale
        kpss = np.vstack(kpss_list) / det_scale
        pre_det = np.hstack((bboxes, scores)).astype(np.float32, copy=False)[order, :]
        keep = self._nms(pre_det)
        return pre_det[keep, :], kpss[order, :, :][keep, :, :]


# ======================================================================================================== GenD
GEND_DST = np.array([[0.34, 0.46], [0.66, 0.46], [0.5, 0.64], [0.37, 0.82], [0.63, 0.82]], dtype=np.float32)


def gend_align(img, landmarks, scale=1.3):
    """GenD align_face(target_size=None, scale=1.3), verbatim operation order (float32 in-place ops; see BENCHMARK.md -
    the fp32 model is insensitive to the 3e-5 px template difference under NumPy 2, the int8 one is not)."""
    dst = GEND_DST.copy()
    desired = np.linalg.norm(landmarks[:, None, :] - landmarks[None, :, :], axis=-1)
    dd = np.linalg.norm(dst[:, None, :] - dst[None, :, :], axis=-1)
    iu = np.triu_indices(len(dst), k=1)
    approx = np.round(np.mean(desired[iu] / dd[iu]) * scale).astype(int)
    target_size = (int(approx), int(approx))
    dst[:, 0] *= target_size[0]
    dst[:, 1] *= target_size[1]
    margin = scale - 1
    xm, ym = target_size[0] * margin / 2.0, target_size[1] * margin / 2.0
    dst[:, 0] += xm
    dst[:, 1] += ym
    dst[:, 0] *= target_size[0] / (target_size[0] + 2 * xm)
    dst[:, 1] *= target_size[1] / (target_size[1] + 2 * ym)
    M = cv2.estimateAffinePartial2D(landmarks.astype(np.float32), dst, method=cv2.LMEDS)[0]
    return cv2.warpAffine(img, M, target_size, flags=cv2.INTER_LINEAR)


class GenD:
    def __init__(self, model_dir: Path, threads: int = 4, onnx_name: str = "gend_clip.onnx"):
        from transformers import CLIPImageProcessor
        self.det = SCRFD(model_dir / "det_10g.onnx", threads)
        self.sess = _ort_session(model_dir / onnx_name, threads)
        self.inp = self.sess.get_inputs()[0].name
        self.proc = CLIPImageProcessor.from_pretrained(str(model_dir / "clip_preprocessor"), local_files_only=True)

    def crop(self, rgb):
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        det, kps = self.det.detect(bgr)
        if len(det) == 0:
            return None, None
        i = int(np.argmax((det[:, 2] - det[:, 0]) * (det[:, 3] - det[:, 1])))   # largest face
        return cv2.cvtColor(gend_align(bgr, kps[i]), cv2.COLOR_BGR2RGB), det[i, :4]

    def frame_p(self, rgb):
        """-> (P(fake), box x0,y0,x1,y1 in px, aligned RGB crop) or (None, None, None) without a face."""
        crop, box = self.crop(rgb)
        if crop is None:
            return None, None, None
        px = self.proc(images=[crop], return_tensors="np")["pixel_values"].astype(np.float32)
        y = self.sess.run(None, {self.inp: px})[0][0].astype(np.float64)
        e = np.exp(y - y.max())
        return float(e[1] / e.sum()), [float(v) for v in box], crop


# ============================================================================================ DFDC B7 (ONNX)
def _iso_resize(img, size):
    h, w = img.shape[:2]
    if max(w, h) == size:
        return img
    if w > h:
        scale = size / w
        h, w = h * scale, size
    else:
        scale = size / h
        w, h = w * scale, size
    return cv2.resize(img, (int(w), int(h)), interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def _put_to_center(img, n):
    img = img[:n, :n]
    out = np.zeros((n, n, 3), dtype=np.uint8)
    sw, sh = (n - img.shape[1]) // 2, (n - img.shape[0]) // 2
    out[sh:sh + img.shape[0], sw:sw + img.shape[1], :] = img
    return out


class DFDCB7:
    MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(1, 3, 1, 1)
    STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(1, 3, 1, 1)

    def __init__(self, model_dir: Path, threads: int = 4):
        from ..vendor.facenet_pytorch import MTCNN
        self.mtcnn = MTCNN(margin=0, thresholds=[0.7, 0.8, 0.8], device="cpu")
        self.sess = _ort_session(model_dir / "dfdc_b7.onnx", threads)
        self.inp = self.sess.get_inputs()[0].name
        self._lock = threading.Lock()

    def crops(self, rgb):
        from PIL import Image
        img = Image.fromarray(rgb.astype(np.uint8))
        img = img.resize(size=[s // 2 for s in img.size])            # DFDC winner: MTCNN on the half-size frame
        with self._lock:
            boxes, _ = self.mtcnn.detect(img, landmarks=False)
        out = []
        if boxes is None:
            return out
        for bbox in boxes:
            if bbox is None:
                continue
            xmin, ymin, xmax, ymax = [int(b * 2) for b in bbox]
            p_h, p_w = (ymax - ymin) // 3, (xmax - xmin) // 3
            c = rgb[max(ymin - p_h, 0):ymax + p_h, max(xmin - p_w, 0):xmax + p_w]
            if c.size:
                out.append((_put_to_center(_iso_resize(c, 380), 380), [xmin, ymin, xmax, ymax]))
        return out

    def frame_p(self, rgb):
        cs = self.crops(rgb)
        if not cs:
            return None, None, None
        ps = []
        for c, _ in cs:
            x = (c.transpose(2, 0, 1)[None].astype(np.float32) / np.float32(255.0) - self.MEAN) / self.STD
            y = float(self.sess.run(None, {self.inp: np.ascontiguousarray(x)})[0][0, 0])
            ps.append(1 / (1 + math.exp(-y)))
        i = int(np.argmax(ps))                                         # frame score = max over faces
        return ps[i], [float(v) for v in cs[i][1]], cs[i][0]


# ======================================================================================================= API
class FaceSwapDetector:
    """detector = FaceSwapDetector(model_dir, use=("gend", "dfdc")); r = detector.analyze(list_of_rgb_frames)"""

    def __init__(self, model_dir, use=("gend", "dfdc"), threads: int = 4):
        t0 = time.perf_counter()
        model_dir = Path(model_dir)
        self.thr = dict(DEFAULT_THRESHOLDS)
        tf = model_dir / "thresholds.json"
        if tf.exists():
            t = json.loads(tf.read_text())
            t.pop("pair", None)          # legacy ambiguous key (fp32 and int8 pairs need different values) - ignored
            self.thr.update({k: v for k, v in t.items() if not k.startswith("_")})
        self.use = tuple(use)
        self.pair_key = "pair_" + "+".join(k for k in ("gend", "gend_int8", "dfdc") if k in use)
        self.models = {}
        if "gend" in use:
            self.models["gend"] = GenD(model_dir, threads, "gend_clip.onnx")
        if "gend_int8" in use:
            self.models["gend_int8"] = GenD(model_dir, threads, "gend_clip_int8.onnx")
        if "dfdc" in use:
            self.models["dfdc"] = DFDCB7(model_dir, threads)
        log.info("face-swap detector ready (%s) in %.1f s", "+".join(self.models), time.perf_counter() - t0)

    def warmup(self):
        """One dummy pass through every network (ONNX Runtime allocates its buffers on the first run), so the first
        visitor's video does not pay for it."""
        for k, m in self.models.items():
            if isinstance(m, GenD):
                m.det.session.run(m.det.output_names, {m.det.input_name: np.zeros((1, 3, 640, 640), np.float32)})
                m.sess.run(None, {m.inp: np.zeros((1, 3, 224, 224), np.float32)})
            else:
                m.sess.run(None, {m.inp: np.zeros((1, 3, 380, 380), np.float32)})
                from PIL import Image
                with m._lock:
                    m.mtcnn.detect(Image.new("RGB", (320, 240)), landmarks=False)

    def _z(self, probs: dict) -> tuple[float | None, int]:
        zs = [_logit(p) - _logit(self.thr[k]) for k, p in probs.items() if p is not None]
        if not zs:
            return None, 0
        z = float(np.mean(zs))
        if len(zs) > 1:                                  # ONLY when both models voted (verification fix 2)
            z -= _logit(self.thr[self.pair_key])         # the pair's own FF++-chosen threshold -> 50
        return z, len(zs)

    def analyze(self, frames_rgb) -> dict:
        per = {k: [] for k in self.models}
        boxes = {k: [] for k in self.models}
        crops = []
        for rgb in frames_rgb:
            gcrop = None
            for k, m in self.models.items():
                p, box, crop = m.frame_p(rgb)
                per[k].append(p)
                boxes[k].append(box)
                if crop is not None and (gcrop is None or k.startswith("gend")):
                    gcrop = crop
            crops.append(gcrop)
        clip = {k: (float(np.mean([p for p in v if p is not None])) if any(p is not None for p in v) else None)
                for k, v in per.items()}
        z, voters = self._z(clip)
        # per-frame display scores (same formula on one frame's probabilities; the verdict uses the clip means)
        frame_scores = []
        for i in range(len(frames_rgb)):
            zi, _ = self._z({k: per[k][i] for k in per})
            frame_scores.append(None if zi is None else 100.0 / (1.0 + math.exp(-zi)))
        return {"per_frame": per, "boxes": boxes, "crops": crops, "frame_scores": frame_scores, "clip_p": clip,
                "z": z, "voters": voters, "score": None if z is None else 100.0 / (1.0 + math.exp(-z)),
                "frames_with_face": {k: sum(p is not None for p in v) for k, v in per.items()},
                "thresholds": {k: self.thr[k] for k in list(self.models) + ([self.pair_key] if len(self.models) > 1 else [])}}


def pick_frames(n_sampled: int, n: int = N_FRAMES) -> list[int]:
    """Indices of the (up to) 8 evenly spaced frames among the engine's sampled frames."""
    if n_sampled <= 0:
        return []
    return sorted(set(np.linspace(0, n_sampled - 1, n).round().astype(int).tolist()))


def make_report_test(r: dict | None, times: list[float]) -> dict:
    """Turn FaceSwapDetector.analyze() output into the contract's test dict (status skipped without a face)."""
    from .. import charts, config
    from .base import make_test

    if r is None:
        return make_test("face_swap", NAME, "ai_model", status="error", score=None,
                         finding="Face-swap detector unavailable (model files missing).", explain=EXPLAIN)
    metrics = {"frames_scored": len(times)}
    short = {"gend": "GenD", "gend_int8": "GenD_int8", "dfdc": "B7"}
    for k, p in r["clip_p"].items():
        metrics[f"{short[k]}_mean_P(fake)"] = None if p is None else round(p, 4)
        metrics[f"{short[k]}_threshold_(FF++)"] = round(r["thresholds"][k], 4)
        metrics[f"{short[k]}_frames_with_face"] = r["frames_with_face"][k]
    if r["score"] is None:
        return make_test("face_swap", NAME, "ai_model", status="skipped", score=None,
                         finding="No face found by its face detectors in the sampled frames.", explain=EXPLAIN,
                         metrics=metrics)
    s = r["score"]
    sr = int(round(s))     # the report and the fusion use the rounded score: decide on that, so they agree at 50
    fs = [v for v in r["frame_scores"] if v is not None]
    n_fire = sum(v >= 50 for v in fs)
    if sr > config.THRESH_SYNTHETIC:
        finding = f"Face-swap traces: {n_fire} of {len(fs)} face frames above threshold."
    elif sr >= 50:
        finding = f"Weak face-swap traces in {n_fire} of {len(fs)} face frames."
    else:
        finding = "No face-swap traces found (this test only raises alarms)."
    metrics["networks_voting"] = r["voters"]
    metrics["z"] = round(r["z"], 4)
    metrics["one_sided"] = True
    visual = None
    try:
        visual = charts.faceswap_figure(r["crops"], r["frame_scores"], times, silent=sr < 50)
    except Exception as e:  # noqa: BLE001
        log.warning("face-swap visual failed: %s", e)
    t = make_test("face_swap", NAME, "ai_model", score=s, finding=finding, explain=EXPLAIN, visual=visual,
                  metrics=metrics)
    t["_onesided"] = True      # fusion: counts only when score >= 50 (removed by strip_private)
    return t
