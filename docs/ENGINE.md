# The VERITAS forensic engine - how it works (for presenters)

`server/` is a FastAPI app. `POST /api/analyze/{image,video,audio}` runs a set of independent forensic tests,
each giving a 0-100 "synthetic likelihood", and fuses them into one verdict:
**below 35 = authentic, 35-65 = suspicious, above 65 = synthetic.** Everything runs on the laptop CPU, offline.

| Evidence | Tests (id) | Typical time (M4 Mac / 4-core Windows laptop) |
|---|---|---|
| Image | ai_generated, ai_face, ela, noise, fft, jpeg_quant, metadata | 0.5-1.5 s / 3-5 s |
| Video (first 20 s) | ai_face (32-48 frames), face_swap (8 frames), ai_generated (12 frames), blink, landmark_jitter, temporal_flicker, metadata | 5-6 s / 33-43 s on the slow-laptop proxy (4 M4 efficiency cores; face-swap step 19-26 s) |
| Audio (first 30 s) | ai_voice, breath_silence (scored); spectral_cutoff, prosody, spectrogram (pictures only) | 0.3-1.6 s / 2-4 s |

## Image tests
- **AI-Generated Image Detector (`ai_generated`)** - CommunityForensics ViT-Small (CVPR 2025), trained on images
  from 4,803 generators. Scores the whole picture plus a 3x3 grid of overlapping patches (the visual is that grid).
- **AI Face Analysis (`ai_face`)** - YuNet finds faces; each face crop (with 30% margin; near the picture edge the
  square slides inwards instead of mirroring pixels) is scored by the same general AI-image network. Only faces
  that are clear (YuNet confidence >= 0.85) and big enough (>= 8% of the short side, >= 48 px) are scored. It catches
  faces generated whole (GAN, diffusion); it was **not** trained on face-swaps and is often fooled by a well-blended
  swap of a real face. Fills `faces[]` with normalised boxes.
- **Error Level Analysis (`ela`)** - re-save at JPEG quality 90, measure per-pixel change. Busy textures always
  change more, so we compare each 16 px block with blocks of similar texture; a *compact cluster* of blocks that
  deviate strongly (robust z-score) raises the score. The finding only describes the map ("an edit, or just fine
  detail?") - it never accuses. Visual: amplified error map (dark -> amber -> white). Best used by eye.
- **Noise Residual (`noise`)** - noise = image minus denoised image (finest wavelet band). Local noise level in
  32 px blocks, corrected for brightness and texture. Two signals: a region whose grain disagrees (splice), and
  "missing camera grain" (generators don't simulate a sensor) from a 2-number logistic model fitted on our
  calibration split. Phones, webcams and video also remove grain, so only the splice signal is amplified in fusion.
- **Frequency Spectrum (`fft`)** - 2-D FFT + azimuthal average vs. a natural 1/f trend; periodic grid peaks from
  up-sampling layers, and a lack of fine high-frequency detail (3-number logistic model, calibration split). The
  "too smooth" branch can only score high when the measured curve really drops below the trend (hf_excess < -0.4).
- **JPEG Quantisation Tables (`jpeg_quant`)** - reads the 8x8 tables, estimates quality, tells camera tables from
  standard software tables, and looks for double-compression gaps in the DCT histogram. Skipped for PNG.
- **Metadata & Provenance (`metadata`)** - EXIF (camera, exposure, time), XMP, PNG text chunks (Stable Diffusion
  `parameters`, ComfyUI `workflow`), IPTC `trainedAlgorithmicMedia`, C2PA. An AI-tool tag forces the score >= 88.
  AI-tool names are searched **only in provenance fields** (Software, XMP CreatorTool, IPTC DigitalSourceType,
  AI parameter chunks, C2PA) - never in captions, so "runway" or "Imagen de la ciudad" in a description is ignored.
  GPS is never shown, only flagged.

### Special cases
- **Live Cam captures** (file name `live-capture-*`, sent by the lab's Live Cam): a webcam frame is smoothed and
  re-encoded by the camera and browser, so ELA, noise, FFT, JPEG-table and metadata tests are shown as *skipped* and
  only the two AI detectors are scored. A flag says so in the report.
- **Black-and-white images**: removing colour also removes the colour fingerprints the AI detectors rely on (an AI
  face turned grey scored "authentic" before this fix). A grey picture is never called authentic: the verdict is
  at least "suspicious" with the summary "Black-and-white image ... inconclusive".
- **Blank / tiny images** (one flat colour, or shorter side < 128 px) are refused with a clear 400 message instead
  of a meaningless verdict. 16-bit PNG/TIFF are scaled to 8 bits (no more white-out); HEIC (iPhone) is supported.

## Video tests
- **AI Face (per-frame)** - up to 48 frames spread over the clip (48 on a 10+ thread CPU, otherwise 32; 24 only if
  `VERITAS_VIDEO_FRAMES=24` is set, which moves some demo scores);
  timeline + keyframes. Same general AI-image network: catches generated faces, misses most face-swaps /
  reenactments / lip-syncs on its own (that is why the face-swap detector below was added).
- **Face-Swap Detector (`face_swap`, added 19 Nov 2026)** - two PRETRAINED published detectors that we benchmarked
  and chose (we did not train them; `server/forensics/face_swap.py`, files in `models/face_swap/`, 1.5 GB):
  - **GenD** (Yermakov, Cech, Matas, Fritz, *Deepfake Detection that Generalizes Across Benchmarks*, WACV 2026; MIT):
    OpenAI's CLIP ViT-L/14 vision transformer with only its LayerNorm layers (0.03 % of the weights) and a linear
    head tuned on FaceForensics++ (train split). Exact published fp32 weights, run as ONNX (logits = PyTorch within
    2.4e-6). Its own face detector, **SCRFD-10G** (InsightFace `det_10g.onnx`, 640 px letterbox, threshold 0.5), the
    largest face, 5-point alignment to GenD's template at scale 1.3, CLIP preprocessing (224 px, CLIP mean/std).
    99.97 % of its weights are OpenAI's CLIP ViT-L/14 (MIT), which comes inside GenD's checkpoint.
  - **DFDC-B7**: the Deepfake Detection Challenge (2020) first-place EfficientNet-B7 by Selim Seferbekov (MIT), one
    of its 7 checkpoints, trained on the DFDC training set only, starting from the Noisy-Student ImageNet
    EfficientNet-B7 (`tf_efficientnet_b7_ns`, Xie et al., CVPR 2020). ONNX (= PyTorch within 5e-7). Its own face detector,
    **MTCNN** (facenet-pytorch, vendored in `server/vendor/`), on the half-size frame; box +1/3 margin, 380 px,
    ImageNet normalisation; the frame score is the most suspicious face.
  - **8 frames**, evenly spaced over the engine's sampled frames. Each model's P(fake) is averaged over the frames
    where it found a face. Fixed rule (nothing fitted but three thresholds, all chosen on the 45 FaceForensics++
    test clips only): `z = 0.5*(logit pG - logit 0.8121) + 0.5*(logit pB - logit 0.6968) - logit 0.1178`,
    `score = 100*sigmoid(z)`, so 50 = the pair's FF++ threshold. The pair term (-logit 0.1178 = +2.01 log-odds)
    dominates: the pair can fire while each network is slightly below its own threshold (e.g. a real FF++ clip with
    GenD 0.30 and B7 0.38 scores 55). If only one model finds a face it is scored on its own threshold.
    What the networks look at is not known (black boxes); such detectors are trained to pick up blending seams and
    texture mismatches. Per-frame scores (same formula on one frame) feed the timeline (diamonds) and keyframes; the
    visual is the 8 aligned faces the model judged.
  - **One-sided** (see Fusion): both networks call fully generated (GAN) faces "real" - they only ever saw swaps -
    so the test may raise an alarm but never vouches. On the animated-GAN exhibit it scores about 0 and stays out.
  - Modes (`VERITAS_FACESWAP`): `fp32` (default), `int8` (RAM fallback, GenD int8: ~0.6 GB less, its borderline
    decisions jitter), `b7` (B7 alone, smallest), `off`. Never fewer than 8 frames: the thresholds are for 8-frame
    means.
- **AI-Generated Frames** - whole-frame detector on 12 frames (catches fully generated text-to-video clips).
- **Blink Rate (EAR)** - MediaPipe FaceLandmarker (478 points) at ~12 fps.
  EAR = (|p2-p6| + |p3-p5|) / (2|p1-p4|). A blink = EAR dip below 72% of the open-eye level for <= 0.6 s.
  Poisson model with 17 blinks/min: "how likely is a real person to blink this little?"
- **Landmark Jitter** - align consecutive frames' landmarks with a similarity transform (removes head motion),
  then measure leftover second-difference "shake" as % of eye distance. Too much = frame-by-frame synthesis;
  almost zero = a still photo being animated.
- **Temporal Flicker** - fast brightness/colour changes inside the face hull vs. the background; a face rendered
  frame by frame flickers on its own.

## Audio tests
- **Speech gate** - before anything is scored, the engine measures how many seconds rise clearly above the clip's
  own background (20 ms frames). Under 1 s of speech (silence, a tone, noise, a 0.7 s snippet) the report says
  "Not enough clear speech to judge" with a neutral score of 50 instead of a confident verdict.
- **AI Voice (`ai_voice`)** - wav2vec2-base fine-tuned on In-the-Wild deepfake speech; we take its layer-4
  features (768 numbers per 4 s window) and a logistic-regression probe trained on our calibration clips
  (transfer learning). Per-window chart. Silent windows are ignored.
- **Breaths & Silence** - energy every 20 ms: pauses, digital-zero gaps, noise floor, breath-like noises.
- **Spectral Cut-off** - *visual evidence, not scored* (held-out AUC 0.42): long-term spectrum and where it falls
  off. Skipped for files recorded at 16 kHz.
- **Prosody & Pitch** - *visual evidence, not scored* (held-out AUC 0.52): pYIN pitch track and its spread in
  semitones. (Earlier versions claimed to measure "jitter"; true jitter is cycle-to-cycle variation of the vocal-fold
  period and cannot be measured from 20 ms pitch frames, so that claim was removed.)
- **Spectrogram** - mel spectrogram picture (not scored; status "ok" with `score: null` by design). The y-axis is
  labelled at the true mel positions of 0.5/1/2/4/8 kHz. Plus `waveform` (600 peaks) for the UI.

## Fusion (server/fusion.py)
1. Tests that could not run drop out; weights renormalise. The **one-sided** face-swap test (weight 1.25 next to the
   other video weights, which sum to 1) only votes when its score is 50 or more, and the result is
   max(fused without it, fused with it): it can raise a score, never lower it. Its weight was chosen on FF++ only.
2. Each score -> log-odds; weighted mean (AI models ~70% of the weight). A classic test above 65 gets its weight
   amplified up to 3x only when its evidence is specific (localised splice, periodic grid, AI tag, frozen face,
   missing blinks) - never for "too smooth / too little grain", which webcams and phones also produce.
3. Gain/bias fitted on the calibration split (images, including degraded copies); then back to 0-100.
   The image detectors' calibration curves are constrained: a "synthetic" (> 65) test score needs the network's own
   probability to be at least 25%.
4. `confidence` = agreement between tests blended with distance from 50.

## Honest limitations (say these before the judges ask)
All numbers: `web/data/results.json` (see its `notes`).
- **Face-swap videos: much better, not solved.** Before 19 Nov the engine missed most face-swaps (its image network
  was never trained on them). With the pretrained face-swap detector, on 30 clips from datasets neither network was
  trained on (Celeb-DF 10 + 10, Google DFD 5 + 5; no threshold or weight was chosen on them) the AUC of the verdict
  score went from 0.60 to 0.998 (95% CI about 0.87-1.00, Newcombe; the bootstrap's 0.99-1.00 is far too narrow with
  so few clips), fakes called 'synthetic' from 0 to 12 of 15 (3 'suspicious', none 'authentic'), reals called
  'synthetic' 0 -> 0, but reals called 'suspicious' 2 -> 5 of 15. These 30 clips are **not a clean held-out test**:
  our pre-registered rule ranked the 6 candidates by their AUC on them, we chose the pair after seeing them, and
  GenD's authors chose their checkpoint using Celeb-DF++ validation videos (Celeb-DF is unseen in training, not in
  model selection). Only Google DFD (5 + 5, AUC 1.00) is fully unseen. On these clips the pair is statistically tied
  with the DFDC winner alone (+0.03 AUC, 95% CI 0.00-0.09). FaceForensics++ test (45 clips; in-sample for the
  thresholds, GenD's home ground): AUC 0.61 -> 0.945; FaceShifter, in neither network's training, only 1 of 5
  'synthetic'. 10 booth demo clips: 5 of 6 fakes 'synthetic' (was 1), but the 3 FF++ 069 fakes are in GenD's training
  split, the Celeb-DF id2 pair is from Celeb-DF's training portion, and the DFD 09_13 face-swap is only 'suspicious'
  (41; 44 at 32 frames): only the Wav2Lip lip-sync we made is a fully unseen catch. Only 2019-2020 manipulation
  methods were tested: modern swap apps (FaceFusion/inswapper, SimSwap), talking-head avatars and
  WhatsApp-recompressed clips were not.
- **Frame count matters a little.** The engine samples 48 frames on a 10+ thread CPU, otherwise 32 (never fewer since
  19 Nov; `VERITAS_VIDEO_FRAMES` overrides), and the face-swap test uses 8 of them. At 32 frames all 10 demo clips
  and all 30 cross clips keep their verdict (one score moves: DFD 09_13 41 -> 44). At 24 frames (the old 4-thread
  setting) the Wav2Lip clip drops 70 -> 64 (suspicious) and the real Celeb-DF clip rises 34 -> 38.
- **More real videos read "suspicious", most of all grainy ones.** The face-swap pair's threshold was set on
  FaceForensics++, GenD's training domain, where it is overconfident about real faces; out of that domain it is too
  low, so real interviews can fire it (7 of 15 cross real clips scored >= 50 on the test alone, Celeb-DF reals 7 of
  10; in the fused verdict 5 of 15 became 'suspicious', none 'synthetic'). "None synthetic" is fragile: with 4 or 16
  frames instead of 8 the benchmark simulation called one of them synthetic, and 0 of 15 still allows a true rate up
  to 22 %. On 39 real clips re-encoded like a cheap webcam (360p, blur, noise,
  denoise, H.264 CRF 30) it fired on 21: verdicts went from 38/1/0 (authentic/suspicious/synthetic) to **27/11/1** -
  one real FF++ news clip was called 'synthetic' (72). Heavily compressed real video is its weak spot; we did not
  re-tune anything on these clips. Test real webcam/phone videos of classmates on Friday.
- **The face-swap detector is video-only.** On single still images it raised false alarms on real faces (see
  results.json `image_details.faceswap_on_stills`), so photos and Live Cam captures do not use it.
- **Compressed video frames of real people can be called synthetic.** Stills from real research videos (low
  resolution, heavy compression) were flagged in 5 of 12 cases (3 with a 'synthetic' verdict; before the review fixes it was 12 of 12). Simulated webcam frames do much better
  (1 of 49 held-out real images flagged after a simulated webcam pipeline, 2 of 49 as H.264 video stills), but test the Live Cam on the booth laptop with real people on Friday.
- **Phone "beauty" / heavy denoise filters** make real photos look AI-smooth: 4 of 49 held-out real images flagged after a bilateral 'beauty' filter.
- **Voice detection does not generalise.** Held-out speakers from the *same* datasets: AUC 0.81 (accuracy 75.7%). A whole
  dataset family left out of training: AUC 0.50-0.85 (0.5 = coin toss), and 75% of FLEURS real voices were flagged
  when FLEURS was left out - the probe partly learns dataset quirks (microphones, rooms). On 10 outside clips
  (generators never used for tuning: F5-TTS, Chatterbox, WaveGlow, ASVspoof A10; but LibriSpeech speaker 260, in 4 of
  the clips, and the HiFi-GAN vocoder type ARE in the calibration split): fakes caught 2 of 6, real voices cleared
  4 of 4 (an "always real" detector would score 4/10); none of the 6 fakes gets a 'synthetic' verdict in the lab;
  ranking AUC 0.92 from only 4 real + 6 fake clips (95% CI roughly 0.73-1.0). Voice clones mostly pass as real.
  A fake voice played through a speaker and re-recorded loses its fingerprints.
- **Classic tests do not catch our hand-made splice.** An AI region pasted into a real phone photo is visible to the
  eye in the ELA map, but no score caught it (ELA, noise, FFT, JPEG-ghost and grid-alignment ideas all tried).
  ELA / noise / FFT are weak on whole AI images too (held-out AUC 0.50-0.65), so they carry small weights.
- **Black-and-white removes the colour fingerprint**: a grey AI face can slip under the AI detectors, so grey
  pictures are reported as inconclusive (never "authentic").
- **The image numbers are optimistic.** The AI-image network's authors list FFHQ and COCO among its training
  datasets, and 42 of our 49 held-out real photos come from them, so "0 false alarms" is partly in-distribution.
  95% ranges: accuracy 84-96%, false-alarm rate 0-7.3%. Our 7 phone photos (0 flagged) are the fairest real test.
- **Blink and jitter did not fire on any research deepfake** (blink 15 and jitter 12 = their floors on all 10
  clips). Modern deepfakes blink normally; these tests only catch lazy fakes such as an animated still photo.
- We looked at earlier test runs while improving the calibration, so the held-out numbers are slightly optimistic
  even though no number was fitted on the held-out files.
- Fusion weights and the classic tests' thresholds were set by hand; only the neural calibration curves, the
  noise/FFT feature models and the image fusion gain/bias were fitted (on the calibration split).
- 171 images / 206 voice clips / 91 videos (75 benchmark + 10 demo + 6 tuning) is a school-scale experiment, not a
  benchmark: the cross-dataset video test has only 15 real and 15 fake clips.

## Re-running the experiment
```
uv run --with pyarrow python scripts/build_eval_data.py      # download eval_data/ (internet; incl. extra speakers + vocoded pairs)
uv run python scripts/make_faceswap.py --n 16                 # face-swap composites
uv run python scripts/compare_models.py --kind image          # model selection (calibration split)
uv run python scripts/evaluate.py                             # calibrate + held-out + robustness + external -> results.json (~45 min)
uv run python scripts/evaluate.py --kind images --reuse-pass1 # re-fit image curves/fusion from cached pass-1 reports
uv run python scripts/evaluate_video.py                       # video: 75 leak-free clips + demo + tuning, before vs after (~8 min)
uv run python scripts/evaluate_video.py --restat              # recompute intervals + notes from the saved per-clip rows
uv run python scripts/evaluate_faceswap_images.py             # should the face-swap detector score stills? (~45 min)
uv run python scripts/build_samples.py --lab --game           # demo files
```
