"""AI face detector: find faces (YuNet), crop each with context, score with a pretrained classifier."""
from __future__ import annotations

import numpy as np
from PIL import Image

from .. import charts, config
from ..models import REGISTRY, face_crop
from .base import calibrated, make_test

NAME = "AI Face Analysis"
MIN_CONF = 0.85     # YuNet confidence
MIN_REL = 0.08      # face size as a fraction of the picture's shorter side
MIN_PX = 48
EXPLAIN = ("A small neural network (YuNet) finds each face; the same AI-image detector is then zoomed onto a "
           "crop of that face. It reliably catches faces that were generated whole (GANs, diffusion), but it was "
           "not trained on face-swaps or lip-sync, so a well-blended swap of a real face can pass as real.")


def detect_and_score(rgb: np.ndarray, max_faces: int = 4) -> list[dict]:
    """Returns [{box(px), box_norm, p, score, crop}] largest face first."""
    det, clf = REGISTRY.face_detector, REGISTRY.face_deepfake
    if det is None or clf is None:
        return []
    H, W = rgb.shape[:2]
    faces = det.detect(rgb, max_faces=max_faces)
    # only score faces big and clear enough for the classifier to see skin detail: tiny or low-confidence
    # detections are usually background blobs, and a 40 px face crop carries no reliable evidence
    faces = [f for f in faces if f["conf"] >= MIN_CONF and max(f["box"][2], f["box"][3]) >= MIN_REL * min(W, H)
             and max(f["box"][2], f["box"][3]) >= MIN_PX]
    if not faces:
        return []
    crops = [face_crop(rgb, f["box"]) for f in faces]
    probs = clf.predict([Image.fromarray(c) for c in crops])
    out = []
    for f, c, p in zip(faces, crops, probs):
        x, y, w, h = f["box"]
        out.append({"box": f["box"], "box_norm": [x / W, y / H, w / W, h / H], "p": p,
                    "score": calibrated("ai_face", p * 100), "crop": c, "conf": f["conf"]})
    return out


def summarise(faces: list[dict]) -> float:
    """Image-level face score: area-weighted toward the largest faces, but one very fake face counts."""
    if not faces:
        return None
    areas = np.array([f["box"][2] * f["box"][3] for f in faces], dtype=float)
    s = np.array([f["score"] for f in faces], dtype=float)
    weighted = float((areas * s).sum() / areas.sum())
    return max(weighted, float(s.max()) * 0.85)


def run(img: Image.Image) -> tuple[dict, list[dict]]:
    if REGISTRY.face_deepfake is None or REGISTRY.face_detector is None:
        t = make_test("ai_face", NAME, "ai_model", status="error", score=None,
                      finding="Face model is not installed on this computer.", explain=EXPLAIN)
        return t, []
    rgb = np.asarray(img)
    faces = detect_and_score(rgb)
    if not faces:
        t = make_test("ai_face", NAME, "ai_model", status="skipped", score=None,
                      finding="No clear face found, so the face test does not apply.", explain=EXPLAIN,
                      metrics={"faces": 0})
        return t, []
    score = summarise(faces)
    visual = charts.face_strip([f["crop"] for f in faces], [f["score"] for f in faces])
    n = len(faces)
    worst = max(f["score"] for f in faces)
    if score > config.THRESH_SYNTHETIC:
        finding = ("The face shows synthetic skin and detail patterns." if n == 1
                   else f"{sum(f['score'] > config.THRESH_SYNTHETIC for f in faces)} of {n} faces look machine-made.")
    elif score >= config.THRESH_SUSPICIOUS:
        finding = "Face is borderline: some synthetic cues, not conclusive."
    else:
        finding = "Face looks like a real camera capture." if n == 1 else f"All {n} faces look like real camera captures."
    t = make_test("ai_face", NAME, "ai_model", score=score, finding=finding, explain=EXPLAIN, visual=visual,
                  metrics={"faces": n, "max_face_score": worst, "p_fake_max": max(f["p"] for f in faces),
                           "detector": REGISTRY.face_detector.kind, "model": REGISTRY.face_deepfake.repo.split("/")[-1],
                           "raw": max(f["p"] for f in faces) * 100})
    t["_faces_raw"] = [(float(f["p"]), float(f["box"][2] * f["box"][3])) for f in faces]  # for fast re-calibration
    faces_out = [{"box": [round(v, 4) for v in f["box_norm"]], "score": int(round(f["score"]))} for f in faces]
    return t, faces_out
