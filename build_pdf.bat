@echo off
setlocal

if not exist "PDFtoTIFF.spec" (
    echo Error: PDFtoTIFF.spec not found.
    exit /b 1
)

pyinstaller PDFtoTIFF.spec --clean

if errorlevel 1 (
    echo Error: build failed.
    exit /b 1
)

echo Build complete. Output: dist\PDFtoTIFF.exe
endlocal
