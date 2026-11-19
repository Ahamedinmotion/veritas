---
title: VERITAS
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
short_description: Student deepfake forensics lab - photos, voices, videos
pinned: false
---

# VERITAS: Deepfake Forensics Lab (online engine)

VERITAS is a student science-fair project for INFINIA 2026 by Khais Mohammed and Prithvi ({{SCHOOL}}).
It checks a photo, a voice clip or a short video with a set of independent forensic tests and pretrained networks,
then combines their scores into one verdict: **authentic** (score below 35), **suspicious** (35-65) or **synthetic** (above 65).

This Space runs the same engine as our booth laptop and serves the whole site:

- the story: {{SPACE_URL}}/
- the lab: {{SPACE_URL}}/lab.html
- the API: `GET /api/health`, `POST /api/analyze/{image|audio|video}` (multipart field `file`)
- the main website: {{SITE_URL}}
- the code: https://github.com/Ahamedinmotion/veritas

## Online limits

| kind | largest file | longest clip |
|---|---|---|
| photo | 15 MB | - |
| voice | 20 MB | 60 s (the engine listens to the first 30 s) |
| video | 40 MB | 30 s (the engine watches the first 20 s) |

One analysis runs at a time. When several people use it at once, a request waits in a short queue or gets a
"busy, try again in a minute" answer. This Space runs on 2 CPU cores (cpu-basic), so a video takes much longer here
than on our laptop. If the Space is asleep or busy, the lab switches to showcase mode: the Evidence-locker exhibits open their
real saved engine reports.

## Privacy

Uploaded files are analysed in memory and are never saved. Please only upload media you are allowed to share, and
never pictures or recordings of other people without their permission.

## Please read the results with care

VERITAS can be wrong in both directions. Our measured accuracy and its limits are in the story (chapter 06) and in
the repository (`web/data/results.json`, `docs/MODEL_SELECTION.md`, `docs/JUDGE_QA.md`). A few examples: on held-out
photos it flagged 0 of 49 real images but missed 9 of 55 fakes; of 39 real video clips degraded like a cheap webcam,
11 came out "suspicious" and 1 "synthetic" (false alarms from the face-swap detector on grainy video); and it missed
4 of 6 fake voices from generators never used for tuning. A verdict is evidence to think about, not proof.

## Engine settings on this Space

Set in the `Dockerfile`: `VERITAS_ONLINE=1` (upload limits, queue, no storage), `VERITAS_THREADS=2`,
`VERITAS_FACESWAP=int8` and `VERITAS_VIDEO_FRAMES=32`.

- **Face-swap detector: GenD int8 + DFDC-B7.** The int8 version of GenD is about twice as fast on 2 CPU cores
  (a 10 s video: 15-18 s instead of 29-40 s in our 2-core test). This Space's CPUs are slower, so we expect roughly a
  minute for a 10 s video here (an estimate from that test). Our published video results were measured with the full-precision (fp32) pair; int8 gives slightly
  different scores and can flip borderline clips. Every Evidence-locker exhibit keeps its verdict and score (within
  1 point) in int8. To switch to fp32, set the Space variable `VERITAS_FACESWAP=fp32`.
- **32 face frames per video**, as on most laptops (a fast laptop uses 48, which can move a video score by a few
  points). A 10 s clip yields fewer than 32 sampled frames anyway.

## Models (all pretrained, published by their authors)

- CommunityForensics ViT (Park & Owens, CVPR 2025, MIT): AI-generated images and faces
- wav2vec2-base-960h fine-tuned on In-the-Wild deepfake speech (abhishtagatya, Apache-2.0) + our voice probe
- GenD CLIP ViT-L/14 (Yermakov et al., WACV 2026, MIT) and the Deepfake Detection Challenge 1st-place EfficientNet-B7
  (Selim Seferbekov 2020, MIT): video face-swaps. Our ONNX exports are mirrored at
  https://huggingface.co/Ahamedinmotion42/veritas-models
- Face finders: YuNet (OpenCV Zoo, MIT), MediaPipe Face Landmarker (Apache-2.0), SCRFD det_10g (InsightFace,
  non-commercial research licence; downloaded from the official InsightFace release)

No research-dataset media (FaceForensics++, Celeb-DF, Google DFD) is included in this Space.

## Redeploy

From the `veritas/` folder of the repository: `.venv/bin/python scripts/build_hf_space.py --wait`
(re-assembles this Space from the working tree, uploads it and waits until it is running).
