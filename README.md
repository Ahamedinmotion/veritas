# VERITAS: Deepfake Forensics Lab

A student-built deepfake detector that runs **completely offline** on one laptop.
It is our entry for **INFINIA 2026** (South Zone Sahodaya inter-school science exhibition, Thiruvananthapuram):
Category IV (Classes XI–XII), theme *Science for Tomorrow: Imagine – Innovate – Transform*,
sub-theme *Intelligence Beyond Humans*. Team: Khais Mohammed and Prithvi.

VERITAS has two parts that share one look and one local server:

| Part | URL | What it is |
|---|---|---|
| **The story** | `http://127.0.0.1:8000/` (`web/index.html`) | A cinematic scroll-through presentation that replaces slides on the big TV. It covers the threat, how fakes are made and caught, our results and our limits. |
| **The lab** | `http://127.0.0.1:8000/lab.html` (`web/lab.html`) | The working product: drop in evidence and get a forensic case report from the Python engine. |

The **engine** (`server/`) is a FastAPI app. It serves both pages and the analysis API. Every photo, video or
voice clip goes through a battery of independent tests, and the engine combines their scores into one verdict:

- **Photos:** AI-image network, AI-face network, error level analysis, noise residual, FFT spectrum, JPEG tables, metadata.
- **Videos:** per-frame face model, blink rate (eye aspect ratio), landmark jitter, temporal flicker, AI frames, container metadata.
- **Voice:** wav2vec2 voice network and breath/silence analysis. A spectrogram, pitch track and spectral cut-off are shown but not scored.

Verdict: score < 35 **authentic**, 35–65 **suspicious**, > 65 **synthetic**. Our measured accuracy, and where the
engine fails, are in story chapter 06 and in `web/data/results.json`. Be honest about them at the booth.

## Run it

You need internet **once** to install Python, the libraries and the models (models about 530 MB, Python environment
about 1.3 GB; keep 6 GB free). After that, no internet is needed. No internet on the laptop at all? Use the offline
kit (Route C in `docs/SETUP_WINDOWS.md`).

### Windows (the booth laptop)
1. Copy the `veritas` folder to `C:\veritas` (not inside OneDrive). **Leave out `.venv`, `eval_data` and `.git`.**
   Copying `models\` saves a 530 MB download.
2. With internet, double-click `scripts\setup_windows.bat` once. It takes 5–15 minutes, runs a self-test and ends
   with `ALL PASS` and `SETUP COMPLETE`.
3. Every time after that, double-click **`scripts\start_windows.bat`**. Keep the black window open and don't click
   in it. Edge opens `http://127.0.0.1:8000/` by itself when the engine is ready (about 30 s; the very first start
   after setup can take 2–4 minutes).
4. Quick health check any time: `scripts\selftest_windows.bat` must say `ALL PASS`.

The full checklist (Friday tests, speed table, troubleshooting) and the **fallback plan** (`emergency_browser.bat`,
demo video, spare Mac) are in **`docs/SETUP_WINDOWS.md`**.

### macOS / Linux (development)
```bash
cd veritas
uv sync --locked                          # once, with internet
uv run python scripts/download_models.py  # once, with internet
./scripts/start_mac.sh                    # opens http://localhost:8000/
.venv/bin/python scripts/selftest.py      # every locker exhibit through the engine; ALL PASS = ready
./scripts/build_winkit.sh                 # optional: offline Windows kit -> ../_usb/winkit (Route C)
# or by hand:
uv run uvicorn server.app:app --host 127.0.0.1 --port 8000
```
Use Chrome or Edge. Health check: `http://127.0.0.1:8000/api/health` should show `"ok": true` with all three models `true`.

## The three lab modes

| Tab | Key | What visitors do |
|---|---|---|
| **01 Analyze** | `1` | Drop a file, click to choose one, paste with `Ctrl+V`, or pick an exhibit from the **Evidence locker**. The report shows the verdict gauge, every test card (click one for the science and its evidence picture), face boxes, a frame-by-frame video timeline with keyframes, a playable audio waveform and spectrogram, and the metadata. Locker exhibits carry a sealed ground truth that is revealed in the report. |
| **02 Live cam** | `2` | 478-point face mesh, blink counter, eye-aspect-ratio graph and head pose, all computed in the browser. **Liveness check** asks for random blinks and head turns. **Capture & analyze** sends one frame to the engine; only the two AI networks are scored for webcam frames. |
| **03 Spot the fake** | `3` | Ten random images, real or AI. The visitor answers with ← / →, then sees what VERITAS said. A booth scoreboard tracks humans against the AI. |

## Controls

### Story (presenter mode, works with a USB clicker)
| Key | Action |
|---|---|
| `→` · `Space` · `PageDown` | Next step (clickers send PageDown) |
| `←` · `Shift+Space` · `PageUp` | Previous step |
| `0`–`8` | Jump to a chapter (0 Opening … 6 Results … 8 Enter the Lab) |
| `Home` · `End` | First · last step |
| `F` | Fullscreen (the cursor hides after 2.6 s) |
| `?` or `H` | Show the controls panel |

The mouse wheel and trackpad also work; the step counter re-syncs. Chapter 08 has three doors into the lab.

### Lab (kiosk)
| Key | Where | Action |
|---|---|---|
| `1` `2` `3` | anywhere except the game | Switch tab |
| `F` | anywhere | Fullscreen |
| `N` | Analyze report | New case |
| `Esc` | Analyze scan | Cancel the analysis |
| `←` / `→`, `Esc` | Test detail overlay | Previous/next test, close |
| `C` or `Space` | Live cam | Capture & analyze |
| `L` | Live cam | Liveness check |
| `M` | Live cam | Mesh on/off |
| `←` real · `→` AI | Spot the fake | Answer; `Enter` for the next exhibit; `Esc` back to the intro |
| `Shift+R` twice | Spot the fake (not while typing a name) | **Reset the booth scoreboard** (the old board is kept in `localStorage` as `veritas.game.v1.bak`) |

`← The story` (top right) or the VERITAS logo goes back to the story. The scoreboard is stored per browser and per
address, so `localhost` and `127.0.0.1` keep separate boards. Use the address the start script opens.

## Folder map
```
veritas/
  README.md              this file
  pyproject.toml uv.lock exact Python 3.12 dependencies (CPU-only PyTorch on Windows/Linux)
  server/                FastAPI engine: app.py (API + static files), pipeline.py / video_pipeline.py /
                         audio_pipeline.py, fusion.py (score fusion), forensics/ (one module per test),
                         calibration.json (fitted calibration, written by scripts/evaluate.py)
  models/                downloaded AI models (gitignored; copy to the booth laptop)
  scripts/               setup_windows.bat, start_windows.bat, selftest(.py/_windows.bat), emergency_browser.bat,
                         start_windows_kit.bat + build_winkit.sh (offline kit), start_mac.sh, download_models.py,
                         evaluate.py (the experiment), build_samples.py (lab + game samples), build_eval_data.py, ...
  eval_data/             evaluation images and audio (gitignored)
  web/
    index.html           THE STORY        css/story.css   js/story/
    lab.html             THE LAB          css/lab.css     js/lab/
    css/tokens.css       shared colours, fonts, motion
    data/results.json    our measured results (read by story chapter 06)
    samples/lab/         Evidence-locker exhibits + manifest.json
    samples/game/        Spot-the-fake images + manifest.json
    assets/              fonts (local woff2), favicon, story assets
    vendor/              GSAP, Lenis, three.js, MediaPipe (all local, nothing loads from the internet)
  docs/                  ARCHITECTURE.md (API contract), ENGINE.md (how each test works), SETUP_WINDOWS.md,
                         DATA_SOURCES.md (every dataset and licence), MODEL_SELECTION.md, SOURCES_STORY.md
```

## Before Saturday
- Put the real school name into `web/index.html`: search for `[School Name]` in the credits. The line stays hidden until you do.
- Run the Friday checklist in `docs/SETUP_WINDOWS.md` **on the booth laptop with Wi-Fi off**. Most important: Live Cam
  captures and laptop-mic voice recordings of real classmates. Webcam frames and everyday microphones are where the
  engine raises most of its false alarms.
- Re-run the experiment (optional, ~45 min): `uv run python scripts/evaluate.py`. Chapter 06 updates by itself.

## Troubleshooting
| Problem | Fix |
|---|---|
| Lab shows a red **Engine offline** banner | The server is not running. Start `scripts\start_windows.bat` and wait for the green light (top right). Live cam still works without it. |
| "The engine is busy" | It is finishing the previous file. The lab retries by itself after 6 s. |
| A video or voice clip is slow | The CPU is doing all the work. Plug in the charger and close other programs. Videos analyse only the first 20 s, voice the first 30 s. |
| Camera does not start | Open the lab through `http://127.0.0.1:8000/lab.html`, not by double-clicking the file. Allow the camera (Chrome: lock icon → Camera → Allow). Close other apps that use the camera. |
| Evidence locker is empty | `web/samples/lab/manifest.json` is missing. Run `uv run python scripts/build_samples.py --lab`. |
| Results chapter says "Results pending" | `web/data/results.json` is missing. Run `uv run python scripts/evaluate.py`. |
| Port 8000 already in use | Another copy is running. Close all black windows and start once. |
| Story stutters on the TV | Set the TV to 1920×1080 at 100 % scaling, use Edge or Chrome with F11, and plug in the charger. |
| Engine cannot run at all | `scripts\emergency_browser.bat`: story, Live Cam and Spot the Fake work without Python (see the fallback plan). |
| A model shows `false` in `/api/health` | `models\` is incomplete. Run `setup_windows.bat` again with internet. |

More detail: `docs/SETUP_WINDOWS.md` (booth), `docs/ENGINE.md` (science and limits), `docs/ARCHITECTURE.md` (API).

## Ethics and licences
We never faked a celebrity, a politician or anyone we know. Every test fake either comes from a public research
dataset or was made by us from research-dataset material (GAN faces of people who do not exist pasted onto
FFHQ/COCO photos, one consenting paid actor from Google DFD, public-domain audiobook readings), and exists only to
test the detector.

**What is pretrained, and what is ours.** The two AI networks are open, pretrained models we chose by experiment
(best of 12 image and 7 voice candidates): CommunityForensics ViT (Park & Owens, CVPR 2025, MIT) and
wav2vec2-base-960h fine-tuned on In-the-Wild deepfake speech (abhishtagatya, Apache-2.0); faces are found by YuNet
(OpenCV Zoo, MIT) and MediaPipe Face Landmarker (Apache-2.0). Ours: the classic tests, the voice probe on top of
wav2vec2, the calibration, the fusion rule, the whole evaluation, the lab and the story.
Analysis never leaves the laptop. Sources and licences are listed in `docs/DATA_SOURCES.md` and `docs/SOURCES_STORY.md`.
Some evaluation material (FFHQ, research deepfake datasets) is non-commercial. Check those terms before publishing
this repository or the samples anywhere public.
