@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "SHORTCUT_NAME=每日新闻流"
set "TARGET=%SCRIPT_DIR%start.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%.lnk"

echo =====================================
echo  NewsBot Auto-Start Setup
echo =====================================
echo.
echo 1 - Enable auto-start
echo 2 - Disable auto-start
echo 3 - Check status
echo.
choice /c 123 /n /m "Select option: "

if errorlevel 3 goto check
if errorlevel 2 goto disable
if errorlevel 1 goto enable

:enable
echo.
echo Enabling auto-start...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');$s.TargetPath='cmd.exe';$s.Arguments='/c \"%TARGET%\"';$s.WorkingDirectory='%SCRIPT_DIR%';$s.WindowStyle=7;$s.Save()"
echo Done!
goto end

:disable
echo.
del /f /q "%SHORTCUT_PATH%" 2>nul
echo Done!
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
