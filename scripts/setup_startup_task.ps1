$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $scriptDir "startup_sync.ps1"

if (-not (Test-Path $syncScript)) {
  Write-Error "Missing sync script: $syncScript"
  exit 1
}

$taskName = "WatchlistGitHubPagesSync"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$syncScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch { }

try {
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Sync watchlist JSON to GitHub Pages on logon" -ErrorAction Stop | Out-Null
  Write-Output "Created scheduled task: $taskName"
} catch {
  Write-Error "Failed to create scheduled task (run PowerShell as Administrator once): $($_.Exception.Message)"
  exit 1
}
