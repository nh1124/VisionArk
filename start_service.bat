@echo off
REM AI TaskManagement OS - Docker Start Script

echo ========================================
echo AI TaskManagement OS - Docker Mode
echo ========================================
echo.

echo [1/3] Checking Docker installation...
docker --version
if errorlevel 1 (
    echo ERROR: Docker not found. Please install Docker Desktop
    pause
    exit /b 1
)

echo [2/3] Building containers (this may take a while on first run)...
docker-compose build --no-cache
if errorlevel 1 (
    echo ERROR: Failed to build containers
    pause
    exit /b 1
)

echo [3/3] Starting services...
echo.
echo Services will be available at:
echo   - Frontend: http://localhost:3000
echo   - Backend:  http://localhost:8000
echo   - Database: localhost:5432
echo.
echo Press Ctrl+C to stop all services
echo.

docker-compose up
