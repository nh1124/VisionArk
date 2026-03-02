@echo off
:: VisionArk Native App — development startup script (Windows)
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set ROOT=%SCRIPT_DIR%..

echo === VisionArk Native Dev ===

:: Build daemon sidecar
echo [1/2] Building daemon sidecar...
cd /d %ROOT%\daemon
cargo build
if errorlevel 1 (
    echo [ERROR] Failed to build daemon.
    exit /b 1
)

:: Ensure binaries dir exists and copy
if not exist "%ROOT%\desktop\binaries" mkdir "%ROOT%\desktop\binaries"
copy /Y "%ROOT%\target\debug\visionark-daemon.exe" "%ROOT%\desktop\binaries\visionark-daemon-x86_64-pc-windows-msvc.exe" >nul

:: Start Tauri desktop
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
endlocal
