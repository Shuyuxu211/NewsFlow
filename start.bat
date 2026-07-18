@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv not found. Create it and install requirements.txt first.
    pause
    exit /b 1
)

echo.
echo =====================================
echo  Starting NewsFlow standalone web server...
echo  Visit: http://127.0.0.1:8000
echo  Includes the standalone Chrome render endpoint
echo  AstrBot image rendering runs inside its container
echo  Close this window to stop
echo =====================================
echo.
".venv\Scripts\python.exe" main.py web --host 127.0.0.1 --port 8000
pause
