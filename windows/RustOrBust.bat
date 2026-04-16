@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

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
    echo Run windows\install_windows.bat first, or check that Python and Tkinter are installed.
    echo.
    pause
)

endlocal
