$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$logDir = Join-Path $scriptDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "startup_sync.log"
$attemptsFile = Join-Path $logDir "startup_sync_attempts.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToString("s"), $msg
  Add-Content -Path $logFile -Value $line
  Write-Output $line
}

function Write-AttemptRecord([int]$code) {
  $ts = (Get-Date).ToString("o")
  Add-Content -Path $attemptsFile -Value ("{0},{1}" -f $ts, $code)
}

function Exit-Sync([int]$code, [string]$msg = "") {
  if ($msg) { Write-Log $msg }
  Write-Log ("Exit code {0}" -f $code)
  Write-AttemptRecord $code
  exit $code
}

function Invoke-PythonStep([string]$label, [string]$scriptPath) {
  Write-Log ("--- {0} ---" -f $label)
  $prevPref = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $out = & $pythonExe $scriptPath 2>&1
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $prevPref
  }
  $out | ForEach-Object {
    Write-Log ("[{0}] {1}" -f $label, "$_")
  }
  if ($code -ne 0) {
    Exit-Sync $code ("{0} failed with exit code {1}" -f $label, $code)
  }
}

try {
  Write-Log "======== Run start ========"
  Write-Log ("Computer={0} User={1} whoami={2}" -f $env:COMPUTERNAME, $env:USERNAME, ((whoami).Trim()))
  Write-Log ("Repo root: {0}" -f $repoRoot.Path)

  Set-Location $repoRoot
  Write-Log ("PWD: {0}" -f (Get-Location).Path)

  $pythonExe = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
  if (-not $pythonExe) { $pythonExe = "python" }
  Write-Log ("Python executable: {0}" -f $pythonExe)
  $pv = & $pythonExe --version 2>&1
  Write-Log ("Python version: {0}" -f "$pv")

  Invoke-PythonStep "refresh" (Join-Path $scriptDir "refresh_local_cache.py")
  Write-Log "Local cache refresh completed"

  Invoke-PythonStep "export" (Join-Path $scriptDir "export_watchlist.py")
  Write-Log "Export completed"

  if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
    Write-Log "Not a git repo; skipping commit/push"
    Exit-Sync 0
  }

  $prevPref = $ErrorActionPreference
  $ErrorActionPreference = "Continue"

  Write-Log "--- git add ---"
  $ga = git add "docs/data/watchlist.json" 2>&1
  $ga | ForEach-Object { Write-Log ("[git] {0}" -f "$_") }
  $pending = git status --porcelain "docs/data/watchlist.json"
  if (-not $pending) {
    $ErrorActionPreference = $prevPref
    Write-Log "No data changes to commit"
    Exit-Sync 0
  }

  $msg = "auto-update watchlist data"
  Write-Log "--- git commit ---"
  $gc = git commit -m $msg 2>&1
  $gc | ForEach-Object { Write-Log ("[git] {0}" -f "$_") }
  $commitCode = $LASTEXITCODE
  if ($commitCode -ne 0) {
    $ErrorActionPreference = $prevPref
    Exit-Sync $commitCode "Commit failed"
  }

  Write-Log "--- git push ---"
  $gp = git push 2>&1
  $gp | ForEach-Object { Write-Log ("[git] {0}" -f "$_") }
  $pushCode = $LASTEXITCODE

  $ErrorActionPreference = $prevPref

  if ($pushCode -ne 0) {
    Exit-Sync $pushCode "Push failed"
  }

  Write-Log "Push completed"
  Exit-Sync 0
}
catch {
  Write-Log ("Unhandled error: {0}" -f $_.Exception.Message)
  if ($_.ScriptStackTrace) {
    Write-Log ("Stack: {0}" -f $_.ScriptStackTrace)
  }
  Exit-Sync 1
}
