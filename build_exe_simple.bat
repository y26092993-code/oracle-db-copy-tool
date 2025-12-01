@echo off
REM CSV to Excel変換アプリのシンプルなEXE化ビルドスクリプト
REM より高速なビルド（複数ファイルで構成）

echo ========================================
echo CSV to Excel 変換ツール - 簡易ビルド
echo ========================================
echo.

REM 仮想環境のPyInstallerを使用
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

echo 既存のビルドファイルをクリーンアップ...
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist Conv_Csv_To_Excel.spec del Conv_Csv_To_Excel.spec

echo.
echo EXEファイルをビルド中（簡易版）...
echo.

%PYINSTALLER% ^
    --name="CsvToExcel" ^
    --onedir ^
    --windowed ^
    Conv_Csv_To_Excel.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    echo 実行ファイルの場所: dist\CsvToExcel\CsvToExcel.exe
    echo フォルダごと配布してください
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
