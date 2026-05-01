param(
  [Parameter()]
  [ValidateRange(0, 1439)]
  [int]$LogonDelayMinutes = 0
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $scriptDir "startup_sync.ps1"

if (-not (Test-Path $syncScript)) {
  Write-Error "Missing sync script: $syncScript"
  exit 1
}

$taskName = "WatchlistGitHubPagesSync"
$conhostExe = Join-Path $env:SystemRoot "System32\conhost.exe"
$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

function Remove-StaleWatchlistTasks {
  param(
    [string]$CurrentRepoRoot
  )

  $normalizedRoot = $CurrentRepoRoot.ToLowerInvariant()
  $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue
  foreach ($task in $tasks) {
    foreach ($actionItem in $task.Actions) {
      if (-not $actionItem.Execute) { continue }
      $execLower = $actionItem.Execute.ToLowerInvariant()
      $isPowerShellHost = $execLower -like "*powershell.exe" -or $execLower -like "*pwsh.exe"
      $isConhostLauncher = $execLower -like "*conhost.exe"
      if (-not $isPowerShellHost -and -not $isConhostLauncher) { continue }
      if (-not $actionItem.Arguments) { continue }

      $argsLower = $actionItem.Arguments.ToLowerInvariant()
      $matchesWatchlistScript = $argsLower.Contains("startup_sync.ps1") -or $argsLower.Contains("start_site.ps1")
      if (-not $matchesWatchlistScript) { continue }
      if ($argsLower.Contains($normalizedRoot)) { continue }

      try {
        Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false -ErrorAction Stop | Out-Null
        Write-Output ("Removed stale startup task: {0}{1}" -f $task.TaskPath, $task.TaskName)
      } catch {
        Write-Warning ("Failed to remove stale task {0}{1}: {2}" -f $task.TaskPath, $task.TaskName, $_.Exception.Message)
      }
      break
    }
  }
}

Remove-StaleWatchlistTasks -CurrentRepoRoot $repoRoot

# conhost --headless avoids a visible PowerShell console flash (powershell.exe allocates a console before -WindowStyle Hidden applies).
$taskArgument = '--headless "{0}" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}"' -f $psExe, $syncScript
$action = New-ScheduledTaskAction `
  -Execute $conhostExe `
  -Argument $taskArgument `
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
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Sync watchlist JSON to GitHub Pages on logon" -ErrorAction Stop | Out-Null
  Write-Output "Created scheduled task: $taskName"
  Write-Output "schtasks /Query /TN WatchlistGitHubPagesSync"
} catch {
  Write-Error "Failed to create scheduled task (run PowerShell as Administrator once): $($_.Exception.Message)"
  exit 1
}
