"""Installed LingTu ART application: native WebView2 window + local service."""
import ctypes
import json
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

TITLE = "灵图 ART · 美术素材库"

def style_native_titlebar():
    """Blend the Windows caption into the app canvas while keeping native behavior."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        hwnd = user32.FindWindowW(None, TITLE)
        if not hwnd:
            return
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        color = ctypes.c_int(0x00F7F1F0)  # COLORREF for #f0f1f7
        for attribute in (34, 35, 36):  # border, caption, caption text
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        logging.exception("Unable to theme the native title bar")

def configure():
    resource = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    os.environ["PATH"] = str(resource / "bin") + os.pathsep + os.environ.get("PATH", "")
    user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ARTSPACE"
    user_dir.mkdir(parents=True, exist_ok=True)
    config = Path(os.environ.get("ARTLIB_CONFIG", user_dir / "config.json"))
    if not config.exists() and (user_dir / "source-library.txt").exists():
        legacy = Path((user_dir / "source-library.txt").read_text("utf-8-sig").strip())
        if legacy.is_file():
            values = json.loads(legacy.read_text("utf-8"))
            for key in ("data_dir", "backup_dir", "export_dir"):
                if key in values:
                    path = Path(values[key]).expanduser()
                    values[key] = str(path if path.is_absolute() else (legacy.parent / path).resolve())
            values["open_browser"] = False
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps(values, ensure_ascii=False, indent=2), "utf-8")
    os.environ["ARTLIB_CONFIG"] = str(config)
    if sys.stdout is None:
        sys.stdout = open(user_dir / "desktop.log", "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    logging.basicConfig(filename=user_dir / "desktop.log", level=logging.INFO, encoding="utf-8")
    return user_dir

def desktop(user_dir):
    from artlib import config as config_module, media, server
    import uvicorn
    import webview

    cfg = config_module.load()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server.CFG = {**cfg, "host": "127.0.0.1", "port": port, "open_browser": False}
    server.open_library(config_module.resolve(cfg["data_dir"]))
    service = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    thread = threading.Thread(target=service.run, name="ARTSPACE-service", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/ping", timeout=.5).close()
                break
            except OSError:
                if not thread.is_alive():
                    raise RuntimeError("素材库服务未能启动")
                time.sleep(.1)
        else:
            raise RuntimeError("素材库服务启动超时")
        smoke = "--desktop-smoke" in sys.argv
        window = webview.create_window(TITLE, url, width=1440, height=940, min_size=(960, 640), background_color="#f0f1f7", hidden=smoke)
        window.events.shown += style_native_titlebar
        def smoke_check():
            report = Path(sys.argv[sys.argv.index("--desktop-smoke") + 1])
            try:
                if not window.events.loaded.wait(40):
                    raise RuntimeError("WebView2 页面加载超时")
                for _ in range(100):
                    result = window.evaluate_js("({title:document.title,brand:document.body.innerText.includes('灵图 ART'),logo:(document.querySelector('.brand-mark img')?.naturalWidth||0)>0,search:!!document.querySelector('input[aria-label=\"搜索\"]'),cards:document.querySelectorAll('.card').length})")
                    if result.get("brand") and result.get("logo") and result.get("search"):
                        break
                    time.sleep(.1)
                report.write_text(json.dumps({"ok": bool(result.get("brand") and result.get("logo") and result.get("search")), "page": result, "renderer": "edgechromium", "url": url, "tools": media.ffmpeg_status()}, ensure_ascii=False, indent=2), "utf-8")
            except Exception as error:
                report.write_text(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), "utf-8")
            finally:
                window.destroy()
        webview.start(smoke_check if smoke else None, gui="edgechromium", private_mode=False, storage_path=str(user_dir / "webview"))
    finally:
        service.should_exit = True
        thread.join(timeout=10)

def main():
    user_dir = configure()
    if "--no-browser" in sys.argv:
        from artlib.__main__ import main as service_main
        service_main()
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    smoke = "--desktop-smoke" in sys.argv
    mutex_name = "Local\\ARTSPACE-Desktop-Smoke" if smoke else "Local\\ARTSPACE-Desktop-Application"
    mutex = kernel.CreateMutexW(None, False, mutex_name)
    if not smoke and ctypes.get_last_error() == 183:
        user = ctypes.windll.user32
        user.FindWindowW.restype = ctypes.c_void_p
        user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        handle = user.FindWindowW(None, TITLE)
        if handle:
            user.ShowWindow(handle, 9)
            user.SetForegroundWindow(handle)
        kernel.CloseHandle(mutex)
        return
    try:
        desktop(user_dir)
    finally:
        kernel.CloseHandle(mutex)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception as error:
        logging.exception("ARTSPACE startup failed")
        if "--desktop-smoke" in sys.argv:
            report = Path(sys.argv[sys.argv.index("--desktop-smoke") + 1])
            report.write_text(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), "utf-8")
        else:
            ctypes.windll.user32.MessageBoxW(None, f"启动失败：{error}\n详情见 %LOCALAPPDATA%\\ARTSPACE\\desktop.log", TITLE, 16)
        sys.exit(1)
