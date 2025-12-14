@echo off
chcp 65001 >nul
title 实盘框架前端 - WSL启动

echo.
echo ╔══════════════════════════════════════════╗
echo ║   实盘交易框架前端 - WSL启动脚本        ║
echo ╚══════════════════════════════════════════╝
echo.
echo 提示: WebSocket连接失败是正常的，需要先启动C++后端
echo      后端启动命令: cd cpp/build ^&^& ./ui_server
echo.

REM 获取当前目录
set CURRENT_DIR=%~dp0
echo [INFO] 当前目录: %CURRENT_DIR%

REM 转换Windows路径到WSL路径
set WSL_PATH=%CURRENT_DIR:\=/%
set WSL_PATH=%WSL_PATH:D:/=/mnt/d/%
set WSL_PATH=%WSL_PATH:C:/=/mnt/c/%
set WSL_PATH=%WSL_PATH:E:/=/mnt/e/%
set WSL_PATH=%WSL_PATH:F:/=/mnt/f/%

echo [INFO] WSL路径: %WSL_PATH%
echo.

REM 检查WSL是否安装
wsl --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] WSL未安装！
    echo.
    echo 请先安装WSL:
    echo   wsl --install
    echo.
    pause
    exit /b 1
)

echo [INFO] WSL已安装 ✓
echo.

REM 检查启动脚本
if not exist "%CURRENT_DIR%start-wsl.sh" (
    echo [WARNING] start-wsl.sh 不存在，使用默认启动方式
    echo.
    
    REM 直接启动npm dev
    echo [INFO] 正在启动前端开发服务器...
    echo.
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo   前端地址: http://localhost:5173
    echo   WebSocket: ws://localhost:8001
    echo.
    echo   按 Ctrl+C 停止服务器
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo.
    
    wsl bash -c "cd '%WSL_PATH%' && npm run dev"
) else (
    REM 使用启动脚本
    echo [INFO] 使用启动脚本: start-wsl.sh
    echo.
    
    REM 添加执行权限并运行
    wsl bash -c "cd '%WSL_PATH%' && chmod +x start-wsl.sh && ./start-wsl.sh"
)

REM 如果退出
echo.
echo [INFO] 开发服务器已停止
pause

