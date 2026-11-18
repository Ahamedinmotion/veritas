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
