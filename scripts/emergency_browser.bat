@echo off
setlocal EnableExtensions
title VERITAS - emergency mode (no Python engine)
REM TIER 1 FALLBACK - use only if the Python engine cannot run at all.
REM Opens the story straight from the folder in a separate Edge (or Chrome) profile that may read local files.
REM Works: the story, Live Cam and Spot the Fake. Analyze needs the engine: use  lab.html?mock=1&samples=1
REM and tell visitors it is DEMO DATA.
cd /d "%~dp0..\web"
set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" (
  echo  Neither Edge nor Chrome was found.
  pause
  exit /b 1
)
echo.
echo  EMERGENCY MODE - no forensic engine.
echo  Story, Live Cam and Spot the Fake work normally.
echo  Analyze shows DEMO DATA only - say so to visitors.
echo.
start "" "%BROWSER%" --user-data-dir="%TEMP%\veritas-emergency" --allow-file-access-from-files --no-first-run "%CD%\index.html"
