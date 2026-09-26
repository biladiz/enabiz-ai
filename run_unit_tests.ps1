# e-Nabız AI - Automated Test Suite Runner
param(
    [string]$Target = "tests",
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "   e-Nabız AI -- Automated Test Suite (pytest)       " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment python not found at: $PythonExe" -ForegroundColor Red
    exit 1
}

$PytestArgs = @("-m", "pytest", $Target)
if ($Verbose) {
    $PytestArgs += "-vv"
} else {
    $PytestArgs += "-v"
}

& $PythonExe $PytestArgs
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAll tests passed successfully!" -ForegroundColor Green
} else {
    Write-Host "`nSome tests failed. See output above." -ForegroundColor Red
}
exit $LASTEXITCODE
