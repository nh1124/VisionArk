@echo off
REM Quick start script for frontend (local development)

echo ========================================
echo AI TaskManagement OS - Frontend
echo ========================================
echo.
echo Mode: Local Development
echo For Docker mode, use start_docker.bat
echo.

set FRONTEND_PORT=3000
set BACKEND_PORT=8000
if exist .env (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if "%%a"=="FRONTEND_PORT" set FRONTEND_PORT=%%b
        if "%%a"=="BACKEND_PORT" set BACKEND_PORT=%%b
    )
)

echo Starting Next.js development server...
echo.
echo Frontend: http://localhost:%FRONTEND_PORT%
echo Backend:  http://localhost:%BACKEND_PORT%
echo.
echo Make sure backend is running...
echo.
echo Press Ctrl+C to stop the server
echo.

cd app\frontend
npm run dev -- -p %FRONTEND_PORT%
