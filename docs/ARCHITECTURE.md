# VERITAS — Deepfake Forensics Lab

Science fair entry for INFINIA 2026 (Category IV, Classes XI–XII). Fair: Saturday 21 Nov 2026.
The booth runs on a **Windows laptop, fully offline**. The project is developed on macOS.

## Layout

```
veritas/
  server/            Python FastAPI app. Serves web/ as static files AND the /api/* endpoints.
    app.py           entry: `uvicorn server.app:app --port 8000` (run from veritas/)
    forensics/       one module per technique (ela.py, noise.py, fft.py, metadata.py, video.py, audio.py, models.py ...)
  models/            pre-downloaded Hugging Face models (gitignored, copied to the Windows laptop)
  scripts/           download_models.py, setup_windows.bat, start_windows.bat, start_mac.sh
  web/
    index.html       THE STORY — cinematic scroll website that replaces slides
    lab.html         THE PRODUCT — forensic analysis app (Analyze / Live Cam / Spot the Fake)
    css/tokens.css   shared design tokens (colors, fonts, motion) — both pages import it
    css/story.css    story-only styles          js/story/   story-only scripts
    css/lab.css      lab-only styles            js/lab/     lab-only scripts
    vendor/          third-party libs, vendored for offline use (gsap/, lenis/, mediapipe/ ...)
    assets/fonts/    local woff2 fonts + fonts.css
    samples/
      lab/           demo evidence files for the Analyze tab + manifest.json
      game/          labelled real/fake images for Spot the Fake + manifest.json
```

Rules: no CDN links at runtime (everything vendored, offline). Vanilla HTML/CSS/JS with ES modules, no build step.
Story and lab share tokens.css; verdict colors have fixed meaning: `--authentic` real, `--synthetic` fake, `--evidence` suspicious/warning.

## API contract (server ⇄ lab)

All responses JSON. Images inside responses are `data:image/png;base64,...` (or jpeg) strings.

### `GET /api/health`
```json
{ "ok": true, "version": "1.0.0",
  "models": { "face_deepfake": true, "ai_generated": true, "audio_deepfake": true },
  "device": "cpu" }
```

### `POST /api/analyze/image`  (multipart, field `file`)
### `POST /api/analyze/video`  (multipart, field `file`; server samples ≤ 48 frames, ≤ 20 s)
### `POST /api/analyze/audio`  (multipart, field `file`; wav/mp3/m4a/ogg/webm, ≤ 30 s analysed)

Common report shape:
```json
{
  "kind": "image | video | audio",
  "case_id": "VX-20261121-0042",
  "elapsed_ms": 1840,
  "file": { "name": "x.jpg", "size": 123456, "sha256": "…", "format": "JPEG",
            "width": 1024, "height": 768, "duration": null },
  "verdict": "authentic | suspicious | synthetic",
  "score": 87,                 // 0–100 likelihood of synthetic manipulation (fused)
  "confidence": 0.74,          // 0–1, how much the tests agree
  "summary": "One plain-English sentence explaining the verdict.",
  "preview": "data:image/jpeg;base64,…",       // downscaled original (image) or poster frame (video); null for audio
  "faces": [ { "box": [0.31, 0.18, 0.22, 0.30], "score": 91 } ],  // normalised x,y,w,h; per-face synthetic score
  "tests": [
    {
      "id": "ela",
      "name": "Error Level Analysis",
      "category": "compression | noise | frequency | metadata | ai_model | biometric | temporal | acoustic",
      "score": 72,             // 0–100 synthetic likelihood for this test, or null if not applicable
      "weight": 0.15,          // contribution to fused score
      "status": "ok | skipped | error",
      "finding": "Short finding, ≤ 14 words.",
      "explain": "2–3 sentences of the underlying science, Class XII level.",
      "visual": "data:image/png;base64,…",   // optional heatmap / spectrum / chart
      "metrics": { "mean_error": 6.2 }        // optional raw numbers shown in mono
    }
  ],
  "timeline": [ { "t": 0.5, "score": 40 } ],          // video only: per-sampled-frame score
  "keyframes": [ { "t": 3.0, "score": 92, "thumb": "data:…" } ], // video only: most suspicious frames
  "waveform": [0.01, 0.2, …],                           // audio only: ~600 abs-peak values 0–1
  "metadata": { "exif": { "Make": "…" }, "flags": ["No camera EXIF", "Software: Photoshop"] }
}
```

Verdict thresholds: score < 35 authentic, 35–65 suspicious, > 65 synthetic.

Test ids — image: `ai_face`, `ai_generated`, `ela`, `noise`, `fft`, `jpeg_quant`, `metadata`.
Video adds: `blink`, `landmark_jitter`, `temporal_flicker`, `ai_face` (per-frame avg), `face_swap` (one-sided). Audio: `ai_voice`, `spectral_cutoff`, `prosody`, `breath_silence`, `spectrogram` (visual).
Errors: HTTP 4xx/5xx with `{ "error": "message" }`.

Engine notes (additive, nothing above changed): video reports contain the tests `ai_face`, `ai_generated` (12 frames),
`blink`, `landmark_jitter`, `temporal_flicker`, `metadata` (container tags). Every report always carries `timeline`,
`keyframes` and `waveform` keys (empty lists when not applicable); video/audio reports add `timing_ms`; health adds
`detail`. Heatmap visuals are JPEG data URIs, charts PNG. `web/data/results.json` adds `image_details`, `audio`,
`video` blocks. See docs/ENGINE.md.

## Team decisions (latest — these override earlier placeholders)
- **Team:** Khais Mohammed and Prithvi (two students, Category IV). Use these names in the story's credits chapter and in docs/PITCH.md / JUDGE_QA.md (who-says-what). School name is still a placeholder: "[School Name]".
- **Media sourcing policy (from the team):** the competition allows any found material: existing tools, GitHub projects, datasets and assets are all permitted. Research deepfake datasets (FaceForensics++, Celeb-DF, DFDC, DeeperForensics, FakeAVCeleb, WaveFake, ASVspoof, In-the-Wild), well-known *educational* deepfakes (e.g. widely published awareness PSAs), and deepfakes we generate ourselves with open-source tools are all fine. Keep it school-appropriate: no sexual content, nothing defamatory, and no political misinformation framing. Every item is shown only as a detection example. Record each source in docs/DATA_SOURCES.md.
- **Incoming media:** a separate sourcing job is collecting deepfake + real **videos** and cloned + real **voice** clips into `../_incoming/media/` (outside the repo) with `manifest.json` and `SOURCES.md`. Integration and final stages: if present, analyse them with the real engine and copy the best correct-verdict examples into `web/samples/lab/` + manifest (re-encode videos to H.264 MP4 ≤ 20 s, ≤ 720p, ≤ 8 MB each).
- **Incoming media is ready (verified 2026-11-18):** `../_incoming/media/video/` holds 10 clips: FaceForensics++ #069 original + Deepfakes/Face2Face/NeuralTextures; Google DFD actor 09 original + face-swap; Celeb-DF v2 real + synthesis; DFD actor 07 original + a Wav2Lip lip-sync. `../_incoming/media/audio/` holds 10 clips: LJSpeech real + WaveFake HiFi-GAN/WaveGlow + an F5-TTS clone; LibriSpeech real + Chatterbox/F5-TTS clones; ASVspoof2019 bona fide + A10. Each folder has `manifest.json` and `VERIFIED.md`, and sources are in `../_incoming/media/SOURCES.md`. Use the matched pairs for side-by-side demos, and also run them through the engine as a small **video and audio experiment** for the Results chapter. Report the numbers honestly; with only a few clips, say so.
- **Licence caveat:** FaceForensics++, Google DFD and Celeb-DF clips are research/non-commercial and must **not be redistributed publicly**, and Wav2Lip is non-commercial. Showing them offline at the fair is fine. Add a `web/samples/lab/NOTICE.md` with their terms. If this repo is ever pushed to a public GitHub or a public website, these clips must be excluded, so list them in a `.gitignore`-ready `docs/PUBLIC_RELEASE.md` note.

## Integration notes (19 Nov 2026) — what the two pages actually rely on
These describe the shipped behaviour; nothing in the API contract above changed.

- **One identity.** Both pages use the same mark (a "V" with a red dot) and wordmark (`VERITAS` in IBM Plex Sans
  Condensed 600, tracked 0.32em, with "Deepfake forensics lab" under it) and the same favicon `web/assets/favicon.svg`.
- **Metadata flags.** The engine sends plain strings in `metadata.flags`. The lab sorts them into three levels and
  only shows warnings and AI markers in the verdict block (all of them appear in §05 with a key):
  - *fact* (neutral): `Camera: …`, `Captured …`, `Created …`, `Device tags: …`, `GPS location present …`, `C2PA …`,
    `Encoder: …`, `Text chunks: …`, `Sample rate …`, `Only the first 30 s analysed`, `Live webcam capture: …`,
    and `Software: …` unless it names an editing app.
  - *warning* (amber): `No camera EXIF`, `No container metadata`, `EXIF present but no camera make/model`,
    `Software: <editing app>`, `Black-and-white image: …`, `Not enough speech to judge`, and any unknown string.
  - *AI marker* (red): `AI marker: …`.
  A flag may also be sent as `{ "text": "…", "level": "info" | "warn" | "alert" }`; the lab accepts both.
- **Live Cam captures** are uploaded as `live-capture-HHMMSS.jpg`. The engine relies on that prefix: it scores only
  the two AI detectors and marks the other five tests `skipped` (webcam frames are smoothed and re-encoded).
- **HEIC/HEIF** photos are sent to the engine (pillow-heif decodes them); the browser cannot preview them during the
  scan, but the report shows the engine's preview.
- **`web/samples/lab/manifest.json`** (Evidence locker): array of
  `{ file, kind: image|video|audio, label: authentic|synthetic, title, note, engine_score, thumb? }`.
  `label` is the sealed ground truth shown after the report. Built by `scripts/build_samples.py --lab`.
- **`web/samples/game/manifest.json`** (Spot the Fake, lab + story chapter 03): array of
  `{ file, label: real|fake, ai_score: 0–100 fused engine score, source, hint }`. The game counts the engine as saying
  "AI" when `ai_score > 50`. One image per text prompt (no near-duplicate scenes). Built by `--game`.
- **`web/data/results.json`** (story chapter 06) — fields read by `js/story/results.js`: `metrics`, `confusion`,
  `roc`, `per_test`, `dataset.{real,fake,split}`, `image_details.{condition,by_group}`, `audio.{metrics,confusion,
  generalisation[].{unseen_family,n,auc|false_alarm_rate},external.{clips,correct,auc},dataset}`,
  `video.{clips[].{file,label,group,score},correct,mean_latency_ms}`, `generated`. Clip file names are never printed
  (some research clips show celebrities); they are mapped to short labels such as "Face-swap · FF++".
- **Research clips are not shipped.** FaceForensics++ / Google DFD / Celeb-DF / Wav2Lip clips stay in
  `../_incoming/media/` and only appear as numbers in `results.json`; `web/samples/` holds none of them (its image
  sources and licences, e.g. FFHQ CC BY-NC-SA, are listed in docs/DATA_SOURCES.md).
- **Offline.** No page or server path requests a remote URL. The vendored MediaPipe bundle had a usage logger that
  POSTs to `odml.pa.googleapis.com`; it is disabled in `web/vendor/mediapipe/vision_bundle.js` (see `VERSION.txt`).

## Release notes (final stage, 19 Nov 2026)
- **MIME types are pinned** in `server/app.py` (`.js` -> `text/javascript`, `.wasm`, `.css`, ...). Windows reads
  MIME types from the registry, and a `.js` = `text/plain` entry would make Chrome/Edge refuse every ES module.
- **Warm-up.** Start-up runs one tiny image, then one voice exhibit, and a video exhibit in a background thread that
  holds the analysis lock (`VERITAS_SKIP_WARMUP=1` skips the voice/video part). `uvicorn` binds the port only after
  the lifespan, so `/api/health` answering means the models are loaded.
- **Windows console.** `server/config.py` disables QuickEdit on Windows so a click in the server window cannot block
  log writes (and with them every analysis).
- **Large photos** (> 24 MP) run ELA, noise and FFT one after another instead of in parallel (same results, about a
  third of the peak RAM).
- **Self-test:** `scripts/selftest.py` runs every `web/samples/lab/manifest.json` exhibit in-process and compares
  with `engine_score` ± 5; it also checks the `.js` MIME type. Exit code 0 = ALL PASS.
- **Evidence locker has 9 exhibits.** The last one, `missed-fake-voice.wav` (label `synthetic`, `engine_score` 34),
  is a deliberate miss; the locker footnote says the others were chosen to show each test working.
- **Kiosk privacy.** Analyze forgets Live Cam captures and closes a finished report after 150 s without input
  (`?idle=SECONDS`); Live Cam pauses the camera after 90 s with no face (button "Wake").
- **Story chapter 05** shows the engine's real output for the Wav2Lip lip-sync demo clip (70, confidence 0.49; 14
  without the face-swap test; until 19 Nov it showed the FF++ Deepfakes 069 clip, 76) and credits the pretrained
  networks (refs [23]-[25], [27]-[29]). Chapter 06 computes exact 95% intervals in the browser from the
  confusion matrix and reads `image_details.external_video_stills.real_as_photo` for the "Real video stills" chip.

## Face-swap detector (19 Nov 2026, additive; nothing above changed)
- **Video test `face_swap`** ("Face-Swap Detector", category `ai_model`), second in the video `tests` list (after
  `ai_face`). Two pretrained networks, GenD (CLIP ViT-L/14) + the DFDC-winning EfficientNet-B7, each with its own
  face detector (SCRFD / MTCNN), on 8 evenly spaced sampled frames; `server/forensics/face_swap.py`, models in
  `models/face_swap/`. `status` is `skipped` when neither face detector finds a face, `error` when the model files are
  missing. It is **one-sided**: `weight` is 0 when its `score` < 50, and the fused score is max(without, with) it.
  Its `metrics` include `GenD_mean_P(fake)`, `B7_mean_P(fake)`, their FF++ thresholds, frames with a face,
  `networks_voting`, `one_sided: true`; its `visual` is the grid of the 8 aligned faces with per-frame scores.
- **`/api/health`** `models` gains `face_swap` (true when loaded, or when switched off with `VERITAS_FACESWAP=off`);
  `detail.model_names.face_swap` names the active mode. The lab shows "Online · 3/4 models" if it is missing.
- **`timeline`** points may carry `swap` (the face-swap detector's per-frame score, on its 8 frames). **`keyframes`**
  carry `by`: `ai_face` | `face_swap` | `ai_generated` (which test rated that frame most suspicious).
- **`web/data/results.json`**: `video.benchmark` = the 75-clip benchmark (`parts.{ffpp,celebdf,dfd,cross,all}.
  {before,after}.{auc,auc_ci95,accuracy_at_50,fakes,reals,...}`, `per_method[]`, `face_swap_test`, `cross_gain`,
  `clips[]`), `video.clips[].before` / `before_verdict` (the engine without the face-swap test), `video.summary_before`,
  `image_details.faceswap_on_stills` (why the detector is video-only). Story chapter 06·3 (`#results-video`) reads them.
- **Modes:** `VERITAS_FACESWAP` = `fp32` (default) | `int8` | `b7` | `off` (server/config.py `FACESWAP_MODES`;
  quotes are stripped, an unknown value logs a warning and uses `fp32`). The start scripts print the mode and frames.
- **Frames (release fix, 19 Nov):** the engine samples 48 frames on a 10+ thread CPU, otherwise **32** (24 only via
  `VERITAS_VIDEO_FRAMES`). At 24 the face-swap test saw different frames and published demo scores moved (Wav2Lip
  70 -> 64); at 32 all 40 checked clips keep their verdict.
- **results.json additions (review fixes):** `parts.*.{before,after}.auc_ci95_newcombe` and
  `face_swap_test.*.auc_ci95_newcombe` (Newcombe Wilson-type AUC intervals; the story shows these),
  `video.clips[].celebdf_train_portion` (‡ on 06·3). `scripts/evaluate_video.py --restat` rebuilds them and the notes
  from the saved per-clip rows without re-running any clip.
- **Lab:** a silent one-sided test (score < 50) is grey everywhere: card, scan pipeline, face tiles
  (`charts.faceswap_figure(silent=True)`), timeline diamonds and keyframes it picked; it never looks like it vouches.
- **Self-test:** `scripts/selftest.py` also checks the face-swap test on both locker videos (status ok, score ±5 of
  16 / 0 in `fp32`, frames with a face GenD/B7 = 8/8 on the real video and 0/8 on the talking photo).
