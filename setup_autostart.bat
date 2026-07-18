@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "SHORTCUT_NAME=NewsFlow AutoStart"
set "TARGET=%SCRIPT_DIR%\start.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%.lnk"

echo =====================================
echo  NewsFlow Auto-Start Setup
echo =====================================
echo.
echo 1 - Enable auto-start on boot
echo 2 - Disable auto-start on boot
echo 3 - Check current status
echo.
set /p CHOICE="Select (1/2/3): "

if "%CHOICE%"=="3" goto check
if "%CHOICE%"=="2" goto disable
if "%CHOICE%"=="1" goto enable
echo Invalid selection.
goto end

:enable
echo.
echo Enabling auto-start...
echo   Script dir : %SCRIPT_DIR%
echo   Target file: %TARGET%

if not exist "%STARTUP_FOLDER%" mkdir "%STARTUP_FOLDER%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo SUCCESS: NewsFlow will auto-start on next boot.
) else (
    echo FAILED: Unable to create shortcut. Check the Startup folder permissions and target path.
)
goto end

:disable
echo.
if exist "%SHORTCUT_PATH%" (
    del /f /q "%SHORTCUT_PATH%"
    echo Auto-start disabled. Shortcut removed from Startup folder.
) else (
    echo No auto-start entry found. Nothing to disable.
)
goto end

:check
echo.
if exist "%SHORTCUT_PATH%" (
    echo Status: ENABLED
) else (
    echo Status: DISABLED
)
goto end

:end
echo.
pause
