@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 美术素材库 - 首次安装

echo ==========================================
echo   美术素材库 首次安装（只需运行一次）
echo ==========================================
echo.

rem ---- 1. Python ----
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [1/3] 未找到 Python 3.11 或更高版本，正在通过 winget 安装 Python 3.12 ...
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 goto nopython
  echo.
  echo Python 已安装。请关闭本窗口，再次双击“安装.bat”继续。
  pause
  exit /b 0
)
echo [1/3] 已找到 Python：
%PY% --version

rem ---- 2. 虚拟环境与依赖 ----
if not exist ".venv\Scripts\python.exe" (
  echo [2/3] 创建独立运行环境 .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto fail
)
echo [2/3] 安装依赖（fastapi, uvicorn, Pillow）...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败。若网络较慢，可改用国内镜像后重试：
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  goto fail
)

rem ---- 3. FFmpeg（视频时长、封面） ----
".venv\Scripts\python.exe" -c "from artlib.vendor.feral.tools import find_binary as f; import sys; sys.exit(0 if f('ffmpeg') and f('ffprobe') else 1)"
if errorlevel 1 (
  echo [3/3] 未找到 FFmpeg，正在通过 winget 安装（用于读取视频信息和生成封面）...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo FFmpeg 安装失败。图片功能不受影响；视频将无法显示时长和封面。
    echo 可稍后手动执行：winget install Gyan.FFmpeg
  )
) else (
  echo [3/3] 已找到 FFmpeg。
)

echo.
echo 安装完成。以后双击“启动素材库.bat”即可使用。
pause
exit /b 0

:nopython
echo.
echo 自动安装 Python 失败。请手动安装：
echo   1. 打开 https://www.python.org/downloads/windows/ 下载 Python 3.12
echo   2. 安装时勾选 “Add python.exe to PATH”
echo   3. 安装完成后再次双击“安装.bat”
:fail
echo.
echo 安装未完成，请查看上面的错误信息。
pause
exit /b 1
