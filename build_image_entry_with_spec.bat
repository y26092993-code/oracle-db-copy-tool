@echo off
chcp 65001 >nul
REM Image Entry GUI OCR - Specファイルを使用した高度なビルド

echo ========================================
echo Image Entry GUI - Spec使用ビルド
echo ========================================
echo.

REM 仮想環境のPyInstallerを使用
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

REM PyInstallerがインストールされているか確認
if not exist "%PYINSTALLER%" (
    echo PyInstallerが見つかりません。インストール中...
    python -m pip install pyinstaller
)

echo Specファイルを使用してビルド中...
echo.

%PYINSTALLER% ImageEntryGUI.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    echo 実行ファイルの場所: dist\ImageEntryGUI.exe
    
    REM ファイルサイズを表示
    if exist dist\ImageEntryGUI.exe (
        for %%A in (dist\ImageEntryGUI.exe) do (
            set size=%%~zA
            set /A sizeMB=%%~zA/1048576
            echo ファイルサイズ: !sizeMB! MB
        )
    )
    echo.
    echo 使用方法:
    echo 1. dist\ImageEntryGUI.exe を任意の場所にコピー
    echo 2. 納税義務者情報.csv を同じフォルダに配置（検索機能を使う場合）
    echo 3. 実行して画像フォルダを選択
    echo.
    pause
) else (
    echo.
    echo ========================================
    echo ビルド失敗
    echo ========================================
    echo.
    pause
)
