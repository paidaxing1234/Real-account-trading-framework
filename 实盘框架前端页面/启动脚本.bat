@echo off
chcp 65001 >nul
echo ========================================
echo   实盘交易管理系统 - 启动脚本
echo ========================================
echo.

echo [1/3] 检查依赖...
if not exist "node_modules\" (
    echo 未检测到 node_modules，正在安装依赖...
    call npm install
    if errorlevel 1 (
        echo 依赖安装失败！
        pause
        exit /b 1
    )
) else (
    echo 依赖已存在
)

echo.
echo [2/3] 启动开发服务器...
echo.
echo 系统将在 http://localhost:3000 启动
echo 按 Ctrl+C 可停止服务器
echo.
echo ========================================
echo.

call npm run dev

pause

