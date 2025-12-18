@echo off
REM Quick start script for AI TaskManagement OS backend

echo ========================================
echo AI TaskManagement OS - Backend Server
echo ========================================
echo.

echo [1/3] Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo [2/3] Installing dependencies...
cd app\backend
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

set BACKEND_PORT=8000
if exist .env (
    for /f "tokens=1,2 delims==" %%a in (.env) do (
        if "%%a"=="BACKEND_PORT" set BACKEND_PORT=%%b
    )
)

echo [3/3] Starting FastAPI server...
echo.
echo Server will start at http://localhost:%BACKEND_PORT%
echo API docs available at http://localhost:%BACKEND_PORT%/docs
echo.
echo Press Ctrl+C to stop the server
echo.

python main.py
