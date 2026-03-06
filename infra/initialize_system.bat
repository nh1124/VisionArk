@echo off
setlocal enabledelayedexpansion

set "CORE_ENV_FILE=../.env.core"
set "EDGE_ENV_FILE=../.env.edge"
if not exist ".env.core" (
    echo ERROR: .env.core not found.
    exit /b 1
)
if not exist ".env.edge" (
    echo ERROR: .env.edge not found.
    exit /b 1
)

echo ========================================
echo VISION ARK - System Initialization
echo [WARNING] This will wipe ALL user data and registrations!
echo ========================================
echo.

set /p confirm="Are you sure you want to proceed? (y/n): "
if /i "%confirm%" neq "y" (
    echo Initialization cancelled.
    exit /b 0
)

echo.
echo [1/4] Stopping and removing Docker containers and volumes...
docker-compose -f infra/docker-compose.yml down -v
if errorlevel 1 (
    echo ERROR: Failed to stop containers.
    pause
    exit /b 1
)

echo.
echo [2/4] Wiping host data directories...
echo Cleaning data/...
if exist data (
    powershell -Command "Remove-Item -Path 'data\*' -Recurse -Force -ErrorAction SilentlyContinue"
)

echo.
echo [3/4] Rebuilding and starting services...
docker-compose -f infra/docker-compose.yml --profile all up -d --build
if errorlevel 1 (
    echo ERROR: Failed to restart services.
    pause
    exit /b 1
)

echo.
echo [4/4] Verification...
echo.
echo System has been initialized.
echo All test data, user accounts, and directories have been cleared.
echo The global system prompt will be re-populated from source code on next registration.
echo.
echo Done!
pause
