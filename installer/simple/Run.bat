@echo off
title Attendance
setlocal EnableExtensions
cd /d "%~dp0"

set "PORT=8000"
if exist "app-port.txt" set /p PORT=<"app-port.txt"
set "PY=%~dp0backend\.venv\Scripts\python.exe"

if not exist "%PY%" goto missing
if not exist "%~dp0backend\.env" goto noenv

netstat -ano | findstr /C:":%PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 goto open

echo Starting Attendance on port %PORT%...
start "Attendance" /D "%~dp0backend" /min cmd /k ""%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%"
set "WAIT=0"

:wait
curl.exe -fsS -o nul "http://127.0.0.1:%PORT%/api/health/ready"
if not errorlevel 1 goto open
set /a WAIT+=1
if %WAIT% GEQ 30 goto slow
timeout /t 2 /nobreak >nul
goto wait

:open
start "" "http://localhost:%PORT%"
echo.
echo This PC:  http://localhost:%PORT%
echo.
pause
exit /b 0

:slow
echo The program window is open, but the page is not ready yet.
echo Leave that window open, then refresh the browser.
pause
exit /b 0

:missing
echo Python environment is missing.
echo Run Attendance_Setup.exe again.
pause
exit /b 1

:noenv
echo The database settings are missing.
echo Run Attendance_Setup.exe again and enter the MySQL root password.
pause
exit /b 1
