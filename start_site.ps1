# Starts the local Flask watchlist site for your PC.
# Designed to be called by Windows Task Scheduler at startup / log on.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$listenHost = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$listenPort = if ($env:PORT) { $env:PORT } else { "5000" }

$env:HOST = $listenHost
$env:PORT = $listenPort

$logDir = Join-Path $scriptDir "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "startup.log"
$appLogFile = Join-Path $logDir "app_runtime.log"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToString("s"), $msg
  Add-Content -Path $logFile -Value $line
  Write-Output $line
}

$pythonExe = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
if (-not $pythonExe) { $pythonExe = "python" }

$exitCode = 0
try {
  Write-Log "======== Run start ========"
  Write-Log ("Computer={0} User={1} whoami={2}" -f $env:COMPUTERNAME, $env:USERNAME, ((whoami).Trim()))
  Write-Log ("Repo path: {0}" -f (Resolve-Path $scriptDir).Path)

  Write-Log ("Python executable: {0}" -f $pythonExe)
  $pv = & $pythonExe --version 2>&1
  Write-Log ("Python version: {0}" -f "$pv")

  Write-Log ("Starting watchlist site (listenHost={0}, listenPort={1})" -f $listenHost, $listenPort)

  $ErrorActionPreference = "Continue"
  # Keep Flask/stdout on a separate file to avoid file-share locks with Write-Log.
  & $pythonExe "app.py" 1>> $appLogFile 2>> $appLogFile
  $exitCode = $LASTEXITCODE
  $ErrorActionPreference = "Stop"
  if ($null -eq $exitCode) { $exitCode = 0 }
}
catch {
  Write-Log ("Unhandled error: {0}" -f $_.Exception.Message)
  if ($_.ScriptStackTrace) {
    Write-Log ("Stack: {0}" -f $_.ScriptStackTrace)
  }
  $exitCode = 1
}
finally {
  Write-Log ("Exit code {0}" -f $exitCode)
}

exit $exitCode
