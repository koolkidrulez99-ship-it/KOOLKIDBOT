param([string]$Root)

$ErrorActionPreference = 'Continue'
$runDir = Join-Path $Root '.koolkid-run'
$stopFile = Join-Path $runDir 'watchdog.stop'
$logFile = Join-Path $runDir 'watchdog.log'
$services = @(
    @{ Name='MT5 multi-account worker'; Port=8002; Match='mt5_multi_account.app:app'; Url='http://127.0.0.1:8002/health'; Work=(Join-Path $Root 'mt5_module'); Command=('"{0}" -m uvicorn mt5_multi_account.app:app --host 127.0.0.1 --port 8002' -f (Join-Path $Root 'mt5_module\mt5_bridge\.venv\Scripts\python.exe')) },
    @{ Name='MT5 bridge'; Port=8000; Match='START_MT5_BRIDGE.bat|mt5_bridge.*main.py'; Url='http://127.0.0.1:8000/health'; Work=$Root; Command=('call "{0}"' -f (Join-Path $Root 'mt5_module\START_MT5_BRIDGE.bat')) },
    @{ Name='MT5 EA worker'; Port=8001; Match='START_MT5_EA_WORKER.bat|mt5_ea_worker.*main.py'; Url='http://127.0.0.1:8001/health'; Work=$Root; Command=('call "{0}"' -f (Join-Path $Root 'mt5_module\START_MT5_EA_WORKER.bat')) }
)
$failures = @{}
$nextTry = @{}

function Healthy([string]$url) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; return $r.StatusCode -ge 200 -and $r.StatusCode -lt 400 } catch { return $false }
}

function Listener-Exists([int]$port) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Service-Process-Exists([string]$pattern) {
    return $null -ne (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @('cmd.exe','python.exe') -and $_.CommandLine -and $_.CommandLine -match $pattern } | Select-Object -First 1)
}

Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
while (!(Test-Path -LiteralPath $stopFile)) {
    foreach ($service in $services) {
        if (Healthy $service.Url) { $failures[$service.Name] = 0; continue }
        $previousFailures = if ($null -eq $failures[$service.Name]) { 0 } else { [int]$failures[$service.Name] }
        $failures[$service.Name] = 1 + $previousFailures
        $retryAt = if ($null -eq $nextTry[$service.Name]) { [datetime]::MinValue } else { $nextTry[$service.Name] }
        if ($failures[$service.Name] -lt 3 -or (Get-Date) -lt $retryAt) { continue }

        if ((Listener-Exists $service.Port) -or (Service-Process-Exists $service.Match)) {
            "$(Get-Date -Format o) $($service.Name) unhealthy but existing owner detected; refusing duplicate start" | Add-Content -LiteralPath $logFile
            $nextTry[$service.Name] = (Get-Date).AddSeconds(30)
            continue
        }

        $delay = [Math]::Max(30, [Math]::Min(120, [Math]::Pow(2, [Math]::Min($failures[$service.Name] - 2, 7))))
        $nextTry[$service.Name] = (Get-Date).AddSeconds($delay)
        "$(Get-Date -Format o) starting $($service.Name) after $($failures[$service.Name]) failed health checks" | Add-Content -LiteralPath $logFile
        Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -ArgumentList @('/k', $service.Command) -WorkingDirectory $service.Work | Out-Null
        $failures[$service.Name] = 0
    }
    Start-Sleep -Seconds 3
}
