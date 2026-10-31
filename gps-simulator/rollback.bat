@echo off
rem ============================================================
rem  LocaTester - roll back pymobiledevice3 to the last known good version
rem  Use this if the tool stopped working right after an automatic update.
rem ============================================================
cd /d "%~dp0"
if not exist venv (
    echo [ERROR] venv not found. Run start.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo [RUN] Installing the known good version...
type known_good.txt
python -m pip install --no-cache-dir -r known_good.txt
if errorlevel 1 (
    echo [ERROR] Rollback failed.
    pause
    exit /b 1
)
echo.
echo [OK] Done. Start with start-noupdate.bat to keep this version
echo      (start.bat updates automatically again).
pause
