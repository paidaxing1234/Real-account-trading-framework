@echo off
chcp 65001 >nul
title 一键修复前端问题

echo.
echo ╔══════════════════════════════════════════╗
echo ║        一键修复 - 前端所有问题          ║
echo ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [步骤 1/3] 停止当前服务...
taskkill /F /IM node.exe 2>nul
timeout /t 2 >nul

echo.
echo [步骤 2/3] 清理缓存...
if exist "node_modules\.vite" rmdir /s /q "node_modules\.vite"
if exist ".vite" rmdir /s /q ".vite"
if exist "dist" rmdir /s /q "dist"

echo.
echo [步骤 3/3] 重新启动...
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo ✅ 已修复的问题:
echo   • accountApi / strategyApi 未定义
echo   • 图标错误
echo   • 空值错误
echo   • 性能优化
echo   • Mock模式启用
echo.
echo 🎭 Mock模式说明:
echo   • 5秒内连不上C++后端会自动启用Mock模式
echo   • 使用模拟数据展示所有功能
echo   • 不依赖C++后端也能运行
echo.
echo 🚀 正在启动开发服务器...
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

call npm run dev

pause

