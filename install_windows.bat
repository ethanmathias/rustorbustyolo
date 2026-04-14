@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY_LAUNCHER=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY_LAUNCHER=python"
    ) else (
        echo Python 3 was not found.
        echo Install Python 3 for Windows and make sure it is on PATH, then rerun this script.
        pause
        exit /b 1
    )
)

echo Creating virtual environment...
%PY_LAUNCHER% -m venv .venv
if errorlevel 1 (
    echo Failed to create .venv
    pause
    exit /b 1
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

echo Installing RustOrBust UI dependencies...
".venv\Scripts\python.exe" -m pip install -r UI\requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

where tesseract >nul 2>nul
if errorlevel 1 (
    echo.
    echo Note: the Python OCR package was installed, but the Tesseract OCR executable was not found on PATH.
    echo Scale-label OCR will stay disabled until Tesseract OCR is installed.
    echo You can install it from:
    echo   https://github.com/UB-Mannheim/tesseract/wiki
)

echo.
echo Setup complete.
echo Run RustOrBust.bat to launch the UI.
echo.
pause
endlocal
