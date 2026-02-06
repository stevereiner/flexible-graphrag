@echo off
REM Set refresh interval for all datasources
REM Usage: 
REM   set-refresh-interval.bat 120
REM   set-refresh-interval.bat 120 http://localhost:8000

setlocal

set SECONDS=%1
set API_URL=%2

if "%SECONDS%"=="" set SECONDS=60
if "%API_URL%"=="" set API_URL=http://localhost:8000

echo Setting refresh interval to %SECONDS% seconds for all datasources...

curl -s -X POST "%API_URL%/api/datasource/update-all-refresh-intervals?seconds=%SECONDS%" > temp_response.json

if %ERRORLEVEL% equ 0 (
    echo SUCCESS: Refresh interval updated.
    type temp_response.json
    del temp_response.json
) else (
    echo ERROR: Failed to update refresh interval
    del temp_response.json
    exit /b 1
)
