@echo off
setlocal enabledelayedexpansion
:: VisionArk System Import
:: Validates integrity, restores PostgreSQL and data\ from an export archive.
::
:: Usage: system_import.bat [--dry-run] <archive.tar.gz>
::   --dry-run   Validate archive and print restore plan without applying any changes

:: ── Resolve paths ────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%i in ("%SCRIPT_DIR%") do set "PROJECT_ROOT=%%~dpi"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "COMPOSE_FILE=%SCRIPT_DIR%\docker-compose.yml"

:: ── Defaults ─────────────────────────────────────────────────────────────────
set "DRY_RUN=0"
set "ARCHIVE="

:: ── Parse arguments ───────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--dry-run" ( set "DRY_RUN=1" & shift & goto :parse_args )
if /i "%~1"=="-h"        goto :usage
if /i "%~1"=="--help"    goto :usage
if "!ARCHIVE!"=="" ( set "ARCHIVE=%~f1" & shift & goto :parse_args )
echo Unknown option: %~1 >&2
exit /b 1
:usage
echo Usage: %~nx0 [--dry-run] ^<archive.tar.gz^>
echo   --dry-run   Validate and preview without applying changes
exit /b 0
:done_args

if "!ARCHIVE!"=="" (
    echo ERROR: No archive specified. >&2
    goto :usage
)
if not exist "!ARCHIVE!" (
    echo ERROR: Archive not found: !ARCHIVE! >&2
    exit /b 1
)

:: ── Load .env (non-overriding) ────────────────────────────────────────────────
set "ENV_FILE=%PROJECT_ROOT%\.env"
if exist "%ENV_FILE%" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
        set "_k=%%a"
        if not "!_k:~0,1!"=="#" if not "%%a"=="" (
            if not defined %%a set "%%a=%%b"
        )
    )
)
if not defined POSTGRES_USER set "POSTGRES_USER=atmos"
if not defined POSTGRES_DB   set "POSTGRES_DB=atmos"
set "PG_USER=%POSTGRES_USER%"
set "PG_DB=%POSTGRES_DB%"
set "DB_CONTAINER=atmos-db"

echo ========================================
echo VISION ARK - System Import
if "%DRY_RUN%"=="1" echo [DRY RUN MODE -- no changes will be applied]
echo Archive : !ARCHIVE!
echo ========================================
echo.

:: ── Work directory ────────────────────────────────────────────────────────────
for /f "tokens=*" %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TIMESTAMP=%%t"
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "[System.IO.Path]::GetTempPath().TrimEnd('\')"') do set "TEMP_BASE=%%d"
set "WORK_DIR=%TEMP_BASE%\va_import_%TIMESTAMP%"
mkdir "%WORK_DIR%"

:: ── Step 1: Extract ───────────────────────────────────────────────────────────
echo [1/5] Extracting archive...
tar -xzf "!ARCHIVE!" -C "%WORK_DIR%"
if errorlevel 1 ( echo ERROR: Failed to extract archive. >&2 & goto :cleanup_fail )

set "BACKUP_DIR="
for /d %%d in ("%WORK_DIR%\*") do (
    if "!BACKUP_DIR!"=="" set "BACKUP_DIR=%%d"
)
if "!BACKUP_DIR!"=="" (
    echo ERROR: Corrupt archive -- no top-level directory found. >&2
    goto :cleanup_fail
)
for %%d in ("!BACKUP_DIR!") do echo       Found: %%~nxd

:: ── Step 2: Validate manifest.json ───────────────────────────────────────────
if not exist "!BACKUP_DIR!\manifest.json" (
    echo ERROR: manifest.json not found in archive. >&2
    goto :cleanup_fail
)

echo [2/5] Validating manifest.json...

:: Write validation Python script to temp file
set "PY=%WORK_DIR%\validate.py"
echo import json, sys > "%PY%"
echo with open(sys.argv[1]) as f: m = json.load(f) >> "%PY%"
echo required = ['schema_version', 'db_type', 'db_name', 'db_user', 'files'] >> "%PY%"
echo missing = [k for k in required if k not in m] >> "%PY%"
echo if missing: sys.exit('ERROR: manifest.json missing fields: ' + str(missing)) >> "%PY%"
echo if m['schema_version'] != '1': sys.exit('ERROR: Unsupported schema_version: ' + str(m['schema_version'])) >> "%PY%"
echo if m['db_type'] != 'postgresql': sys.exit('ERROR: Unsupported db_type: ' + str(m['db_type'])) >> "%PY%"
echo print('      App version :', m.get('app_version', 'unknown')) >> "%PY%"
echo print('      Created at  :', m.get('created_at', 'unknown')) >> "%PY%"
echo print('      DB name     :', m['db_name']) >> "%PY%"
echo print('      Has data    :', m.get('has_data_dir', False)) >> "%PY%"
echo print('      Files       :', list(m['files'].keys())) >> "%PY%"

python "%PY%" "!BACKUP_DIR!\manifest.json"
if errorlevel 1 goto :cleanup_fail

:: ── Step 3: Verify checksums ──────────────────────────────────────────────────
echo [3/5] Verifying checksums...

if not exist "!BACKUP_DIR!\checksums.sha256" (
    echo       WARNING: checksums.sha256 not found -- skipping verification.
    goto :skip_checksum
)

:: Write checksum verification Python script
set "PY=%WORK_DIR%\verify.py"
echo import sys, os, hashlib >> "%PY%"
echo backup_dir = sys.argv[1] >> "%PY%"
echo cs_path = os.path.join(backup_dir, 'checksums.sha256') >> "%PY%"
echo errors = [] >> "%PY%"
echo with open(cs_path) as f: lines = f.readlines() >> "%PY%"
echo for line in lines: >> "%PY%"
echo  parts = line.strip().split(None, 1) >> "%PY%"
echo  if len(parts) != 2: continue >> "%PY%"
echo  expected, fname = parts[0].lower(), parts[1] >> "%PY%"
echo  fpath = os.path.join(backup_dir, fname) >> "%PY%"
echo  if not os.path.exists(fpath): errors.append('MISSING: ' + fname); continue >> "%PY%"
echo  h = hashlib.sha256() >> "%PY%"
echo  fp = open(fpath, 'rb') >> "%PY%"
echo  [h.update(c) for c in iter(lambda: fp.read(65536), b'')] >> "%PY%"
echo  fp.close() >> "%PY%"
echo  actual = h.hexdigest().lower() >> "%PY%"
echo  if actual != expected: errors.append('MISMATCH: ' + fname) >> "%PY%"
echo  else: print('      OK:', fname) >> "%PY%"
echo if errors: >> "%PY%"
echo  [print('ERROR:', e, file=sys.stderr) for e in errors] >> "%PY%"
echo  sys.exit(1) >> "%PY%"
echo print('      All checksums OK.') >> "%PY%"

python "%PY%" "!BACKUP_DIR!"
if errorlevel 1 goto :cleanup_fail

:skip_checksum

:: ── Read manifest values into variables ──────────────────────────────────────
set "PY=%WORK_DIR%\read_manifest.py"
echo import json, sys > "%PY%"
echo m = json.load(open(sys.argv[1])) >> "%PY%"
echo print(m['db_name']) >> "%PY%"
echo print('true' if m.get('has_data_dir') else 'false') >> "%PY%"

set "MANIFEST_DB_NAME="
set "HAS_DATA="
for /f "tokens=*" %%v in ('python "%PY%" "!BACKUP_DIR!\manifest.json"') do (
    if "!MANIFEST_DB_NAME!"=="" ( set "MANIFEST_DB_NAME=%%v" ) else ( set "HAS_DATA=%%v" )
)

:: ── Step 4: Show restore plan ─────────────────────────────────────────────────
echo [4/5] Restore plan:
echo       1. Stop containers  : backend, worker
echo       2. Terminate active DB connections
echo       3. Restore PostgreSQL DB '!MANIFEST_DB_NAME!' to container '%DB_CONTAINER%'
if "!HAS_DATA!"=="true" echo       4. Replace data\ directory from archive
echo       5. Restart containers: backend, worker

if "%DRY_RUN%"=="1" (
    if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
    echo.
    echo ========================================
    echo DRY RUN complete -- no changes applied.
    echo ========================================
    exit /b 0
)

:: ── Step 5: Apply restore ─────────────────────────────────────────────────────
echo.
set /p "confirm=[5/5] Apply restore? This will OVERWRITE the current DB and data. (y/n): "
if /i "!confirm!" neq "y" (
    echo Import cancelled.
    goto :cleanup_ok
)

docker info >nul 2>&1
if errorlevel 1 ( echo ERROR: Docker is not running. >&2 & goto :cleanup_fail )

set "DB_RUNNING=0"
for /f "tokens=*" %%n in ('docker ps --format "{{.Names}}" 2^>nul') do (
    if /i "%%n"=="%DB_CONTAINER%" set "DB_RUNNING=1"
)
if "!DB_RUNNING!"=="0" (
    echo ERROR: Container '%DB_CONTAINER%' is not running. >&2
    goto :cleanup_fail
)

echo.
echo Stopping backend and worker...
docker-compose -f "%COMPOSE_FILE%" stop backend worker 2>nul

echo Terminating active DB connections...
docker exec %DB_CONTAINER% psql -U %PG_USER% -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '%PG_DB%' AND pid <> pg_backend_pid();" >nul 2>&1

echo Restoring database...
docker exec -i %DB_CONTAINER% psql -U %PG_USER% -d %PG_DB% < "!BACKUP_DIR!\db_dump.sql"
if errorlevel 1 ( echo ERROR: DB restore failed. >&2 & goto :restart_and_fail )
echo   DB restore complete.

if "!HAS_DATA!"=="true" (
    if exist "!BACKUP_DIR!\data.tar.gz" (
        echo Restoring data\...
        if exist "%PROJECT_ROOT%\data" rmdir /s /q "%PROJECT_ROOT%\data"
        tar -xzf "!BACKUP_DIR!\data.tar.gz" -C "%PROJECT_ROOT%"
        if errorlevel 1 ( echo ERROR: data\ restore failed. >&2 & goto :restart_and_fail )
        echo   data\ restore complete.
    )
)

echo Restarting backend and worker...
docker-compose -f "%COMPOSE_FILE%" start backend worker 2>nul || docker-compose -f "%COMPOSE_FILE%" up -d backend worker

:cleanup_ok
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
echo.
echo ========================================
echo Import complete!
echo ========================================
exit /b 0

:restart_and_fail
echo Attempting to restart containers after failure...
docker-compose -f "%COMPOSE_FILE%" start backend worker 2>nul
:cleanup_fail
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
exit /b 1
