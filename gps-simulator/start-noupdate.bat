@echo off
rem ============================================================
rem  LocaTester - launcher without automatic updates
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
echo  LocaTester - Starting...
echo ========================================
echo.

rem Run setup on the first launch, or again if a previous setup did not finish
if not exist venv\installed.txt (
    echo [INFO] Running setup...
    call setup.bat /nopause
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

rem --- No automatic update (use after rollback.bat)

rem --- Another LocaTester (e.g. the check edition) is still running: the browser would show that one
python -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1', 8000)) == 0 else 0)"
if errorlevel 1 (
    echo.
    echo [ERROR] LocaTester is already running in another window ^(port 8000 is in use^).
    echo   Close the other black LocaTester window first, then double-click start.bat again.
    pause
    exit /b 1
)

echo [INFO] Starting server at http://localhost:8000
echo [INFO] tunneld is started automatically in the background.
echo [INFO] Close this window (or press Ctrl+C) to stop everything.
echo.

start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
