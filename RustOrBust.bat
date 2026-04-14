@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_EXE=py -3"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo Launching RustOrBust...
%PYTHON_EXE% UI\rust_portal_gui.py
if errorlevel 1 (
    echo.
    echo RustOrBust failed to launch.
    echo Run install_windows.bat first, or check that Python and Tkinter are installed.
    echo.
    pause
)

endlocal
