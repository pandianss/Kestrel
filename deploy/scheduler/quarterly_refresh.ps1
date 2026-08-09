<#
.SYNOPSIS
    Kestrel quarterly refresh (D-18) — regenerate the ranking and rebalance the
    paper book to the current top-N. This is the cadence the backtest validated
    (fundamentals only change quarterly, so monthly churn just pays cost).

.DESCRIPTION
    Fully UNATTENDED — unlike morning.ps1 it needs no Kite token or 2FA: the
    ranking scores from the fundamentals store, and prices come from the Kite
    daily cache (ranking) and Yahoo (paper book). Two steps:
      1. rank_baskets.py  -> data/baskets_ranking.json (5-pillar, sector-relative
         valuation — the IR-0.49 config).
      2. mock_trade.py --rebalance -> carry the paper book's equity forward and
         re-select the current top-N (or open a fresh book on first run).

    Run with -Register once to install a quarterly Task Scheduler job (the 5th of
    Jan/Apr/Jul/Oct, after each results season has begun).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\scheduler\quarterly_refresh.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\scheduler\quarterly_refresh.ps1 -Register
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
    # Quarterly = the 5th of Jan/Apr/Jul/Oct at 18:00 (after results season opens).
    schtasks /Create /TN "Kestrel Quarterly Refresh" /TR $cmd `
        /SC MONTHLY /M JAN,APR,JUL,OCT /D 5 /ST 18:00 /F
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Registered 'Kestrel Quarterly Refresh' (5th of Jan/Apr/Jul/Oct, 18:00)." -ForegroundColor Green
    }
    exit $LASTEXITCODE
}

Write-Host "[1/3] Regenerating ranking (5-pillar, sector-relative valuation) ..." -ForegroundColor Cyan
& $py scripts/rank_baskets.py
if ($LASTEXITCODE -ne 0) { Write-Host "rank_baskets failed ($LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "`n[2/3] Rebuilding dashboard.html (gated leaderboard) ..." -ForegroundColor Cyan
& $py scripts/dashboard.py

Write-Host "`n[3/3] Rebalancing the paper book ..." -ForegroundColor Cyan
if (Test-Path 'data/paper_portfolio.json') {
    & $py scripts/mock_trade.py --rebalance
} else {
    & $py scripts/mock_trade.py            # first run: open the book
}

Write-Host "`nQuarterly refresh complete." -ForegroundColor Green
