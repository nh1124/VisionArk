@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Sync service_registry.base_url for service_name='lbs' from .env.core
REM Usage:
REM   infra\sync_lbs_base_url_from_env.bat
REM   infra\sync_lbs_base_url_from_env.bat C:\path\to\.env.core

set "ENV_FILE=%~1"
if "%ENV_FILE%"=="" set "ENV_FILE=%~dp0..\.env.core"

if not exist "%ENV_FILE%" (
  echo [ERROR] env file not found: %ENV_FILE%
  exit /b 1
)

for /f "usebackq tokens=1* delims==" %%A in ("%ENV_FILE%") do (
  if /I "%%A"=="POSTGRES_USER" set "POSTGRES_USER=%%B"
  if /I "%%A"=="POSTGRES_PASSWORD" set "POSTGRES_PASSWORD=%%B"
  if /I "%%A"=="POSTGRES_DB" set "POSTGRES_DB=%%B"
  if /I "%%A"=="LBS_SERVICE_URL" set "LBS_SERVICE_URL=%%B"
)

if not defined POSTGRES_USER set "POSTGRES_USER=atmos"
if not defined POSTGRES_PASSWORD set "POSTGRES_PASSWORD=atmos_secret"
if not defined POSTGRES_DB set "POSTGRES_DB=atmos"

if not defined LBS_SERVICE_URL (
  echo [ERROR] LBS_SERVICE_URL is empty in %ENV_FILE%
  exit /b 1
)

echo [INFO] Applying LBS base_url from %ENV_FILE%
echo [INFO] target URL: %LBS_SERVICE_URL%
echo [INFO] target DB : %POSTGRES_DB% (user=%POSTGRES_USER%)

docker exec -e PGPASSWORD=%POSTGRES_PASSWORD% atmos-db ^
  psql -U %POSTGRES_USER% -d %POSTGRES_DB% -v ON_ERROR_STOP=1 ^
  -c "UPDATE service_registry SET base_url='%LBS_SERVICE_URL%', updated_at=NOW() WHERE service_name='lbs';"
if errorlevel 1 exit /b 1

docker exec -e PGPASSWORD=%POSTGRES_PASSWORD% atmos-db ^
  psql -U %POSTGRES_USER% -d %POSTGRES_DB% -c "SELECT COUNT(*) AS lbs_rows, MIN(base_url) AS current_lbs_base_url FROM service_registry WHERE service_name='lbs';"
if errorlevel 1 exit /b 1

echo [INFO] Done.
exit /b 0

