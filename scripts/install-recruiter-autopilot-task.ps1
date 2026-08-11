param(
    [string]$TaskName = "BOSS Recruit AI Autopilot",
    [string]$DailyAt = "09:00",
    [int]$MaxPages = 30,
    [int]$MaxCandidatesPerJob = 2000,
    [int]$RefreshSeenHours = 24,
    [int]$DraftTop = 10,
    [switch]$IncludeChat,
    [switch]$NoAutoConfigure,
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $PSScriptRoot "run-recruiter-autopilot.ps1"
$BossExe = Join-Path $Root ".venv\Scripts\boss.exe"
if (-not (Test-Path $Runner)) { throw "未找到 Autopilot runner: $Runner" }
if (-not (Test-Path $BossExe)) {
    throw "未找到 $BossExe。请先运行 start-recruiter-web.bat，确认 Web/CLI 环境初始化成功后再安装计划任务。"
}

try {
    $At = [DateTime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "DailyAt 必须使用 HH:mm 格式，例如 09:00"
}
if ($MaxPages -lt 1 -or $MaxPages -gt 100) { throw "MaxPages 必须在 1-100 之间" }
if ($MaxCandidatesPerJob -lt 1 -or $MaxCandidatesPerJob -gt 10000) { throw "MaxCandidatesPerJob 必须在 1-10000 之间" }
if ($RefreshSeenHours -lt 0 -or $RefreshSeenHours -gt 720) { throw "RefreshSeenHours 必须在 0-720 之间" }
if ($DraftTop -lt 0 -or $DraftTop -gt 100) { throw "DraftTop 必须在 0-100 之间" }

$ArgumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $Runner),
    "-MaxPages", "$MaxPages",
    "-MaxCandidatesPerJob", "$MaxCandidatesPerJob",
    "-RefreshSeenHours", "$RefreshSeenHours",
    "-DraftTop", "$DraftTop"
)
if ($IncludeChat) { $ArgumentParts += "-IncludeChat" }
if ($NoAutoConfigure) { $ArgumentParts += "-NoAutoConfigure" }
if ($DataDir) {
    $ArgumentParts += @("-DataDir", ('"{0}"' -f $DataDir))
}
$Arguments = $ArgumentParts -join " "

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $Identity -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Incrementally sync current BOSS recruiter jobs/applications, score resumes with AI, rank candidates, and create human-review reply drafts."

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null

Write-Host ""
Write-Host "Recruiter Autopilot 计划任务已安装" -ForegroundColor Green
Write-Host "Task: $TaskName"
Write-Host "Daily: $DailyAt"
Write-Host "User: $Identity (Interactive only)"
Write-Host "Runner: $Runner"
Write-Host "Data:  $([string]($(if ($DataDir) { $DataDir } else { Join-Path $HOME '.boss-agent' })))"
Write-Host ""
Write-Host "立即测试一次："
Write-Host "Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host ""
Write-Host "查看任务状态："
Write-Host "Get-ScheduledTask -TaskName `"$TaskName`" | Get-ScheduledTaskInfo"
Write-Host ""
Write-Host "删除计划任务："
Write-Host "Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
