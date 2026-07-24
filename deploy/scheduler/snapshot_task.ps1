<#
.SYNOPSIS
    Non-interactive snapshot runner (Windows) — a Task Scheduler backstop.

.DESCRIPTION
    Runs the reference snapshot in --require-live mode. Needs NO secrets: it
    reads the token already minted by the morning login (morning.ps1). If no
    valid token exists it exits 3 and writes nothing — the signal that the
    morning login has not happened yet. Safe to schedule: it can never archive
    dev data as a real snapshot, and re-running after a successful capture is an
    idempotent no-op.

    Register it as a daily task (adjust the time to after your usual login):

        $ps  = (Get-Command powershell).Source
        $arg = '-NoProfile -ExecutionPolicy Bypass -File "' + `
               (Resolve-Path deploy\scheduler\snapshot_task.ps1).Path + '"'
        schtasks /Create /TN "Kestrel Snapshot" /TR "$ps $arg" `
                 /SC DAILY /ST 09:35 /F

    (Task Scheduler fires in the host's local time; on an India PC that is IST.)
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $repo
$env:PYTHONPATH = $repo

$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

& $py scripts/snapshot_reference.py --require-live
exit $LASTEXITCODE
