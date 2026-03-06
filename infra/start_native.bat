@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "NATIVE_ROOT=%SCRIPT_DIR%\..\core\native"

echo === VisionArk Native Dev ===
echo [INFO] Daemon startup is managed by desktop (Tauri command), not this script.

echo [1/2] Building daemon sidecar...
cd /d "%NATIVE_ROOT%\daemon"
cargo build
if errorlevel 1 (
    echo [ERROR] Failed to build daemon.
    exit /b 1
)

if not exist "%NATIVE_ROOT%\desktop\binaries" mkdir "%NATIVE_ROOT%\desktop\binaries"
copy /Y "%NATIVE_ROOT%\target\debug\visionark-daemon.exe" "%NATIVE_ROOT%\desktop\binaries\visionark-daemon-x86_64-pc-windows-msvc.exe" >nul

echo [2/2] Starting Tauri desktop...
cd /d "%NATIVE_ROOT%\desktop"
if not exist node_modules (
    echo     node_modules not found, running npm install...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Aborting.
        exit /b 1
    )
)
cargo tauri dev

endlocal
