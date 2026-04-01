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

function Wait-ForHealth {
    param(
        [int]$Port,
        [int]$Retries = 30,
        [int]$DelaySeconds = 1
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        if (Test-Health -Port $Port) {
            return $true
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    return $false
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runDir = if ($env:AUTOR_RUN_DIR_WIN) { $env:AUTOR_RUN_DIR_WIN } else { Join-Path $repoRoot ".run" }
$autoDownloadDir = if ($env:AUTOR_AUTODOWNLOAD_WIN_DIR) { $env:AUTOR_AUTODOWNLOAD_WIN_DIR } else { "F:\AutoDownload" }
$port = if ($env:AUTOR_AUTODOWNLOAD_PORT) { [int]$env:AUTOR_AUTODOWNLOAD_PORT } else { 8001 }
$pidFile = Join-Path $runDir "autodownload.pid"
$stdoutLog = Join-Path $runDir "autodownload.stdout.log"
$stderrLog = Join-Path $runDir "autodownload.stderr.log"

New-Item -ItemType Directory -Path $runDir -Force | Out-Null

if (-not (Test-Path $autoDownloadDir)) {
    throw "AutoDownload 目录不存在: $autoDownloadDir"
}

if (Test-Health -Port $port) {
    Write-Host "AutoDownload 已在运行: http://127.0.0.1:$port"
    exit 0
}

$service = Get-Service -Name "AutoDownload" -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne "Running") {
        Start-Service -Name "AutoDownload"
    }

    if (-not (Wait-ForHealth -Port $port)) {
        throw "AutoDownload Windows Service 已启动，但健康检查未通过。"
    }

    Write-Host "AutoDownload Windows Service 已启动。"
    exit 0
}

$pythonExe = Join-Path $autoDownloadDir ".venv\Scripts\python.exe"
$arguments = @()

if (Test-Path $pythonExe) {
    $filePath = $pythonExe
    $arguments = @("-m", "autodownload", "serve", "--port", "$port")
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $filePath = "uv"
    $arguments = @("run", "python", "-m", "autodownload", "serve", "--port", "$port")
} else {
    throw "未找到 AutoDownload 的 .venv\\Scripts\\python.exe，也未找到 uv。"
}

$startProcessParams = @{
    FilePath = $filePath
    ArgumentList = $arguments
    WorkingDirectory = $autoDownloadDir
    WindowStyle = "Hidden"
    RedirectStandardOutput = $stdoutLog
    RedirectStandardError = $stderrLog
    PassThru = $true
}

$process = Start-Process @startProcessParams

Set-Content -Path $pidFile -Value $process.Id -Encoding ascii

if (-not (Wait-ForHealth -Port $port)) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    throw "AutoDownload 启动失败，健康检查未通过。"
}

Write-Host "AutoDownload 已启动 (PID $($process.Id))。"