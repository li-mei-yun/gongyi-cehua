@echo off
setlocal
cd /d "%~dp0"
title Process Planning Assistant

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    echo Please install Python or add it to PATH.
    echo.
    pause
    exit /b 1
)

python -c "import flask, markdown, requests" >nul 2>nul
if errorlevel 1 (
    echo Required Python packages are missing.
    echo Run: python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Starting Process Planning Assistant...
echo Browser address: http://127.0.0.1:8501
echo Keep this window open while using the application.
echo.
python -u app.py

set APP_EXIT_CODE=%errorlevel%
echo.
echo Application stopped. Exit code: %APP_EXIT_CODE%
echo Press any key to close this window.
pause >nul
exit /b %APP_EXIT_CODE%
