# VERITAS on the booth laptop (Windows) - dead-simple steps

The lab runs **completely offline** at the fair. You only need internet **once**, before the fair, to install
Python, the libraries and the AI models. Do it at home or school, not at the venue.

## What you need
- The Windows laptop (Windows 10 or 11, **x64**; 8 GB RAM is fine, no graphics card needed)
- Microsoft Edge or Google Chrome (version 120 or newer)
- **6 GB free on C:** - models about 530 MB, the Python environment about 1.3 GB, plus about 1.4 GB of uv cache
- Internet for 15 minutes (only for setup - or none at all with Route C)
- Set up and run under the **same Windows user account** (the environment points into that user's AppData)

## Route A - set up directly on the laptop (recommended)

1. Copy the `veritas` folder to **`C:\veritas`** (ASCII-only path, **not** inside OneDrive, Desktop or Documents).
   **Leave out `.venv`, `eval_data` and `.git`** (`.venv` belongs to the Mac; `eval_data` is only for
   `scripts/evaluate.py`). Copying `models\` saves the 530 MB model download.
2. Open `C:\veritas\scripts` and **double-click `setup_windows.bat`**.
   - If Windows shows "Windows protected your PC", click **More info -> Run anyway**.
   - It installs `uv`, Python 3.12 and the libraries (CPU-only PyTorch), downloads any missing models, checks that
     the AI libraries really load, and runs the **self-test** (every Evidence-locker exhibit through the engine,
     which also pre-warms the one-time caches). It must end with `ALL PASS` and `SETUP COMPLETE`. 5-15 minutes.
   - If it stops with "the AI libraries cannot load": install the **Microsoft Visual C++ 2015-2022 Redistributable
     x64** (`vc_redist.x64.exe` on the USB stick, or https://aka.ms/vs/17/release/vc_redist.x64.exe; needs admin),
     then run setup again.
3. Test it: **double-click `scripts\start_windows.bat`**. A black window opens ("keep this window open"); Edge
   opens `http://127.0.0.1:8000/` by itself when the engine is ready. **The very first start after setup can take
   2-4 minutes** (Windows Defender scans the new files); after that about 30 s.
4. Turn Wi-Fi **off** and start it again - it must still work. That is exactly the situation at the fair.

## Route B - USB stick, laptop gets internet briefly
The Python environment (`.venv`) is **not** portable between computers, but the models are. Copy `veritas`
(with `models\`, without `.venv`, `eval_data`, `.git`) to `C:\veritas`, then run `setup_windows.bat` with a phone
hotspot for 15 minutes. `download_models.py` sees the models are already there and skips them.

## Route C - offline kit, no internet on the laptop at all (backup; untested on Windows until Friday)
Built on the Mac with `./scripts/build_winkit.sh` (needs internet on the Mac only; about 5 s with a warm cache).
It writes `../_usb/winkit/` (1.3 GB): every library cross-installed for Windows x64 + Python 3.12, the Visual C++
runtime DLLs copied next to PyTorch (no admin install needed), and the portable Python archive.
1. Copy `veritas` (with `models\`) to `C:\veritas`, then copy the kit folder to **`C:\veritas\winkit`**.
2. In a Command Prompt:
   ```
   cd /d C:\veritas
   tar -xf "winkit\cpython-3.12.12+20260127-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" -C winkit
   ```
   This creates `winkit\python\python.exe`.
3. Double-click **`scripts\start_windows_kit.bat`** (instead of `start_windows.bat`).

## Every day of the fair
1. Plug in the charger (the AI uses a lot of CPU; battery mode makes it slower). Power mode: Best performance.
2. Double-click `scripts\start_windows.bat`. Wait for the browser to open. **Do not click inside the black window**
   (the engine turns off "QuickEdit" so a click can no longer freeze it, but leave it alone anyway).
3. Leave the black window open (minimise it). Closing it stops the lab. If the engine ever stops on its own, the
   window restarts it (up to 5 times).
4. Saturday 7:45: start the server, double-click `scripts\selftest_windows.bat` (or analyse one photo, one voice clip
   and one video), then open the story on the TV with **F11**.
5. If anything freezes: close the black window, double-click `start_windows.bat` again (about 30 s).

## Pre-fair checklist (Friday 20 Nov, on the booth laptop, Wi-Fi OFF unless a step says otherwise)
1. [ ] `echo %PROCESSOR_ARCHITECTURE%` prints **AMD64** (ARM laptops: setup switches to x64 Python under emulation;
       test everything twice).
2. [ ] The folder is `C:\veritas`: ASCII only, not inside OneDrive, Desktop or Documents. Setup and the fair use
       the same Windows user.
3. [ ] MIME check: the self-test line `PASS .js is served as text/javascript` (the engine pins the types; Windows
       registry entries such as `reg query HKCR\.js /v "Content Type"` = `text/plain` would otherwise blank both
       pages).
4. [ ] Run `setup_windows.bat` **with internet**; then, with Wi-Fi **off**, run `selftest_windows.bat`: it must say
       `ALL PASS`. Write down the cold-start time of `start_windows.bat`, then restart and write down the warm time.
5. [ ] `http://127.0.0.1:8000/api/health` shows `"ok": true` and all three models `true` (the lab header says
       "Online · CPU"). Run the story's 49 steps on the TV. Analyse every locker exhibit and fill in the speed table.
6. [ ] Click inside the black window, then run an analysis: it must still finish.
7. [ ] Double-click `start_windows.bat` a second time: it must say "Port 8000 is already in use" and just open the
       browser.
8. [ ] Camera:
       - Settings -> Privacy & security -> Camera: **Camera access ON** and **"Let desktop apps access your camera" ON**.
       - Open the physical privacy shutter / turn off the F-key camera kill switch.
       - Quit Teams/Zoom and stop them auto-starting.
       - Allow the camera for `127.0.0.1` in Edge (lock icon -> Camera -> Allow).
9. [ ] **Live Cam false-alarm test (important).** Both presenters plus 2-3 classmates each capture & analyse 3
       frames of themselves (different lighting, with and without glasses). Also record 3 laptop-mic voice clips
       and analyse them. Write down every score. Webcam frames and everyday microphones are the engine's weakest
       spot (5 of 12 real video stills flagged; 75% of everyday-mic voices flagged when that dataset was left out).
       If a real person comes out "synthetic", say so honestly at the booth and explain why.
10. [ ] Display: **Extend** mode; the TV at 1920×1080 and **100%** scaling; the laptop panel at **100%** if it is
       1366×768 (at 125% the locker and the game buttons fall below the fold). Use **F11** browser fullscreen (it
       survives moving between story and lab; the page's own `F` fullscreen ends on every story <-> lab jump).
       Optional kiosk window for the lab: `msedge --kiosk http://127.0.0.1:8000/lab.html --edge-kiosk-type=fullscreen --no-first-run` (exit with Alt+F4).
11. [ ] Sound: play the "Real human voice" exhibit and pick HDMI or the laptop speakers.
12. [ ] Power and interruptions: charger in, Best performance; sleep and screen-off **Never**, lid close **Do
       nothing**; no screen saver or lock timeout; **Do Not Disturb** on; **Windows Update paused**; OneDrive and
       Teams auto-start off; no antivirus scan scheduled for Saturday.
13. [ ] Edge: open it once to finish the first-run screens; `edge://settings/system` -> "Never put these sites to
       sleep" -> add `127.0.0.1`; `edge://version` is 120 or newer; if Live Cam's tracker fails to load, try turning
       off "Enhance your security on the web" for 127.0.0.1. Do **not** use InPrivate or a Guest profile (they wipe
       the game scoreboard).
14. [ ] Windows Security -> App & browser control -> **Smart App Control: Off or Evaluation** (otherwise unsigned
       Python DLLs may be blocked).
15. [ ] Spot the Fake loads its images; Live Cam's "Camera paused" message appears after 90 s with nobody in front of
       it, and **Wake** restarts it.
16. [ ] Record the **Tier 2 demo video** (below), then dry-run `emergency_browser.bat` **with the server closed**.
17. [ ] Each presenter can explain: ELA, noise residual, FFT, EAR blink formula, what AUC means, why the held-out
       test set matters, and the honest limitations on slide 06·2.

## Fallback plan (if something breaks on the day)
| Tier | When | What to do |
|---|---|---|
| **0** | Anything freezes | Close the black window and run `start_windows.bat` again (about 30 s). |
| **1** | The Python engine cannot run at all (VC++ runtime, antivirus, broken `.venv`, another Windows user) | Double-click **`scripts\emergency_browser.bat`**. It opens Edge (or Chrome) with a separate profile that may read local files. The story, Live Cam and Spot the Fake work for real. Analyze needs the engine: open `lab.html?mock=1&samples=1` and **tell visitors it is demo data** (the engine light reads "Mock data"). |
| **2** | The laptop itself misbehaves | Play the **demo video** recorded on Friday on this laptop (Win+Alt+R, or the Snipping Tool screen recorder): the story run-through, every locker analysis and a Live Cam capture. Keep it on the laptop and on the USB stick. |
| **3** | The laptop is dead | Bring the development Mac with a USB-C to HDMI adapter as a hot spare. `./scripts/start_mac.sh` is verified to work with no network. |

**The USB stick holds:** the `veritas` folder (without `.venv`, `eval_data`, `.git`); the offline kit (`winkit`,
Route C); `vc_redist.x64.exe`; the demo video; and a copy of `web/samples/lab/` for drag-and-drop demos.

## Speed you can expect (CPU only)
Measured on the development Mac (Apple M4) and on the same Mac restricted to its 4 slow efficiency cores, which is a
pessimistic stand-in for a budget laptop. Fill in the last column on Friday.

| Evidence | M4, all cores | M4, 4 efficiency cores (slow-laptop proxy) | Booth laptop (measure!) |
|---|---|---|---|
| First-ever start after setup | 66 s | 75 s (Windows Defender may add minutes) | |
| Warm restart | 5 s | | |
| Photo | 0.5-1.1 s | 3-5 s | |
| Voice clip (up to 30 s analysed) | 0.3-1.6 s | 2-4 s | |
| Video (first 20 s analysed) | 2-5 s | 15-25 s (24 face frames are used on <= 4-thread CPUs) | |

The engine now warms up voice and video analysis at start (the one-time numba / matplotlib / codec cost of 10-30 s
is paid before the first visitor; a visitor who arrives during the video warm-up simply queues for a few seconds).
Very large photos (> 24 MP) run their pixel tests one after another to stay within 8 GB of RAM.

## Troubleshooting
| Problem | Fix |
|---|---|
| `uv is not recognized` | Run `setup_windows.bat` again; then close and reopen the window. |
| Setup says "library install failed" | Read the lines above it: network filter, antivirus, or an old uv (setup now runs `uv self update`). No internet at all: use Route C. |
| Black window shows `Error loading c10.dll` / setup says "the AI libraries cannot load" | Install `vc_redist.x64.exe` from the USB stick (admin). No admin: use Route C (its kit carries the DLLs). |
| Black window says "the Python environment is broken" | `.venv` was made by another Windows user or AppData was cleaned. Run `setup_windows.bat` again as this user. |
| Black window closes immediately | Run `setup_windows.bat` first (the `.venv` folder is missing). |
| Story stuck on its "000" loader, or the lab shows only its header | A browser refused the JavaScript files. Open DevTools -> Console. The engine pins the MIME types, so this should not happen with `start_windows.bat`; check that you opened `http://127.0.0.1:8000/`, not the file. |
| Browser says "This site can't be reached" | Wait until the black window has finished loading, then press F5. |
| "Port 8000 is already in use" | VERITAS is already running in another window - use that one, or close all black windows and start once. |
| Every analysis hangs with "taking longer than usual" while the light is green | Someone selected text in the black window: press **Esc** in it. (The engine disables QuickEdit, so this should not happen.) |
| Health shows a model `false`, or start says "model files are missing" | The `models\` folder is incomplete - copy it from the USB stick or run `setup_windows.bat` with internet. |
| Camera does not start / "Camera access blocked" / "Camera is busy" | Windows Settings -> Privacy & security -> Camera: turn on camera access and "Let desktop apps access your camera"; open the camera shutter; close Teams/Zoom; allow the camera in Edge. |
| Live Cam says "Camera paused" | Nobody was in view for 90 s. Click **Wake**. |
| Antivirus blocks `uv.exe` or Python | Allow it; Smart App Control must be Off or Evaluation. |
| Very slow analysis | Plug in the charger; close other programs; use Windows "Best performance" power mode. |

## Privacy at the kiosk
After 150 s without any mouse, key or touch input, the Analyze tab forgets every Live Cam capture (the thumbnails
are visitors' faces) and returns a finished report to the intake screen. Other cases stay in "This session".
(`lab.html?idle=300` changes the delay.)

## For the curious: what the scripts do
- `scripts\setup_windows.bat` -> installs uv (and updates it), runs `uv sync --locked --compile-bytecode` (creates
  `.venv` with exactly the library versions in `uv.lock`: Python 3.12 and CPU PyTorch), runs
  `scripts\download_models.py` (pinned model revisions, SHA-256 checked), checks that PyTorch & co. import, then
  runs `scripts\selftest.py`.
- `scripts\start_windows.bat` -> checks `.venv`, the models and port 8000, then runs
  `.venv\Scripts\python.exe -m uvicorn server.app:app --port 8000` with `HF_HUB_OFFLINE=1` (restarting it up to 5
  times if it stops), waits for `/api/health`, then opens Edge.
- `scripts\selftest_windows.bat` -> runs every locker exhibit through the engine without a browser; `ALL PASS` = ready.
- `scripts\emergency_browser.bat` -> Tier 1 fallback without Python (see above).
- `scripts\start_windows_kit.bat` -> Route C, the engine from the offline kit.
- Mac/Linux: `./scripts/start_mac.sh` does the same as `start_windows.bat`.
