# How we chose the AI models (the experiment behind the engine)

We did not pick models by popularity. Every candidate was downloaded and run on our **calibration split**
(40% of `eval_data/`). The **held-out test split** (60%) was never used for any choice; its numbers are in
`web/data/results.json`. Script: `scripts/compare_models.py`.

*Note (18 Nov, after review):* the model comparison below ran on the first version of the split, which was chosen
per file (58 calibration images, 54 calibration clips). The split is now **group-aware** - a speaker, a text prompt
or a face-swap and its source photos never sit on both sides - and has 67 calibration images and 70 calibration
clips (24 extra LibriSpeech speakers, 24 FLEURS voices and 24 vocoder-resynthesised LibriSpeech clips were added). The model ranking is so lopsided that this
does not change the choice; all calibration curves and results were re-fitted on the new split.

AUC = area under the ROC curve: the probability that a randomly chosen fake gets a higher score than a randomly
chosen real file. 0.5 = coin toss, 1.0 = perfect.

## Images - 12 candidates (58 calibration images at the time: FFHQ/COCO real vs StyleGAN + DALL-E 3/FLUX/Midjourney/SD)

"orig" = files as downloaded, "laund" = all files re-encoded identically (JPEG q90, metadata stripped).
"face" = classifier run on the face crop found by YuNet, instead of the whole image.

| Model (Hugging Face) | Size MB | ms/img (M4 CPU) | AUC whole orig | AUC whole laund | AUC face orig | AUC face laund |
|---|---|---|---|---|---|---|
| **buildborderless/CommunityForensics-DeepfakeDet-ViT** | **87** | **41** | **1.000** | **0.999** | **0.973** | **0.971** |
| Organika/sdxl-detector | 347 | 131 | 0.859 | 0.825 | 0.749 | 0.730 |
| Smogy/SMOGY-Ai-images-detector | 347 | 73 | 0.853 | 0.808 | 0.698 | 0.745 |
| Ateeqq/ai-vs-human-image-detector | 372 | 74 | 0.852 | 0.845 | 0.703 | 0.703 |
| haywoodsloan/ai-image-detector-deploy | 781 | 623 | 0.821 | 0.857 | 0.671 | 0.695 |
| aaronkantrowitz/ai-image-detection | 343 | 44 | 0.635 | 0.632 | 0.607 | 0.612 |
| prithivMLmods/open-deepfake-detection | 372 | 44 | 0.584 | 0.591 | 0.658 | 0.674 |
| prithivMLmods/Deep-Fake-Detector-v2-Model | 343 | 52 | 0.576 | 0.575 | 0.588 | 0.586 |
| umm-maybe/AI-image-detector | 348 | 92 | 0.514 | 0.575 | 0.666 | 0.698 |
| dima806/ai_vs_human_generated_image_detection | 343 | 86 | 0.510 | 0.504 | 0.340 | 0.332 |
| Wvolf/ViT_Deepfake_Detection | 343 | 70 | 0.400 | 0.409 | 0.457 | 0.471 |
| dima806/deepfake_vs_real_image_detection | 343 | 37 | 0.394 | 0.398 | 0.428 | 0.447 |

**Decision.** CommunityForensics ViT-Small (Park & Owens, *Community Forensics: Using Thousands of Generators to
Train Fake Image Detectors*, CVPR 2025) won on every column while being the smallest and fastest. It is used
twice: on the whole image (`ai_generated`) and zoomed in on each face crop (`ai_face`, one shared copy in RAM).

**Lesson worth telling the judges.** The popular "deepfake face" classifiers on Hugging Face scored at or below
coin-toss level (AUC 0.39-0.59) on modern AI faces. They were trained on one older face-swap dataset and learnt
its quirks, not the general idea of "synthetic". The winner was trained on images from 4,803 different
generators - diversity of training data beats model size.

**But know its limits.** It is a *general AI-image* detector. It reliably catches pictures and faces that were
generated whole (GANs, diffusion), but it was never trained on face-swaps, face reenactment or lip-sync, and on
the external research videos (FaceForensics++, Google DFD, Celeb-DF, Wav2Lip) it missed most of them. Heavily
smoothed or compressed real frames (webcams, video stills, phone "beauty" filters) can also look "too clean" to
it; that is why its calibration curve is now fitted on degraded copies too (see results.json `robustness`).

## Audio - 7 candidates (54 calibration clips at the time)

| Model | Size MB | Calibration AUC | Notes |
|---|---|---|---|
| **abhishtagatya/wav2vec2-base-960h-itw-deepfake** | **378** | **0.733** | fine-tuned on In-the-Wild deepfake speech; ~1.6 s per clip |
| garystafford/wav2vec2-deepfake-voice-detector | 1263 | 0.690 | XLS-R large, ~15 s per clip on CPU, flagged real audiobook speech as fake |
| mo-thecreator/Deepfake-audio-detection | 378 | 0.683 | |
| Vansh180/deepfake-audio-wav2vec2 | 378 | 0.558 | |
| MelodyMachine/Deepfake-audio-detection-V2 | 378 | 0.456 | |
| Gustking/wav2vec2-large-xlsr-deepfake-audio-classification | 1263 | not finished | too slow for a booth laptop (stopped) |
| DavidCombei/wavLM-base-Deepfake_V2 | 378 | - | label meaning undocumented (LABEL_0/LABEL_1), excluded |

None of the off-the-shelf heads was good enough (best 0.73). So we used **transfer learning**: we keep the best
network's early layer-4 features (768 numbers per 4-second window that describe fine acoustic texture) and train
a tiny logistic-regression "probe" on the calibration clips only. The layer was chosen by 5-fold cross-validation
*inside* the calibration split: layer 4 AUC 0.94, layer 8 0.83, layer 12 0.77 (early layers keep vocoder
artefacts; late layers have specialised to the network's original training data).
Robustness check: re-encoding every clip to the same MP3 codec before feature extraction did not change the result,
so the probe is not just detecting file formats. **However**, it does learn *which dataset* a clip came from: when a
whole source family is left out of training, its AUC on that family drops to chance (0.50-0.60) for two of three
families (see results.json `audio.generalisation`). The honest headline for the voice test is therefore the external
spot check (`audio.external`: generators never used for tuning, though LibriSpeech speaker 260 and the HiFi-GAN vocoder
type are in the calibration split): fakes caught 2 of 6, real voices cleared 4 of 4 - not the in-distribution
held-out accuracy.

## Classic forensic tests

ELA, noise, FFT and JPEG-table tests are physics/signal-processing methods, not trained networks. On the
calibration split we found that, for whole AI-generated images, the useful signal is the *absence* of camera
traces (weak, uneven sensor noise; too little fine high-frequency detail). We therefore fitted two tiny
logistic models (2-3 numbers each) on calibration data for the noise and FFT tests, and kept ELA as a pure
splice detector. Their held-out AUCs are reported honestly in `results.json` (`per_test`). Tested on a hand-made
splice (an AI region pasted into a real phone photo), the ELA *map* shows the pasted square clearly to a human eye,
but none of the classic *scores* caught it - we tried a JPEG-ghost and a block-grid-alignment detector as well,
and on our test images neither separated splices from ordinary photos reliably, so they were not shipped.
For voices, the pitch (prosody) and spectral cut-off tests scored at chance level (AUC 0.52 and 0.42); they are
now shown as charts ("visual evidence") but carry no weight.

## Fusion

Each test score is converted to log-odds and combined as a weighted vote (AI models carry ~70% of the weight;
classic tests ~30%). A classic test is amplified up to 3x only for *specific* evidence - a localised grain
mismatch, a periodic up-sampling grid, an AI-tool tag, a frozen face, a missing blink - never for vague "too smooth"
evidence, which phone denoising, webcams and video compression also produce. The fusion weights and the classic
tests' thresholds were set by hand (not fitted). A gain and bias are fitted on the
calibration split for images; for audio they are left neutral because the probe was trained on the same clips.
Details: `server/fusion.py`, fitted numbers: `server/calibration.json`.

## Video face-swaps - 6 published detectors (benchmark of 19 Nov 2026)

**Why.** The engine's video face test reuses the general AI-image network. On real research deepfakes it was close to
a coin toss (AUC 0.60 on Celeb-DF + Google DFD), because it was never trained on face-swaps, reenactment or lip-sync.
We did not train a new detector: we **benchmarked six published, pretrained face-swap detectors** on a test set we
built, then integrated a pair of them (GenD + the DFDC winner; see "Decision" for why not the rule's winner). Full report: `../_incoming/detector/BENCHMARK.md` (incl. an independent
"Verification" section); the integrated module is `server/forensics/face_swap.py`.

**The test set (75 leak-free clips, `eval_data/video_faceswap/`, `SPLITS.md` explains every check).**
FaceForensics++ c23 **official test split** (20 real + 25 fake: Deepfakes, FaceSwap, Face2Face, NeuralTextures,
FaceShifter x 5), Celeb-DF v2 **official test list** (10 + 10) and Google DFD (5 + 5, actors in no training set, fakes
not in the Kaggle FF++ bundle). Whole identities of the booth demo clips were excluded. Every clip went through one
identical H.264 re-encode, so no codec shortcut. "Cross" = Celeb-DF + DFD (15 real, 15 fake): in no candidate's
training data, and no threshold or weight was chosen on it. It is still not a clean held-out test: (1) the
pre-registered rule ranked the candidates by their AUC on these clips, and the pair was chosen after seeing them, so
the winner's number is optimistic; (2) GenD's authors chose their checkpoint using Celeb-DF++ validation videos, so
Celeb-DF is unseen in training but not in model selection. Only Google DFD (5 + 5) is fully unseen. Thresholds were
chosen on the 45 FF++ clips **only**, so FF++ accuracy is in-sample.

| candidate (pretrained, not ours) | trained on | FF++ test AUC | cross AUC [95% bootstrap CI, too narrow near 1.0] (N=16 frames) | ms/face, M4 |
|---|---|---|---|---|
| GenD CLIP ViT-L/14 (WACV 2026) | FF++ train | 0.976 | 0.920 [0.80-1.00] | 207 |
| SBI EfficientNet-B4 (CVPR 2022) | FF++ train (reals only) | 0.928 | 0.884 [0.74-0.98] | 855 |
| FF++ official XceptionNet (ICCV 2019) | FF++ train | 0.900 | 0.836 [0.67-0.96] | 183 |
| DeepfakeBench Xception | FF++ train | 0.912 | 0.929 [0.81-1.00] | 208 |
| DeepfakeBench EfficientNet-B4 | FF++ train | 0.916 | 0.822 [0.65-0.95] | 210 |
| DFDC 1st place EfficientNet-B7 (2020) | DFDC train only | 0.808 | 0.973 [0.91-1.00] | 115 |
| *engine's AI-face model (baseline)* | *AI-generated images* | *0.584* | *0.644 [0.43-0.84]* | *43* |
| **GenD + DFDC-B7 pair (fixed rule)** | both | 0.948 | **0.987 [0.95-1.00]** | 322 |

**Decision.** The pre-registered rule (highest cross AUC, ties within 0.02 broken by speed) picks **B7 alone**. We
integrated the **GenD (fp32) + B7 pair** instead, after looking at the engine-level and demo results, and we say so:
- B7 never saw FF++ and is weak on reenactment (Face2Face 0.78, NeuralTextures 0.65 AUC) and on the unseen
  FaceShifter (0.76); GenD covers those (0.97 / 0.97 / 0.87). Run through the whole engine, B7 alone calls 10 of 15
  unseen fakes and 1 of 6 booth fakes "synthetic"; the pair 12 of 15 and 5 of 6.
- On the cross clips the pair is **not** significantly better than B7 alone: +0.027 AUC, 95% CI [0.000, 0.085].
- **fp32, not int8.** An int8-quantised GenD is 0.9 GB smaller, but a 3e-5-pixel change in face alignment flipped 5 of
  91 decisions and its threshold moved from 0.087 to 0.434 when one FF++ clip was left out; fp32: 0 flips,
  0.117-0.133. int8 is kept only as a RAM fallback (`VERITAS_FACESWAP=int8`).
- **One-sided, weight 1.25, 8 frames** (chosen on FF++, with our 6 tuning clips as a no-regression check): both
  networks call fully generated GAN faces "real", so the test may only raise an alarm.
- **8 frames was chosen for speed after all results were known.** By the FF++ rule it was not the best (decisive
  accuracy 0.750 at 8 frames vs 0.765 at 4 and 16), and in the benchmark simulation 4 or 16 frames called one cross
  real clip "synthetic" (reals 7/7/1 and 10/4/1). So "no real cross clip called synthetic" is a fragile result.

**Result in the full engine** (`scripts/evaluate_video.py`, `web/data/results.json` -> `video.benchmark`):

| part | AUC of the verdict score, before -> after [95% CI, Newcombe] | fakes authentic/suspicious/synthetic | reals authentic/suspicious/synthetic |
|---|---|---|---|
| cross (Celeb-DF 10 + 10, DFD 5 + 5; not in training) | 0.60 [0.41-0.77] -> **0.998** [0.87-1.00] | 12/3/0 -> **0/3/12** | 13/2/0 -> 10/5/0 |
| FF++ test, 20 + 25 (in-sample thresholds) | 0.61 [0.44-0.75] -> 0.945 [0.82-0.98] | 19/6/0 -> 3/6/16 | 19/1/0 -> 17/3/0 |
| webcam-degraded reals (39; false-alarm check) | - | - | 38/1/0 -> **27/11/1** |

AUC intervals: Newcombe's Wilson-type method. The stratified percentile bootstrap gave 0.987-1.000 for the cross AUC,
which is far too narrow at the ceiling with 15 + 15 clips (one misordered pair moves the AUC by 0.004). Counts are
small too: 12 of 15 fakes "synthetic" has an exact 95% range of 52-96 %, and 0 of 15 reals "synthetic" still allows
up to 22 %. The paired-bootstrap gain over the old engine is +0.39 [0.19-0.59].

**The face-swap test on its own** fires on 7 of 15 cross real clips (Celeb-DF reals: 7 of 10) and on 21 of 39
webcam-quality real clips. Its threshold was set on FaceForensics++, the dataset GenD was trained on, where GenD is
overconfident about real faces; out of that domain the threshold is too low. The fusion turns most of these alarms
into "suspicious", not "synthetic".

**The cost, measured.** Grainy, heavily compressed real video fires the face-swap test (21 of 39 webcam-like real
copies): 11 became "suspicious" and one real news clip "synthetic". Nothing was re-tuned on these clips.

**Not for photos.** On single still images the same detector raised false alarms on real faces: it fired on 20 of 105
frames of real people saved like a Live Cam capture, and added to the photo fusion it would have raised real
webcam-style photos flagged from 1 to 4 of 49 (`scripts/evaluate_faceswap_images.py`,
`results.json` -> `image_details.faceswap_on_stills`). So it scores videos only; Live Cam is unchanged.
