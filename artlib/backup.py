"""完整备份与恢复。

备份 = 一个 zip（不压缩，素材本身已压缩）：
  library.db    —— 用 SQLite 在线备份 API 得到的一致性快照（不是直接复制正在写入的文件）
  originals/... —— 快照中记录的全部原文件
  config.json   —— 当时的配置（仅供参考）
  manifest.json —— 文件清单与 SHA-256
缩略图不备份，恢复后自动重建。

恢复永远写入一个新的数据目录，不覆盖现有数据。
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

from . import config as cfgmod
from . import db, ai_edit
from .library import FILE_LOCK, sha256_file


def create_backup(data_dir: Path, backup_dir: Path, progress=lambda done, total: None) -> dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"素材库备份-{stamp}.zip"
    part = target.with_suffix(".zip.part")
    snap = backup_dir / f".snapshot-{stamp}.db"
    with ai_edit.LOCK, FILE_LOCK:
        src = db.open_db(data_dir / "library.db")
        dst = sqlite3.connect(snap)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        conn = sqlite3.connect(snap)
        rows = conn.execute("SELECT rel_path, sha256 FROM assets").fetchall()
        conn.close()
        manifest = {"created_at": stamp, "app": "art-library", "version": 1, "files": []}
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                z.write(snap, "library.db")
                if cfgmod.CONFIG_PATH.exists():
                    z.write(cfgmod.CONFIG_PATH, "config.json")
                for n, (rel, sha) in enumerate(rows, 1):
                    f = data_dir / rel
                    if f.is_file():
                        z.write(f, rel)
                        manifest["files"].append({"path": rel, "sha256": sha})
                    else:
                        manifest.setdefault("missing", []).append(rel)
                    progress(n, len(rows))
                for f in sorted((data_dir / 'ai-edit').rglob('*')):
                    if f.is_file() and f.suffix in ('.json', '.png'):
                        rel = f.relative_to(data_dir).as_posix()
                        z.write(f, rel)
                        manifest['files'].append({'path': rel, 'sha256': sha256_file(f)})
                z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
            part.replace(target)
        finally:
            snap.unlink(missing_ok=True)
            part.unlink(missing_ok=True)
    return {"path": str(target), "files": len(manifest["files"]), "missing": manifest.get("missing", []),
            "bytes": target.stat().st_size}


def list_backups(backup_dir: Path) -> list[dict]:
    if not backup_dir.is_dir():
        return []
    return [{"path": str(p), "name": p.name, "bytes": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)]


def restore_backup(zip_path: Path, target_dir: Path, progress=lambda done, total: None) -> dict:
    """把备份解压到一个新的（不存在或为空的）目录，并逐个校验哈希。"""
    if target_dir.exists() and any(target_dir.iterdir()):
        raise ValueError(f"目标目录不为空：{target_dir}")
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if "library.db" not in names or "manifest.json" not in names:
            raise ValueError("这不是本素材库生成的备份文件")
        manifest = json.loads(z.read("manifest.json"))
        target_dir.mkdir(parents=True, exist_ok=True)
        root = target_dir.resolve()
        files = manifest["files"]
        for n, entry in enumerate(files, 1):
            rel = entry["path"]
            dest = (root / rel).resolve()
            original = rel.startswith('originals/') and dest.is_relative_to(root / 'originals')
            ai_file = bool(re.fullmatch(r'ai-edit/(settings\.json|references/[a-f0-9]{32}\.png|jobs/[a-f0-9]{32}/(job\.json|result\.png|input-[0-7]\.png))', rel)) and dest.is_relative_to(root / 'ai-edit')
            if not original and not ai_file:
                raise ValueError(f"备份中包含非法路径：{rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(rel) as fin, open(dest, "wb") as fout:
                while chunk := fin.read(1 << 20):
                    fout.write(chunk)
            if sha256_file(dest) != entry["sha256"]:
                raise ValueError(f"文件校验失败：{rel}")
            progress(n, len(files))
        (target_dir / "library.db").write_bytes(z.read("library.db"))
    conn = sqlite3.connect(target_dir / "library.db")
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("备份中的数据库校验失败")
        with conn:
            conn.execute("UPDATE assets SET thumb_state=0")  # 缩略图不在备份中，重建
        count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    finally:
        conn.close()
    return {"dir": str(target_dir), "assets": count, "files": len(files), "missing": manifest.get("missing", [])}


if __name__ == "__main__":
    # 命令行：python -m artlib.backup restore <备份.zip> <新目录>
    if len(sys.argv) == 4 and sys.argv[1] == "restore":
        print(json.dumps(restore_backup(Path(sys.argv[2]), Path(sys.argv[3])), ensure_ascii=False, indent=1))
    else:
        print("用法：python -m artlib.backup restore <备份.zip> <新目录>")
