@echo off
title 陈毅数字人文项目 - 本地服务器
cd /d "%~dp0"
echo ========================================
echo   陈毅数字人文项目 - 本地服务器
echo ========================================
echo.
echo 正在启动HTTP服务器并打开浏览器...
echo.
echo 按 Ctrl+C 停止服务器
echo ========================================
echo.
start http://localhost:9999
python -m http.server 9999
