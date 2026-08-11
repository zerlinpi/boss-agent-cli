@echo off
setlocal
title BOSS Recruit AI - Local Package
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package-recruiter-local.ps1"
if errorlevel 1 (
  echo.
  echo Packaging failed. Review the error above, then press any key to close.
  pause >nul
) else (
  echo.
  echo Packaging completed. Press any key to close.
  pause >nul
)
endlocal
