# e-Nabiz AI - Trial Access Test Launcher
# Runs locally on Windows in the isolated virtual environment

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "   e-Nabiz AI -- Local Trial Login and 2FA Test       " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$ScriptPy = Join-Path $PSScriptRoot "scripts\test_edevlet_login.py"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment python not found at: $PythonExe" -ForegroundColor Red
    exit 1
}

Write-Host "Starting trial test with visible Chromium browser..." -ForegroundColor Green
& $PythonExe $ScriptPy
