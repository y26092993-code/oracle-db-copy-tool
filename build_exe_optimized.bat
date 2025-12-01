@echo off
REM CSV to Excel変換アプリの最適化EXE化ビルドスクリプト
REM ファイルサイズを最小化

echo ========================================
echo CSV to Excel 変換ツール - 最適化ビルド
echo ========================================
echo.

REM 仮想環境のPyInstallerを使用
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

echo 既存のビルドファイルをクリーンアップ...
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist Conv_Csv_To_Excel.spec del Conv_Csv_To_Excel.spec

echo.
echo 最適化EXEファイルをビルド中...
echo - 不要なモジュールを除外
echo - UPXで圧縮
echo.

%PYINSTALLER% ^
    --name="CsvToExcel" ^
    --onefile ^
    --windowed ^
    --optimize=2 ^
    --strip ^
    --noupx ^
    --exclude-module=PIL ^
    --exclude-module=PIL.Image ^
    --exclude-module=matplotlib ^
    --exclude-module=scipy ^
    --exclude-module=IPython ^
    --exclude-module=jupyter ^
    --exclude-module=notebook ^
    --exclude-module=pytest ^
    --exclude-module=setuptools ^
    --exclude-module=wheel ^
    --exclude-module=pip ^
    --exclude-module=tkinter ^
    --exclude-module=test ^
    --exclude-module=unittest ^
    --exclude-module=distutils ^
    --exclude-module=email ^
    --exclude-module=html ^
    --exclude-module=http ^
    --exclude-module=urllib3 ^
    --exclude-module=requests ^
    --hidden-import=pytz ^
    Conv_Csv_To_Excel.py

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
        set /A sizeMB=%%~zA/1048576
        echo ファイルサイズ: !sizeMB! MB
    )
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
