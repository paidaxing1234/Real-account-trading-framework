@echo off
chcp 65001 >nul
title 实盘框架前端启动

echo.
echo ╔══════════════════════════════════════════╗
echo ║        实盘交易框架前端启动脚本          ║
echo ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM 检查node_modules
if not exist "node_modules" (
    echo [提示] 首次运行，正在安装依赖...
    echo.
    call npm install
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败！
        pause
        exit /b 1
    )
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 启动信息:
echo   • 前端地址: http://localhost:3000
echo   • WebSocket: ws://localhost:8001
echo   • (如果3000被占用会自动换端口)
echo.
echo 重要提示:
echo   ⚠ WebSocket连接失败是正常的
echo   ⚠ 需要先启动C++后端: cpp/build/ui_server
echo   ⚠ 登录后才能访问系统日志等页面
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

timeout /t 2 >nul

echo 正在启动开发服务器...
echo.

call npm run dev

pause

