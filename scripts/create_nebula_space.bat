@echo off
echo NebulaGraph Space Creation Script
echo =====================================
echo.

echo Checking if NebulaGraph is running...
python -c "import socket; s = socket.socket(); s.settimeout(3); result = s.connect_ex(('localhost', 9669)); s.close(); exit(0 if result == 0 else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Cannot connect to NebulaGraph on localhost:9669
    echo.
    echo Please make sure NebulaGraph is running:
    echo   docker-compose -f docker-compose.yaml -p flexible-graphrag up -d nebula-metad nebula-storaged nebula-graphd
    echo.
    pause
    exit /b 1
)

echo NebulaGraph is accessible on port 9669
echo.
echo Running space creation script...
python scripts\create_nebula_space.py

pause
