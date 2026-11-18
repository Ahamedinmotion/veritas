"""Dense face tracking with MediaPipe FaceLandmarker (478 3-D landmarks + blendshapes per frame).
Shared by the blink, landmark-jitter and temporal-flicker tests."""
from __future__ import annotations

import logging

import cv2
import numpy as np

from ..models import new_landmarker

log = logging.getLogger("veritas.track")

# EAR points (p1..p6) per eye on the MediaPipe face mesh
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
# rigid-ish points used to cancel head motion before measuring jitter (no mouth / jaw)
STABLE = [33, 133, 362, 263, 1, 4, 5, 6, 168, 197, 195, 70, 63, 105, 66, 107, 336, 296, 334, 293, 300, 10, 151, 9,
          234, 454, 93, 323, 127, 356, 46, 276]


def ear(pts: np.ndarray, idx: list[int]) -> float:
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in idx)
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2.0 * np.linalg.norm(p1 - p4) + 1e-6))


def track(dense: list[tuple[float, np.ndarray]]) -> dict:
    """Returns per-frame arrays (NaN where no face): t, ear, blink_bs, iod, landmarks(px), face/bg luminance."""
    import mediapipe as mp

    n = len(dense)
    out = {
        "t": np.array([t for t, _ in dense]), "ear": np.full(n, np.nan), "blink_bs": np.full(n, np.nan),
        "iod": np.full(n, np.nan), "pts": [None] * n,
        "face_y": np.full(n, np.nan), "bg_y": np.full(n, np.nan), "face_c": np.full(n, np.nan), "bg_c": np.full(n, np.nan),
        "box": [None] * n,
    }
    lm = new_landmarker(video=True)
    if lm is None:
        out["error"] = "landmarker model missing"
        return out
    try:
        last_ts = -1
        for i, (t, rgb) in enumerate(dense):
            ts = max(last_ts + 1, int(t * 1000))
            last_ts = ts
            res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)), ts)
            if not res.face_landmarks:
                continue
            H, W = rgb.shape[:2]
            pts = np.array([[p.x * W, p.y * H] for p in res.face_landmarks[0]], dtype=np.float32)
            out["pts"][i] = pts
            out["ear"][i] = 0.5 * (ear(pts, LEFT_EYE) + ear(pts, RIGHT_EYE))
            out["iod"][i] = float(np.linalg.norm(pts[33] - pts[263]))
            if res.face_blendshapes:
                bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
                out["blink_bs"][i] = 0.5 * (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0))
            # luminance / chroma inside the face hull vs. the background outside an enlarged box
            ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32)
            hull = cv2.convexHull(pts.astype(np.int32))
            fm = np.zeros((H, W), np.uint8)
            cv2.fillConvexPoly(fm, hull, 1)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            cx, cy, bw, bh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0), (y1 - y0)
            out["box"][i] = (x0 / W, y0 / H, bw / W, bh / H)
            bm = np.ones((H, W), np.uint8)
            ex0, ey0 = int(max(0, cx - bw * 0.95)), int(max(0, cy - bh * 1.0))
            ex1, ey1 = int(min(W, cx + bw * 0.95)), int(min(H, cy + bh * 1.6))
            bm[ey0:ey1, ex0:ex1] = 0
            if bm.sum() < 0.04 * H * W:  # close-up: background = everything outside a dilated face hull
                k = max(3, int(bw * 0.25)) | 1
                bm = (cv2.dilate(fm, np.ones((k, k), np.uint8)) == 0).astype(np.uint8)
            if fm.sum() > 50:
                out["face_y"][i] = float(ycc[..., 0][fm > 0].mean())
                out["face_c"][i] = float(ycc[..., 1][fm > 0].mean() + ycc[..., 2][fm > 0].mean())
            if bm.sum() > 500:
                out["bg_y"][i] = float(ycc[..., 0][bm > 0].mean())
                out["bg_c"][i] = float(ycc[..., 1][bm > 0].mean() + ycc[..., 2][bm > 0].mean())
    finally:
        lm.close()
    return out
