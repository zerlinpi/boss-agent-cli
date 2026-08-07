@echo off
setlocal
title BOSS Recruit AI - One Click
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-recruiter-web.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Review the error above, then press any key to close.
  pause >nul
)
endlocal
