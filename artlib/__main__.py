"""启动：python -m artlib"""

from __future__ import annotations

import socket
import sys
import threading
import urllib.request
import webbrowser


def _port_busy(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _is_us(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/sidebar", timeout=2) as r:
            return r.status == 200 and b'"folders"' in r.read()
    except Exception:
        return False


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("需要 Python 3.11 或更高版本")
    try:
        import fastapi, uvicorn, PIL  # noqa: F401
    except ImportError as e:
        raise SystemExit(f"缺少依赖 {e.name}。请先双击运行 “安装.bat”。")

    from . import config as cfgmod
    cfg = cfgmod.load()
    host, port = cfg["host"], int(cfg["port"])
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}/"
    no_browser = "--no-browser" in sys.argv or not cfg.get("open_browser", True)

    if _port_busy("127.0.0.1", port):
        if _is_us(url):
            print(f"素材库已经在运行：{url}")
            if not no_browser:
                webbrowser.open(url)
            return
        raise SystemExit(
            f"端口 {port} 已被其他程序占用。\n"
            f"请关闭占用该端口的程序，或编辑 {cfgmod.CONFIG_PATH} 把 \"port\" 改成其他数字（如 8766）后重新启动。")

    from . import media, server
    server.CFG = cfg
    data_dir = cfgmod.resolve(cfg["data_dir"])
    server.open_library(data_dir)
    tools = media.ffmpeg_status()
    print(f"素材库目录：{data_dir}")
    if not tools["ffmpeg"] or not tools["ffprobe"]:
        print("提示：未找到 FFmpeg。图片功能正常；视频将无法读取时长或生成封面。运行 “安装.bat” 可自动安装。")
    print(f"打开浏览器访问：{url}   （关闭本窗口即停止）")
    if not no_browser:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()

    import uvicorn
    uvicorn.run(server.app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
