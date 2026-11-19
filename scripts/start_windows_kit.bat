@echo off
setlocal EnableExtensions
title VERITAS - Deepfake Forensics Lab, offline kit (keep this window open)
REM ROUTE C - runs the engine from the prebuilt offline kit (winkit\) instead of .venv. No internet, no install.
REM Build the kit on the Mac with  scripts/build_winkit.sh  and copy the winkit folder into this veritas folder.
REM UNTESTED ON WINDOWS until the Friday check - keep start_windows.bat as the main route.
cd /d "%~dp0.."
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONUTF8=1
REM Face-swap detector (video): fp32 = default, int8 = less RAM, b7 = smallest, off. See docs\SETUP_WINDOWS.md.
REM Remove "REM " to switch (no quotes around the value):
REM set VERITAS_FACESWAP=int8
REM Video frames sampled per clip: the engine uses 32 (48 on a 10+ thread CPU); 24 is faster but moves demo scores.
REM set VERITAS_VIDEO_FRAMES=24
set "PYTHONPATH=%CD%\winkit\site-packages"
if not exist "winkit\python\python.exe" (
  echo  ERROR: winkit\python\python.exe is missing.
  echo         In this folder run:  tar -xf "winkit\cpython-3.12.12+20260127-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" -C winkit
  pause
  exit /b 1
)
REM Models: models\ (copied with veritas) or, if that is missing or has no face-swap detector, the copy in the kit.
set "MODELDIR=models"
if not exist "models\face_swap\dfdc_b7.onnx" if exist "winkit\models\face_swap\dfdc_b7.onnx" set "MODELDIR=winkit\models"
if not "%MODELDIR%"=="models" set "VERITAS_MODELS=%CD%\%MODELDIR%"
if not exist "%MODELDIR%\ai_generated\model.safetensors" (
  echo  ERROR: the models folder is missing - copy it from the USB stick into this folder.
  pause
  exit /b 1
)
echo  Models: %MODELDIR%
if not exist "%MODELDIR%\face_swap\dfdc_b7.onnx" echo  WARNING: %MODELDIR%\face_swap is missing - videos will run WITHOUT the face-swap detector.
"winkit\python\python.exe" -c "from server import config as c; print('  Face-swap detector mode:', c.faceswap_mode(), '   video frames per clip:', c.video_sampled_frames())"
start "" /min powershell -NoProfile -ExecutionPolicy ByPass -c "for($i=0;$i -lt 600;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health; if($r.StatusCode -eq 200){try{Start-Process msedge -ArgumentList '--new-window','http://127.0.0.1:8000/'}catch{Start-Process 'http://127.0.0.1:8000/'}; break}}catch{}; Start-Sleep -Seconds 1}"
echo  Loading AI models from the offline kit ... the browser opens by itself when ready.
"winkit\python\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --log-level warning
echo.
echo  The VERITAS server has stopped.
pause
