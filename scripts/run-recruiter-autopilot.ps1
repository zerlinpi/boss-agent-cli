param(
    [int]$MaxPages = 30,
    [int]$MaxCandidatesPerJob = 2000,
    [int]$RefreshSeenHours = 24,
    [int]$DraftTop = 10,
    [switch]$IncludeChat,
    [switch]$Force,
    [switch]$NoAutoConfigure,
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BossExe = Join-Path $Root ".venv\Scripts\boss.exe"
if (-not (Test-Path $BossExe)) {
    throw "未找到 $BossExe。请先在仓库根目录运行 start-recruiter-web.bat 完成环境初始化。"
}

if ($MaxPages -lt 1 -or $MaxPages -gt 100) { throw "MaxPages 必须在 1-100 之间" }
if ($MaxCandidatesPerJob -lt 1 -or $MaxCandidatesPerJob -gt 10000) { throw "MaxCandidatesPerJob 必须在 1-10000 之间" }
if ($RefreshSeenHours -lt 0 -or $RefreshSeenHours -gt 720) { throw "RefreshSeenHours 必须在 0-720 之间" }
if ($DraftTop -lt 0 -or $DraftTop -gt 100) { throw "DraftTop 必须在 0-100 之间" }

$ResolvedDataDir = if ($DataDir) {
    [Environment]::ExpandEnvironmentVariables($DataDir)
} else {
    Join-Path $HOME ".boss-agent"
}
$LogDir = Join-Path $ResolvedDataDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "recruiter-autopilot.log"

$BossArgs = @(
    "--data-dir", $ResolvedDataDir,
    "hr", "ai", "autopilot",
    "--max-pages", "$MaxPages",
    "--max-candidates-per-job", "$MaxCandidatesPerJob",
    "--refresh-seen-hours", "$RefreshSeenHours",
    "--top", "50",
    "--draft-top", "$DraftTop"
)
if ($IncludeChat) { $BossArgs += "--include-chat" }
if ($Force) { $BossArgs += "--force" }
if ($NoAutoConfigure) { $BossArgs += "--no-auto-configure" } else { $BossArgs += "--auto-configure" }

$env:PYTHONUTF8 = "1"
$StartStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$StartStamp] START boss $($BossArgs -join ' ')" | Add-Content -Path $LogFile -Encoding UTF8

Push-Location $Root
try {
    & $BossExe @BossArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
    $ExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

$EndStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$EndStamp] END exit=$ExitCode" | Add-Content -Path $LogFile -Encoding UTF8
if ($null -eq $ExitCode) { $ExitCode = 0 }
exit $ExitCode
