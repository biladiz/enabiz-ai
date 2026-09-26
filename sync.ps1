# e-Nabiz AI - Full Data Sync and AI Analysis Runner
# Collects all medical records from e-Nabiz, updates SQLite, runs AI analysis, and sends Telegram report.

param (
    [string]$Profile = "default"
)

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "   e-Nabiz AI -- Veri Senkronizasyonu ve AI Analiz    " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[HATA] Sanal ortam Python bulunamadi: $PythonExe" -ForegroundColor Red
    exit 1
}

Write-Host "`nProfil: $Profile icin e-Nabiz verileri toplaniyor..." -ForegroundColor Green
Write-Host "- Tahlillerim (Tum biyokimya ve test sonuclari)" -ForegroundColor Gray
Write-Host "- Hastaliklarim (ICD-10 tanilari)" -ForegroundColor Gray
Write-Host "- Recetelerim (Ilac ve recete gecmisi)" -ForegroundColor Gray
Write-Host "- Ziyaretlerim (Doktor ve hastane ziyaretleri)`n" -ForegroundColor Gray

& "$PythonExe" -m enabiz_ai.cli weekly --profile "$Profile"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[OK] Senkronizasyon ve AI analizi basariyla tamamlandi!" -ForegroundColor Green
    Write-Host "Raporunuz Telegram botunuza (@onur_enabiz_bot) iletildi." -ForegroundColor Cyan
} else {
    Write-Host "`n[HATA] Islem sirasinda bir hata olustu (Exit Code: $LASTEXITCODE)." -ForegroundColor Red
}
