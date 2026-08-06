@echo off
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%.venv\Scripts\pythonw.exe" (
	start "" "%ROOT%.venv\Scripts\pythonw.exe" "%ROOT%start-recruiter-web.pyw"
	exit /b 0
)
where pyw >nul 2>nul
if %errorlevel%==0 (
	start "" pyw "%ROOT%start-recruiter-web.pyw"
	exit /b 0
)
start "" pythonw "%ROOT%start-recruiter-web.pyw"
