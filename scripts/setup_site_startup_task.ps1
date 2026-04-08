param(
  [Parameter()]
  [ValidateRange(0, 1439)]
  [int]$LogonDelayMinutes = 0
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteScript = Join-Path (Resolve-Path (Join-Path $scriptDir "..")) "start_site.ps1"

if (-not (Test-Path $siteScript)) {
  Write-Error "Missing site script: $siteScript"
  exit 1
}

$taskName = "WatchlistLocalSite"
$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$action = New-ScheduledTaskAction `
  -Execute $psExe `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$siteScript`"" `
  -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
if ($LogonDelayMinutes -gt 0) {
  $trigger.Delay = "PT${LogonDelayMinutes}M"
}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch { }

try {
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Start local Flask watchlist site on logon" -ErrorAction Stop | Out-Null
  Write-Output "Created scheduled task: $taskName"
  Write-Output "schtasks /Query /TN WatchlistLocalSite"
} catch {
  Write-Error "Failed to create scheduled task (run PowerShell as Administrator once): $($_.Exception.Message)"
  exit 1
}
