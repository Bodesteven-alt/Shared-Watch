# Starts the local Flask watchlist site for your PC.
# Designed to be called by Windows Task Scheduler at startup / log on.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$host = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$port = if ($env:PORT) { $env:PORT } else { "5000" }

$env:HOST = $host
$env:PORT = $port

$logDir = Join-Path $scriptDir "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "startup.log"

# Use Python 3.12 (matches your current interactive `python`).
$pythonExe = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
if (-not $pythonExe) { $pythonExe = "python" }

Add-Content -Path $logFile -Value ("[{0}] Starting watchlist site (HOST={1}, PORT={2})" -f (Get-Date).ToString("s"), $host, $port)

# Blocking call: Task Scheduler will keep the job "running" while the server is up.
& $pythonExe "app.py" 1>> $logFile 2>> $logFile

