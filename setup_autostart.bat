@echo off
setlocal

:: 获取脚本所在目录（去掉末尾反斜杠）
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "SHORTCUT_NAME=每日新闻流"
set "TARGET=%SCRIPT_DIR%\start.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%.lnk"

echo =====================================
echo  每日新闻流 开机自动启动设置
echo =====================================
echo.
echo 1 - 启用开机启动
echo 2 - 禁用开机启动
echo 3 - 查看状态
echo.
choice /c 123 /n /m "请选择: "

if errorlevel 3 goto check
if errorlevel 2 goto disable
if errorlevel 1 goto enable

:enable
echo.
echo 正在启用开机启动...
echo 脚本目录: %SCRIPT_DIR%
echo 目标文件: %TARGET%
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = 'cmd.exe'; $s.Arguments = '/c cd /d ''%SCRIPT_DIR%'' && ''%TARGET%'''; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save()"
if exist "%SHORTCUT_PATH%" (
    echo 完成！开机后自动启动每日新闻流。
) else (
    echo 创建快捷方式失败，请以管理员身份运行。
)
goto end

:disable
echo.
del /f /q "%SHORTCUT_PATH%" 2>nul
echo 已禁用开机启动。
goto end

:check
echo.
if exist "%SHORTCUT_PATH%" (
    echo 状态: 已启用
) else (
    echo 状态: 未启用
)
goto end

:end
echo.
pause
