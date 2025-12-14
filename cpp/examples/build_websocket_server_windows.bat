@echo off
REM ============================================================================
REM WebSocket服务器编译脚本（Windows）
REM 
REM 注意：推荐在WSL中编译和运行，Windows原生编译需要手动配置Boost
REM ============================================================================

echo.
echo ========================================================================
echo     WebSocket服务器编译脚本（Windows）
echo ========================================================================
echo.
echo 建议：在WSL中编译和运行更简单！
echo.
echo 在WSL中执行：
echo   wsl bash build_websocket_server.sh
echo.
echo 如果坚持在Windows下编译，需要：
echo   1. 安装 MSVC 或 MinGW-w64
echo   2. 安装 Boost 库（建议用 vcpkg）
echo      vcpkg install boost-beast boost-asio nlohmann-json
echo   3. 配置编译器路径和库路径
echo.
pause

REM 检查是否安装了WSL
where wsl >nul 2>nul
if %errorlevel% == 0 (
    echo.
    echo 检测到WSL，是否在WSL中编译？[Y/N]
    set /p use_wsl=
    if /i "%use_wsl%"=="Y" (
        echo 启动WSL编译...
        wsl bash "%~dp0build_websocket_server.sh"
        goto :end
    )
)

echo.
echo 请手动编译或使用WSL
pause

:end

