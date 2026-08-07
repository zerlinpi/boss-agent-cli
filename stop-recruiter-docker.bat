@echo off
setlocal
title Stop BOSS Recruit AI Docker
cd /d "%~dp0"
docker compose -f "%~dp0docker-compose.recruiter.yml" down
if errorlevel 1 pause
endlocal
