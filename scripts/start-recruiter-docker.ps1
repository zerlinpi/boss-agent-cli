$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $Root 'docker-compose.recruiter.yml'
$PortText = if ($env:BOSS_WEB_PORT) { $env:BOSS_WEB_PORT.Trim() } else { '8765' }
$ParsedPort = 0
if (-not [int]::TryParse($PortText, [ref]$ParsedPort) -or $ParsedPort -lt 1 -or $ParsedPort -gt 65535) {
    throw 'BOSS_WEB_PORT must be an integer between 1 and 65535.'
}
$Port = $ParsedPort.ToString()
$env:BOSS_WEB_PORT = $Port
$Url = "http://127.0.0.1:$Port/"

function Resolve-Docker {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path $default) { return $default }
    return $null
}

function Test-PortOpen([int]$PortNumber) {
    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync('127.0.0.1', $PortNumber)
        if (-not $task.Wait(600)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        if ($client) { $client.Dispose() }
    }
}

function Test-RecruiterWorkspace([string]$Address) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Address -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match 'BOSS Recruit AI'
    } catch {
        return $false
    }
}

Write-Host ''
Write-Host '=== BOSS Recruit AI - Docker One Click ===' -ForegroundColor Cyan
Write-Host "Web address: $Url" -ForegroundColor DarkGray

if (Test-RecruiterWorkspace $Url) {
    Write-Host "Recruiter workspace is already running: $Url" -ForegroundColor Green
    Start-Process $Url
    exit 0
}
if (Test-PortOpen $ParsedPort) {
    throw "Host port $Port is already in use by another application. Set BOSS_WEB_PORT to a free port and retry."
}

$Docker = Resolve-Docker
if (-not $Docker) {
    Write-Host 'Docker Desktop was not found. Trying winget installation...' -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop, then double-click this file again.'
    }
    & winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop installation failed.' }
    $Docker = Resolve-Docker
    if (-not $Docker) { throw 'Docker Desktop was installed. Restart Windows if requested, then run this file again.' }
}

& $Docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) {
        Write-Host 'Starting Docker Desktop...' -ForegroundColor Yellow
        Start-Process $desktop
    }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        & $Docker info *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Docker engine is not ready. Open Docker Desktop and retry.' }
}

Set-Location $Root
Write-Host '[1/2] Building and starting container...' -ForegroundColor Cyan
& $Docker compose -f $ComposeFile up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed. Check the Docker output above for the exact cause.' }

Write-Host '[2/2] Waiting for Web workspace...' -ForegroundColor Cyan
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    if (Test-RecruiterWorkspace $Url) { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    & $Docker compose -f $ComposeFile logs --tail 80 recruiter-web
    throw 'Container started but Web workspace did not become healthy.'
}

Write-Host "Recruiter workspace is ready: $Url" -ForegroundColor Green
Write-Host 'Data is persisted in Docker volume: boss-recruiter-data' -ForegroundColor DarkGray
Start-Process $Url
