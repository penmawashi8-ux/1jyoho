@echo off
rem ============================================================
rem  iPhone GPS Simulator - connection diagnostics
rem  Double-click, then send the contents of diagnose.txt
rem ============================================================
cd /d "%~dp0"
set OUT=diagnose.txt

echo Collecting diagnostics... please wait.
echo ===== python ===== > %OUT%
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe --version >> %OUT% 2>&1
    venv\Scripts\python.exe -m pip show pymobiledevice3 >> %OUT% 2>&1
) else (
    echo venv not found - run start.bat first >> %OUT%
)

echo. >> %OUT%
echo ===== Apple Mobile Device Service ===== >> %OUT%
sc query "Apple Mobile Device Service" >> %OUT% 2>&1
powershell -NoProfile -Command "Test-NetConnection 127.0.0.1 -Port 27015 -InformationLevel Quiet" >> %OUT% 2>&1

echo. >> %OUT%
echo ===== usbmux list ===== >> %OUT%
if exist venv\Scripts\pymobiledevice3.exe venv\Scripts\pymobiledevice3.exe usbmux list >> %OUT% 2>&1

echo. >> %OUT%
echo ===== tunneld.log ===== >> %OUT%
if exist tunneld.log type tunneld.log >> %OUT%

echo.
echo Done. Please send the contents of diagnose.txt
notepad %OUT%
