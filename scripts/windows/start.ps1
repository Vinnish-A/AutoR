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

function Test-Port {
    param([int]$Port)

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-Ready {
    param([int]$Port)

    if (Test-Health -Port $Port) {
        return $true
    }
    if ($env:AUTOR_AUTODOWNLOAD_HEALTH_STRICT -eq "1") {
        return $false
    }
    return Test-Port -Port $Port
}

function Wait-ForReady {
    param(
        [int]$Port,
        [int]$Retries = 30,
        [int]$DelaySeconds = 1
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        if (Test-Ready -Port $Port) {
            return $true
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    return $false
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runDir = if ($env:AUTOR_RUN_DIR_WIN) { $env:AUTOR_RUN_DIR_WIN } else { Join-Path $repoRoot ".run" }
$autoDownloadDir = if ($env:AUTOR_AUTODOWNLOAD_WIN_DIR) { $env:AUTOR_AUTODOWNLOAD_WIN_DIR } else { "F:\Records" }
$port = if ($env:AUTOR_AUTODOWNLOAD_PORT) { [int]$env:AUTOR_AUTODOWNLOAD_PORT } else { 8001 }
$pidFile = Join-Path $runDir "autodownload.pid"
$stdoutLog = Join-Path $runDir "autodownload.stdout.log"
$stderrLog = Join-Path $runDir "autodownload.stderr.log"

New-Item -ItemType Directory -Path $runDir -Force | Out-Null

if (-not (Test-Path $autoDownloadDir)) {
    throw "Records repository not found: $autoDownloadDir"
}

if (Test-Ready -Port $port) {
    Write-Host "Records service is already running: http://127.0.0.1:$port"
    exit 0
}

$service = Get-Service -Name "AutoDownload" -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne "Running") {
        Start-Service -Name "AutoDownload"
    }

    if (-not (Wait-ForReady -Port $port)) {
        throw "The AutoDownload Windows service started, but the Records service did not become reachable."
    }

    if (-not (Test-Health -Port $port)) {
        Write-Warning "Records service is listening, but /health did not respond. Startup continues; set AUTOR_AUTODOWNLOAD_HEALTH_STRICT=1 to require /health."
    }
    Write-Host "Records Windows service started."
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
    throw "Could not find .venv\\Scripts\\python.exe in the Records repo, and uv is not available."
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

if (-not (Wait-ForReady -Port $port)) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    throw "The Records service failed to start because the port did not become reachable."
}

if (-not (Test-Health -Port $port)) {
    Write-Warning "Records service is listening, but /health did not respond. Startup continues; set AUTOR_AUTODOWNLOAD_HEALTH_STRICT=1 to require /health."
}
Write-Host "Records service started (PID $($process.Id))."
