@echo off
setlocal
title Boss Recruit AI - Build EXE
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-recruiter-exe.ps1"
if errorlevel 1 (
  echo.
  echo Build failed. Review the error above, then press any key to close.
  pause >nul
)
endlocal
