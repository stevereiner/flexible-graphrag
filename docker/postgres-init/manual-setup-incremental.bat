@echo off
REM Manual setup script for flexible_graphrag_incremental database
REM Run this from Windows if you need to manually create the incremental database
REM (Not for Docker init - that uses the .sh script automatically)

echo ========================================
echo Incremental Database - Manual Setup
echo ========================================
echo.

REM Check if Docker is running
docker ps >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker is not running or not in PATH
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

REM Check if PostgreSQL container is running
docker ps --filter "name=flexible-graphrag-postgres" --format "{{.Names}}" | findstr "flexible-graphrag-postgres" >nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PostgreSQL container is not running
    echo.
    echo Please start the container with:
    echo   cd docker
    echo   docker-compose -f docker-compose.yaml -p flexible-graphrag up -d postgres-pgvector
    echo.
    pause
    exit /b 1
)

echo PostgreSQL container found. Proceeding...
echo.

REM Step 1: Create the database
echo Step 1: Creating database flexible_graphrag_incremental...
docker exec -i flexible-graphrag-postgres psql -U postgres -c "CREATE DATABASE flexible_graphrag_incremental;"

if %ERRORLEVEL% EQU 0 (
    echo   SUCCESS: Database created
) else (
    echo   Note: Database may already exist (this is OK)
)
echo.

REM Step 2: Apply the schema
echo Step 2: Applying schema from incremental_updates/schema.sql...
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental < "%~dp0..\..\flexible-graphrag\incremental_updates\schema.sql"

if %ERRORLEVEL% EQU 0 (
    echo   SUCCESS: Schema applied
) else (
    echo   ERROR: Failed to apply schema
    pause
    exit /b 1
)
echo.

REM Step 3: Verify
echo Step 3: Verifying tables...
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Database: flexible_graphrag_incremental
echo Tables: datasource_config, document_state
echo.
echo Connection string for .env file:
echo POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental
echo.
pause
