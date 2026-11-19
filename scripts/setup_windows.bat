@echo off
REM ==========================================================================================
REM  VERITAS one-time setup for Windows 10 / 11 (x64; ARM64 runs x64 Python under emulation).
REM  Normally started by "1 - SETUP (run once).bat" in the downloaded VERITAS folder.
REM    1. copies the app to %USERPROFILE%\VERITAS (C:\VERITAS if the user name has non-English
REM       letters - OpenCV cannot open such paths) and unblocks the files
REM    2. installs uv, Python 3.12 and the locked libraries (CPU PyTorch) into .venv
REM    3. downloads the AI models (scripts\download_models.py, SHA-256 checked)
REM    4. downloads the booth demo clips (scripts\fetch_demo_clips.py; never fatal)
REM    5. checks the AI libraries load (installs the VC++ runtime if needed), makes the Desktop
REM       shortcuts "VERITAS" and "VERITAS demo clips", runs the self-test
REM  Running it again = repair / update: finished downloads are kept.
REM  VERITAS_CI=1          no pauses, prints the log at the end (GitHub Actions)
REM  VERITAS_HOME=folder   install somewhere else
REM  cmd.exe rules kept on purpose in this file: NO ( ) blocks anywhere (a folder such as
REM  "Downloads\VERITAS-Windows (1)" would break them), every path in quotes, single-line IF + GOTO,
REM  no delayed expansion (a "!" in a path would vanish), ASCII only, CRLF line endings.
REM ==========================================================================================
setlocal EnableExtensions DisableDelayedExpansion
title VERITAS setup - please wait
set "CI_MODE="
if "%VERITAS_CI%"=="1" set "CI_MODE=1"
set "VERITAS_TICK="

REM ---- where the files come from (SRC = the folder above scripts\) and where they go (DEST)
pushd "%~dp0.."
set "SRC=%CD%"
popd
set "DEST=%USERPROFILE%\VERITAS"
if defined VERITAS_HOME set "DEST=%VERITAS_HOME%"
if defined VERITAS_HOME goto dest_chosen
powershell -NoProfile -ExecutionPolicy Bypass -Command "if ($env:USERPROFILE -match '[^\x20-\x7E]') { exit 1 }" >nul 2>nul
if errorlevel 1 set "DEST=C:\VERITAS"
:dest_chosen
set "LOG=%DEST%\setup-log.txt"
set "PY=%DEST%\.venv\Scripts\python.exe"
set "UV_INSTALL_DIR=%USERPROFILE%\.local\bin"
set "UVEXE=%USERPROFILE%\.local\bin\uv.exe"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_HTTP_TIMEOUT=300"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UV_PYTHON=cpython-3.12-windows-x86_64-none"

echo.
echo  ==============================================================
echo    VERITAS - Deepfake Forensics Lab : ONE-TIME SETUP
echo.
echo    Needs the internet this one time: about 3.5 GB, 15-30 minutes.
echo    Keep the laptop plugged in and awake. Do not close this window.
echo  ==============================================================
echo.

REM ---- the install folder and the log file
if not exist "%DEST%\" mkdir "%DEST%" >nul 2>nul
if exist "%DEST%\" goto dest_ok
set "LOG=%TEMP%\veritas-setup-log.txt"
> "%LOG%" echo VERITAS setup log - could not create the install folder
set "FIX=Windows did not let setup create the VERITAS folder. Restart the laptop, then run 1 - SETUP again."
goto fail
:dest_ok
if exist "%LOG%" copy /y "%LOG%" "%DEST%\setup-log-previous.txt" >nul 2>nul
> "%LOG%" echo VERITAS setup log - %DATE% %TIME%
>> "%LOG%" echo SRC="%SRC%"
>> "%LOG%" echo DEST="%DEST%"
>> "%LOG%" echo USERPROFILE="%USERPROFILE%"
>> "%LOG%" echo CI_MODE="%CI_MODE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$o = Get-CimInstance Win32_OperatingSystem; $c = Get-CimInstance Win32_ComputerSystem; 'Windows: ' + $o.Caption + ' ' + $o.Version + ' ' + $o.OSArchitecture; 'RAM GB: ' + [math]::Round($c.TotalPhysicalMemory / 1GB, 1); 'CPU threads: ' + $env:NUMBER_OF_PROCESSORS + '   PROCESSOR_ARCHITECTURE: ' + $env:PROCESSOR_ARCHITECTURE" >> "%LOG%" 2>&1

REM ---- VERITAS must not be running while it is repaired (its files are in use)
curl.exe -s -f -m 3 -o nul "http://127.0.0.1:8000/api/health" >nul 2>nul
if errorlevel 1 goto not_running
set "FIX=VERITAS is running right now. Close the black VERITAS window, then run 1 - SETUP again."
goto fail
:not_running

REM ---- enough disk space? (8 GB for a fresh install, 2 GB for a repair)
set "NEED_GB=8"
if exist "%PY%" set "NEED_GB=2"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$q = Split-Path -Qualifier $env:DEST; $f = (New-Object System.IO.DriveInfo $q).AvailableFreeSpace / 1GB; 'Free space on ' + $q + ' ' + [math]::Round($f, 1) + ' GB, need ' + $env:NEED_GB; if ($f -lt [double]$env:NEED_GB) { exit 3 }" >> "%LOG%" 2>&1
if errorlevel 3 goto fail_disk

REM ---- internet? (only a warning: a repair works offline when everything is already downloaded)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; try { $null = Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Method Head 'https://huggingface.co'; 'internet: ok' } catch { 'internet: NOT reachable - ' + $_.Exception.Message; exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 echo  NOTE: the internet does not seem to work. Setup needs it the first time - connect to Wi-Fi.
if errorlevel 1 echo.

REM ---- keep the laptop awake while setup runs: a laptop that falls asleep stops the downloads. A background helper
REM      asks Windows not to sleep (no admin needed; the screen may still turn off). It ends with setup or this window.
set "VERITAS_AWAKE=%TEMP%\veritas-awake-%RANDOM%%RANDOM%.flag"
> "%VERITAS_AWAKE%" echo running
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = $env:VERITAS_AWAKE; try { $q = [char]34; Add-Type -Name Awake -Namespace Veritas -MemberDefinition ('[DllImport(' + $q + 'kernel32.dll' + $q + ')] public static extern uint SetThreadExecutionState(uint f);'); if ([Veritas.Awake]::SetThreadExecutionState([uint32]2147483649)) { Set-Content -LiteralPath ($f + '.on') -Value 'on' } } catch {}; while (Test-Path -LiteralPath $f) { Start-Sleep -Seconds 5 }" >nul 2>nul

REM =========================================================================== STEP 1
echo  Step 1 of 5: copying VERITAS to your user folder (1 minute) ...
>> "%LOG%" echo.
>> "%LOG%" echo ==== STEP 1 copy - %TIME%
if /i "%SRC%"=="%DEST%" goto copied
robocopy "%SRC%" "%DEST%" /E /R:2 /W:2 /NP /NFL /NDL /XD "%SRC%\.venv" "%SRC%\.git" "%SRC%\eval_data" "%SRC%\dist" "%SRC%\deploy" "%SRC%\winkit" "%SRC%\demo-clips" /XF setup-log.txt setup-log-previous.txt >> "%LOG%" 2>&1
if errorlevel 8 goto fail_copy
:copied
if not exist "%DEST%\scripts\start_windows.bat" goto fail_copy
REM Unblock the files (removes the "downloaded from the internet" mark, so Windows stops asking).
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($n in 'scripts','server','web','docs') { $p = Join-Path $env:DEST $n; if (Test-Path -LiteralPath $p) { Get-ChildItem -LiteralPath $p -Recurse -File | Unblock-File } }; Get-ChildItem -LiteralPath $env:DEST -File | Unblock-File; if ((Split-Path -Leaf $env:SRC) -eq 'app') { Get-ChildItem -LiteralPath (Split-Path -Parent $env:SRC) -File | Unblock-File }; 'files unblocked'" >> "%LOG%" 2>&1
cd /d "%DEST%"
echo            done.

REM =========================================================================== STEP 2
echo  Step 2 of 5: installing Python and the AI libraries (about 10 minutes) ...
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" echo            ARM processor: using x64 Python under emulation - slower, but it works.
>> "%LOG%" echo.
>> "%LOG%" echo ==== STEP 2 uv + Python + libraries - %TIME%
call :ticker_start
if exist "%UVEXE%" goto have_uv
>> "%LOG%" echo installing uv into "%UV_INSTALL_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; irm https://astral.sh/uv/install.ps1 | iex" >> "%LOG%" 2>&1
:have_uv
if not exist "%UVEXE%" goto fail_uv
REM an old uv cannot read this project's lock file: update it (harmless if it is already current)
"%UVEXE%" self update >> "%LOG%" 2>&1
"%UVEXE%" --version >> "%LOG%" 2>&1
"%UVEXE%" sync --locked --compile-bytecode >> "%LOG%" 2>&1
if errorlevel 1 goto fail_sync
"%PY%" -c "import sys; print('python', sys.version)" >> "%LOG%" 2>&1
if errorlevel 1 goto fail_sync
call :ticker_stop
echo            done.

REM =========================================================================== STEP 3
echo  Step 3 of 5: downloading the AI models - about 2 GB (about 10 minutes) ...
>> "%LOG%" echo.
>> "%LOG%" echo ==== STEP 3 models - %TIME%
call :ticker_start
"%PY%" scripts\download_models.py >> "%LOG%" 2>&1
if errorlevel 1 goto fail_models
call :ticker_stop
echo            done.

REM =========================================================================== STEP 4
echo  Step 4 of 5: downloading the booth demo clips (about 2 minutes) ...
>> "%LOG%" echo.
>> "%LOG%" echo ==== STEP 4 demo clips - %TIME%
call :ticker_start
"%PY%" scripts\fetch_demo_clips.py >> "%LOG%" 2>&1
call :ticker_stop
if not exist "%DEST%\demo-clips\" mkdir "%DEST%\demo-clips" >nul 2>nul
findstr /c:"research clips ready" "%LOG%"

REM =========================================================================== STEP 5
echo  Step 5 of 5: testing VERITAS and making the Desktop shortcuts (about 5 minutes) ...
>> "%LOG%" echo.
>> "%LOG%" echo ==== STEP 5 libraries, shortcuts, self-test - %TIME%
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
REM PyTorch and ONNX Runtime need the Microsoft Visual C++ runtime. ONNX Runtime loads its DLLs only when a
REM session is created, so open the small face detector once.
"%PY%" -c "import os, torch, transformers, mediapipe, cv2, av, soundfile, librosa, torchvision, onnxruntime as ort; p = os.path.join('models', 'face_swap', 'det_10g.onnx'); os.path.exists(p) and ort.InferenceSession(p, providers=['CPUExecutionProvider']); print('engine libraries OK')" >> "%LOG%" 2>&1
if not errorlevel 1 goto libs_ok
echo            Installing the Microsoft Visual C++ runtime that the AI libraries need.
echo            If Windows asks "Do you want to allow this app to make changes", click YES.
>> "%LOG%" echo libraries did not load - installing the VC++ 2015-2022 x64 runtime
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; $f = Join-Path $env:TEMP 'vc_redist.x64.exe'; Invoke-WebRequest -UseBasicParsing 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $f; $p = Start-Process -FilePath $f -ArgumentList '/install', '/passive', '/norestart' -Verb RunAs -Wait -PassThru; 'vc_redist exit code ' + $p.ExitCode" >> "%LOG%" 2>&1
"%PY%" -c "import os, torch, transformers, mediapipe, cv2, av, soundfile, librosa, torchvision, onnxruntime as ort; p = os.path.join('models', 'face_swap', 'det_10g.onnx'); os.path.exists(p) and ort.InferenceSession(p, providers=['CPUExecutionProvider']); print('engine libraries OK')" >> "%LOG%" 2>&1
if errorlevel 1 goto fail_libs
:libs_ok

REM Desktop shortcuts (the real Desktop folder, also when OneDrive moved it)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = [Environment]::GetFolderPath('Desktop'); $w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut((Join-Path $d 'VERITAS.lnk')); $s.TargetPath = (Join-Path $env:DEST 'scripts\start_windows.bat'); $s.WorkingDirectory = $env:DEST; $s.IconLocation = (Join-Path $env:DEST 'scripts\assets\veritas.ico') + ',0'; $s.Description = 'Start VERITAS - deepfake forensics lab'; $s.Save(); $s = $w.CreateShortcut((Join-Path $d 'VERITAS demo clips.lnk')); $s.TargetPath = (Join-Path $env:DEST 'demo-clips'); $s.Description = 'VERITAS booth demo videos, photos and voices'; $s.Save(); 'shortcuts in ' + $d; if (-not (Test-Path -LiteralPath (Join-Path $d 'VERITAS.lnk'))) { exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 echo            NOTE: the Desktop shortcuts could not be made. Use "2 - START VERITAS" in the download folder instead.

REM The self-test runs every Evidence-locker exhibit through the engine and pre-warms the one-time caches.
call :ticker_start
"%PY%" scripts\selftest.py >> "%LOG%" 2>&1
set "SELFTEST_RC=%errorlevel%"
call :ticker_stop
findstr /r /c:"^ALL PASS" /c:"^FAIL" /c:"^[0-9]* FAILED" "%LOG%"
if not "%SELFTEST_RC%"=="0" goto fail_selftest

REM =========================================================================== DONE
>> "%LOG%" echo.
if exist "%VERITAS_AWAKE%.on" >> "%LOG%" echo laptop kept awake during setup: yes
call :awake_stop
>> "%LOG%" echo SETUP COMPLETE - %DATE% %TIME%
echo.
echo  ==============================================================
echo.
echo     ALL DONE - double-click VERITAS on your Desktop.
echo.
echo     From now on no internet is needed.
echo     Videos, photos and voices to drag into the lab are in the
echo     "VERITAS demo clips" folder on the Desktop.
echo.
echo  ==============================================================
echo.
if "%CI_MODE%"=="1" type "%LOG%"
if "%CI_MODE%"=="1" exit /b 0
echo  Press any key to close this window.
pause >nul
exit /b 0

REM =========================================================================== FAILURES
REM Each one sets ONE plain-English fix. Keep these texts free of the characters  and  pipe  less/greater.
:fail_disk
set "FIX=Not enough free space. Free up at least %NEED_GB% GB on drive C - empty the Recycle Bin and delete big files in Downloads - then run 1 - SETUP again."
goto fail
:fail_copy
set "FIX=Copying the files failed. Close other programs and any open VERITAS window, then run 1 - SETUP again."
goto fail
:fail_uv
set "FIX=The Python installer could not be downloaded. Connect to the internet - a phone hotspot works if the school Wi-Fi blocks it - then run 1 - SETUP again."
goto fail
:fail_sync
set "FIX=Python or the AI libraries did not install. Check the internet - a phone hotspot works if the school Wi-Fi blocks downloads - then run 1 - SETUP again. Finished parts are kept."
goto fail
:fail_models
set "FIX=Some AI models did not download. Check the internet, then run 1 - SETUP again. Finished downloads are kept."
goto fail
:fail_libs
set "FIX=The AI libraries cannot start. Install the Microsoft Visual C++ Redistributable x64 from https://aka.ms/vs/17/release/vc_redist.x64.exe - it needs an administrator - then run 1 - SETUP again."
goto fail
:fail_selftest
set "FIX=The self-test found a problem. Restart the laptop and run 1 - SETUP again. If it still fails, send the file setup-log.txt from the VERITAS folder to the VERITAS team. The Desktop shortcut may still work."
goto fail

:fail
call :ticker_stop
call :awake_stop
>> "%LOG%" echo.
>> "%LOG%" echo SETUP FAILED - %DATE% %TIME% - %FIX%
echo.
echo  ==============================================================
echo    SETUP DID NOT FINISH.
echo.
echo    What to do: %FIX%
echo.
echo    Details for the team are in this file:
echo    "%LOG%"
echo  ==============================================================
echo.
if "%CI_MODE%"=="1" type "%LOG%"
if "%CI_MODE%"=="1" exit /b 1
echo  Press any key to close this window.
pause >nul
exit /b 1

REM =========================================================================== HELPERS
REM A small background PowerShell that prints "... still working, N min" every minute until the flag file
REM is deleted, so a quiet 10-minute download does not look frozen. Not used in CI.
:ticker_start
if "%CI_MODE%"=="1" exit /b 0
call :ticker_stop
set "VERITAS_TICK=%TEMP%\veritas-setup-%RANDOM%%RANDOM%.tick"
> "%VERITAS_TICK%" echo running
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = $env:VERITAS_TICK; $m = 0; while ($true) { for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Seconds 1; if (-not (Test-Path -LiteralPath $f)) { exit } }; $m++; Write-Host ('           ... still working, ' + $m + ' min so far - please wait') }"
exit /b 0

:ticker_stop
if defined VERITAS_TICK del /q "%VERITAS_TICK%" >nul 2>nul
set "VERITAS_TICK="
exit /b 0

:awake_stop
if not defined VERITAS_AWAKE exit /b 0
del /q "%VERITAS_AWAKE%" "%VERITAS_AWAKE%.on" >nul 2>nul
set "VERITAS_AWAKE="
exit /b 0
