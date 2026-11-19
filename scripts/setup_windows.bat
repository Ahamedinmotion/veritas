@echo off
setlocal EnableExtensions
title VERITAS - one-time setup
cd /d "%~dp0.."

echo.
echo  ==============================================================
echo    VERITAS - Deepfake Forensics Lab : ONE-TIME SETUP
echo    Needs INTERNET. Takes 5-15 minutes. Run it once, at home/school.
echo    Run it as the SAME Windows user that will run the fair.
echo  ==============================================================
echo.

REM ---- warnings about the install location
echo %CD% | find /i "OneDrive" >nul && echo  WARNING: this folder is inside OneDrive. Move it to C:\veritas - OneDrive can make files unavailable offline. && echo.

REM ---- ARM laptops (Snapdragon): numpy has no Windows-ARM wheel, so use x64 Python under emulation
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
  echo  ARM processor detected - using x64 Python under emulation.
  set "UV_PYTHON=cpython-3.12-windows-x86_64-none"
)

REM ---- 1. uv (Python manager). Installs to %USERPROFILE%\.local\bin
where uv >nul 2>nul
if %errorlevel%==0 goto have_uv
if exist "%USERPROFILE%\.local\bin\uv.exe" goto add_path
echo  [1/4] Installing uv - the Python package manager ...
powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
:add_path
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
:have_uv
where uv >nul 2>nul
if not %errorlevel%==0 (
  echo.
  echo  ERROR: uv could not be installed. Check the internet connection and run this file again.
  pause
  exit /b 1
)
REM an old uv cannot read this project's lock file; update it - harmless if it is already current
uv self update >nul 2>nul
uv --version
echo  [1/4] uv is ready.

REM ---- 2. Python 3.12 + all libraries (CPU-only PyTorch) into .venv
echo  [2/4] Installing Python 3.12 and libraries into .venv - about 1.3 GB ...
uv sync --locked --compile-bytecode
if not %errorlevel%==0 (
  echo.
  echo  ERROR: library install failed - see the messages above: network, antivirus, or an old uv.
  pause
  exit /b 1
)

REM ---- 3. AI models into models\  (about 530 MB; skipped if the models folder was copied)
echo  [3/4] Downloading the AI models into models\ ...
".venv\Scripts\python.exe" scripts\download_models.py
if not %errorlevel%==0 (
  echo.
  echo  ERROR: some models did not download. Run this file again with internet.
  pause
  exit /b 1
)

REM ---- 4. Can the AI libraries actually load? PyTorch needs the Microsoft Visual C++ runtime.
echo  [4/4] Checking that the engine libraries load ...
REM (onnxruntime only loads its DLLs when a session is created, so open the small face detector once.)
".venv\Scripts\python.exe" -c "import os, torch, transformers, mediapipe, cv2, av, soundfile, librosa, torchvision, onnxruntime as ort; p='models/face_swap/det_10g.onnx'; os.path.exists(p) and ort.InferenceSession(p, providers=['CPUExecutionProvider']); print('  engine libraries OK')"
if errorlevel 1 (
  echo.
  echo  ERROR: the AI libraries cannot load. Install the Microsoft Visual C++ 2015-2022 Redistributable x64
  echo         from https://aka.ms/vs/17/release/vc_redist.x64.exe - or vc_redist.x64.exe on the USB stick -
  echo         then run this file again.
  pause
  exit /b 1
)

echo.
echo  Running the self-test - this also pre-warms the one-time caches, so the first visitor does not wait ...
echo.
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONUTF8=1
".venv\Scripts\python.exe" scripts\selftest.py
if errorlevel 1 (
  echo.
  echo  WARNING: the self-test did not pass - read the FAIL lines above, then see docs\SETUP_WINDOWS.md.
  pause
  exit /b 1
)

echo.
echo  ==============================================================
echo    SETUP COMPLETE. From now on no internet is needed.
echo    Start the lab any time by double-clicking  scripts\start_windows.bat
echo  ==============================================================
echo.
pause
