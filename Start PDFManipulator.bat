@echo off
setlocal
cd /d "%~dp0"
title PDFManipulator

rem Prefer the packaged native Windows application if it has been built.
if exist "dist\PDFManipulator.exe" (
    start "" "%~dp0dist\PDFManipulator.exe"
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    py -3 -m venv ".venv" 2>nul
    if errorlevel 1 (
        python -m venv ".venv"
        if errorlevel 1 goto :python_error
    )
)

".venv\Scripts\python.exe" -c "import pypdf, fitz, customtkinter, PIL, tkinterdnd2, cryptography" >nul 2>&1
if errorlevel 1 (
    echo Installing local PDFManipulator libraries...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :install_error
)

".venv\Scripts\python.exe" launch.py
if errorlevel 1 (
    echo.
    echo The app exited with an error.
    pause
)
exit /b 0

:python_error
echo Python 3.11 or later is required.
pause
exit /b 1

:install_error
echo Could not install dependencies. Check the internet connection.
pause
exit /b 1
