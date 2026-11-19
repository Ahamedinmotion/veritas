# Start VERITAS exactly like the Desktop shortcut "VERITAS" does, wait for /api/health, check that a second start
# ("2 - START VERITAS.bat" from the download folder) notices the running engine and just exits, analyse the
# Evidence-locker samples through the real HTTP API (check_api.py), then stop the engine again.
# Used by .github/workflows/windows-setup.yml (twice in the default job: auto -> fp32, then auto forced to int8).
#   pwsh .github/scripts/engine_check.ps1 -Label auto-fp32 -ExpectFaceSwap fp32
param(
  [string]$Label = 'engine',
  [string]$ExpectFaceSwap = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desk = [Environment]::GetFolderPath('Desktop')
$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'VERITAS.lnk'))
$logs = Join-Path $env:RUNNER_TEMP 'veritas-logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$out = Join-Path $logs "server-log-$Label.txt"
$err = Join-Path $logs "server-err-$Label.txt"
$health = 'http://127.0.0.1:8000/api/health'

function Stop-Engine {
  Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*server.app*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  for ($i = 0; $i -lt 30; $i++) {   # wait until the port is free, so a following start is a real cold start
    $busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if (-not $busy) { break }
    Start-Sleep -Seconds 1
  }
}

"[$Label] shortcut: $($s.TargetPath)  (working folder $($s.WorkingDirectory))"
# cmd /s /c ""<target>"" keeps the quotes around a path with spaces and brackets
$p = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c ""' + $s.TargetPath + '""') `
       -WorkingDirectory $s.WorkingDirectory -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -NoNewWindow
try {
  $t0 = Get-Date; $up = $false
  while (((Get-Date) - $t0).TotalMinutes -lt 20) {
    if ($p.HasExited) { break }
    try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 $health; if ($r.StatusCode -eq 200) { $up = $true; break } } catch {}
    Start-Sleep -Seconds 2
  }
  $secs = [int]((Get-Date) - $t0).TotalSeconds
  "[$Label] TIMING engine-start: engine answered /api/health: $up after $secs s"
  Get-Content -LiteralPath $out -ErrorAction SilentlyContinue | Select-Object -First 25
  if (-not $up) { Get-Content $out, $err -ErrorAction SilentlyContinue | Select-Object -Last 80; throw "engine did not answer /api/health" }
  # a second start (the zip's "2 - START VERITAS.bat") must notice the running engine and just exit
  $q = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /s /c ""' + $env:START_BAT + '""') -Wait -PassThru -NoNewWindow
  if ($q.ExitCode -ne 0) { throw "2 - START VERITAS.bat did not detect the running engine (exit $($q.ExitCode))" }
  $a = @((Join-Path $here 'check_api.py'), 'http://127.0.0.1:8000', (Join-Path $env:VH 'web\samples\lab'))
  if ($ExpectFaceSwap) { $a += @('--faceswap', $ExpectFaceSwap) }
  python @a
  if ($LASTEXITCODE -ne 0) { Get-Content $err -ErrorAction SilentlyContinue | Select-Object -Last 60; throw "API check failed" }
} finally {
  taskkill /PID $p.Id /T /F 2>$null | Out-Null
  Stop-Engine
  $global:LASTEXITCODE = 0   # taskkill's exit code must not decide the step; the checks above throw on failure
}
