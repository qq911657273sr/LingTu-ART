"""配置与目录布局。config.json 与程序放在一起；素材库目录可迁移。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
CONFIG_PATH = Path(os.environ.get("ARTLIB_CONFIG") or APP_DIR / "config.json").resolve()

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8765,
    "data_dir": "data",
    "backup_dir": "backups",
    "export_dir": str(Path.home() / "Downloads" / "美术素材导出"),
    "open_browser": True,
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text("utf-8")))
        except ValueError as e:
            raise SystemExit(f"配置文件 {CONFIG_PATH} 不是有效的 JSON：{e}\n请修正或删除该文件后重新启动。")
    else:
        save(cfg)
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, CONFIG_PATH)


def resolve(p: str) -> Path:
    path = Path(p).expanduser()
    return (path if path.is_absolute() else CONFIG_PATH.parent / path).resolve()


@dataclass(frozen=True)
class Paths:
    data: Path

    @property
    def db(self) -> Path:
        return self.data / "library.db"

    @property
    def originals(self) -> Path:
        return self.data / "originals"

    @property
    def thumbs(self) -> Path:
        return self.data / "thumbs"

    @property
    def tmp(self) -> Path:
        return self.data / "tmp"

    def ensure(self) -> None:
        for d in (self.originals, self.thumbs, self.tmp):
            d.mkdir(parents=True, exist_ok=True)

    def original(self, rel_path: str) -> Path:
        p = (self.data / rel_path).resolve()
        if not p.is_relative_to(self.originals.resolve()):
            raise ValueError("素材路径不在素材库内")
        return p

    def thumb(self, asset_id: str) -> Path:
        return self.thumbs / asset_id[:2] / f"{asset_id}.webp"
