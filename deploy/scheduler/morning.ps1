<#
.SYNOPSIS
    Kestrel morning routine (Windows host, D-18) — mint today's token and
    capture the reference snapshot, in one command.

.DESCRIPTION
    The daily login needs your Zerodha 2FA in a browser (G-12), so it cannot be
    fully unattended. This script makes the unavoidable manual step a single
    command: it sets the API credentials (prompting securely if not already in
    the environment), runs the operator-in-the-loop login, and — only if a valid
    token results — captures the live instruments snapshot in --require-live mode.

    The API secret is read as a SecureString and lives only in this process's
    environment. It is never written to disk, never echoed, never committed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\scheduler\morning.ps1
#>
[CmdletBinding()]
param(
    [string]$ApiKey = $env:KITE_API_KEY
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here '..\..')).Path
Set-Location $repo
$env:PYTHONPATH = $repo

# Pick an interpreter: prefer the repo venv, else whatever 'python' resolves to.
$py = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }

# --- credentials (session-scoped, never persisted) ---
if (-not $ApiKey) { $ApiKey = Read-Host 'KITE_API_KEY' }
$env:KITE_API_KEY = $ApiKey

if (-not $env:KITE_API_SECRET) {
    $secure = Read-Host 'KITE_API_SECRET' -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:KITE_API_SECRET = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

Write-Host "`n[1/2] Minting today's Kite token (browser login) ..." -ForegroundColor Cyan
& $py scripts/kite_login.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Login did not complete (exit $LASTEXITCODE). Snapshot skipped." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "`n[2/2] Capturing the live reference snapshot ..." -ForegroundColor Cyan
& $py scripts/snapshot_reference.py --require-live
$rc = $LASTEXITCODE

# The secret has done its job; clear it from this process now.
Remove-Item Env:\KITE_API_SECRET -ErrorAction SilentlyContinue

if ($rc -eq 0) {
    Write-Host "`nDone. Today's universe is captured." -ForegroundColor Green
} else {
    Write-Host "`nSnapshot exit $rc — see the message above." -ForegroundColor Yellow
}
exit $rc
