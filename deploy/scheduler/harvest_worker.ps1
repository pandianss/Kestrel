<#
.SYNOPSIS
    Start the background fundamentals worker (detached, windowless) if it isn't
    already running.

.DESCRIPTION
    The worker keeps the fundamentals store current while the system runs —
    polite, rate-limited, resumable (deploy/scheduler + scripts/harvest_worker.py).
    This launcher is idempotent: if a live worker is already running (PID file),
    it does nothing. It needs no Kite token — NSE results are public.

    Auto-start at logon so it runs "whenever the project is running":
        $ps = (Get-Command powershell).Source
        $f  = (Resolve-Path deploy\scheduler\harvest_worker.ps1).Path
        schtasks /Create /TN "Kestrel Fundamentals Worker" `
                 /TR "$ps -NoProfile -ExecutionPolicy Bypass -File `"$f`"" `
                 /SC ONLOGON /F

    morning.ps1 also calls this, so the daily routine ensures it is up.
    Stop it any time: Stop-Process -Id (Get-Content logs\fundamentals_worker.pid)
#>
[CmdletBinding()]
param([switch]$Once)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $repo
$env:PYTHONPATH = $repo

# already running? (pid file + alive check)
$pidfile = Join-Path $repo 'logs\fundamentals_worker.pid'
if (Test-Path $pidfile) {
    $opid = (Get-Content $pidfile -Raw).Trim()
    if ($opid -and (Get-Process -Id $opid -ErrorAction SilentlyContinue)) {
        Write-Host "Fundamentals worker already running (pid $opid)."
        return
    }
}

# pythonw = no console window; fall back to python, then PATH
$py = Join-Path $repo '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) { $py = Join-Path $repo '.venv\Scripts\python.exe' }
if (-not (Test-Path $py)) { $py = 'python' }

$pyArgs = @('scripts/harvest_worker.py')
if ($Once) { $pyArgs += '--once' }
Start-Process -FilePath $py -ArgumentList $pyArgs -WorkingDirectory $repo -WindowStyle Hidden
Write-Host "Started background fundamentals worker."
