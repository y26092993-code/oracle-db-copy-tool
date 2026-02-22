@echo off
setlocal

set REQUIREMENTS=requirements_pdf.txt
set WHEEL_DIR=wheelhouse

if not exist "%REQUIREMENTS%" (
    echo Error: %REQUIREMENTS% not found.
    exit /b 1
)

python -m pip download -r "%REQUIREMENTS%" -d "%WHEEL_DIR%"

if errorlevel 1 (
    echo Error: pip download failed.
    exit /b 1
)

echo Download complete. Copy the "%WHEEL_DIR%" folder and "%REQUIREMENTS%" to the offline PC.
endlocal
