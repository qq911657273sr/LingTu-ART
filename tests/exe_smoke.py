"""Exercise the frozen executable against a separate disposable library."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = Path(sys.argv[1]).resolve()
WORK = Path(tempfile.mkdtemp(prefix="artspace-exe-"))
PORT = 8798
BASE = f"http://127.0.0.1:{PORT}"
checks = []

def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)
    print(f"PASS: {label}", flush=True)

def request(method, path, body=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()
        return json.loads(content) if "json" in response.headers.get("content-type", "") else content

cfg = {"host": "127.0.0.1", "port": PORT, "data_dir": "数据", "backup_dir": "备份", "export_dir": str(WORK / "导出"), "open_browser": False}
config = WORK / "config.json"
config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
env = {**os.environ, "ARTLIB_CONFIG": str(config), "PATH": str(Path(os.environ["SystemRoot"]) / "System32")}
log = open(WORK / "exe.log", "w", encoding="utf-8")
process = subprocess.Popen([str(EXE), "--no-browser"], cwd=WORK, env=env, stdout=log, stderr=log,
                           creationflags=subprocess.CREATE_NO_WINDOW)
try:
    for _ in range(180):
        if process.poll() is not None:
            raise RuntimeError(f"Executable exited with {process.returncode}; see {WORK / 'exe.log'}")
        try:
            request("GET", "/api/ping")
            break
        except OSError:
            time.sleep(.5)
    else:
        raise RuntimeError("Frozen service did not become ready")
    check((WORK / "数据" / "library.db").is_file(), "database persists outside one-file extraction directory")
    check(request('GET', '/api/update')['current_version'] == '1.4.1', 'bundled shared version and update endpoint available')
    ai_settings = request("GET", "/api/ai/settings")
    check(ai_settings.get("prompt_presets") == [], "LLM prompt presets have a separate settings collection")
    saved_presets = request("POST", "/api/ai/prompt-presets", {"presets": [{"name": "测试规则", "text": "把用户的自然语言整理成图生图提示词，只返回结果。"}]})
    check(saved_presets["prompt_presets"][0]["name"] == "测试规则", "LLM prompt preset saves and returns")
    html = request("GET", "/").decode()
    check('src="/assets/' in html, "bundled React frontend served")
    import re
    js_path = re.search(r'src="([^"]+\.js)"', html).group(1)
    check(len(request("GET", js_path)) > 100_000, "bundled frontend script served")
    settings = request("GET", "/api/settings")
    check(all('_MEI' in settings['tools'][name] or Path(settings['tools'][name]).is_relative_to(EXE.parent) for name in ('ffmpeg', 'ffprobe')), "FFmpeg and ffprobe are supplied by executable")
    samples = ROOT / "tests" / "samples" / "测试 素材"
    image = samples / "批次A" / "庭院 夜景.png"
    video = samples / "批次B" / "角色 动作 测试.mp4"
    from urllib.parse import urlencode
    asset_ids = []
    for sample in (image, video):
        result = request("POST", "/api/import?" + urlencode({"name": sample.name}), raw=sample.read_bytes())
        check(result['status'] == 'ok', f"import {sample.suffix}")
        asset_ids.append(result['asset_id'])
    for _ in range(60):
        if request("GET", "/api/sidebar")["pending_thumbs"] == 0:
            break
        time.sleep(.5)
    for asset_id in asset_ids:
        check(len(request("GET", f"/thumb/{asset_id}")) > 100, "image/video thumbnail generated")
    asset_id = asset_ids[0]
    edited = request("PATCH", f"/api/assets/{asset_id}", {"favorite": True, "name": "测试重命名", "tags": ["测试标签"]})
    check(edited['favorite'] and edited['name'] == '测试重命名' and '测试标签' in edited['tags'], "favorite, rename and tags persist")
    export = request("POST", "/api/export", {"ids": [asset_id]})
    check(not export['failed'] and len(export['exported']) == 1, "export original file")
    original = request("GET", f"/file/{asset_id}?download=1")
    check(hashlib.sha256(original).digest() == hashlib.sha256(image.read_bytes()).digest(), "download preserves original bytes")
    request("POST", "/api/batch", {"ids": [asset_id], "action": "trash"})
    check(request("GET", "/api/assets?scope=trash")['total'] == 1, "move to recycle bin")
    request("POST", "/api/batch", {"ids": [asset_id], "action": "restore"})
    check(request("GET", "/api/assets")['total'] == 2, "restore from recycle bin")
    print(f"{len(checks)}/{len(checks)} checks passed; logs: {WORK}", flush=True)
finally:
    subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32' / 'taskkill.exe'), '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    process.wait(timeout=15)
    log.close()
