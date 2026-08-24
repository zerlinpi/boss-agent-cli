$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PyprojectPath = Join-Path $Root 'pyproject.toml'
$BuildVenv = Join-Path $Root '.venv-build'
$BuildPython = Join-Path $BuildVenv 'Scripts\python.exe'
$BuildRoot = Join-Path $Root 'build\desktop'
$PyInstallerDist = Join-Path $BuildRoot 'dist'
$PyInstallerWork = Join-Path $BuildRoot 'work'
$Dist = Join-Path $Root 'dist'

function Test-Python([string]$Executable) {
	if (-not $Executable -or -not (Test-Path $Executable)) { return $false }
	try {
		& $Executable -c "import sys, struct; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') * 8 == 64 else 1)" 2>$null
		return $LASTEXITCODE -eq 0
	} catch {
		return $false
	}
}

function Find-BasePython {
	if (Get-Command py -ErrorAction SilentlyContinue) {
		# Prefer the project's most conservative desktop-build interpreter. Newer
		# interpreters remain fallbacks, but PyInstaller/WebView compatibility is
		# deliberately optimized around Python 3.12 for reproducible Windows builds.
		foreach ($version in @('-3.12','-3.13','-3.11','-3.10','-3.14')) {
			try {
				$resolved = (& py $version -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
				if ($LASTEXITCODE -eq 0 -and (Test-Python $resolved)) { return $resolved }
			} catch {}
		}
	}
	$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
	if ($pythonCommand -and (Test-Python $pythonCommand.Source)) { return $pythonCommand.Source }
	return $null
}

if (-not (Test-Path $PyprojectPath)) {
	throw 'pyproject.toml was not found. Run this from a complete boss-agent-cli checkout.'
}

$Pyproject = Get-Content $PyprojectPath -Raw
$VersionMatch = [regex]::Match($Pyproject, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) { throw 'Unable to read project version from pyproject.toml.' }
$Version = $VersionMatch.Groups[1].Value
$ReleaseName = "BossRecruitAI-v$Version-win64"
$ReleaseDir = Join-Path $Dist $ReleaseName
$Archive = Join-Path $Dist "$ReleaseName.zip"

Write-Host ''
Write-Host '=== Boss Recruit AI - Windows EXE Builder ===' -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host "Version: $Version"

$BasePython = Find-BasePython
if (-not $BasePython) {
	throw '64-bit Python 3.10-3.14 is required to build the Windows desktop package.'
}

if ((Test-Path $BuildVenv) -and (-not (Test-Python $BuildPython))) {
	Remove-Item -Recurse -Force $BuildVenv
}
if (-not (Test-Path $BuildPython)) {
	Write-Host '[1/5] Creating isolated build environment...' -ForegroundColor Cyan
	& $BasePython -m venv $BuildVenv
	if ($LASTEXITCODE -ne 0) { throw 'Build virtual environment creation failed.' }
} else {
	Write-Host '[1/5] Build environment is ready.' -ForegroundColor DarkGray
}

Write-Host '[2/5] Installing desktop build dependencies...' -ForegroundColor Cyan
& $BuildPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $BuildPython -m pip install --disable-pip-version-check -e $Root 'pywebview>=5,<7' 'pyinstaller>=6,<7' 'pypdf>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Desktop build dependency installation failed.' }

Write-Host '[3/5] Building BossRecruitAI.exe...' -ForegroundColor Cyan
if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot }
New-Item -ItemType Directory -Path $PyInstallerDist -Force | Out-Null
New-Item -ItemType Directory -Path $PyInstallerWork -Force | Out-Null

$Entry = Join-Path $Root 'src\boss_agent_cli\desktop.py'
& $BuildPython -m PyInstaller `
	--noconfirm `
	--clean `
	--onedir `
	--windowed `
	--name BossRecruitAI `
	--paths (Join-Path $Root 'src') `
	--collect-all boss_agent_cli `
	--collect-all webview `
	--distpath $PyInstallerDist `
	--workpath $PyInstallerWork `
	--specpath $PyInstallerWork `
	$Entry
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

$BuiltDir = Join-Path $PyInstallerDist 'BossRecruitAI'
$BuiltExe = Join-Path $BuiltDir 'BossRecruitAI.exe'
if (-not (Test-Path $BuiltExe)) { throw 'BossRecruitAI.exe was not produced.' }

Write-Host '[4/5] Preparing release folder...' -ForegroundColor Cyan
New-Item -ItemType Directory -Path $Dist -Force | Out-Null
if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
Copy-Item -Path $BuiltDir -Destination $ReleaseDir -Recurse -Force

$StartHere = @'
Boss Recruit AI - Windows Desktop
=================================

1. Double-click BossRecruitAI.exe.
2. Follow only the main flow in the app:
   Configure AI -> Log in to BOSS -> Enable Research -> Run 5-candidate validation.
3. After validation, use Autopilot for daily incremental screening and review results manually.

Notes:
- The app binds only to a random localhost port and stores local data under ~/.boss-agent.
- Login credentials and API keys are not included in this package.
- BOSS login can open a separate Chrome/Edge window by design.
- If Windows SmartScreen warns about an unsigned local build, verify the ZIP source before running it.
'@
Set-Content -Path (Join-Path $ReleaseDir 'START-HERE.txt') -Value $StartHere -Encoding UTF8

Write-Host '[5/5] Creating release ZIP...' -ForegroundColor Cyan
if (Test-Path $Archive) { Remove-Item -Force $Archive }
Compress-Archive -Path $ReleaseDir -DestinationPath $Archive -CompressionLevel Optimal -Force
if (-not (Test-Path $Archive)) { throw 'Release ZIP creation failed.' }

$ArchiveInfo = Get-Item $Archive
Write-Host ''
Write-Host 'Build complete.' -ForegroundColor Green
Write-Host "EXE: $(Join-Path $ReleaseDir 'BossRecruitAI.exe')" -ForegroundColor Green
Write-Host "ZIP: $Archive" -ForegroundColor Green
Write-Host ("ZIP size: {0:N1} MB" -f ($ArchiveInfo.Length / 1MB)) -ForegroundColor DarkGray
Write-Host 'The release does not contain .git, .venv, auth sessions, API keys or local recruiter data.' -ForegroundColor DarkGray
