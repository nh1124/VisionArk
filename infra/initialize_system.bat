@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "COMPOSE_FILE=%SCRIPT_DIR%docker-compose.yml"
set "CORE_ENV_PATH=%PROJECT_ROOT%\.env.core"
set "EDGE_ENV_PATH=%PROJECT_ROOT%\.env.edge"

if not exist "%CORE_ENV_PATH%" (
    echo ERROR: %CORE_ENV_PATH% not found.
    exit /b 1
)
if not exist "%EDGE_ENV_PATH%" (
    echo ERROR: %EDGE_ENV_PATH% not found.
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
echo [1/6] Stopping and removing Docker containers and volumes...
docker-compose -f "%COMPOSE_FILE%" --profile all down -v --remove-orphans
if errorlevel 1 (
    echo ERROR: Failed to stop containers.
    pause
    exit /b 1
)

echo.
echo [2/6] Removing residual PostgreSQL volumes...
for /f "delims=" %%V in ('docker volume ls --format "{{.Name}}" ^| findstr /R /C:"postgres_data"') do (
    echo Removing volume: %%V
    docker volume rm -f %%V >nul 2>&1
)

echo.
echo [3/6] Wiping host data directories...
if exist "%PROJECT_ROOT%\data" (
    echo Cleaning %PROJECT_ROOT%\data\ ...
    powershell -NoProfile -Command "Remove-Item -Path '%PROJECT_ROOT%\data\*' -Recurse -Force -ErrorAction SilentlyContinue"
)

if exist "%PROJECT_ROOT%\logs" (
    echo Cleaning %PROJECT_ROOT%\logs\ ...
    powershell -NoProfile -Command "Remove-Item -Path '%PROJECT_ROOT%\logs\*' -Recurse -Force -ErrorAction SilentlyContinue"
)

echo.
echo [4/6] Migration mode...
echo _run_migrations is now a placeholder (no legacy migration replay).

echo.
echo [5/6] Rebuilding and starting services...
docker-compose -f "%COMPOSE_FILE%" --profile all up -d --build
if errorlevel 1 (
    echo ERROR: Failed to restart services.
    pause
    exit /b 1
)

echo.
echo [6/6] Verification...
docker-compose -f "%COMPOSE_FILE%" ps
if errorlevel 1 (
    echo WARNING: Verification command failed.
)
echo.
echo System has been initialized.
echo All test data, user accounts, and directories have been cleared.
echo The global system prompt will be re-populated from source code on next registration.
echo.
echo Done!
pause
