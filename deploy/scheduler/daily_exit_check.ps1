<#
.SYNOPSIS
    Kestrel daily EXIT check — the automated exit leg of the paper book.

.DESCRIPTION
    Entries come from the ranking; rotation is quarterly (quarterly_refresh.ps1).
    Between rebalances, capital still needs protecting — so this runs the trailing
    stop DAILY: it marks each open position to the latest Kite close, ratchets its
    high-water peak, and sells any name that has fallen 15% below its peak, booking
    the exit to cash. Fully unattended (no Kite token; uses the offline price cache).

    Best scheduled for after market close, once harvest_history has written the
    day's candles. Run with -Register to install a daily Task Scheduler job (18:30).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\scheduler\daily_exit_check.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\scheduler\daily_exit_check.ps1 -Register
#>
[CmdletBinding()]
param([switch]$Register)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $repo
$env:PYTHONPATH = $repo

$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

if ($Register) {
    $self = $MyInvocation.MyCommand.Path
    $cmd = "powershell -ExecutionPolicy Bypass -NonInteractive -File `"$self`""
    schtasks /Create /TN "Kestrel Daily Exit Check" /TR $cmd /SC DAILY /ST 18:30 /F
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Registered 'Kestrel Daily Exit Check' (daily 18:30)." -ForegroundColor Green
    }
    exit $LASTEXITCODE
}

Write-Host "Checking trailing-stop exits ..." -ForegroundColor Cyan
& $py scripts/mock_trade.py --check-exits
