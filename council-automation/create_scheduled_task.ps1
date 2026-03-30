$taskName = 'PerplexitySessionRefresh'
$pythonPath = (Get-Command python).Source
$scriptPath = 'C:\Users\AustinKidwell\.claude\council-automation\refresh_session.py'

# Check if task exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task already exists, removing..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create action
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $scriptPath

# Create trigger: every 12 hours starting at 6:00 AM
$trigger = New-ScheduledTaskTrigger -Once -At '06:00AM' -RepetitionInterval (New-TimeSpan -Hours 12) -RepetitionDuration (New-TimeSpan -Days 3650)

# Create settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

# Register task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Refresh Perplexity session cookies for Claude council commands' -RunLevel Limited

Write-Host "Task created successfully!"
Get-ScheduledTask -TaskName $taskName | Format-List TaskName, State, Description
