@echo off
title Pustika Audiobook - Backend Server
echo ===================================================
echo     Starting Pustika Backend Flask Server...
echo ===================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
)

if not exist "database.db" (
    echo Database not found. Initializing database...
    "%PYTHON_EXEC%" seed_data.py
    echo.
)

echo Starting Flask server at http://127.0.0.1:5000 ...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:5000"

"%PYTHON_EXEC%" app.py

pause
