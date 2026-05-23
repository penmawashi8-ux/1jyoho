@echo off
echo ========================================
echo  iPhone GPS Simulator - Setup
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10 or later:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found:
python --version
echo.

if exist venv (
    echo [SKIP] venv already exists.
) else (
    echo [RUN] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo [OK] venv created.
)
echo.

echo [RUN] Installing packages...
call venv\Scripts\activate.bat
pip install --upgrade pip -q --no-cache-dir
pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Setup complete!
echo ========================================
echo.
echo Next steps:
echo  1. Open cmd AS ADMINISTRATOR and run:
echo     pymobiledevice3 remote tunneld
echo     (Keep this window open)
echo.
echo  2. In another cmd window run:
echo     start.bat
echo.
pause
