---
license: mit
library_name: onnx
pipeline_tag: image-classification
tags:
  - deepfake-detection
  - face-forgery-detection
  - onnx
  - clip
  - efficientnet
---

# VERITAS model mirror: GenD + DFDC-B7 face-swap detectors (ONNX)

This repository mirrors **ONNX exports of two published, pretrained, MIT-licensed deepfake detectors**. It exists so
that the setup of [VERITAS](https://github.com/Ahamedinmotion/veritas), a student deepfake-forensics lab built for the
INFINIA 2026 school science fair (team: Khais Mohammed and Prithvi), can download verified files instead of rebuilding
them from the original PyTorch checkpoints on every laptop.

**We did not train these networks.** All credit for the weights goes to their original authors (below). The files
were **exported to ONNX by the VERITAS team; numerically checked against the originals.**

## Files

| file | what it is | size (bytes) | SHA-256 |
|---|---|---|---|
| `gend_clip.onnx` | GenD, CLIP ViT-L/14 vision tower + GenD head, fp32 (exact published weights) | 1,212,926,317 | `371b05b7c3e66d6998313406a4d1fb5610cb195fe87634c1b1c842981364889f` |
| `gend_clip_int8.onnx` | the same network, dynamic int8 quantisation (ONNX Runtime), an optional low-RAM fallback | 308,306,010 | `4234075cd6dc79e8be489944b057ba062bd4431d7417e18df1f415628c529e9e` |
| `dfdc_b7.onnx` | DFDC first-place EfficientNet-B7, one of its 7 published checkpoints, fp32 | 254,811,737 | `6c14e1dae05a7ed999c971e581f620f7fe9f677d9e605307c006978a818bd7f1` |

Nothing else is mirrored here: no face detector (VERITAS downloads InsightFace's SCRFD `det_10g.onnx` from the
official InsightFace release, because its licence is non-commercial research only), no other model and no images,
audio or video.

## The original models

**GenD** - "Deepfake Detection that Generalizes Across Benchmarks", Andrii Yermakov, Jan Cech, Jiri Matas, Mario
Fritz, WACV 2026. Code: https://github.com/yermandy/GenD . Weights: https://huggingface.co/yermandy/GenD_CLIP_L_14
(revision `891ce014a0308386c4d7d25b3dcf436a22db5504`, `model.safetensors`, SHA-256
`d76f0bdfd74a29fe1b1c1b84a80ac92486993e426878e8c7a3944281fbb96833`). Licence: MIT. Trained by its authors on the
FaceForensics++ training split (FaceForensics++ terms of use apply to that data). Architecture: the CLIP ViT-L/14
vision tower (configuration of `openai/clip-vit-large-patch14`, MIT); every weight comes from GenD's checkpoint.

**DFDC-B7** - the 1st-place solution of the Deepfake Detection Challenge (2020) by **Selim Seferbekov**.
Code and weights: https://github.com/selimsef/dfdc_deepfake_challenge (release 0.0.1, checkpoint
`final_999_DeepFakeClassifier_tf_efficientnet_b7_ns_0_23`, SHA-256
`849036dc211387420412feb68c7451e98a948072b94e213e1104e2f2bf7791ad`). Licence: MIT. Trained by its author on the DFDC
training set (DFDC research terms apply to that data). Architecture: `tf_efficientnet_b7_ns` from timm.

## How the files were made and checked

`scripts/export_faceswap_onnx.py` in the VERITAS repository downloads the original checkpoints from the pinned URLs
above (SHA-256 checked), rebuilds the networks, exports them with `torch.onnx` (torch 2.15.0, onnx 1.23.2,
timm 1.0.31) and checks the result on fixed inputs against reference logits recorded from the PyTorch originals
(tolerance 2e-3 logit units). In our benchmark the ONNX outputs matched PyTorch within 2.4e-6 (GenD) and 5e-7 (B7)
logit units. With the locked torch version the rebuild is byte-identical to the files here. The int8 file was made
from `gend_clip.onnx` with ONNX Runtime dynamic quantisation (`quantize_dynamic`: int8 per-channel weights,
MatMul layers only); it is not numerically identical to fp32, and in our
tests its decisions jittered on borderline clips, so VERITAS uses fp32 by default.

## Inputs and outputs

| file | input `x` | output `y` |
|---|---|---|
| `gend_clip*.onnx` | float32 `[1, 3, 224, 224]`: a face aligned with 5 SCRFD landmarks (GenD's alignment, scale 1.3), RGB, CLIP preprocessing (resize 224 bicubic, centre crop, mean `[0.48145466, 0.4578275, 0.40821073]`, std `[0.26862954, 0.26130258, 0.27577711]`) | `[1, 2]` logits; softmax index 1 = P(fake) |
| `dfdc_b7.onnx` | float32 `[1, 3, 380, 380]`: an MTCNN face box with 1/3 margin, longest side resized to 380 and centred on black, RGB / 255, ImageNet mean `[0.485, 0.456, 0.406]` / std `[0.229, 0.224, 0.225]` | `[1, 1]` logit; sigmoid = P(fake) |

The full pre-processing, face detection and score fusion are in `server/forensics/face_swap.py` of the VERITAS repository.

## How VERITAS uses them, and the limits

VERITAS benchmarked six published face-swap detectors on 75 research clips (FaceForensics++ test split, Celeb-DF v2
test list, Google DFD) and integrated this pair. Each network scores 8 evenly spaced video frames; the thresholds were
chosen on the 45 FaceForensics++ test clips only. The test is one-sided in VERITAS: it may raise an alarm, but it
never vouches that a face is real, because both networks call fully generated (GAN) faces "real".

Please read the numbers with care (details in `docs/MODEL_SELECTION.md` of the repository):

- The pair was chosen **after** seeing its results on the Celeb-DF + DFD clips (datasets neither network was trained
  on), so its 0.998 AUC there (whole engine, 15 real + 15 fake clips) is optimistic. GenD's authors also used
  Celeb-DF++ validation videos to pick their checkpoint, so only Google DFD is fully unseen.
- It raises **false alarms on grainy, heavily compressed real video**: on its own it fired on 21 of 39 real clips
  degraded like a cheap webcam.
- It is meant for videos, not single photos.

These files are provided as-is for research and education, under the MIT licences of the original works.

## Licences

- GenD weights: MIT (c) the GenD authors. ONNX exports of them (`gend_clip.onnx`, `gend_clip_int8.onnx`): MIT.
- DFDC-B7 weights: MIT (c) 2020 Selim Seferbekov. ONNX export (`dfdc_b7.onnx`): MIT.
- The training data of both networks (FaceForensics++, DFDC) has its own research terms; no data is included here.
