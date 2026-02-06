@echo off
REM Trigger immediate sync for all datasources with auto-sync enabled
REM Usage: 
REM   sync-now.bat
REM   sync-now.bat alfresco_12345
REM   sync-now.bat alfresco_12345 http://localhost:8000

setlocal

set CONFIG_ID=%1
set API_URL=%2

if "%API_URL%"=="" set API_URL=http://localhost:8000

if "%CONFIG_ID%"=="" (
    echo Triggering immediate sync for all datasources with auto-sync enabled...
    set ENDPOINT=%API_URL%/api/datasource/sync-now-all
) else (
    echo Triggering immediate sync for datasource: %CONFIG_ID%...
    set ENDPOINT=%API_URL%/api/datasource/%CONFIG_ID%/sync-now
)

curl -s -X POST "%ENDPOINT%" > temp_response.json

if %ERRORLEVEL% equ 0 (
    echo SUCCESS: Sync triggered.
    type temp_response.json
    del temp_response.json
) else (
    echo ERROR: Failed to trigger sync
    del temp_response.json
    exit /b 1
)
