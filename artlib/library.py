"""素材库业务逻辑：导入、查询、整理、导出、回收站。"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import db, media
from .config import Paths

PATHS: Paths | None = None

# 在素材卡片/详情里需要的列（列表不取大字段）
LIST_COLS = ("id, name, ext, kind, size, width, height, duration, playable, folder_id, favorite, "
             "imported_at, deleted_at, thumb_state")

SEARCH_FIELDS = ("prompt", "negative_prompt", "model", "tool", "lora", "description")
_BAD_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str, fallback: str = "file") -> str:
    """Windows 可用的文件名：去掉非法字符、末尾点/空格、保留名，限制长度。保留中文与空格。"""
    name = _BAD_CHARS.sub("_", name).strip().rstrip(". ")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    ext = ext[:16]
    stem = stem[: 120 - len(ext)]
    name = f"{stem}.{ext}" if ext else stem
    return name or fallback


def unique_path(folder: Path, filename: str) -> Path:
    """同名时生成 “名称 (2).ext”，不覆盖已有文件。"""
    p = folder / filename
    stem, suffix = p.stem, p.suffix
    n = 2
    while p.exists():
        p = folder / f"{stem} ({n}){suffix}"
        n += 1
    return p


# ---------------------------------------------------------------- 后台缩略图

FILE_LOCK = threading.Lock()  # 备份期间不删除原文件
_jobs: "queue.Queue[str]" = queue.Queue()
_worker_started = False


def enqueue_thumb(asset_id: str) -> None:
    _jobs.put(asset_id)


def _thumb_worker() -> None:
    while True:
        asset_id = _jobs.get()
        try:
            build_thumb(asset_id)
        except Exception as e:  # 后台线程永不退出
            print(f"[缩略图] {asset_id} 失败：{e}")


def build_thumb(asset_id: str) -> None:
    conn = db.connect()
    row = conn.execute("SELECT rel_path, kind, duration FROM assets WHERE id=?", (asset_id,)).fetchone()
    if row is None:
        return
    try:
        media.make_thumb(PATHS.original(row["rel_path"]), PATHS.thumb(asset_id), row["kind"], row["duration"])
        state, note = 1, ""
    except media.MediaError as e:
        state, note = 2, str(e)
    except Exception as e:
        state, note = 2, f"缩略图生成失败：{e}"
    with conn:
        conn.execute("UPDATE assets SET thumb_state=?, note_sys=? WHERE id=?", (state, note, asset_id))


def start(paths: Paths) -> None:
    global PATHS, _worker_started
    PATHS = paths
    paths.ensure()
    db.init(paths.db)
    for f in paths.tmp.glob("*.part"):
        f.unlink(missing_ok=True)
    if not _worker_started:
        threading.Thread(target=_thumb_worker, daemon=True, name="thumbs").start()
        _worker_started = True
    for (aid,) in db.connect().execute("SELECT id FROM assets WHERE thumb_state=0"):
        enqueue_thumb(aid)


def rebuild_thumbs() -> int:
    conn = db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM assets")]
    with conn:
        conn.execute("UPDATE assets SET thumb_state=0")
    for aid in ids:
        enqueue_thumb(aid)
    return len(ids)


# ---------------------------------------------------------------- 导入

def import_file(tmp: Path, sha256: str, original_name: str, folder_id: int | None, mtime: float | None) -> dict:
    """tmp 是已完整写入并算好哈希的临时文件。返回 {status, asset?, message?}。"""
    conn = db.connect()
    try:
        dup = conn.execute("SELECT id, name, deleted_at FROM assets WHERE sha256=?", (sha256,)).fetchone()
        if dup:
            where = "（在回收站中）" if dup["deleted_at"] else ""
            return {"status": "duplicate", "asset_id": dup["id"], "message": f"已存在：{dup['name']}{where}"}

        original_name = safe_filename(original_name or "未命名")
        ext = Path(original_name).suffix.lower()
        info = media.probe(tmp, ext)  # MediaError → 调用方报告失败
        if folder_id is not None and not conn.execute("SELECT 1 FROM folders WHERE id=?", (folder_id,)).fetchone():
            folder_id = None

        asset_id = uuid.uuid4().hex
        rel = f"originals/{asset_id[:2]}/{asset_id}/{original_name}"
        dest = PATHS.data / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
        name = Path(original_name).stem or original_name
        try:
            with conn:
                conn.execute(
                    """INSERT INTO assets(id, sha256, name, original_name, rel_path, ext, kind, container, size,
                       width, height, duration, fps, playable, folder_id, source_mtime, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (asset_id, sha256, name, original_name, rel, ext, info["kind"], info["container"],
                     dest.stat().st_size, info["width"], info["height"], info["duration"], info["fps"],
                     info["playable"], folder_id, mtime, time.time()),
                )
                conn.execute("INSERT INTO asset_meta(asset_id, raw_json, fields_json, warnings_json) VALUES (?,?,?,?)",
                             (asset_id, info["raw_json"], info["fields_json"], info["warnings_json"]))
                refresh_search(conn, [asset_id])
        except sqlite3.IntegrityError:
            shutil.rmtree(dest.parent, ignore_errors=True)  # 并发导入了同一文件
            return {"status": "duplicate", "message": "已存在（同时导入的相同文件）"}
        except Exception:
            shutil.rmtree(dest.parent, ignore_errors=True)
            raise
        enqueue_thumb(asset_id)
        warnings = json.loads(info["warnings_json"])
        return {"status": "ok", "asset_id": asset_id, "message": "；".join(warnings)}
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- 搜索文本

def refresh_search(conn: sqlite3.Connection, ids: list[str]) -> None:
    for aid in ids:
        a = conn.execute("SELECT name, original_name, note, manual_prompt, manual_platform FROM assets WHERE id=?",
                         (aid,)).fetchone()
        if a is None:
            continue
        parts = [a["name"], a["original_name"], a["note"], a["manual_prompt"], a["manual_platform"]]
        parts += [r[0] for r in conn.execute(
            "SELECT t.name FROM tags t JOIN asset_tags x ON x.tag_id=t.id WHERE x.asset_id=?", (aid,))]
        m = conn.execute("SELECT fields_json FROM asset_meta WHERE asset_id=?", (aid,)).fetchone()
        if m:
            parts += [f["value"] for f in json.loads(m[0]) if f["field"] in SEARCH_FIELDS]
        conn.execute("UPDATE assets SET search_text=? WHERE id=?", ("\n".join(p for p in parts if p).lower(), aid))


# ---------------------------------------------------------------- 查询

def folder_subtree(conn: sqlite3.Connection, folder_id: int) -> list[int]:
    return [r[0] for r in conn.execute(
        "WITH RECURSIVE t(id) AS (SELECT ? UNION ALL SELECT f.id FROM folders f JOIN t ON f.parent_id=t.id) "
        "SELECT id FROM t", (folder_id,))]


SORTS = {"imported": "imported_at", "name": "name COLLATE NOCASE", "size": "size"}


def query_assets(scope: str = "all", q: str = "", kind: str = "", favorite: bool = False,
                 sort: str = "imported", order: str = "desc", offset: int = 0, limit: int = 100) -> dict:
    conn = db.connect()
    where, args = [], []
    if scope == "trash":
        where.append("deleted_at IS NOT NULL")
    else:
        where.append("deleted_at IS NULL")
        if scope == "inbox":
            where.append("folder_id IS NULL")
        elif scope == "favorites":
            where.append("favorite=1")
        elif scope.startswith("folder:"):
            ids = folder_subtree(conn, int(scope.split(":", 1)[1]))
            where.append(f"folder_id IN ({','.join('?' * len(ids))})")
            args += ids
    if kind in ("image", "video"):
        where.append("kind=?")
        args.append(kind)
    if favorite:
        where.append("favorite=1")
    # ponytail: 子串全表扫描，1 万条约数毫秒；到数十万条再换 FTS5 trigram
    for term in q.lower().split():
        where.append("instr(search_text, ?) > 0")
        args.append(term)
    sql_where = " AND ".join(where)
    col = SORTS.get(sort, "imported_at")
    direction = "ASC" if order == "asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM assets WHERE {sql_where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT {LIST_COLS} FROM assets WHERE {sql_where} ORDER BY {col} {direction}, id LIMIT ? OFFSET ?",
        [*args, max(1, min(limit, 500)), max(0, offset)],
    ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


def asset_ids(scope: str, q: str, kind: str, favorite: bool) -> list[str]:
    """当前筛选下全部 ID（用于“全选”）。"""
    res = query_assets(scope, q, kind, favorite, limit=500, offset=0)
    out = [i["id"] for i in res["items"]]
    offset = 500
    while offset < res["total"]:
        out += [i["id"] for i in query_assets(scope, q, kind, favorite, offset=offset, limit=500)["items"]]
        offset += 500
    return out


def get_asset(asset_id: str) -> dict | None:
    conn = db.connect()
    a = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if a is None:
        return None
    d = dict(a)
    d.pop("search_text")
    d["tags"] = [r[0] for r in conn.execute(
        "SELECT t.name FROM tags t JOIN asset_tags x ON x.tag_id=t.id WHERE x.asset_id=? ORDER BY t.name", (asset_id,))]
    m = conn.execute("SELECT * FROM asset_meta WHERE asset_id=?", (asset_id,)).fetchone()
    raw = json.loads(m["raw_json"]) if m else []
    d["fields"] = json.loads(m["fields_json"]) if m else []
    d["warnings"] = json.loads(m["warnings_json"]) if m else []
    d["raw"] = [{**r, "base64": None, "bytes": len(r["base64"]) * 3 // 4} if "base64" in r else r for r in raw]
    d["workflows"] = [k for k in ("workflow", "prompt") if _raw_json_text(raw, k)]
    d["path"] = str(PATHS.original(a["rel_path"]))
    d["folder_path"] = folder_path(conn, a["folder_id"])
    return d


def _raw_json_text(raw: list[dict], keyword: str) -> str | None:
    for r in raw:
        if (r.get("keyword") or "").lower() == keyword and r.get("text"):
            try:
                obj = json.loads(r["text"])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return r["text"]
    return None


def workflow_json(asset_id: str, keyword: str) -> str | None:
    m = db.connect().execute("SELECT raw_json FROM asset_meta WHERE asset_id=?", (asset_id,)).fetchone()
    return _raw_json_text(json.loads(m[0]), keyword) if m else None


def raw_metadata(asset_id: str) -> list[dict]:
    m = db.connect().execute("SELECT raw_json FROM asset_meta WHERE asset_id=?", (asset_id,)).fetchone()
    return json.loads(m[0]) if m else []


def folder_path(conn: sqlite3.Connection, folder_id: int | None) -> str:
    names = []
    while folder_id is not None:
        f = conn.execute("SELECT name, parent_id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if f is None:
            break
        names.append(f["name"])
        folder_id = f["parent_id"]
    return " / ".join(reversed(names))


def sidebar() -> dict:
    conn = db.connect()
    folders = [dict(r) for r in conn.execute("SELECT id, parent_id, name, sort_order FROM folders ORDER BY sort_order, id")]
    counts = {r[0]: r[1] for r in conn.execute(
        "SELECT folder_id, COUNT(*) FROM assets WHERE deleted_at IS NULL AND folder_id IS NOT NULL GROUP BY folder_id")}
    for f in folders:
        f["count"] = counts.get(f["id"], 0)
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "folders": folders,
        "counts": {
            "all": one("SELECT COUNT(*) FROM assets WHERE deleted_at IS NULL"),
            "inbox": one("SELECT COUNT(*) FROM assets WHERE deleted_at IS NULL AND folder_id IS NULL"),
            "favorites": one("SELECT COUNT(*) FROM assets WHERE deleted_at IS NULL AND favorite=1"),
            "trash": one("SELECT COUNT(*) FROM assets WHERE deleted_at IS NOT NULL"),
        },
        "tags": [r[0] for r in conn.execute(
            "SELECT t.name FROM tags t WHERE EXISTS (SELECT 1 FROM asset_tags x WHERE x.tag_id=t.id) ORDER BY t.name")],
        "pending_thumbs": one("SELECT COUNT(*) FROM assets WHERE thumb_state=0"),
    }


# ---------------------------------------------------------------- 编辑

def _tag_id(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0]


def clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = t.strip().lstrip("#").strip()
        if t and t not in out:
            out.append(t[:60])
    return out


def update_asset(asset_id: str, data: dict) -> None:
    conn = db.connect()
    with conn:
        for key in ("name", "note", "manual_prompt", "manual_platform"):
            if key in data and data[key] is not None:
                value = str(data[key])
                if key == "name":
                    value = value.strip()
                    if not value:
                        raise ValueError("名称不能为空")
                conn.execute(f"UPDATE assets SET {key}=? WHERE id=?", (value, asset_id))
        if data.get("favorite") is not None:
            conn.execute("UPDATE assets SET favorite=? WHERE id=?", (1 if data["favorite"] else 0, asset_id))
        if "folder_id" in data:
            _check_folder(conn, data["folder_id"])
            conn.execute("UPDATE assets SET folder_id=? WHERE id=?", (data["folder_id"], asset_id))
        if data.get("tags") is not None:
            conn.execute("DELETE FROM asset_tags WHERE asset_id=?", (asset_id,))
            for t in clean_tags(data["tags"]):
                conn.execute("INSERT OR IGNORE INTO asset_tags VALUES (?,?)", (asset_id, _tag_id(conn, t)))
        refresh_search(conn, [asset_id])


def _check_folder(conn: sqlite3.Connection, folder_id: int | None) -> None:
    if folder_id is not None and not conn.execute("SELECT 1 FROM folders WHERE id=?", (folder_id,)).fetchone():
        raise ValueError("目标文件夹不存在")


def batch(ids: list[str], action: str, folder_id: int | None = None, tags: list[str] | None = None,
          value: bool | None = None) -> int:
    conn = db.connect()
    ids = list(dict.fromkeys(ids))
    ph = ",".join("?" * len(ids))
    if not ids:
        return 0
    if action == "purge":
        return purge(ids)
    with conn:
        if action == "move":
            _check_folder(conn, folder_id)
            conn.execute(f"UPDATE assets SET folder_id=? WHERE id IN ({ph})", (folder_id, *ids))
        elif action in ("tag_add", "tag_remove"):
            for t in clean_tags(tags or []):
                tid = _tag_id(conn, t)
                if action == "tag_add":
                    conn.executemany("INSERT OR IGNORE INTO asset_tags VALUES (?,?)", [(i, tid) for i in ids])
                else:
                    conn.execute(f"DELETE FROM asset_tags WHERE tag_id=? AND asset_id IN ({ph})", (tid, *ids))
            refresh_search(conn, ids)
        elif action == "favorite":
            conn.execute(f"UPDATE assets SET favorite=? WHERE id IN ({ph})", (1 if value else 0, *ids))
        elif action == "trash":
            conn.execute(f"UPDATE assets SET deleted_at=? WHERE deleted_at IS NULL AND id IN ({ph})", (time.time(), *ids))
        elif action == "restore":
            conn.execute(f"UPDATE assets SET deleted_at=NULL WHERE id IN ({ph})", ids)
        else:
            raise ValueError(f"未知操作：{action}")
    return len(ids)


def purge(ids: list[str]) -> int:
    """彻底删除（只允许回收站里的素材）：先删记录，再删文件。"""
    conn = db.connect()
    ph = ",".join("?" * len(ids))
    with FILE_LOCK:
        rows = conn.execute(f"SELECT id, rel_path FROM assets WHERE deleted_at IS NOT NULL AND id IN ({ph})",
                            ids).fetchall()
        with conn:
            conn.executemany("DELETE FROM assets WHERE id=?", [(r["id"],) for r in rows])
        for r in rows:
            shutil.rmtree(PATHS.original(r["rel_path"]).parent, ignore_errors=True)
            PATHS.thumb(r["id"]).unlink(missing_ok=True)
    return len(rows)


def empty_trash() -> int:
    return purge([r[0] for r in db.connect().execute("SELECT id FROM assets WHERE deleted_at IS NOT NULL")])


# ---------------------------------------------------------------- 文件夹

def create_folder(name: str, parent_id: int | None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("名称不能为空")
    conn = db.connect()
    with conn:
        _check_folder(conn, parent_id)
        order = conn.execute("SELECT COALESCE(MAX(sort_order)+1, 0) FROM folders WHERE parent_id IS ?",
                             (parent_id,)).fetchone()[0]
        return conn.execute("INSERT INTO folders(parent_id, name, sort_order, created_at) VALUES (?,?,?,?)",
                            (parent_id, name, order, time.time())).lastrowid


def rename_folder(folder_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("名称不能为空")
    conn = db.connect()
    with conn:
        conn.execute("UPDATE folders SET name=? WHERE id=?", (name, folder_id))


def move_folder(folder_id: int, direction: int) -> None:
    """与同级相邻文件夹交换顺序。"""
    conn = db.connect()
    with conn:
        f = conn.execute("SELECT parent_id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if f is None:
            raise ValueError("文件夹不存在")
        sibs = [r[0] for r in conn.execute("SELECT id FROM folders WHERE parent_id IS ? ORDER BY sort_order, id",
                                           (f["parent_id"],))]
        i = sibs.index(folder_id)
        j = i + (1 if direction > 0 else -1)
        if 0 <= j < len(sibs):
            sibs[i], sibs[j] = sibs[j], sibs[i]
        conn.executemany("UPDATE folders SET sort_order=? WHERE id=?", [(n, fid) for n, fid in enumerate(sibs)])


def folder_usage(folder_id: int) -> dict:
    conn = db.connect()
    ids = folder_subtree(conn, folder_id)
    ph = ",".join("?" * len(ids))
    n = conn.execute(f"SELECT COUNT(*) FROM assets WHERE folder_id IN ({ph})", ids).fetchone()[0]
    return {"assets": n, "subfolders": len(ids) - 1}


def delete_folder(folder_id: int, move_to_inbox: bool) -> int:
    """非空文件夹必须显式 move_to_inbox=True；素材（含回收站里的）移到待整理，绝不删除素材。"""
    conn = db.connect()
    ids = folder_subtree(conn, folder_id)
    ph = ",".join("?" * len(ids))
    usage = folder_usage(folder_id)
    if (usage["assets"] or usage["subfolders"]) and not move_to_inbox:
        raise ValueError("文件夹非空，需要确认将素材移至待整理")
    with conn:
        moved = conn.execute(f"UPDATE assets SET folder_id=NULL WHERE folder_id IN ({ph})", ids).rowcount
        for fid in reversed(ids):  # 子节点在后，逆序删除满足外键
            conn.execute("DELETE FROM folders WHERE id=?", (fid,))
    return moved


# ---------------------------------------------------------------- 导出

def export_assets(ids: list[str], target_dir: Path) -> dict:
    """复制原文件到 target_dir，同名自动编号，复制后校验哈希。"""
    conn = db.connect()
    target_dir.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    for aid in dict.fromkeys(ids):
        a = conn.execute("SELECT name, ext, rel_path, sha256 FROM assets WHERE id=?", (aid,)).fetchone()
        if a is None:
            continue
        name = a["name"] if a["name"].lower().endswith(a["ext"]) else a["name"] + a["ext"]
        try:
            dest = unique_path(target_dir, safe_filename(name))
            shutil.copy2(PATHS.original(a["rel_path"]), dest)
            if sha256_file(dest) != a["sha256"]:
                raise OSError("导出文件校验失败")
            done.append(dest.name)
        except OSError as e:
            failed.append(f"{name}：{e}")
    return {"dir": str(target_dir), "exported": done, "failed": failed}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
