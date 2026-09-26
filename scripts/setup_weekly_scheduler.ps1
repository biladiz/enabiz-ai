# PowerShell script to register weekly e-Nabız AI sync and clinical analysis task in Windows Task Scheduler

$TaskName = "ENabizAI_WeeklySync"
$ActionExecutable = "D:\AI\enabiz-ai\.venv\Scripts\python.exe"
$ActionArguments = "-m enabiz_ai.cli weekly"
$WorkingDirectory = "D:\AI\enabiz-ai"

Write-Host "Creating Windows Task Scheduler job: $TaskName ..." -ForegroundColor Cyan

# Define Action
$Action = New-ScheduledTaskAction -Execute $ActionExecutable -Argument $ActionArguments -WorkingDirectory $WorkingDirectory

# Define Trigger: Every Sunday at 20:00 (8:00 PM)
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 8:00PM

# Define Settings: Start when available if missed, wake to run
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Check if task already exists and unregister if so
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "Existing task found. Updating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Register Task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Runs weekly e-Nabız AI health data refresh and delivers AI clinical evaluation report to Telegram."

Write-Host "`n✅ Successfully registered $TaskName in Windows Task Scheduler!" -ForegroundColor Green
Write-Host "Schedule: Every Sunday at 20:00 (runs on PC wake if missed)" -ForegroundColor Cyan
Write-Host "Target: $ActionExecutable $ActionArguments" -ForegroundColor Gray
