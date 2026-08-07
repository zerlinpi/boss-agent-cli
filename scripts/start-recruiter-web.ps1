$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Marker = Join-Path $Venv '.recruiter-web-deps.sha256'

function Test-Python([string]$Executable) {
    if (-not $Executable -or -not (Test-Path $Executable)) { return $false }
    try {
        & $Executable -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-BasePython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.12','-3.11','-3.10')) {
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

Write-Host ''
Write-Host '=== BOSS Recruit AI - Windows One Click ===' -ForegroundColor Cyan
Write-Host "Project: $Root"

$BasePython = Find-BasePython
if (-not $BasePython) {
    Write-Host 'Python 3.10+ was not found. Trying to install Python 3.12 with winget...' -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Python 3.10+ is required. Install Python 3.12 from python.org, then double-click this file again.'
    }
    & winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 installation failed.' }
    $InstalledPython = Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'
    if (Test-Python $InstalledPython) {
        $BasePython = $InstalledPython
    } else {
        $BasePython = Find-BasePython
    }
    if (-not $BasePython) { throw 'Python was installed, but the current session cannot locate it. Reopen start-recruiter-web.bat.' }
}

if ((Test-Path $Venv) -and (-not (Test-Python $VenvPython))) {
    Write-Host '[1/3] Existing .venv is invalid or too old; rebuilding it...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Venv
}
if (-not (Test-Path $VenvPython)) {
    Write-Host '[1/3] Creating isolated Python environment...' -ForegroundColor Cyan
    & $BasePython -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}

$hashInput = @()
foreach ($fileName in @('pyproject.toml','uv.lock')) {
    $filePath = Join-Path $Root $fileName
    if (Test-Path $filePath) { $hashInput += (Get-FileHash $filePath -Algorithm SHA256).Hash }
}
$hashInput += 'recruiter-web-bootstrap-v5'
$bytes = [System.Text.Encoding]::UTF8.GetBytes(($hashInput -join '|'))
$sha = [System.Security.Cryptography.SHA256]::Create()
try { $Fingerprint = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','') } finally { $sha.Dispose() }
$InstalledFingerprint = if (Test-Path $Marker) { (Get-Content $Marker -Raw).Trim() } else { '' }

$NeedsInstall = $InstalledFingerprint -ne $Fingerprint
if (-not $NeedsInstall) {
    & $VenvPython -c "import boss_agent_cli, pypdf" 2>$null
    $NeedsInstall = $LASTEXITCODE -ne 0
}
if ($NeedsInstall) {
    Write-Host '[2/3] Installing/updating project dependencies (first run may take a few minutes)...' -ForegroundColor Cyan
    & $VenvPython -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $VenvPython -m pip install --disable-pip-version-check -e $Root 'pypdf>=6,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Set-Content -Path $Marker -Value $Fingerprint -Encoding ASCII
} else {
    Write-Host '[2/3] Dependencies are ready.' -ForegroundColor DarkGray
}

Write-Host '[3/3] Starting recruiter workspace...' -ForegroundColor Green
Write-Host 'The browser will open automatically. Close this window to stop the service.' -ForegroundColor DarkGray
Set-Location $Root
& $VenvPython -m boss_agent_cli.web
if ($LASTEXITCODE -ne 0) { throw "Recruiter workspace exited with code $LASTEXITCODE" }
