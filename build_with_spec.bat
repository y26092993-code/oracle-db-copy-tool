@echo off
REM 最適化specファイルを使用したビルド

echo ========================================
echo CSV to Excel - SPEC最適化ビルド
echo ========================================
echo.

set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

echo 既存のビルドファイルをクリーンアップ...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo.
echo SPECファイルを使用してビルド中...
echo.

%PYINSTALLER% build_spec_optimized.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    echo 実行ファイルの場所: dist\CsvToExcel.exe
    
    REM ファイルサイズを表示
    for %%A in (dist\CsvToExcel.exe) do (
        set size=%%~zA
        echo ファイルサイズ: %%~zA bytes
    )
    echo.
    pause
) else (
    echo.
    echo ビルド失敗
    echo.
    pause
)
