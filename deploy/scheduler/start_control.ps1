<#
.SYNOPSIS
    Start Kestrel Mission Control (the on-host server) if it isn't already up.
    The server, on startup, also brings up the background fundamentals worker —
    so this one command starts the whole background stack.

.DESCRIPTION
    Idempotent: if the server already answers on the port, it does nothing.
    Windowless (pythonw) so nothing pops a console. Localhost-only (the server
    binds 127.0.0.1).

    Auto-start at logon so the stack comes up whenever you log in:
        $ps = (Get-Command powershell).Source
        $f  = (Resolve-Path deploy\scheduler\start_control.ps1).Path
        schtasks /Create /TN "Kestrel Mission Control" `
                 /TR "$ps -NoProfile -ExecutionPolicy Bypass -File `"$f`"" `
                 /SC ONLOGON /F

    morning.ps1 also calls this, so the daily routine ensures it is up.
    Open it at http://localhost:8000
#>
[CmdletBinding()]
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $repo
$env:PYTHONPATH = $repo

# already up?
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port/api/status" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -eq 200) {
        Write-Host "Mission Control already running on http://localhost:$Port"
        return
    }
} catch { }

$py = Join-Path $repo '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $py)) { $py = Join-Path $repo '.venv\Scripts\python.exe' }
if (-not (Test-Path $py)) { $py = 'python' }

Start-Process -FilePath $py -ArgumentList @('scripts/server.py', '--port', "$Port") `
              -WorkingDirectory $repo -WindowStyle Hidden
Write-Host "Started Mission Control on http://localhost:$Port (worker auto-starts)."
