@echo off
setlocal EnableExtensions
title VERITAS - self-test (no internet needed)
cd /d "%~dp0.."
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONUTF8=1
echo.
echo  VERITAS self-test: runs every Evidence-locker exhibit through the engine.
echo  Takes about 30 s - 3 min. It must end with  ALL PASS.
echo.
if not exist ".venv\Scripts\python.exe" (
  echo  ERROR: .venv is missing. Run scripts\setup_windows.bat once with internet first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\selftest.py
echo.
pause
