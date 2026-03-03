@echo off
setlocal enabledelayedexpansion
:: VisionArk System Export
:: Dumps PostgreSQL, archives data/, and bundles a manifest + checksums.
::
:: Usage: system_export.bat [--output-dir DIR] [--no-data]
::   --output-dir DIR   Destination for the .tar.gz archive (default: .\exports\)
::   --no-data          Skip the data\ directory archive

:: ── Resolve paths ────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%i in ("%SCRIPT_DIR%") do set "PROJECT_ROOT=%%~dpi"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "COMPOSE_FILE=%SCRIPT_DIR%\docker-compose.yml"

:: ── Defaults ─────────────────────────────────────────────────────────────────
set "OUTPUT_DIR=%PROJECT_ROOT%\exports"
set "INCLUDE_DATA=1"

:: ── Parse arguments ───────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--output-dir" ( set "OUTPUT_DIR=%~2" & shift & shift & goto :parse_args )
if /i "%~1"=="--no-data"    ( set "INCLUDE_DATA=0" & shift & goto :parse_args )
if /i "%~1"=="-h"           goto :usage
if /i "%~1"=="--help"       goto :usage
echo Unknown option: %~1 >&2
exit /b 1
:usage
echo Usage: %~nx0 [--output-dir DIR] [--no-data]
echo   --output-dir DIR   Write archive here (default: .\exports\)
echo   --no-data          Skip archiving the data\ directory
exit /b 0
:done_args

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

:: ── Timestamp & names ─────────────────────────────────────────────────────────
for /f "tokens=*" %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TIMESTAMP=%%t"
set "BACKUP_NAME=visionark_backup_%TIMESTAMP%"
set "APP_VERSION=unknown"
if exist "%PROJECT_ROOT%\VERSION" set /p APP_VERSION=<"%PROJECT_ROOT%\VERSION"

echo ========================================
echo VISION ARK - System Export
echo Archive : %BACKUP_NAME%.tar.gz
echo Output  : %OUTPUT_DIR%
echo ========================================
echo.

:: ── Preflight ─────────────────────────────────────────────────────────────────
docker info >nul 2>&1
if errorlevel 1 ( echo ERROR: Docker is not running. >&2 & exit /b 1 )

set "DB_RUNNING=0"
for /f "tokens=*" %%n in ('docker ps --format "{{.Names}}" 2^>nul') do (
    if /i "%%n"=="%DB_CONTAINER%" set "DB_RUNNING=1"
)
if "!DB_RUNNING!"=="0" (
    echo ERROR: Container '%DB_CONTAINER%' is not running. Start services first. >&2
    echo   Running containers:
    docker ps --format "  {{.Names}}  ({{.Status}})"
    exit /b 1
)

:: ── Work directory ────────────────────────────────────────────────────────────
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "[System.IO.Path]::GetTempPath().TrimEnd('\')"') do set "TEMP_BASE=%%d"
set "WORK_DIR=%TEMP_BASE%\va_export_%TIMESTAMP%"
set "STAGE=%WORK_DIR%\%BACKUP_NAME%"
mkdir "%STAGE%"

:: ── Step 1: PostgreSQL dump ───────────────────────────────────────────────────
echo [1/4] Dumping PostgreSQL database '%PG_DB%'...
docker exec %DB_CONTAINER% pg_dump -U %PG_USER% -d %PG_DB% --format=plain --clean --if-exists > "%STAGE%\db_dump.sql"
if errorlevel 1 ( echo ERROR: pg_dump failed. >&2 & goto :cleanup_fail )
for /f "tokens=*" %%s in ('powershell -NoProfile -Command "(Get-Item '%STAGE%\db_dump.sql').Length"') do set "DB_SIZE=%%s"
echo       OK  (%DB_SIZE% bytes)

:: ── Step 2: data\ directory ───────────────────────────────────────────────────
set "DATA_SIZE=0"
if "%INCLUDE_DATA%"=="1" (
    if exist "%PROJECT_ROOT%\data" (
        echo [2/4] Archiving data\...
        tar -czf "!STAGE!\data.tar.gz" -C "%PROJECT_ROOT%" data
        if errorlevel 1 ( echo ERROR: tar failed for data\. >&2 & goto :cleanup_fail )
        for /f "tokens=*" %%s in ('powershell -NoProfile -Command "(Get-Item '!STAGE!\data.tar.gz').Length"') do set "DATA_SIZE=%%s"
        echo       OK  ^(!DATA_SIZE! bytes^)
    ) else (
        echo [2/4] data\ not found -- skipping.
        set "INCLUDE_DATA=0"
    )
) else (
    echo [2/4] --no-data specified -- skipping.
)

:: ── Step 3: SHA-256 checksums ─────────────────────────────────────────────────
echo [3/4] Computing SHA-256 checksums...

:: Compute DB hash (always)
for /f "tokens=*" %%h in ('powershell -NoProfile -Command "(Get-FileHash '%STAGE%\db_dump.sql' -Algorithm SHA256).Hash.ToLower()"') do set "DB_HASH=%%h"

:: Compute data hash if the archive was created
set "DATA_HASH="
if exist "%STAGE%\data.tar.gz" (
    for /f "tokens=*" %%h in ('powershell -NoProfile -Command "(Get-FileHash '!STAGE!\data.tar.gz' -Algorithm SHA256).Hash.ToLower()"') do set "DATA_HASH=%%h"
)

:: Write checksums file (outside blocks so %VAR% expansion is current)
echo %DB_HASH%  db_dump.sql> "%STAGE%\checksums.sha256"
if not "%DATA_HASH%"=="" (
    echo %DATA_HASH%  data.tar.gz>> "%STAGE%\checksums.sha256"
)
type "%STAGE%\checksums.sha256"

:: ── Step 4: manifest.json ─────────────────────────────────────────────────────
echo [4/4] Writing manifest.json...

:: Get UTC timestamp for manifest
for /f "tokens=*" %%t in ('powershell -NoProfile -Command "(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')"') do set "CREATED_AT=%%t"

:: Write a flat Python script to temp file (no indentation = no CMD escaping issues)
set "PY=%WORK_DIR%\gm.py"
echo import json,os,sys > "%PY%"
echo s,av,dn,du,dc,cat = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6] >> "%PY%"
echo cp = os.path.join(s, 'checksums.sha256') >> "%PY%"
echo cs = {} >> "%PY%"
echo cs.update({p[1]: p[0] for l in (open(cp).readlines() if os.path.exists(cp) else []) for p in [l.strip().split(None, 1)] if len(p) == 2}) >> "%PY%"
echo files = {n: {'size_bytes': os.path.getsize(os.path.join(s, n)), 'sha256': cs.get(n, '')} for n in ['db_dump.sql', 'data.tar.gz'] if os.path.exists(os.path.join(s, n))} >> "%PY%"
echo m = {'schema_version': '1', 'app_version': av, 'created_at': cat, 'db_type': 'postgresql', 'db_name': dn, 'db_user': du, 'db_container': dc, 'has_data_dir': 'data.tar.gz' in files, 'files': files} >> "%PY%"
echo print(json.dumps(m, indent=2)) >> "%PY%"

python "%PY%" "%STAGE%" "%APP_VERSION%" "%PG_DB%" "%PG_USER%" "%DB_CONTAINER%" "%CREATED_AT%" > "%STAGE%\manifest.json"
if errorlevel 1 ( echo ERROR: manifest generation failed. >&2 & goto :cleanup_fail )
type "%STAGE%\manifest.json"

:: ── Bundle ────────────────────────────────────────────────────────────────────
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
set "ARCHIVE=%OUTPUT_DIR%\%BACKUP_NAME%.tar.gz"
echo.
echo Bundling archive...
tar -czf "%ARCHIVE%" -C "%WORK_DIR%" "%BACKUP_NAME%"
if errorlevel 1 ( echo ERROR: bundling failed. >&2 & goto :cleanup_fail )
rmdir /s /q "%WORK_DIR%"

for /f "tokens=*" %%s in ('powershell -NoProfile -Command "'{0:N0} KB' -f ((Get-Item '%ARCHIVE%').Length / 1KB)"') do set "ARCHIVE_SIZE=%%s"
echo.
echo ========================================
echo Export complete!
echo Archive : %ARCHIVE%
echo Size    : %ARCHIVE_SIZE%
echo ========================================
exit /b 0

:cleanup_fail
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
exit /b 1
