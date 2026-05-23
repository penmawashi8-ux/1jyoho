@echo off
chcp 65001 >nul
echo ========================================
echo  iPhone GPS シミュレーター 起動中...
echo ========================================
echo.

if not exist venv (
    echo [エラー] venv が見つかりません。先に setup.bat を実行してください。
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [情報] サーバーを起動します（http://localhost:8000）
echo [情報] 終了するには Ctrl+C を押してください
echo.

:: ブラウザを3秒後に開く（サーバー起動を待つ）
start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

uvicorn main:app --host 0.0.0.0 --port 8000
