# The VERITAS forensic engine - how it works (for presenters)

`server/` is a FastAPI app. `POST /api/analyze/{image,video,audio}` runs a set of independent forensic tests,
each giving a 0-100 "synthetic likelihood", and fuses them into one verdict:
**below 35 = authentic, 35-65 = suspicious, above 65 = synthetic.** Everything runs on the laptop CPU, offline.

| Evidence | Tests (id) | Typical time (M4 Mac / 4-core Windows laptop) |
|---|---|---|
| Image | ai_generated, ai_face, ela, noise, fft, jpeg_quant, metadata | 0.5-1.5 s / 3-5 s |
| Video (first 20 s) | ai_face (24-48 frames), ai_generated (12 frames), blink, landmark_jitter, temporal_flicker, metadata | 2-5 s / 10-25 s |
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
- **AI Face (per-frame)** - up to 48 frames spread over the clip (32 on an 8-thread laptop, 24 on <= 4 threads);
  timeline + 4 most suspicious keyframes. Same general AI-image network: catches generated faces, misses most
  face-swaps / reenactments / lip-syncs (see the external video results).
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
1. Tests that could not run drop out; weights renormalise.
2. Each score -> log-odds; weighted mean (AI models ~70% of the weight). A classic test above 65 gets its weight
   amplified up to 3x only when its evidence is specific (localised splice, periodic grid, AI tag, frozen face,
   missing blinks) - never for "too smooth / too little grain", which webcams and phones also produce.
3. Gain/bias fitted on the calibration split (images, including degraded copies); then back to 0-100.
   The image detectors' calibration curves are constrained: a "synthetic" (> 65) test score needs the network's own
   probability to be at least 25%.
4. `confidence` = agreement between tests blended with distance from 50.

## Honest limitations (say these before the judges ask)
All numbers: `web/data/results.json` (see its `notes`).
- **Real deepfake videos are mostly missed.** The image network is a *general AI-image* detector. It catches faces
  generated whole (GAN, diffusion, animated "talking photos"), but it was never trained on face-swaps, reenactment
  or lip-sync. On the external research clips (FaceForensics++, Google DFD, Celeb-DF, Wav2Lip) it caught
  1 of 6 with a 'synthetic' verdict (2 of 6 above 50; the DFD face-swap scored 5 and the Wav2Lip lip-sync 14), while 3 of 4 real clips were called authentic and the FF++ original was 'suspicious' (47). Our own ethical face-swap made with `make_faceswap.py --video` also passes as real.
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
- 171 images / 206 voice clips / 16 videos is a school-scale experiment, not a benchmark.

## Re-running the experiment
```
uv run --with pyarrow python scripts/build_eval_data.py      # download eval_data/ (internet; incl. extra speakers + vocoded pairs)
uv run python scripts/make_faceswap.py --n 16                 # face-swap composites
uv run python scripts/compare_models.py --kind image          # model selection (calibration split)
uv run python scripts/evaluate.py                             # calibrate + held-out + robustness + external -> results.json (~45 min)
uv run python scripts/evaluate.py --kind images --reuse-pass1 # re-fit image curves/fusion from cached pass-1 reports
uv run python scripts/build_samples.py --lab --game           # demo files
```
