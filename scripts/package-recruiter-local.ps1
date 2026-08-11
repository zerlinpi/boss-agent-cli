$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Dist = Join-Path $Root 'dist'
$PyprojectPath = Join-Path $Root 'pyproject.toml'

function Copy-PackageItem([string]$RelativePath, [string]$DestinationRoot, [bool]$Required = $true) {
	$Source = Join-Path $Root $RelativePath
	if (-not (Test-Path $Source)) {
		if ($Required) { throw "Required package item is missing: $RelativePath" }
		return
	}
	$Destination = Join-Path $DestinationRoot $RelativePath
	$Parent = Split-Path $Destination -Parent
	if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
	Copy-Item -Path $Source -Destination $Destination -Recurse -Force
}

if (-not (Test-Path $PyprojectPath)) {
	throw 'pyproject.toml was not found. Run this script from a complete boss-agent-cli checkout.'
}

$Pyproject = Get-Content $PyprojectPath -Raw
$VersionMatch = [regex]::Match($Pyproject, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) {
	throw 'Unable to read the project version from pyproject.toml.'
}
$Version = $VersionMatch.Groups[1].Value
$PackageName = "boss-recruit-ai-local-v$Version"
$Stage = Join-Path $Dist ".package-$PID"
$StageRoot = Join-Path $Stage $PackageName
$Archive = Join-Path $Dist "$PackageName.zip"

Write-Host ''
Write-Host '=== BOSS Recruit AI - Local Package ===' -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host "Version: $Version"
Write-Host ''
Write-Host '[1/3] Preparing minimal runtime files...' -ForegroundColor Cyan

New-Item -ItemType Directory -Path $Dist -Force | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

try {
	# Explicit allowlist: package only the runtime needed by the recruiter Web workspace.
	# Never copy .venv, .git, dist, tests, caches, local data, auth sessions or API keys.
	Copy-PackageItem 'src' $StageRoot
	Copy-PackageItem 'scripts\start-recruiter-web.ps1' $StageRoot
	Copy-PackageItem 'start-recruiter-web.bat' $StageRoot
	Copy-PackageItem 'pyproject.toml' $StageRoot
	Copy-PackageItem 'uv.lock' $StageRoot $false
	Copy-PackageItem 'README.md' $StageRoot
	Copy-PackageItem 'LICENSE' $StageRoot

	$PackageReadme = @'
BOSS Recruit AI - Local Windows Package
========================================

Start:
  1. Extract this ZIP to a normal local folder.
  2. Double-click start-recruiter-web.bat.
  3. In the Web UI follow only: AI -> BOSS login -> Research -> 5-candidate validation.

The first start creates its own .venv and installs runtime dependencies.
Local recruiter data, login credentials and API keys are NOT included in this ZIP.
They remain in the current Windows user's ~/.boss-agent directory.

Do not copy an existing .boss-agent/auth directory or API key into a package for sharing.
'@
	Set-Content -Path (Join-Path $StageRoot 'START-HERE.txt') -Value $PackageReadme -Encoding UTF8

	Write-Host '[2/3] Creating ZIP...' -ForegroundColor Cyan
	if (Test-Path $Archive) { Remove-Item -Force $Archive }
	Compress-Archive -Path $StageRoot -DestinationPath $Archive -CompressionLevel Optimal -Force

	if (-not (Test-Path $Archive)) { throw 'ZIP creation failed.' }
	$ArchiveInfo = Get-Item $Archive
	if ($ArchiveInfo.Length -le 0) { throw 'ZIP creation produced an empty file.' }

	Write-Host '[3/3] Package ready.' -ForegroundColor Green
	Write-Host "Output: $Archive" -ForegroundColor Green
	Write-Host ("Size: {0:N1} MB" -f ($ArchiveInfo.Length / 1MB)) -ForegroundColor DarkGray
	Write-Host ''
	Write-Host 'The package contains only the recruiter runtime. It does not include local credentials, .venv, tests or Git history.' -ForegroundColor DarkGray
} finally {
	if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
}
