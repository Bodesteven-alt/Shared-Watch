$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$logDir = Join-Path $scriptDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "startup_sync.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToString("s"), $msg
  Add-Content -Path $logFile -Value $line
  Write-Output $line
}

Set-Location $repoRoot
Write-Log "Starting startup_sync"

$pythonExe = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
if (-not $pythonExe) { $pythonExe = "python" }

& $pythonExe (Join-Path $scriptDir "refresh_local_cache.py")
if ($LASTEXITCODE -ne 0) {
  Write-Log "Local cache refresh failed with exit code $LASTEXITCODE"
  exit $LASTEXITCODE
}
Write-Log "Local cache refresh completed"

& $pythonExe (Join-Path $scriptDir "export_watchlist.py")
if ($LASTEXITCODE -ne 0) {
  Write-Log "Export failed with exit code $LASTEXITCODE"
  exit $LASTEXITCODE
}
Write-Log "Export completed"

if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
  Write-Log "Not a git repo; skipping commit/push"
  exit 0
}

git add "docs/data/watchlist.json"
$pending = git status --porcelain "docs/data/watchlist.json"
if (-not $pending) {
  Write-Log "No data changes to commit"
  exit 0
}

$msg = "auto-update watchlist data"
git commit -m $msg
if ($LASTEXITCODE -ne 0) {
  Write-Log "Commit failed"
  exit $LASTEXITCODE
}

git push
if ($LASTEXITCODE -ne 0) {
  Write-Log "Push failed"
  exit $LASTEXITCODE
}

Write-Log "Push completed"
exit 0
