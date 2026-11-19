@echo off
REM VERITAS self-test: every Evidence-locker exhibit through the engine (no browser, no internet).
REM Setup runs it once. Run it again on the morning of the fair: it must end with ALL PASS.
REM cmd.exe rules: no ( ) blocks, paths in quotes, CRLF line endings.
setlocal EnableExtensions DisableDelayedExpansion
title VERITAS - self-test (no internet needed)
cd /d "%~dp0.."
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "PYTHONUTF8=1"
echo.
echo  VERITAS self-test: runs every Evidence-locker exhibit through the engine.
echo  Takes about 1-4 minutes. It must end with  ALL PASS.
echo.
if not exist ".venv\Scripts\python.exe" goto need_setup
".venv\Scripts\python.exe" scripts\selftest.py
echo.
if "%VERITAS_CI%"=="1" exit /b %errorlevel%
pause
exit /b 0
:need_setup
echo  VERITAS is not set up yet. Double-click "1 - SETUP (run once)" in the downloaded VERITAS folder.
if "%VERITAS_CI%"=="1" exit /b 1
pause
exit /b 1
