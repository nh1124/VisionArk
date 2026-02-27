@echo off
:: VisionArk Native App — development startup script (Windows)
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set ROOT=%SCRIPT_DIR%..

echo === VisionArk Native Dev ===

:: Set defaults if not already set
if not defined VISIONARK_API_URL set VISIONARK_API_URL=http://localhost:8000
if not defined VISIONARK_TOKEN set VISIONARK_TOKEN=

:: Start daemon in a separate window (background)
echo [1/2] Starting daemon...
start "VisionArk Daemon" cmd /k "cd /d %ROOT%\daemon && set VISIONARK_API_URL=%VISIONARK_API_URL% && set VISIONARK_TOKEN=%VISIONARK_TOKEN% && cargo run"

:: Brief wait for daemon to start binding
timeout /t 2 /nobreak >nul

:: Install npm dependencies if node_modules is missing
echo [2/2] Starting Tauri desktop...
cd /d %ROOT%\desktop
if not exist node_modules (
    echo     node_modules not found, running npm install...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Aborting.
        exit /b 1
    )
)
cargo tauri dev

echo.
echo Daemon window is still running. Close it manually if needed.
endlocal
