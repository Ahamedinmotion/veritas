@echo off
REM ==========================================================================================
REM  VERITAS - start the forensic engine and open the story in the default browser.
REM  The Desktop shortcut "VERITAS" runs this file. KEEP ITS WINDOW OPEN during the fair.
REM  If VERITAS is already running, it only opens the browser.
REM
REM  Face-swap detector mode: "auto" by default = int8 on a laptop with less than 12 GB of RAM,
REM  otherwise fp32 (the benchmarked setting). To force a mode, remove "REM " from the next line
REM  and write fp32, int8, b7 or off - no quotes. See docs\SETUP_WINDOWS.md.
REM set VERITAS_FACESWAP=int8
REM  Never set VERITAS_VIDEO_FRAMES below 32: the demo scores would move.
REM
REM  VERITAS_CI=1  no browser, no pauses, no automatic restarts (GitHub Actions)
REM  cmd.exe rules kept on purpose: NO ( ) blocks, every path in quotes, single-line IF + GOTO,
REM  ASCII only, CRLF line endings.
REM ==========================================================================================
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "PORT=8000"
if defined VERITAS_PORT set "PORT=%VERITAS_PORT%"
set "VERITAS_PORT=%PORT%"
set "VURL=http://127.0.0.1:%PORT%/"
set "CI_MODE="
if "%VERITAS_CI%"=="1" set "CI_MODE=1"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

REM ---- 1. Already running? Then just open the browser.
curl.exe -s -f -m 3 -o nul "%VURL%api/health" >nul 2>nul
if not errorlevel 1 goto already_running

REM ---- 2. Is everything installed?
if not exist "%PY%" goto need_setup
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto broken_env
if not exist "%ROOT%\models\ai_generated\model.safetensors" goto need_setup
if not exist "%ROOT%\models\audio_deepfake\model.safetensors" goto need_setup
if not exist "%ROOT%\models\face_detector\face_detection_yunet_2023mar.onnx" goto need_setup

REM ---- 3. Another VERITAS window still loading its models? Wait for that one instead of starting a second engine.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*server.app*' }; if ($p) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 goto starting_elsewhere

REM ---- 4. Port taken by some other program?
netstat -ano -p TCP | findstr /R /C:"127\.0\.0\.1:%PORT% .*LISTENING" /C:"0\.0\.0\.0:%PORT% .*LISTENING" >nul
if not errorlevel 1 goto port_busy

title VERITAS engine - keep this window open
echo.
echo  ==============================================================
echo    VERITAS - Deepfake Forensics Lab
echo.
echo    Keep this window open during the fair.
echo    Close it to stop VERITAS.
echo.
echo    Starting: about 30 seconds - the very first start after
echo    setup can take 2-4 minutes. The browser opens by itself.
echo    Do not click inside this window.
echo  ==============================================================
echo.
echo "%ROOT%" | find /i "OneDrive" >nul
if not errorlevel 1 echo  WARNING: this folder is inside OneDrive - OneDrive can make files unavailable offline. Run 1 - SETUP again.
"%PY%" -c "from server import config as c; print('  Face-swap detector:', c.faceswap_mode_note(), '   video frames per clip:', c.video_sampled_frames())" 2>nul
echo.

REM ---- 5. Open the story in the default browser as soon as /api/health answers (background, up to 15 min).
if "%CI_MODE%"=="1" goto run_engine
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$ProgressPreference = 'SilentlyContinue'; for ($i = 0; $i -lt 900; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 ($env:VURL + 'api/health'); if ($r.StatusCode -eq 200) { Start-Process $env:VURL; break } } catch {}; Start-Sleep -Seconds 1 }"
echo  Loading the AI models ... If the browser does not open by itself, type
echo  %VURL%  into Edge or Chrome.
echo.

REM ---- 6. Run the engine. If it ever stops on its own, start it again - up to 5 times.
:run_engine
set "RESTARTS=0"
:run
"%PY%" -m uvicorn server.app:app --host 127.0.0.1 --port %PORT% --log-level warning
set "RC=%errorlevel%"
if "%CI_MODE%"=="1" exit /b %RC%
set /a RESTARTS+=1
if %RESTARTS% GEQ 5 goto stopped
echo.
echo  The engine stopped - starting it again in 5 seconds. Close this window to stop VERITAS.
timeout /t 5 /nobreak >nul
goto run

REM =========================================================================== messages
:already_running
echo.
echo  VERITAS is already running - opening the browser.
if "%CI_MODE%"=="1" exit /b 0
start "" "%VURL%"
timeout /t 4 >nul
exit /b 0

:starting_elsewhere
echo.
echo  VERITAS is already starting in another window.
echo  The browser opens when it is ready - this window closes by itself.
if "%CI_MODE%"=="1" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; for ($i = 0; $i -lt 600; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 ($env:VURL + 'api/health'); if ($r.StatusCode -eq 200) { Start-Process $env:VURL; exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if not errorlevel 1 exit /b 0
echo  It did not answer within 10 minutes.
echo  Fix: close every black VERITAS window, then double-click VERITAS on the Desktop again.
goto pause_exit

:need_setup
echo.
echo  VERITAS is not completely set up on this laptop.
echo  Fix: double-click "1 - SETUP (run once)" in the downloaded VERITAS folder - it needs the internet once.
goto pause_exit

:broken_env
echo.
echo  The Python part of VERITAS does not start - for example it was set up by another Windows user.
echo  Fix: as this Windows user, double-click "1 - SETUP (run once)" again, with internet.
goto pause_exit

:port_busy
echo.
echo  Another program is using port %PORT%, so VERITAS cannot start.
echo  Fix: restart the laptop, then double-click VERITAS on the Desktop again.
goto pause_exit

:stopped
echo.
echo  The VERITAS engine stopped 5 times - read the messages above.
echo  Fix: restart the laptop and double-click VERITAS again. If it happens again, run "1 - SETUP (run once)" again.
goto pause_exit

:pause_exit
if "%CI_MODE%"=="1" exit /b 1
echo.
pause
exit /b 1
