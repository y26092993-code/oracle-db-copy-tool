@echo off
chcp 65001 >nul

echo ========================================
echo EasyOCR Build Script
echo ========================================
echo.
echo Target: image_entry_gui3OCR.py
echo Spec: ImageEntryGUI.spec
echo.

call .venv\Scripts\activate.bat
pyinstaller --clean ImageEntryGUI.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Build Complete
    echo ========================================
    echo Output: dist\ImageEntryGUI.exe
    if exist dist\ImageEntryGUI.exe (
        for %%A in (dist\ImageEntryGUI.exe) do (
            set /A sizeMB=%%~zA/1048576
            echo Size: !sizeMB! MB
        )
    )
) else (
    echo.
    echo ========================================
    echo Build Failed
    echo ========================================
)

pause
