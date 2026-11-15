@echo off
setlocal
cd /d "%~dp0.."
title Legacy Duplex Scanner

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Automatic Duplex Scanning for the first time...
    py -3 -m venv ".venv" 2>nul
    if errorlevel 1 (
        python -m venv ".venv"
        if errorlevel 1 goto :python_error
    )
)

".venv\Scripts\python.exe" -c "import pypdf" >nul 2>&1
if errorlevel 1 (
    echo Installing the PDF library (internet required on first run)...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :install_error
)

".venv\Scripts\python.exe" legacy\duplex_app.py
if errorlevel 1 (
    echo.
    echo The application exited with an error.
    pause
)
exit /b 0

:python_error
echo.
echo Python 3 is required. Install Python from https://www.python.org/downloads/
echo and select "Add Python to PATH" during installation.
pause
exit /b 1

:install_error
echo.
echo Could not install the PDF dependency. Check your internet connection.
pause
exit /b 1
