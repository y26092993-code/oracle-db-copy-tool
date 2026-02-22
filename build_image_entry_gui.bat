@echo off
chcp 65001 >nul
REM Image Entry GUI OCR - EXE化ビルドスクリプト
REM 最適化してファイルサイズを削減

echo ========================================
echo Image Entry GUI OCR - EXEビルド
echo ========================================
echo.

REM 仮想環境のPyInstallerを使用
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

REM PyInstallerがインストールされているか確認
if not exist "%PYINSTALLER%" (
    echo PyInstallerが見つかりません。インストール中...
    python -m pip install pyinstaller
)

echo 既存のビルドファイルをクリーンアップ...
if exist build\image_entry_gui rd /s /q build\image_entry_gui
if exist dist\ImageEntryGUI.exe del dist\ImageEntryGUI.exe

echo.
echo EXEファイルをビルド中...
echo - OCR機能を含む
echo - PySide6 GUI
echo - 最適化レベル2
echo.

%PYINSTALLER% ^
    --name="ImageEntryGUI" ^
    --onefile ^
    --windowed ^
    --optimize=2 ^
    --noupx ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=pytesseract ^
    --hidden-import=easyocr ^
    --hidden-import=paddleocr ^
    --hidden-import=yomitoku ^
    --hidden-import=PIL ^
    --hidden-import=PIL.Image ^
    --hidden-import=csv ^
    --hidden-import=dataclasses ^
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
    --collect-all=pytesseract ^
    --collect-all=easyocr ^
    image_entry_gui3OCR.py

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
    echo 注意事項:
    echo - OCR機能を使用する場合は、必要なOCRエンジンをインストールしてください
    echo - Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
    echo - EasyOCR/PaddleOCR/Yomitoku: Pythonパッケージとして別途インストール
    echo - 納税義務者情報.csv は実行ファイルと同じフォルダに配置してください
    echo.
    pause
) else (
    echo.
    echo ========================================
    echo ビルド失敗
    echo ========================================
    echo エラーログを確認してください。
    echo.
    pause
)
