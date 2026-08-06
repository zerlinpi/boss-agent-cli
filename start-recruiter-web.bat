@echo off
setlocal
set "ROOT=%~dp0"
title BOSS Recruit AI
cd /d "%ROOT%"
if exist "%ROOT%.venv\Scripts\python.exe" (
	"%ROOT%.venv\Scripts\python.exe" "%ROOT%start-recruiter-web.pyw"
	exit /b %errorlevel%
)
where py >nul 2>nul
if %errorlevel%==0 (
	py "%ROOT%start-recruiter-web.pyw"
	exit /b %errorlevel%
)
python "%ROOT%start-recruiter-web.pyw"
