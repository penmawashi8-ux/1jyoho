@echo off
chcp 65001 >nul
echo ========================================
echo  iPhone GPS シミュレーター セットアップ
echo ========================================
echo.

:: Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Python が見つかりません。
    echo Python 3.10 以上をインストールしてください:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python が見つかりました:
python --version
echo.

:: venv作成
if exist venv (
    echo [スキップ] venv はすでに存在します。
) else (
    echo [実行] 仮想環境を作成中...
    python -m venv venv
    if errorlevel 1 (
        echo [エラー] venv の作成に失敗しました。
        pause
        exit /b 1
    )
    echo [OK] venv を作成しました。
)
echo.

:: 依存パッケージインストール
echo [実行] パッケージをインストール中...
call venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [エラー] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)
echo.
echo ========================================
echo  セットアップ完了！
echo ========================================
echo.
echo 次のステップ:
echo  1. 管理者権限のコマンドプロンプトで以下を実行（起動中は閉じないこと）:
echo     pymobiledevice3 remote tunneld
echo.
echo  2. 別のコマンドプロンプトで start.bat を実行:
echo     start.bat
echo.
pause
