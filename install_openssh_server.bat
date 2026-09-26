@echo off
:: Ensure admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Administrator privileges required. Requesting elevation...
    powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo ================================================================
echo   Installing and Starting OpenSSH Server for Tailscale SSH...
echo ================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Write-Host '[1/4] Installing OpenSSH Server capability...' -ForegroundColor Cyan; " ^
  "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; " ^
  "Write-Host '[2/4] Starting sshd service...' -ForegroundColor Cyan; " ^
  "Start-Service sshd; " ^
  "Write-Host '[3/4] Setting sshd to start automatically...' -ForegroundColor Cyan; " ^
  "Set-Service -Name sshd -StartupType 'Automatic'; " ^
  "Write-Host '[4/4] Ensuring Firewall rule allows Port 22...' -ForegroundColor Cyan; " ^
  "New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue; " ^
  "Write-Host 'OpenSSH Server successfully configured!' -ForegroundColor Green;"

echo.
echo ================================================================
echo Service Status:
echo ================================================================
powershell -NoProfile -Command "Get-Service sshd | Format-Table -AutoSize"

echo.
echo Port 22 status:
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue | Format-Table LocalAddress, LocalPort, State -AutoSize"

echo.
echo Done! You can now connect from your phone over Tailscale.
pause
