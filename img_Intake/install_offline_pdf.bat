@echo off
setlocal

set REQUIREMENTS=requirements_pdf.txt
set WHEEL_DIR=wheelhouse

if not exist "%REQUIREMENTS%" (
    echo Error: %REQUIREMENTS% not found.
    exit /b 1
)

if not exist "%WHEEL_DIR%" (
    echo Error: %WHEEL_DIR% folder not found.
    exit /b 1
)

python -m pip install --no-index --find-links "%WHEEL_DIR%" -r "%REQUIREMENTS%"

if errorlevel 1 (
    echo Error: offline install failed.
    exit /b 1
)

echo Offline install complete.
endlocal
