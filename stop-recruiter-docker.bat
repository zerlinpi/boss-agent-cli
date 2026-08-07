@echo off
setlocal
title Stop BOSS Recruit AI Docker
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-recruiter-docker.ps1"
if errorlevel 1 (
  echo.
  echo Stop failed. Review the error above, then press any key to close.
  pause >nul
)
endlocal
