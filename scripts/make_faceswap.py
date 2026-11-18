"""Build classical face-swap composites for the evaluation set and the demo samples.

Technique (the "classic deepfake pipeline", no neural face-swapper):
  1. MediaPipe FaceLandmarker finds 478 landmarks on a SOURCE face and a TARGET photo.
  2. The source face is warped onto the target, triangle by triangle (Delaunay triangulation).
  3. Colours are matched and the face is blended in with Poisson (seamless) cloning.

Ethics: the SOURCE faces are StyleGAN faces of people who do not exist (thispersondoesnotexist), so every
composite shows a non-existent identity. No real person's face is ever put on anyone else.

    uv run python scripts/make_faceswap.py --n 16                     # eval_data/images/fake/swap_*.jpg
    uv run python scripts/make_faceswap.py --video IN.mp4 --face F.jpg --out OUT.mp4   # face-swap a video
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVAL = ROOT / "eval_data"

# outer face oval of the MediaPipe mesh (used for the blend mask)
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176,
             149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]


def landmarker():
    from mediapipe.tasks.python import BaseOptions, vision

    data = (ROOT / "models/face_landmarker/face_landmarker.task").read_bytes()
    return vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_buffer=data), running_mode=vision.RunningMode.IMAGE, num_faces=1))


def landmarks(lm, rgb):
    import mediapipe as mp

    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    if not res.face_landmarks:
        return None
    H, W = rgb.shape[:2]
    return np.array([[p.x * W, p.y * H] for p in res.face_landmarks[0]], dtype=np.float32)


_TRI = None


def triangles(pts):
    global _TRI
    if _TRI is None:
        rect = (0, 0, int(pts[:, 0].max()) + 10, int(pts[:, 1].max()) + 10)
        sub = cv2.Subdiv2D(rect)
        for p in pts[:468]:
            sub.insert((float(p[0]), float(p[1])))
        tri = []
        lookup = {(round(float(p[0]), 2), round(float(p[1]), 2)): i for i, p in enumerate(pts[:468])}
        for t in sub.getTriangleList():
            ids = []
            for k in range(3):
                key = (round(float(t[2 * k]), 2), round(float(t[2 * k + 1]), 2))
                if key in lookup:
                    ids.append(lookup[key])
            if len(ids) == 3:
                tri.append(ids)
        _TRI = tri
    return _TRI


def warp_face(src, sp, dst_shape, dp, tri):
    out = np.zeros(dst_shape, dtype=np.float32)
    for a, b, c in tri:
        t1 = np.float32([sp[a], sp[b], sp[c]])
        t2 = np.float32([dp[a], dp[b], dp[c]])
        r1 = cv2.boundingRect(t1)
        r2 = cv2.boundingRect(t2)
        if r1[2] <= 0 or r1[3] <= 0 or r2[2] <= 0 or r2[3] <= 0:
            continue
        t1o = np.float32(t1 - np.float32(r1[:2]))
        t2o = np.float32(t2 - np.float32(r2[:2]))
        patch = src[r1[1]:r1[1] + r1[3], r1[0]:r1[0] + r1[2]]
        if patch.size == 0:
            continue
        M = cv2.getAffineTransform(t1o, t2o)
        warped = cv2.warpAffine(patch.astype(np.float32), M, (r2[2], r2[3]), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REFLECT_101)
        mask = np.zeros((r2[3], r2[2], 3), dtype=np.float32)
        cv2.fillConvexPoly(mask, np.int32(t2o), (1.0, 1.0, 1.0), 16, 0)
        y0, x0 = r2[1], r2[0]
        y1, x1 = min(dst_shape[0], y0 + r2[3]), min(dst_shape[1], x0 + r2[2])
        if y1 <= y0 or x1 <= x0 or y0 < 0 or x0 < 0:
            continue
        region = out[y0:y1, x0:x1]
        m = mask[: y1 - y0, : x1 - x0]
        region[:] = region * (1 - m) + warped[: y1 - y0, : x1 - x0] * m
    return out


def swap(src_rgb, sp, dst_rgb, dp):
    tri = triangles(sp)
    warped = np.clip(warp_face(src_rgb, sp, dst_rgb.shape, dp, tri), 0, 255).astype(np.uint8)
    hull = cv2.convexHull(np.int32(dp[FACE_OVAL]))
    mask = np.zeros(dst_rgb.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)
    mask = cv2.erode(mask, np.ones((5, 5), np.uint8), iterations=2)
    # colour transfer in LAB inside the mask
    m = mask > 0
    w_lab = cv2.cvtColor(warped, cv2.COLOR_RGB2LAB).astype(np.float32)
    d_lab = cv2.cvtColor(dst_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    for c in range(3):
        ws, ds = w_lab[..., c][m], d_lab[..., c][m]
        w_lab[..., c] = (w_lab[..., c] - ws.mean()) / (ws.std() + 1e-6) * ds.std() + ds.mean()
    warped = cv2.cvtColor(np.clip(w_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    x, y, w, h = cv2.boundingRect(hull)
    center = (x + w // 2, y + h // 2)
    out = cv2.seamlessClone(cv2.cvtColor(warped, cv2.COLOR_RGB2BGR), cv2.cvtColor(dst_rgb, cv2.COLOR_RGB2BGR), mask,
                            center, cv2.NORMAL_CLONE)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def yaw(pts) -> float:
    """Crude head-turn measure: nose-tip offset from the eye midpoint, in eye-distances."""
    mid = (pts[33] + pts[263]) / 2
    return float((pts[1][0] - mid[0]) / (np.linalg.norm(pts[263] - pts[33]) + 1e-6))


def read_rgb(p):
    return cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)


def make_images(n: int):
    lm = landmarker()
    src_meta = json.loads((EVAL / "sources.json").read_text())
    targets = [p for p in sorted((EVAL / "images/real").glob("ffhq_*"))] + \
              [p for p in sorted((EVAL / "images/real").glob("coco_*")) if src_meta.get(f"images/real/{p.name}", {}).get("group") == "scene_people"]
    sources = sorted((EVAL / "images/fake").glob("tpdne_*"))
    rnd = random.Random(7)
    rnd.shuffle(targets)
    rnd.shuffle(sources)
    made = 0
    for tp in targets:
        if made >= n:
            break
        dst = read_rgb(tp)
        dp = landmarks(lm, dst)
        if dp is None or np.linalg.norm(dp[33] - dp[263]) < 40 or abs(yaw(dp)) > 0.15:
            continue  # need a fairly frontal target face, otherwise the warp tears
        for _ in range(12):
            sp_path = sources[rnd.randrange(len(sources))]
            src = read_rgb(sp_path)
            sp = landmarks(lm, src)
            if sp is not None and abs(yaw(sp) - yaw(dp)) < 0.08:
                break
        else:
            continue
        try:
            out = swap(src, sp, dst, dp)
        except cv2.error:
            continue  # face touches the image border - Poisson blending needs a margin
        name = f"swap_{tp.stem}__{sp_path.stem}.jpg"
        op = EVAL / "images/fake" / name
        cv2.imwrite(str(op), cv2.cvtColor(out, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        src_meta[f"images/fake/{name}"] = {
            "label": "fake", "group": "face_swap", "generator": "classic landmark face-swap (Delaunay warp + Poisson blend)",
            "source": f"made by scripts/make_faceswap.py: GAN face {sp_path.name} onto real photo {tp.name}",
            "licence": "derived from the two source images (see their licences)"}
        made += 1
        print("made", name, flush=True)
    (EVAL / "sources.json").write_text(json.dumps(src_meta, indent=1, sort_keys=True))


def make_video(inp: str, face: str, out: str, max_s: float = 20.0):
    import av

    lm = landmarker()
    src = read_rgb(face)
    sp = landmarks(lm, src)
    assert sp is not None, "no face in source image"
    cin = av.open(inp)
    vs = cin.streams.video[0]
    fps = float(vs.average_rate or 25)
    cout = av.open(out, "w")
    so = cout.add_stream("libx264", rate=int(round(fps)))
    so.pix_fmt = "yuv420p"
    so.options = {"crf": "20", "preset": "medium"}
    first = True
    n = 0
    for frame in cin.decode(vs):
        if frame.time is not None and frame.time > max_s:
            break
        rgb = frame.to_ndarray(format="rgb24")
        if first:
            so.width, so.height = rgb.shape[1] // 2 * 2, rgb.shape[0] // 2 * 2
            first = False
        dp = landmarks(lm, rgb)
        if dp is not None:
            try:
                rgb = swap(src, sp, rgb, dp)
            except Exception as e:  # noqa: BLE001
                print("frame swap failed", e)
        rgb = np.ascontiguousarray(rgb[: so.height, : so.width])
        for pkt in so.encode(av.VideoFrame.from_ndarray(rgb, format="rgb24")):
            cout.mux(pkt)
        n += 1
    for pkt in so.encode():
        cout.mux(pkt)
    cout.close()
    print("wrote", out, n, "frames")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--video")
    ap.add_argument("--face")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.video:
        make_video(a.video, a.face, a.out)
    else:
        make_images(a.n)
