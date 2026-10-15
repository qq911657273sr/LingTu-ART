@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 美术素材库（关闭此窗口即停止）

if not exist ".venv\Scripts\python.exe" (
  echo 还没有安装运行环境，请先双击运行“安装.bat”。
  pause
  exit /b 1
)
if not exist "web\dist\index.html" (
  echo 前端文件 web\dist 缺失，程序不完整，请重新获取完整的程序目录。
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -m artlib %*
if errorlevel 1 (
  echo.
  echo 素材库未能启动，请查看上面的提示。
  pause
)
