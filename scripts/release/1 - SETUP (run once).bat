@echo off
REM VERITAS - ONE-CLICK SETUP. Double-click this file once, with internet (about 3.5 GB, 15-30 minutes).
REM It copies VERITAS to your user folder and puts a "VERITAS" shortcut on the Desktop.
REM All the work is done by app\scripts\setup_windows.bat. Running it again = repair / update.
REM cmd.exe rules: this file's own name contains ( ), so NO ( ) blocks here; paths in quotes; CRLF.
setlocal EnableExtensions DisableDelayedExpansion
title VERITAS setup
echo "%~dp0" | find /i ".zip" >nul
if not errorlevel 1 goto not_extracted
if not exist "%~dp0app\scripts\setup_windows.bat" goto not_extracted
call "%~dp0app\scripts\setup_windows.bat"
exit /b %errorlevel%

:not_extracted
echo.
echo  ==============================================================
echo    Please UNZIP VERITAS first.
echo.
echo    1. Close this window.
echo    2. Right-click VERITAS-Windows.zip and choose "Extract All...",
echo       then click "Extract".
echo    3. In the new folder, open VERITAS and double-click
echo       "1 - SETUP (run once)" again.
echo  ==============================================================
echo.
if "%VERITAS_CI%"=="1" exit /b 1
pause
exit /b 1
