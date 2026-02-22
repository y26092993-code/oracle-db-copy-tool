@echo off
REM Oracle DB オブジェクトコピーツール ビルドスクリプト
REM 
REM このスクリプトは PyInstaller を使用して
REM スタンドアロンの実行ファイル（exe）を作成します

echo ========================================
echo Oracle DB オブジェクトコピーツール
echo ビルドスクリプト
echo ========================================
echo.

REM 現在のディレクトリを保存
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo [1/5] 環境チェック中...
python --version >nul 2>&1
if errorlevel 1 (
    echo エラー: Pythonが見つかりません
    echo Pythonをインストールしてください
    pause
    exit /b 1
)

echo [2/5] 必要なパッケージをインストール中...
pip install -r requirements.txt
if errorlevel 1 (
    echo エラー: パッケージのインストールに失敗しました
    pause
    exit /b 1
)

echo [3/5] 既存のビルドファイルをクリーンアップ中...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

echo [4/5] PyInstallerでビルド中...
pyinstaller db_copy_tool.spec
if errorlevel 1 (
    echo エラー: ビルドに失敗しました
    pause
    exit /b 1
)

echo [5/5] ビルド後の処理中...
if exist "dist\DBCopyTool.exe" (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    echo 実行ファイル: %SCRIPT_DIR%dist\DBCopyTool.exe
    echo.
    echo 配布する場合は、dist\DBCopyTool.exe をコピーしてください
    echo （他のファイルは不要です）
    echo.
) else (
    echo エラー: 実行ファイルが作成されませんでした
    pause
    exit /b 1
)

echo ビルドログを確認しますか？ (Y/N)
choice /c YN /n
if errorlevel 2 goto :end
if errorlevel 1 (
    if exist "build\DBCopyTool\warn-DBCopyTool.txt" (
        notepad "build\DBCopyTool\warn-DBCopyTool.txt"
    )
)

:end
pause
