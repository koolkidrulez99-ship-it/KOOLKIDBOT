param(
    [ValidateSet('Start', 'Stop')]
    [string]$Action = 'Start'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runDir = Join-Path $root '.koolkid-run'
$bridgePidFile = Join-Path $runDir 'mt5-bridge.pid'
$workerPidFile = Join-Path $runDir 'mt5-ea-worker.pid'
$multiPidFile = Join-Path $runDir 'mt5-multi-account.pid'
$mainPidFile = Join-Path $runDir 'koolkid-main.pid'
$bridgeHealth = 'http://127.0.0.1:8000/health'
$workerHealth = 'http://127.0.0.1:8001/health'
$multiHealth = 'http://127.0.0.1:8002/health'
$mainPort = if ($env:PORT) { [int]$env:PORT } else { 5055 }
$mainUrl = "http://127.0.0.1:$mainPort/"

function Test-Url([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Wait-Healthy([string]$Url, [int]$Seconds, [string]$Name) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $Url) { return $true }
        Write-Host "Waiting for $Name..."
        Start-Sleep -Seconds 2
    }
    return $false
}

function Save-Pid([System.Diagnostics.Process]$Process, [string]$Path) {
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    Set-Content -LiteralPath $Path -Value $Process.Id -Encoding ascii
}

function Stop-Tracked([string]$PidFile, [string]$ExpectedText, [string]$Label) {
    if (!(Test-Path -LiteralPath $PidFile)) {
        Write-Host "$Label was not started by this launcher."
        return
    }
    $trackedPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$trackedPid" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like "*$ExpectedText*") {
        & taskkill.exe /PID $trackedPid /T /F | Out-Null
        Write-Host "$Label stopped."
    } else {
        Write-Host "$Label PID is no longer owned by this launcher; nothing was stopped."
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

if ($Action -eq 'Stop') {
    Stop-Tracked $mainPidFile 'server.py' 'KOOLKID server'
    Stop-Tracked $multiPidFile 'mt5_multi_account.app:app' 'MT5 multi-account worker'
    Stop-Tracked $workerPidFile 'START_MT5_EA_WORKER.bat' 'MT5 EA worker'
    Stop-Tracked $bridgePidFile 'START_MT5_BRIDGE.bat' 'MT5 bridge'
    exit 0
}

Write-Host 'Starting KOOLKID local services...'

if (Test-Url $multiHealth) {
    Write-Host 'MT5 multi-account worker is already healthy; using the existing process.'
} else {
    $multiPython = Join-Path $root 'mt5_module\mt5_bridge\.venv\Scripts\python.exe'
    $multiModuleDir = Join-Path $root 'mt5_module'
    if (!(Test-Path -LiteralPath $multiPython)) { throw "MT5 multi-account Python runtime was not found: $multiPython" }
    if (!(Test-Path -LiteralPath (Join-Path $multiModuleDir 'mt5_multi_account\app.py'))) { throw "MT5 multi-account module was not found under: $multiModuleDir" }
    $multiCommand = "cd /d `"$multiModuleDir`" && `"$multiPython`" -m uvicorn mt5_multi_account.app:app --host 127.0.0.1 --port 8002"
    $multiProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', $multiCommand) -WorkingDirectory $multiModuleDir -PassThru
    Save-Pid $multiProcess $multiPidFile
    if (!(Wait-Healthy $multiHealth 60 'MT5 multi-account worker')) {
        Write-Host ''
        Write-Host 'ERROR: MT5 multi-account worker failed to become healthy at http://127.0.0.1:8002/health.' -ForegroundColor Red
        Write-Host 'The multi-account worker window has been left open so you can read the startup error.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'MT5 multi-account worker is healthy.'
}

if (Test-Url $bridgeHealth) {
    Write-Host 'MT5 bridge is already healthy; using the existing process.'
} else {
    $bridgeScript = Join-Path $root 'mt5_module\START_MT5_BRIDGE.bat'
    if (!(Test-Path -LiteralPath $bridgeScript)) { throw "MT5 bridge launcher was not found: $bridgeScript" }
    $bridgeCommand = "call `"$bridgeScript`""
    $bridgeProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', $bridgeCommand) -WorkingDirectory $root -PassThru
    Save-Pid $bridgeProcess $bridgePidFile
    if (!(Wait-Healthy $bridgeHealth 90 'MT5 bridge')) {
        Write-Host ''
        Write-Host 'ERROR: MT5 bridge failed to become healthy at http://127.0.0.1:8000/health.' -ForegroundColor Red
        Write-Host 'The MT5 bridge window has been left open so you can read the startup error.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'MT5 bridge is healthy.'
}

if (Test-Url $workerHealth) {
    Write-Host 'MT5 EA worker is already healthy; using the existing process.'
} else {
    $workerScript = Join-Path $root 'mt5_module\START_MT5_EA_WORKER.bat'
    if (!(Test-Path -LiteralPath $workerScript)) { throw "MT5 EA worker launcher was not found: $workerScript" }
    $workerCommand = "call `"$workerScript`""
    $workerProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', $workerCommand) -WorkingDirectory $root -PassThru
    Save-Pid $workerProcess $workerPidFile
    if (!(Wait-Healthy $workerHealth 90 'MT5 EA worker')) {
        Write-Host ''
        Write-Host 'ERROR: MT5 EA worker failed to become healthy at http://127.0.0.1:8001/health.' -ForegroundColor Red
        Write-Host 'The EA worker window has been left open so you can read the startup error.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'MT5 EA worker is healthy.'
}

if (Test-Url $mainUrl) {
    Write-Host "KOOLKID server is already running at $mainUrl"
} else {
    $mainCommand = "cd /d `"$root`" && set `"PORT=$mainPort`" && python server.py"
    $mainProcess = Start-Process -FilePath $env:ComSpec -ArgumentList @('/k', $mainCommand) -WorkingDirectory $root -PassThru
    Save-Pid $mainProcess $mainPidFile
    if (!(Wait-Healthy $mainUrl 60 'KOOLKID server')) {
        Write-Host ''
        Write-Host "ERROR: KOOLKID server failed to become ready at $mainUrl" -ForegroundColor Red
        Write-Host 'The KOOLKID server window has been left open so you can read the startup error.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'KOOLKID server is ready.'
}

Start-Process $mainUrl
Write-Host "Opened $mainUrl"
