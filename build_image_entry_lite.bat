@echo off
chcp 65001 >nul
REM Image Entry GUI - 超軽量化ビルド
REM OCRエンジンは外部依存として実行時にロード

echo ========================================
echo Image Entry GUI - 軽量化ビルド
echo ========================================
echo.

REM 仮想環境のPyInstallerを使用
set PYINSTALLER=C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe

echo 【軽量化の方針】
echo - OCRエンジンを外部依存化
echo - 不要な機械学習ライブラリを除外
echo - UPX圧縮を適用
echo - シンボル情報を削除
echo.
echo これにより、257MB → 30-50MB程度に削減予定
echo.
pause

echo 既存のビルドファイルをクリーンアップ...
if exist build\ImageEntryGUI rd /s /q build\ImageEntryGUI
if exist dist\ImageEntryGUI.exe del dist\ImageEntryGUI.exe

echo.
echo 軽量化ビルド実行中...
echo.

%PYINSTALLER% ^
    --name="ImageEntryGUI" ^
    --onefile ^
    --windowed ^
    --optimize=2 ^
    --strip ^
    --upx-dir="C:\upx" ^
    --noupx ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=csv ^
    --hidden-import=dataclasses ^
    --exclude-module=torch ^
    --exclude-module=tensorflow ^
    --exclude-module=numpy ^
    --exclude-module=scipy ^
    --exclude-module=sklearn ^
    --exclude-module=cv2 ^
    --exclude-module=matplotlib ^
    --exclude-module=pandas ^
    --exclude-module=openpyxl ^
    --exclude-module=requests ^
    --exclude-module=urllib3 ^
    --exclude-module=IPython ^
    --exclude-module=jupyter ^
    --exclude-module=notebook ^
    --exclude-module=pytest ^
    --exclude-module=unittest ^
    --exclude-module=setuptools ^
    --exclude-module=wheel ^
    --exclude-module=pip ^
    --exclude-module=tkinter ^
    --exclude-module=PyQt5 ^
    --exclude-module=PyQt6 ^
    --exclude-module=pytesseract ^
    --exclude-module=easyocr ^
    --exclude-module=paddleocr ^
    --exclude-module=yomitoku ^
    --exclude-module=PIL ^
    --exclude-module=Pillow ^
    --exclude-module=email ^
    --exclude-module=html ^
    --exclude-module=http ^
    --exclude-module=xml ^
    --exclude-module=sqlite3 ^
    --exclude-module=multiprocessing ^
    image_entry_gui3OCR.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo ビルド成功！
    echo ========================================
    echo.
    
    REM ファイルサイズを比較表示
    if exist dist\ImageEntryGUI.exe (
        for %%A in (dist\ImageEntryGUI.exe) do (
            set size=%%~zA
            set /A sizeMB=%%~zA/1048576
            echo 新しいサイズ: !sizeMB! MB
        )
        
        echo.
        echo 【重要】軽量化の影響:
        echo - OCR機能を使用するには、別途OCRエンジンのインストールが必要です
        echo - pytesseract: pip install pytesseract
        echo - easyocr: pip install easyocr
        echo - paddleocr: pip install paddleocr
        echo - yomitoku: pip install yomitoku
        echo - Pillow: pip install Pillow
        echo.
        echo 【配布方法】
        echo 1. EXEファイル単体配布（最軽量）
        echo 2. Pythonインストール不要
        echo 3. OCR使用時のみ追加パッケージが必要
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
