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
set "PYTHONPATH=%CD%\winkit\site-packages"
if not exist "winkit\python\python.exe" (
  echo  ERROR: winkit\python\python.exe is missing.
  echo         In this folder run:  tar -xf "winkit\cpython-3.12.12+20260127-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" -C winkit
  pause
  exit /b 1
)
if not exist "models\ai_generated\model.safetensors" (
  echo  ERROR: the models folder is missing - copy it from the USB stick into this folder.
  pause
  exit /b 1
)
start "" /min powershell -NoProfile -ExecutionPolicy ByPass -c "for($i=0;$i -lt 600;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health; if($r.StatusCode -eq 200){try{Start-Process msedge -ArgumentList '--new-window','http://127.0.0.1:8000/'}catch{Start-Process 'http://127.0.0.1:8000/'}; break}}catch{}; Start-Sleep -Seconds 1}"
echo  Loading AI models from the offline kit ... the browser opens by itself when ready.
"winkit\python\python.exe" -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --log-level warning
echo.
echo  The VERITAS server has stopped.
pause
