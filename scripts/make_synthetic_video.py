"""Make a 'talking photo'-style synthetic video from an AI-generated (StyleGAN) face.

Scam videos often animate a single AI-generated portrait with a slow camera move. This script does exactly
that - smooth zoom, drift and slight head tilt, no blinking - so the lab's video tests (AI face per frame,
blink rate, landmark jitter, flicker) can be demonstrated on a video that involves NO real person.

    uv run python scripts/make_synthetic_video.py IN_FACE.jpg OUT.mp4 [--seconds 12] [--seed 1]
"""
from __future__ import annotations

import argparse
import math

import av
import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("face")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--size", type=int, default=720)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    img = cv2.cvtColor(cv2.imread(a.face), cv2.COLOR_BGR2RGB)
    H, W = img.shape[:2]
    out = av.open(a.out, "w")
    st = out.add_stream("libx264", rate=a.fps)
    st.width = st.height = a.size
    st.pix_fmt = "yuv420p"
    st.options = {"crf": "19", "preset": "medium"}
    n = int(a.seconds * a.fps)
    ph = rng.uniform(0, 2 * math.pi, 4)
    for i in range(n):
        t = i / a.fps
        zoom = 1.05 + 0.10 * (t / a.seconds) + 0.008 * math.sin(2 * math.pi * 0.23 * t + ph[0])
        ang = 1.6 * math.sin(2 * math.pi * 0.11 * t + ph[1])
        dx = 10 * math.sin(2 * math.pi * 0.07 * t + ph[2])
        dy = 6 * math.sin(2 * math.pi * 0.09 * t + ph[3]) - 8 * (t / a.seconds)
        M = cv2.getRotationMatrix2D((W / 2, H / 2 * 0.95), ang, zoom)
        M[0, 2] += dx
        M[1, 2] += dy
        fr = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
        fr = cv2.resize(fr, (a.size, a.size), interpolation=cv2.INTER_AREA)
        for pkt in st.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(fr), format="rgb24")):
            out.mux(pkt)
    for pkt in st.encode():
        out.mux(pkt)
    out.close()
    print("wrote", a.out, n, "frames")


if __name__ == "__main__":
    main()
