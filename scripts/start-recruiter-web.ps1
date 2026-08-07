$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Marker = Join-Path $Venv '.recruiter-web-deps.sha256'

function Find-BasePython {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.12') }
        $candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.11') }
        $candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.10') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += [pscustomobject]@{ Exe = 'python'; Prefix = @() }
    }
    foreach ($candidate in $candidates) {
        try {
            & $candidate.Exe @($candidate.Prefix) -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    return $null
}

function Invoke-PythonCommand($PythonCommand, [string[]]$Arguments) {
    & $PythonCommand.Exe @($PythonCommand.Prefix) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE" }
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
    if (Test-Path $InstalledPython) {
        $BasePython = [pscustomobject]@{ Exe = $InstalledPython; Prefix = @() }
    } else {
        $BasePython = Find-BasePython
    }
    if (-not $BasePython) { throw 'Python was installed, but the current session cannot locate it. Reopen start-recruiter-web.bat.' }
}

if (-not (Test-Path $VenvPython)) {
    Write-Host '[1/3] Creating isolated Python environment...' -ForegroundColor Cyan
    Invoke-PythonCommand $BasePython @('-m','venv',$Venv)
}

$hashInput = @()
foreach ($fileName in @('pyproject.toml','uv.lock')) {
    $filePath = Join-Path $Root $fileName
    if (Test-Path $filePath) { $hashInput += (Get-FileHash $filePath -Algorithm SHA256).Hash }
}
$hashInput += 'recruiter-web-bootstrap-v3'
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
