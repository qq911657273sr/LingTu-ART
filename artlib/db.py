"""SQLite 访问：每线程一个连接，WAL 模式。"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES folders(id),
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    original_name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    ext TEXT NOT NULL,
    kind TEXT NOT NULL,              -- image | video
    container TEXT,
    size INTEGER NOT NULL,
    width INTEGER, height INTEGER, duration REAL, fps REAL,
    playable TEXT,                   -- ok | limited | none | NULL(未知)
    folder_id INTEGER REFERENCES folders(id),
    favorite INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    manual_prompt TEXT NOT NULL DEFAULT '',
    manual_platform TEXT NOT NULL DEFAULT '',
    source_mtime REAL,
    imported_at REAL NOT NULL,
    deleted_at REAL,
    thumb_state INTEGER NOT NULL DEFAULT 0,   -- 0 未生成 | 1 成功 | 2 失败
    note_sys TEXT NOT NULL DEFAULT '',        -- 系统提示（封面失败原因、元数据警告）
    search_text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_assets_folder ON assets(folder_id);
CREATE INDEX IF NOT EXISTS ix_assets_imported ON assets(deleted_at, imported_at);
CREATE TABLE IF NOT EXISTS asset_meta (
    asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    raw_json TEXT NOT NULL,          -- FML 第 1 层原始条目（原样）
    fields_json TEXT NOT NULL,       -- FML 第 2 层解析字段
    warnings_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS asset_tags (
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, tag_id)
);
CREATE INDEX IF NOT EXISTS ix_asset_tags_tag ON asset_tags(tag_id);
"""

DEFAULT_CATEGORIES = ("人物", "场景", "道具", "其他")

_local = threading.local()
_db_path: Path | None = None


def init(path: Path) -> None:
    global _db_path
    _db_path = path
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0] == 0:
        with conn:
            for i, name in enumerate(DEFAULT_CATEGORIES):
                conn.execute(
                    "INSERT INTO folders(parent_id, name, sort_order, created_at) VALUES (NULL, ?, ?, ?)",
                    (name, i, time.time()),
                )


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == _db_path:
        return conn
    conn = open_db(_db_path)
    _local.conn, _local.path = conn, _db_path
    return conn


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn
