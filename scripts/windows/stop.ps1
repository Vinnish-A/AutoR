$ErrorActionPreference = "Stop"

function Test-Health {
    param([int]$Port)

    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runDir = if ($env:AUTOR_RUN_DIR_WIN) { $env:AUTOR_RUN_DIR_WIN } else { Join-Path $repoRoot ".run" }
$port = if ($env:AUTOR_AUTODOWNLOAD_PORT) { [int]$env:AUTOR_AUTODOWNLOAD_PORT } else { 8001 }
$pidFile = Join-Path $runDir "autodownload.pid"

$service = Get-Service -Name "AutoDownload" -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Stop-Service -Name "AutoDownload" -Force
}

if (Test-Path $pidFile) {
    $storedPid = Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($storedPid) {
        Stop-Process -Id ([int]$storedPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

$connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($connectionPid in $connections) {
    Stop-Process -Id $connectionPid -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

if (Test-Health -Port $port) {
    throw "The Records service is still running: http://127.0.0.1:$port"
}

Write-Host "Records service stopped."
