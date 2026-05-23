@echo off
echo ========================================
echo  iPhone GPS Simulator - Starting...
echo ========================================
echo.

if not exist venv (
    echo [ERROR] venv not found. Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [INFO] Starting server at http://localhost:8000
echo [INFO] Press Ctrl+C to stop.
echo.

start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

uvicorn main:app --host 0.0.0.0 --port 8000
