"""Iestatījumi: kur atrodas mapes. Saglabāti JSON failā lietotāja mapē."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PROCESSED_DIR_NAME = "Apstrādāti"
LOG_NAME = "žurnāls.csv"


def data_dir() -> Path:
    override = os.environ.get("KARTOTAJS_DATA")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Kartotajs"
    return Path.home() / ".kartotajs"


@dataclass
class Config:
    inbox: str = str(Path.home() / "Documents" / "Ienākošie")
    output: str = str(Path.home() / "Documents" / "Kārtotie")
    ocr: str = "auto"  # auto | vision | rapidocr

    @property
    def inbox_path(self) -> Path:
        return Path(self.inbox).expanduser()

    @property
    def output_path(self) -> Path:
        return Path(self.output).expanduser()

    @property
    def processed_path(self) -> Path:
        return self.inbox_path / PROCESSED_DIR_NAME

    @property
    def log_path(self) -> Path:
        return self.output_path / LOG_NAME

    @property
    def state_dir(self) -> Path:
        return data_dir()

    @classmethod
    def load(cls) -> "Config":
        path = data_dir() / "config.json"
        cfg = cls()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            for key in asdict(cfg):
                if isinstance(raw.get(key), str) and raw[key].strip():
                    setattr(cfg, key, raw[key].strip())
        return cfg

    def save(self) -> None:
        path = data_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_dirs(self) -> None:
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
