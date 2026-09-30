@echo off
rem ============================================================
rem  iPhone GPS Simulator - one-click launcher
rem  Double-click this file. It will automatically:
rem   1. Re-launch itself as administrator (click "Yes" on UAC)
rem   2. Run setup on first launch (venv + packages)
rem   3. Start tunneld in the background (done by the server)
rem   4. Start the server and open the browser
rem ============================================================

rem --- Not admin? Re-launch self with elevation ---
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

rem After elevation the cwd is System32, so go back to the script dir
cd /d "%~dp0"

echo ========================================
echo  iPhone GPS Simulator - Starting...
echo ========================================
echo.

if not exist venv (
    echo [INFO] First run: running setup...
    call setup.bat /nopause
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

echo [INFO] Starting server at http://localhost:8000
echo [INFO] tunneld is started automatically in the background.
echo [INFO] Close this window (or press Ctrl+C) to stop everything.
echo.

start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
