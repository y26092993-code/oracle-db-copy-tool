@echo off
REM CSV to Excel変換アプリのEXE化ビルドスクリプト
REM 
REM 使用方法:
REM   build_exe.bat

echo ========================================
echo CSV to Excel 変換ツール - EXE化ビルド
echo ========================================
echo.

REM 仮想環境のPythonを使用
set PYTHON_EXE=C:\Users\hiyok\oracleConnect\.venv\Scripts\python.exe
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

echo 既存のビルドファイルをクリーンアップ...
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist Conv_Csv_To_Excel.spec del Conv_Csv_To_Excel.spec

echo.
echo EXEファイルをビルド中...
echo.

%PYINSTALLER% ^
    --name="CsvToExcel" ^
    --onefile ^
    --windowed ^
    --icon=NONE ^
    --add-data=".venv/Lib/site-packages/PySide6/plugins;PySide6/plugins" ^
    --hidden-import=PySide6 ^
    --hidden-import=openpyxl ^
    --hidden-import=pandas ^
    --hidden-import=chardet ^
    --hidden-import=openpyxl.cell._writer ^
    Conv_Csv_To_Excel.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    echo 実行ファイルの場所: dist\CsvToExcel.exe
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
