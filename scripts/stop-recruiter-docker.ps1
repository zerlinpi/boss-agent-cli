$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $Root 'docker-compose.recruiter.yml'

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$Docker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe' }
if (-not (Test-Path $Docker)) { throw 'Docker CLI was not found.' }

Set-Location $Root
& $Docker compose -f $ComposeFile down
if ($LASTEXITCODE -ne 0) { throw 'docker compose down failed.' }
Write-Host 'BOSS Recruit AI Docker service stopped.' -ForegroundColor Green
