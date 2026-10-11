# CareSchedule – App Launch Script
# Usage:  .\run_app.ps1
$ErrorActionPreference = 'Continue'
$Port   = 5010
$AppDir = $PSScriptRoot

Set-Location $AppDir

# ── Create virtual environment if missing ─────────────────────────────────
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment. Make sure Python 3.9+ is installed."
        exit 1
    }
}

# ── Install / update dependencies ─────────────────────────────────────────
Write-Host "Installing dependencies..." -ForegroundColor Cyan
& ".\.venv\Scripts\pip.exe" install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}

# ── Seed database on first run ────────────────────────────────────────────
if (-not (Test-Path "caregiver_schedule.db")) {
    Write-Host "First run – initializing database with default users..." -ForegroundColor Yellow
    & ".\.venv\Scripts\python.exe" init_db.py
}

# ── Kill any stale process already listening on the port ─────────────────
$listeners = netstat -ano 2>$null | Select-String ":$Port\s.*LISTENING"
if ($listeners) {
    $pids = $listeners | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
    foreach ($p in $pids) {
        Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

# ── Launch ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  CareSchedule is running on port $Port" -ForegroundColor Green
Write-Host "  Open:  http://localhost:$Port"          -ForegroundColor Green
Write-Host "  Stop:  Ctrl+C"                          -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

& ".\.venv\Scripts\python.exe" run.py
