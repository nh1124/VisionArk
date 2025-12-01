@echo off
REM Quick start script for frontend

echo ========================================
echo AI TaskManagement OS - Frontend
echo ========================================
echo.

echo Starting Next.js development server...
echo Frontend will be available at http://localhost:3000
echo.
echo Make sure backend is running at http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo.

cd app\frontend
npm run dev
