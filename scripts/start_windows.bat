@echo off
setlocal EnableExtensions
title VERITAS - Deepfake Forensics Lab (keep this window open)
cd /d "%~dp0.."
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONUTF8=1
REM Face-swap detector (video): fp32 = default, int8 = less RAM, b7 = smallest, off. See docs\SETUP_WINDOWS.md.
REM Remove "REM " to switch (no quotes around the value):
REM set VERITAS_FACESWAP=int8
REM Video frames sampled per clip: the engine uses 32 (48 on a 10+ thread CPU). 24 is faster, but then some demo
REM scores move by up to 6 points (the Wav2Lip clip reads 64 instead of 70). See docs\SETUP_WINDOWS.md.
REM set VERITAS_VIDEO_FRAMES=24

echo.
echo  ==============================================================
echo    VERITAS - Deepfake Forensics Lab
echo    Starting the forensic engine: about 30 s, but the very first
echo    start after setup can take 2-4 minutes.
echo    KEEP THIS WINDOW OPEN while the exhibition is running.
echo    Do not click inside this window. To stop: close it.
echo  ==============================================================
echo.

echo %CD% | find /i "OneDrive" >nul && echo  WARNING: this folder is inside OneDrive. Move it to C:\veritas - OneDrive can make files unavailable offline. && echo.

if not exist ".venv\Scripts\python.exe" (
  echo  ERROR: .venv is missing. Run scripts\setup_windows.bat once with internet first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo  ERROR: the Python environment is broken - for example set up by another Windows user.
  echo         Run scripts\setup_windows.bat again with internet, as this Windows user.
  pause
  exit /b 1
)
set "MISSING="
if not exist "models\ai_generated\model.safetensors" set "MISSING=%MISSING% ai_generated"
if not exist "models\audio_deepfake\model.safetensors" set "MISSING=%MISSING% audio_deepfake"
if not exist "models\face_detector\face_detection_yunet_2023mar.onnx" set "MISSING=%MISSING% face_detector"
if defined MISSING (
  echo  ERROR: model files are missing:%MISSING%
  echo         Run scripts\setup_windows.bat once with internet,
  echo         or copy the models folder from the USB stick into this folder.
  pause
  exit /b 1
)

REM Face-swap files the chosen mode needs (fp32: gend_clip + det_10g + dfdc_b7, int8: gend_clip_int8 + det_10g + dfdc_b7)
set "FSMODE=fp32"
if defined VERITAS_FACESWAP set "FSMODE=%VERITAS_FACESWAP:"=%"
set "FSMISSING="
if /i "%FSMODE%"=="off" goto fscheck_done
if not exist "models\face_swap\dfdc_b7.onnx" set "FSMISSING=%FSMISSING% dfdc_b7.onnx"
if /i "%FSMODE%"=="b7" goto fscheck_done
if not exist "models\face_swap\det_10g.onnx" set "FSMISSING=%FSMISSING% det_10g.onnx"
set "FSFILE=gend_clip.onnx"
if /i "%FSMODE%"=="int8" set "FSFILE=gend_clip_int8.onnx"
if not exist "models\face_swap\%FSFILE%" set "FSMISSING=%FSMISSING% %FSFILE%"
:fscheck_done
if defined FSMISSING (
  echo  WARNING: models\face_swap is incomplete:%FSMISSING%
  echo           Videos will run WITHOUT the face-swap detector. Copy the models folder from the USB stick.
  echo.
)
REM Print the settings this engine will actually use (face-swap mode, video frames).
".venv\Scripts\python.exe" -c "from server import config as c; print('  Face-swap detector mode:', c.faceswap_mode(), '   video frames per clip:', c.video_sampled_frames())"

REM Already running? Port 8000 taken - most likely by another VERITAS window.
netstat -ano -p TCP | findstr /R /C:"127\.0\.0\.1:8000 .*LISTENING" /C:"0\.0\.0\.0:8000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo  Port 8000 is already in use - VERITAS is probably already running in another window.
  echo  Opening the browser. If the lab does not load, close ALL black windows and start again.
  start "" "http://127.0.0.1:8000/"
  pause
  exit /b 0
)

REM Open the browser - Edge if present - once /api/health answers. Checked by a background PowerShell loop, up to 10 min.
start "" /min powershell -NoProfile -ExecutionPolicy ByPass -c "for($i=0;$i -lt 600;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health; if($r.StatusCode -eq 200){try{Start-Process msedge -ArgumentList '--new-window','http://127.0.0.1:8000/'}catch{Start-Process 'http://127.0.0.1:8000/'}; break}}catch{}; Start-Sleep -Seconds 1}"

echo  Loading AI models ... the browser opens by itself when the lab is ready.
echo  If it does not, open  http://127.0.0.1:8000/  in Edge or Chrome.
echo.

REM If the engine ever stops on its own, restart it - up to 5 times.
set RESTARTS=0
:run
".venv\Scripts\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --log-level warning
set /a RESTARTS+=1
if %RESTARTS% GEQ 5 goto stopped
echo.
echo  The engine stopped - restarting in 5 s. Close this window to stop for good.
timeout /t 5 /nobreak >nul
goto run
:stopped
echo.
echo  The VERITAS server has stopped 5 times. Read the messages above, then see docs\SETUP_WINDOWS.md.
pause
