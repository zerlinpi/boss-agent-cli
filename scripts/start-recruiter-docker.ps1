$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $Root 'docker-compose.recruiter.yml'
$Port = if ($env:BOSS_WEB_PORT) { $env:BOSS_WEB_PORT } else { '8765' }
$Url = "http://127.0.0.1:$Port/"

function Resolve-Docker {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path $default) { return $default }
    return $null
}

Write-Host ''
Write-Host '=== BOSS Recruit AI - Docker One Click ===' -ForegroundColor Cyan
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
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed.' }

Write-Host '[2/2] Waiting for Web workspace...' -ForegroundColor Cyan
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $healthy) {
    & $Docker compose -f $ComposeFile logs --tail 80 recruiter-web
    throw 'Container started but Web workspace did not become healthy.'
}

Write-Host "Recruiter workspace is ready: $Url" -ForegroundColor Green
Write-Host 'Data is persisted in Docker volume: boss-recruiter-data' -ForegroundColor DarkGray
Start-Process $Url
