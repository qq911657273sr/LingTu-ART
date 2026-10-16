"""HTTP 接口与静态前端。"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import backup, db, library, media, ai_edit, web_auth, agent_service, agent_store, updates
from . import config as cfgmod
from .config import RESOURCE_DIR, Paths

CFG: dict = {}
WEB_DIR = RESOURCE_DIR / "web" / "dist"
MAX_UPLOAD = 20 * 1024**3

app = FastAPI(title="美术素材库", docs_url=None, redoc_url=None, openapi_url=None)


def open_library(data_dir: Path) -> None:
    with agent_store.LOCK, ai_edit.LOCK:
        if ai_edit.ACTIVE:
            raise ValueError("AI 任务仍在生成，请等待完成后切换素材库")
        if library.PATHS and agent_service.busy():
            raise ValueError('助手任务尚未结束，请先停止任务再切换素材库')
        if library.PATHS:
            agent_service.codex.close()
            agent_service._threads.clear()
        library.start(Paths(data_dir))
        agent_service.init()


@app.exception_handler(ValueError)
async def _value_error(_req, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.middleware("http")
async def _local_only(request: Request, call_next):
    # Keep the application bound to loopback; public deployments sit behind a local TLS proxy.
    host = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host in ("testclient", "localhost")
    if not loopback:
        return JSONResponse({"detail": "只允许本机访问"}, status_code=403)
    origin = request.headers.get("origin")
    if web_auth.ENABLED:
        if request.headers.get("host", "").split(":", 1)[0].lower() != web_auth.urlsplit(web_auth.PUBLIC_ORIGIN).hostname:
            return JSONResponse({"detail": "请求域名无效"}, status_code=400)
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin != web_auth.PUBLIC_ORIGIN:
            return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
        auth_route = request.url.path in ("/api/auth/status", "/api/auth/login", "/api/auth/logout", "/api/ping")
        protected = request.url.path.startswith("/api/") or request.url.path.startswith(("/file/", "/thumb/"))
        if protected and not auth_route and not web_auth.authenticated(request):
            return JSONResponse({"detail": "登录状态已失效，请重新登录"}, status_code=401,
                                headers={"Cache-Control": "no-store"})
    elif origin and request.method != "GET":
        o = origin.split("//", 1)[-1].split(":")[0]
        if o not in ("127.0.0.1", "localhost", "[::1]"):
            return JSONResponse({"detail": "拒绝跨站请求"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


def _asset_or_404(asset_id: str) -> dict:
    a = library.get_asset(asset_id)
    if a is None:
        raise HTTPException(404, "素材不存在")
    return a


# ---------------------------------------------------------------- 浏览

@app.get("/api/ping")
def api_ping():
    return {"ok": True}


@app.get("/api/sidebar")
def api_sidebar():
    return library.sidebar()


@app.get("/api/assets")
def api_assets(scope: str = "all", q: str = "", kind: str = "", favorite: bool = False, sort: str = "imported",
               order: str = "desc", offset: int = 0, limit: int = 120):
    return library.query_assets(scope, q, kind, favorite, sort, order, offset, limit)


@app.get("/api/asset-ids")
def api_asset_ids(scope: str = "all", q: str = "", kind: str = "", favorite: bool = False):
    return library.asset_ids(scope, q, kind, favorite)


@app.post("/api/thumb-states")
def api_thumb_states(ids: list[str] = Body(...)):
    ids = ids[:500]
    rows = db.connect().execute(
        f"SELECT id, thumb_state FROM assets WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []
    return {r["id"]: r["thumb_state"] for r in rows}


@app.get("/api/assets/{asset_id}")
def api_asset(asset_id: str):
    return _asset_or_404(asset_id)


@app.patch("/api/assets/{asset_id}")
def api_update(asset_id: str, data: dict = Body(...)):
    _asset_or_404(asset_id)
    library.update_asset(asset_id, data)
    return library.get_asset(asset_id)


@app.post("/api/batch")
def api_batch(data: dict = Body(...)):
    n = library.batch(data.get("ids") or [], data.get("action", ""), data.get("folder_id"), data.get("tags"),
                      data.get("value"))
    return {"count": n}


@app.post("/api/trash/empty")
def api_empty_trash():
    return {"count": library.empty_trash()}


@app.get("/file/{asset_id}")
def api_file(asset_id: str, download: bool = False):
    a = _asset_or_404(asset_id)
    path = Path(a["path"])
    if not path.is_file():
        raise HTTPException(404, "原文件丢失")
    headers = {"Cache-Control": "private, max-age=31536000, immutable"}
    if download:
        name = library.safe_filename(a["name"] if a["name"].lower().endswith(a["ext"]) else a["name"] + a["ext"])
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name)}"
    return FileResponse(path, headers=headers, content_disposition_type="inline")


@app.get("/thumb/{asset_id}")
def api_thumb(asset_id: str):
    p = library.PATHS.thumb(asset_id)
    if not p.is_file():
        raise HTTPException(404, "缩略图尚未生成")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/assets/{asset_id}/workflow")
def api_workflow(asset_id: str, key: str = "workflow"):
    a = _asset_or_404(asset_id)
    text = library.workflow_json(asset_id, key)
    if text is None:
        raise HTTPException(404, "没有可导出的工作流")
    name = quote(f"{a['name']}.{key}.json")
    return Response(text, media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})


@app.get("/api/assets/{asset_id}/raw")
def api_raw(asset_id: str):
    _asset_or_404(asset_id)
    return library.raw_metadata(asset_id)


# ---------------------------------------------------------------- 导入

@app.post("/api/import")
async def api_import(request: Request, name: str, folder_id: int | None = None, mtime: float | None = None):
    """请求体就是文件原始字节（流式写入临时文件并同时计算 SHA-256）。"""
    tmp = library.PATHS.tmp / f"{uuid.uuid4().hex}.part"
    h = hashlib.sha256()
    size = 0
    try:
        with open(tmp, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "文件过大")
                h.update(chunk)
                fh.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if size == 0:
        tmp.unlink(missing_ok=True)
        return {"status": "failed", "message": "文件为空"}
    try:
        return await run_in_threadpool(library.import_file, tmp, h.hexdigest(), name, folder_id,
                                       mtime / 1000 if mtime else None)
    except media.MediaError as e:
        return {"status": "failed", "message": str(e)}
    except Exception as e:
        traceback.print_exc()
        return {"status": "failed", "message": f"导入出错：{e.__class__.__name__}: {e}"}
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- 文件夹

@app.post("/api/folders")
def api_folder_create(data: dict = Body(...)):
    return {"id": library.create_folder(data.get("name", ""), data.get("parent_id"))}


@app.patch("/api/folders/{folder_id}")
def api_folder_update(folder_id: int, data: dict = Body(...)):
    if "name" in data:
        library.rename_folder(folder_id, data["name"])
    if "move" in data:
        library.move_folder(folder_id, int(data["move"]))
    return {"ok": True}


@app.get("/api/folders/{folder_id}/usage")
def api_folder_usage(folder_id: int):
    return library.folder_usage(folder_id)


@app.delete("/api/folders/{folder_id}")
def api_folder_delete(folder_id: int, move_to_inbox: bool = False):
    return {"moved": library.delete_folder(folder_id, move_to_inbox)}


# ---------------------------------------------------------------- 取用

@app.post("/api/export")
def api_export(data: dict = Body(...)):
    target = cfgmod.resolve(CFG["export_dir"])
    if data.get("subfolder"):
        target = target / library.safe_filename(data["subfolder"])
    return library.export_assets(data.get("ids") or [], target)


def _reveal(path: Path, select: bool) -> dict:
    if sys.platform != "win32":
        return {"ok": False, "path": str(path), "message": "当前系统不支持打开资源管理器，请复制路径"}
    # explorer 自己解析命令行，必须整串传递；Windows 路径中不可能含有 "
    cmd = f'explorer /select,"{path}"' if select else f'explorer "{path}"'
    subprocess.Popen(cmd)
    return {"ok": True, "path": str(path)}


@app.post("/api/assets/{asset_id}/reveal")
def api_reveal(asset_id: str):
    path = Path(_asset_or_404(asset_id)["path"])  # 仅数据库记录的位置，且已校验在素材库内
    if not path.is_file():
        raise HTTPException(404, "原文件丢失")
    return _reveal(path, True)


@app.post("/api/reveal/{which}")
def api_reveal_dir(which: str):
    dirs = {"export": cfgmod.resolve(CFG["export_dir"]), "backup": cfgmod.resolve(CFG["backup_dir"]),
            "data": library.PATHS.data}
    if which not in dirs:
        raise HTTPException(404)
    dirs[which].mkdir(parents=True, exist_ok=True)
    return _reveal(dirs[which], False)


# ---------------------------------------------------------------- 设置 / 备份

TASK: dict = {"kind": None, "running": False, "done": 0, "total": 0, "result": None, "error": None}


def _run_task(kind: str, fn):
    if TASK["running"]:
        raise ValueError("已有备份/恢复任务在进行")
    TASK.update(kind=kind, running=True, done=0, total=0, result=None, error=None, started=time.time())

    def progress(done, total):
        TASK.update(done=done, total=total)

    def run():
        try:
            TASK["result"] = fn(progress)
        except ValueError as e:
            TASK["error"] = str(e)
        except Exception as e:
            traceback.print_exc()
            TASK["error"] = f"{e.__class__.__name__}: {e}"
        finally:
            TASK["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return TASK


@app.get("/api/settings")
def api_settings():
    return {
        "data_dir": str(library.PATHS.data),
        "backup_dir": str(cfgmod.resolve(CFG["backup_dir"])),
        "export_dir": str(cfgmod.resolve(CFG["export_dir"])),
        "config_path": str(cfgmod.CONFIG_PATH),
        "tools": media.ffmpeg_status(),
        "backups": backup.list_backups(cfgmod.resolve(CFG["backup_dir"])),
        "task": TASK,
        "platform": sys.platform,
    }


@app.patch("/api/settings")
def api_settings_update(data: dict = Body(...)):
    for key in ("export_dir", "backup_dir"):
        if data.get(key):
            p = Path(data[key]).expanduser()
            if not p.is_absolute():
                raise ValueError("请填写完整路径，例如 D:\\素材导出")
            CFG[key] = str(p)
    cfgmod.save(CFG)
    return api_settings()


@app.post("/api/thumbs/rebuild")
def api_rebuild_thumbs():
    return {"count": library.rebuild_thumbs()}


@app.post("/api/backup")
def api_backup():
    data_dir, backup_dir = library.PATHS.data, cfgmod.resolve(CFG["backup_dir"])
    return _run_task("backup", lambda p: backup.create_backup(data_dir, backup_dir, p))


@app.post("/api/restore")
def api_restore(data: dict = Body(...)):
    zip_path = Path(data.get("path", ""))
    if not zip_path.is_file():
        raise ValueError("备份文件不存在")
    target = data.get("target") or str(cfgmod.resolve(CFG["backup_dir"]) / f"恢复-{time.strftime('%Y%m%d-%H%M%S')}")
    target = Path(target).expanduser()
    if not target.is_absolute():
        raise ValueError("请填写完整的目标路径")
    if target.resolve() == library.PATHS.data.resolve():
        raise ValueError("不能恢复到当前正在使用的素材库目录")
    return _run_task("restore", lambda p: backup.restore_backup(zip_path, target, p))


@app.post("/api/library/switch")
def api_switch(data: dict = Body(...)):
    """切换到另一个素材库目录（例如刚恢复出来的目录）。原目录保持不动。"""
    target = Path(data.get("dir", "")).expanduser()
    if not (target / "library.db").is_file():
        raise ValueError("该目录中没有素材库数据库 library.db")
    open_library(target.resolve())
    CFG["data_dir"] = str(target.resolve())
    cfgmod.save(CFG)
    return {"data_dir": CFG["data_dir"]}


# ---------------------------------------------------------------- 前端

app.include_router(web_auth.router)
app.include_router(ai_edit.router)
app.include_router(agent_service.router)
app.include_router(updates.router)

if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="static")


@app.get("/{_path:path}", include_in_schema=False)
def spa(_path: str):
    # Serve files from the built frontend (including public-root assets such as
    # the brand mark) before falling back to the SPA entry point.
    if _path:
        web_root = WEB_DIR.resolve()
        asset = (WEB_DIR / _path).resolve()
        if asset.is_relative_to(web_root) and asset.is_file():
            return FileResponse(asset, headers={"Cache-Control": "public, max-age=31536000, immutable"})
        if Path(_path).suffix:
            raise HTTPException(404, "前端资源不存在")
    index = WEB_DIR / "index.html"
    if not index.is_file():
        return Response("前端文件缺失：请确认 web/dist 目录完整（开发者可在 web 目录执行 npm run build）。",
                        media_type="text/plain; charset=utf-8", status_code=500)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
