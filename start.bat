@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo.
echo =====================================
echo  Starting Web Server...
echo  Visit: http://127.0.0.1:8000
echo  AstrBot local renderer: host.docker.internal:8000
echo  Close this window to stop
echo =====================================
echo.
python main.py web --host 127.0.0.1 --port 8000
pause
