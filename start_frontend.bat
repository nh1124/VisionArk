@echo off
REM Quick start script for frontend

echo ========================================
echo AI TaskManagement OS - Frontend
echo ========================================
echo.

echo Starting Next.js development server...
set FRONTEND_PORT=3000
set BACKEND_PORT=8000
if exist .env (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if "%%a"=="FRONTEND_PORT" set FRONTEND_PORT=%%b
        if "%%a"=="BACKEND_PORT" set BACKEND_PORT=%%b
    )
)
echo Frontend will be available at http://localhost:%FRONTEND_PORT%
echo Using backend at http://localhost:%BACKEND_PORT%
echo.
echo Make sure backend is running...
echo.
echo Press Ctrl+C to stop the server
echo.

cd app\frontend
npm run dev -- -p %FRONTEND_PORT%
