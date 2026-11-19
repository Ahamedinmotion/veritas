@echo off
REM VERITAS - start the lab (the same as the "VERITAS" shortcut on the Desktop).
REM Runs the installed copy in %USERPROFILE%\VERITAS (or C:\VERITAS, or VERITAS_HOME) - not the files next to this one.
REM cmd.exe rules: no ( ) blocks; paths in quotes; CRLF.
setlocal EnableExtensions DisableDelayedExpansion
set "VSTART=%USERPROFILE%\VERITAS\scripts\start_windows.bat"
if defined VERITAS_HOME set "VSTART=%VERITAS_HOME%\scripts\start_windows.bat"
if not exist "%VSTART%" set "VSTART=C:\VERITAS\scripts\start_windows.bat"
if not exist "%VSTART%" goto not_installed
call "%VSTART%"
exit /b %errorlevel%

:not_installed
echo.
echo  VERITAS is not set up on this laptop yet.
echo  Double-click "1 - SETUP (run once)" first - it needs the internet once.
echo.
if "%VERITAS_CI%"=="1" exit /b 1
pause
exit /b 1
