# VERITAS on the booth laptop (Windows) - one-click setup

You need internet **once** (about 3.5 GB, 15-30 minutes). After that VERITAS runs completely offline.

**You need:** a Windows 10 or 11 laptop (8 GB RAM is enough, no graphics card), **8 GB free on drive C:**, the
charger, and internet for the setup. Use the **same Windows user** for the setup and for the fair. Do not use
"Run as administrator".

## Set it up (do this the evening before, with internet)
1. Download **VERITAS-Windows.zip**:
   https://github.com/Ahamedinmotion/veritas/releases/latest/download/VERITAS-Windows.zip
2. Right-click the zip -> **Extract All...** -> **Extract**. (Double-clicking inside the zip without extracting does
   not work - setup tells you so.)
3. Open the new folder, then **VERITAS**, and double-click **`1 - SETUP (run once)`**.
   - "Windows protected your PC"? Click **More info -> Run anyway**.
   - "Do you want to allow this app to make changes" (Microsoft Visual C++)? Click **Yes**.
4. Wait. The window shows five steps (copy, Python and libraries, AI models, demo clips, test) and prints
   "... still working" every minute. It ends with:
   **`ALL DONE - double-click VERITAS on your Desktop.`**
5. Test it: double-click **VERITAS** on the Desktop. A black window opens ("Keep this window open during the fair.
   Close it to stop VERITAS.") and the browser opens the VERITAS story by itself. The **first** start after setup
   can take 2-4 minutes; later about 30 seconds.
6. Turn **Wi-Fi off**, close the black window, double-click VERITAS again: it must still work. That is the fair.

Setup installs everything into **`%USERPROFILE%\VERITAS`** (for example `C:\Users\Khais\VERITAS`; `C:\VERITAS` if the
user name has non-English letters) and makes two Desktop shortcuts: **VERITAS** and **VERITAS demo clips**. You can
delete the downloaded zip and folder afterwards. Running `1 - SETUP (run once)` again repairs or updates the install;
finished downloads are kept.

## At the fair
1. Charger in. Double-click **VERITAS** at least **2 minutes before** the first visitor (video analysis warms up in
   the background for 20-30 s after the browser opens).
2. Minimise the black window - do not close it and do not click inside it.
3. Press **F11** in the browser for full screen. The lab (Analyze / Live Cam / Spot the Fake) is linked from the story.
4. Demo files: open **VERITAS demo clips** on the Desktop and drag a file into the lab's Analyze tab.
   - `Evidence locker samples` = the lab's own public exhibits.
   - The `.mp4` research clips (FaceForensics++, Google DFD, Celeb-DF) are for **showing at the booth only**: never post,
     share or copy them for anyone. The Celeb-DF pair shows real celebrities: use it only if a judge asks.
   - Our own Wav2Lip clip is not downloaded (we do not publish it); copy it from the team's USB stick if wanted.
5. Something freezes? Close the black window and double-click VERITAS again (about 30 s).
6. The laptop fails completely? On any phone or laptop with internet open **https://veritas-infinia-2026.tocodex42.chatgpt.site/**: the story plays as
   usual and the online lab runs in showcase mode (the Evidence-locker exhibits open their real saved reports; Live Cam
   and Spot the Fake work). It cannot analyse new files: say so.

Scores of the research clips on the development Mac (fp32 face-swap mode, 48 frames; the booth laptop can differ by a
few points, more in int8 mode):

| Clip | Truth | Score | Verdict |
|---|---|---|---|
| `ffpp_original_069.mp4` | real | 47 | suspicious - a false alarm: say so honestly |
| `ffpp_deepfakes_069.mp4` / `ffpp_face2face_069.mp4` / `ffpp_neuraltextures_069.mp4` | fake | 94 / 68 / 69 | synthetic |
| `dfd_original_09.mp4` / `dfd_faceswap_09_13.mp4` | real / fake | 4 / 41 | authentic / only suspicious |
| `dfd_original_07.mp4` | real | 8 | authentic |
| `celebdf_real_id2_0000.mp4` / `celebdf_synthesis_id2_id16_0000.mp4` | real / fake | 34 / 83 | authentic / synthetic |

They are demonstrations, not a fair test: the three FF++ #069 fakes are in the training data of one face-swap network
(GenD), and we chose the face-swap detector pair after seeing its results on Celeb-DF and Google DFD clips.

## If setup stops
Setup prints **one** fix and keeps the details in **`%USERPROFILE%\VERITAS\setup-log.txt`** (send that file to the
team if the fix does not help).

| Setup says | Do this |
|---|---|
| Please UNZIP VERITAS first | Right-click the zip -> Extract All, then run `1 - SETUP (run once)` from the extracted folder. |
| Not enough free space | Free up 8 GB on C: (empty the Recycle Bin, delete big downloads), run setup again. |
| The Python installer could not be downloaded / libraries did not install / models did not download | Internet problem. Use a phone hotspot if the school Wi-Fi blocks downloads, run setup again. |
| The AI libraries cannot start | Install https://aka.ms/vs/17/release/vc_redist.x64.exe (needs an administrator), run setup again. |
| VERITAS is running right now | Close the black VERITAS window, run setup again. |
| The self-test found a problem | Restart the laptop, run setup again; if it still fails send `setup-log.txt` to the team. |
| Windows Security blocks a file | Allow it. Windows Security -> App & browser control -> **Smart App Control: Off or Evaluation**. |

| The black VERITAS window says | Do this |
|---|---|
| VERITAS is not completely set up | Run `1 - SETUP (run once)` again, with internet. |
| The Python part does not start | Run setup again **as this Windows user**. |
| Another program is using port 8000 | Restart the laptop, double-click VERITAS again. |
| VERITAS is already running | Nothing to fix: it just opens the browser. |
| The browser shows "This site can't be reached" | Wait until the black window has finished loading, then press F5. |

## Face-swap detector mode (automatic)
The black window prints the mode, e.g. `Face-swap detector: int8 (auto: 7.8 GB RAM is under 12 GB)`.
- **auto** (default): **int8** on a laptop with less than 12 GB of RAM, otherwise **fp32**, the benchmarked setting.
  On a 12 GB+ machine the scores are exactly the same as before.
- To force a mode, open `%USERPROFILE%\VERITAS\scripts\start_windows.bat` in Notepad and remove `REM ` in front of
  `REM set VERITAS_FACESWAP=int8` (write `fp32`, `int8`, `b7` or `off`; no quotes).

| Setting | What runs | Peak RAM, whole engine (macOS) | Time per video, slow-laptop proxy | Booth demo |
|---|---|---|---|---|
| `fp32` | GenD + DFDC-B7, exactly as benchmarked | 3.6-3.7 GB | 33-43 s (face-swap step 19-26 s) | 5 of 6 fakes synthetic |
| `int8` | GenD int8 + DFDC-B7 | about 2.85 GB | 28-30 s | borderline clips can flip (its threshold is unstable); story numbers are for `fp32` |
| `b7` | DFDC-B7 alone | about 2.3 GB | 20-21 s | 1 of 6 fakes synthetic, 4 suspicious |
| `off` | the engine as it was before 19 Nov | about 1.75 GB | 13-14 s | 1 of 6 fakes synthetic |

Never set `VERITAS_VIDEO_FRAMES` below 32: the engine uses 32 frames per video (48 on a 10+ thread CPU), and at 24 the
demo scores move (the chapter-05 Wav2Lip clip would read 64, not 70). Videos take longer on a slow laptop.

## For the team: how it works
- **The zip** (`python scripts/build_release_zip.py` -> `dist/VERITAS-Windows.zip`): `VERITAS/1 - SETUP (run once).bat`,
  `VERITAS/2 - START VERITAS.bat`, `VERITAS/VERITAS Guide.pdf`, `VERITAS/app/` (the git files minus models, eval data,
  dist, deploy and anything named like a research clip). The two launchers live in `scripts/release/`.
- **`scripts\setup_windows.bat`** (called by `1 - SETUP`): robocopy to `%USERPROFILE%\VERITAS` -> `Unblock-File` ->
  uv (`%USERPROFILE%\.local\bin`) -> `uv sync --locked --compile-bytecode` (Python 3.12, CPU PyTorch; x64 Python under
  emulation on ARM) -> `scripts\download_models.py` (SHA-256 checked) -> `scripts\fetch_demo_clips.py` (the research
  clips re-made from the same public Hugging Face mirrors, identical trims and encoding; never fatal) -> library check
  (installs the VC++ runtime if needed) -> Desktop shortcuts -> `scripts\selftest.py`. Log: `setup-log.txt`.
- **`scripts\start_windows.bat`** (the VERITAS shortcut and `2 - START VERITAS`): opens the browser if VERITAS already
  answers on `http://127.0.0.1:8000/api/health`; otherwise checks the install, starts
  `.venv\Scripts\python.exe -m uvicorn server.app:app --port 8000` offline (restarting it up to 5 times) and opens the
  default browser at the story once `/api/health` answers.
- **`VERITAS_CI=1`** skips every pause and the browser. The GitHub Actions workflow
  `.github/workflows/windows-setup.yml` (run by hand, or on a `v*` tag) builds the zip, unzips it into a folder with
  spaces and brackets, runs setup, checks both shortcuts, starts the engine through the VERITAS shortcut and sends every
  Evidence-locker sample through `/api/analyze/*` (verdicts must match `web/samples/lab/manifest.json`). Logs are
  uploaded as artifacts. Nothing is cached.
- Other scripts: `selftest_windows.bat` (the self-test again, offline), `emergency_browser.bat` (no-Python fallback),
  `start_windows_kit.bat` (offline kit, Appendix C). macOS: `./scripts/start_mac.sh`.

---

## Appendix A - pre-fair checklist (on the booth laptop, Wi-Fi OFF unless a step says otherwise)
1. [ ] Setup ended with `ALL DONE`; `setup-log.txt` shows `ALL PASS`. The black window prints the face-swap mode.
2. [ ] Cold start of VERITAS (first after setup) and warm start: write both times down.
3. [ ] `http://127.0.0.1:8000/api/health` shows `"ok": true` and all four models `true` (the lab header says
       "Online · CPU", not "3/4 models"). Run the story on the TV. Analyse every locker exhibit.
4. [ ] **RAM and time.** With the story (TV) and the lab open, open Task Manager. Analyse the **Real talking video**
       exhibit three times; write down the time, the `python.exe` memory and **Performance -> Memory -> Available**.
       Under about 1 GB available: force `int8`. A video over 40 s: `int8` (about 5 s faster) or `b7` (about 14 s
       faster, but only 1 of 6 booth fakes "synthetic"). Then run `scripts\selftest_windows.bat` again.
5. [ ] Click inside the black window, then run an analysis: it must still finish (the engine turns QuickEdit off).
6. [ ] Double-click VERITAS a second time: it must say "VERITAS is already running" and just open the browser.
7. [ ] Camera: Settings -> Privacy & security -> Camera: camera access ON and "Let desktop apps access your camera"
       ON; open the privacy shutter; quit Teams/Zoom; allow the camera for `127.0.0.1` in the browser.
8. [ ] **Live Cam false-alarm test.** Both presenters and 2-3 classmates each analyse 3 frames of themselves
       (different light, with and without glasses) and 3 laptop-mic voice clips. Write down every score. Webcam frames
       and everyday microphones are the engine's weakest spot (5 of 12 real video stills flagged; 75% of everyday-mic
       voices flagged when that dataset was left out). Also analyse two or three 10-20 s phone/webcam videos of
       classmates: the face-swap detector can push grainy real video to "suspicious" (11 of 39 webcam-quality real
       clips in our test, 1 "synthetic"). If a real person comes out "synthetic", say so honestly.
9. [ ] Display: Extend mode; TV at 1920x1080 and 100% scaling; a 1366x768 laptop panel at 100%. Browser full screen
       with **F11**. Known quirk: once the chapter-03 cards are revealed, later slides sit 25-33 px lower (fits at
       1080 px; on a 768 px screen the last line of slide 06·3 is cut off).
10. [ ] Sound: play the "Real human voice" exhibit; pick HDMI or the laptop speakers.
11. [ ] Power and interruptions: Best performance; sleep and screen-off Never; lid close Do nothing; Do Not Disturb
        on; Windows Update paused; OneDrive/Teams auto-start off; no antivirus scan on fair day.
12. [ ] Browser: finish its first-run screens; Edge: `edge://settings/system` -> "Never put these sites to sleep" ->
        add `127.0.0.1`. Do not use InPrivate/Guest (they wipe the game scoreboard).
13. [ ] Spot the Fake loads its images; Live Cam's "Camera paused" appears after 90 s with nobody in view; **Wake**
        restarts it.
14. [ ] Record a backup **demo video** of the story, every locker analysis and a Live Cam capture (Win+Alt+R).
15. [ ] Each presenter can explain ELA, noise residual, FFT, the EAR blink formula, what AUC means, why the held-out
        test set matters, and the honest limitations on slide 06·2.

## Appendix B - speed you can expect (CPU only)
Measured on the development Mac (Apple M4) and on the same Mac restricted to its 4 slow efficiency cores (a
pessimistic stand-in for a budget laptop). Fill in the last column on the booth laptop.

| Evidence | M4, all cores | M4, 4 efficiency cores (slow-laptop proxy) | Booth laptop (measure!) |
|---|---|---|---|
| First-ever start after setup | 66 s | 75 s (Windows Defender may add minutes) | |
| Warm restart | 5 s | | |
| Photo | 0.5-1.1 s | 3-5 s | |
| Voice clip (up to 30 s analysed) | 0.3-1.6 s | 2-4 s | |
| Video (first 20 s analysed) | 5-6 s (face-swap detector: about 2.5 s of it) | 33-43 s warm (face-swap step 19-26 s; without the detector 13-14 s); up to 55 s right after start-up | |
| Peak RAM, whole engine, while analysing a video | 3.6-3.7 GB (flat over 20 videos in a row) | about 3.6-3.7 GB | |

(Slow-laptop proxy: 4 threads, the 18 s exhibit, warm engine; two review sessions on 19 Nov. The modes other than
`fp32` were measured at 24 frames; add about 1.5 s at 32.) Very large photos (> 24 MP) run their pixel tests one after
another to stay within 8 GB of RAM.

## Appendix C - fallbacks
| Tier | When | What to do |
|---|---|---|
| **0** | Anything freezes | Close the black window, double-click VERITAS again (about 30 s). |
| **1** | The engine cannot run at all (VC++ runtime, antivirus, broken install) | Online: open **https://veritas-infinia-2026.tocodex42.chatgpt.site/** (the story, plus the lab in showcase mode: saved reports, Live Cam and Spot the Fake; it cannot analyse new files). Offline: `%USERPROFILE%\VERITAS\scripts\emergency_browser.bat` opens the story from the folder; Analyze then needs `lab.html?mock=1&samples=1` and you must **tell visitors it is demo data**. |
| **2** | The laptop misbehaves | Play the backup demo video recorded on this laptop. |
| **3** | The laptop is dead | The development Mac with a USB-C to HDMI adapter: `./scripts/start_mac.sh` works with no network. |

**Offline kit (no internet on the laptop at all; backup, untested on Windows).** Built on the Mac with
`./scripts/build_winkit.sh` (writes `../_usb/winkit/`, 3.6 GB: Windows x64 libraries, the VC++ DLLs, a portable Python
and a copy of all models). Copy the app folder to `C:\veritas`, the kit to `C:\veritas\winkit`, then in a Command
Prompt: `cd /d C:\veritas` and
`tar -xf "winkit\cpython-3.12.12+20260127-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" -C winkit`, then
double-click `scripts\start_windows_kit.bat`.

**Privacy at the kiosk.** After 150 s without any input the Analyze tab forgets every Live Cam capture and returns a
finished report to the intake screen (`lab.html?idle=300` changes the delay).
