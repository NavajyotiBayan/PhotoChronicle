@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PhotoChronicle

set "APP_URL=http://127.0.0.1:8765"
set "PY=python"

where %PY% >nul 2>&1
if errorlevel 1 (
    echo.
    echo PhotoChronicle requires Python 3.10 or newer.
    echo Install Python from python.org, then run start.bat again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('%PY% -c "import sys; print(sys.version_info[0], sys.version_info[1])"') do set "PYMINOR=%%V"
for /f "tokens=1" %%V in ('%PY% -c "import sys; print(sys.version_info[0])"') do set "PYMAJOR=%%V"
if "%PYMAJOR%"=="" goto PYFAIL
if %PYMAJOR% LSS 3 goto PYFAIL
if %PYMAJOR% EQU 3 if %PYMINOR% LSS 10 goto PYFAIL

if not exist ".venv\Scripts\python.exe" (
    echo Creating a local Python environment...
    %PY% -m venv .venv
    if errorlevel 1 goto VENVFAIL
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

echo.
echo ========================================
echo          PhotoChronicle v1.0
echo        Preserve Your Timeline
echo ========================================
echo.
echo Checking required packages...
"%PYEXE%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto PIPFAIL

echo Starting local service...
start "PhotoChronicle Server" /min "%PYEXE%" app.py

set /a ATTEMPTS=0
:WAIT
set /a ATTEMPTS+=1
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -Uri '%APP_URL%' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto READY
if %ATTEMPTS% GEQ 30 goto SERVERFAIL
timeout /t 1 /nobreak >nul
goto WAIT

:READY
echo Server is ready. Opening PhotoChronicle...
start "" "%APP_URL%"
exit /b 0

:PYFAIL
echo.
echo Python 3.10 or newer is required.
echo.
pause
exit /b 1

:VENVFAIL
echo.
echo Could not create the local Python environment.
echo Check your Python installation and permissions.
echo.
pause
exit /b 1

:PIPFAIL
echo.
echo Could not install the required Python package.
echo Check your internet connection, then run start.bat again.
echo.
pause
exit /b 1

:SERVERFAIL
echo.
echo PhotoChronicle could not start on 127.0.0.1:8765.
echo The minimized server window should contain the error message.
echo.
pause
exit /b 1
