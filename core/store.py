"""Lưu trữ dữ liệu: file JSON cục bộ, hoặc Upstash Redis khi chạy trên cloud.

Thứ tự ưu tiên:
1. Upstash Redis (nếu có UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
   trong st.secrets hoặc biến môi trường) -> dữ liệu không mất khi cloud restart.
2. File data/threads_data.json -> dùng khi chạy trên máy, hoặc VPS có ổ đĩa.

Có tự động sao lưu theo ngày và phục hồi khi file dữ liệu bị hỏng.
"""

from __future__ import annotations

import json
import os
import random
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from core import constants as C

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DATA_FILE = Path(os.environ.get("THREADS_DATA_FILE", DATA_DIR / "threads_data.json"))
BACKUP_DIR = Path(os.environ.get("THREADS_BACKUP_DIR", DATA_FILE.parent / "backups"))
RESOURCE_SEED = DATA_DIR / "resources.json"
REDIS_KEY = os.environ.get("THREADS_REDIS_KEY", "threads_auto_publisher:data")
MAX_BACKUPS = 14

_LOCK = threading.RLock()

DEFAULTS: dict[str, Any] = {
    "settings": dict(C.DEFAULT_SETTINGS),
    "resources": {
        "links": [],
        "images": [],
        "link_deck": [],
        "link_cursor": 0,
        "image_deck": [],
        "image_cursor": 0,
    },
    "templates": [],
    "posts": [],
    "logs": [],
    "worker": {"owner": "", "heartbeat": ""},
    "meta": {"created_at": "", "updated_at": "", "version": 2, "last_backup": ""},
}


# ---------------------------------------------------------------- secrets
SECRETS_FILE = APP_DIR / ".streamlit" / "secrets.toml"
_file_secrets: dict[str, str] = {}
_file_stamp: float = -1.0


def _secrets_from_file() -> dict[str, str]:
    """Đọc secrets.toml để worker độc lập (ngoài Streamlit) cũng dùng được."""
    global _file_secrets, _file_stamp
    try:
        if not SECRETS_FILE.exists():
            return {}
        stamp = SECRETS_FILE.stat().st_mtime
        if stamp != _file_stamp:
            import tomllib

            raw = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            _file_secrets = {k: str(v) for k, v in raw.items() if isinstance(v, (str, int, float))}
            _file_stamp = stamp
        return _file_secrets
    except Exception:
        return {}


def _secret(name: str) -> str:
    """Đọc secret từ st.secrets, biến môi trường hoặc .streamlit/secrets.toml."""
    try:
        import streamlit as st

        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    env = os.environ.get(name, "").strip()
    if env:
        return env
    return str(_secrets_from_file().get(name, "")).strip()


def _redis_config() -> tuple[str, str] | None:
    url = _secret("UPSTASH_REDIS_REST_URL")
    token = _secret("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return url.rstrip("/"), token
    return None


def _redis_get() -> dict | None:
    cfg = _redis_config()
    if not cfg:
        return None
    url, token = cfg
    res = requests.get(f"{url}/get/{REDIS_KEY}", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    payload = res.json()
    raw = payload.get("result")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def _redis_set(data: dict) -> bool:
    cfg = _redis_config()
    if not cfg:
        return False
    url, token = cfg
    body = json.dumps(data, ensure_ascii=False)
    res = requests.post(
        f"{url}/set/{REDIS_KEY}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=body.encode("utf-8"),
        timeout=20,
    )
    return res.ok


# ---------------------------------------------------------------- seed
def _seed_resources() -> tuple[list[str], list[dict]]:
    if RESOURCE_SEED.exists():
        try:
            payload = json.loads(RESOURCE_SEED.read_text(encoding="utf-8"))
            return payload.get("links", []), payload.get("images", [])
        except Exception:
            pass
    return [], []


def default_data() -> dict:
    links, images = _seed_resources()
    templates = [
        {"id": tid, "theme": theme, "text": text, "enabled": True}
        for tid, theme, text in C.DEFAULT_TEMPLATES
    ]
    data = json.loads(json.dumps(DEFAULTS))
    data["resources"]["links"] = list(links)
    data["resources"]["images"] = list(images)
    data["resources"]["link_deck"] = _shuffled(links)
    data["resources"]["image_deck"] = _shuffled([i["url"] for i in images])
    data["templates"] = templates
    data["meta"]["created_at"] = datetime.now().isoformat(timespec="seconds")
    return data


def _shuffled(items: list) -> list:
    pool = list(items)
    random.shuffle(pool)
    return pool


def _deep_merge(base: dict, incoming: dict) -> dict:
    """Bổ sung key mới cho dữ liệu cũ mà không làm mất dữ liệu người dùng."""
    out = dict(base)
    for key, value in incoming.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _normalise(data: dict) -> dict:
    merged = _deep_merge(DEFAULTS, data if isinstance(data, dict) else {})
    if not merged.get("templates"):
        merged["templates"] = [
            {"id": tid, "theme": theme, "text": text, "enabled": True}
            for tid, theme, text in C.DEFAULT_TEMPLATES
        ]
    return merged


# ---------------------------------------------------------------- sao lưu
def list_backups(limit: int | None = None) -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("threads_data_*.json"), key=lambda p: p.name, reverse=True)
    return files[:limit] if limit else files


def _maybe_daily_backup() -> None:
    """Mỗi ngày giữ lại một bản sao của dữ liệu trước khi ghi đè."""
    try:
        if not DATA_FILE.exists():
            return
        today = datetime.now().strftime("%Y%m%d")
        if any(p.name.startswith(f"threads_data_{today}") for p in list_backups(limit=30)):
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (BACKUP_DIR / f"threads_data_{stamp}.json").write_bytes(DATA_FILE.read_bytes())
        for old in list_backups()[MAX_BACKUPS:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def create_backup(label: str = "manual") -> Path | None:
    """Tạo bản sao lưu ngay (dùng được cả khi đang lưu trên Redis)."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = BACKUP_DIR / f"threads_data_{stamp}_{label}.json"
        data = load_data()
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        for old in list_backups()[MAX_BACKUPS:]:
            old.unlink(missing_ok=True)
        return target
    except Exception:
        return None


def restore_backup(path: str | Path) -> bool:
    """Khôi phục dữ liệu từ một bản sao lưu."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "posts" not in payload:
            return False
        create_backup("before_restore")
        save_data(_normalise(payload))
        return True
    except Exception:
        return False


def backup_age_hours() -> float | None:
    files = list_backups(limit=1)
    if not files:
        return None
    try:
        return (datetime.now() - datetime.fromtimestamp(files[0].stat().st_mtime)).total_seconds() / 3600
    except Exception:
        return None


# ---------------------------------------------------------------- API
def storage_mode() -> str:
    return "Upstash Redis (bền vững trên cloud)" if _redis_config() else "File JSON cục bộ"


def _read_file() -> dict | None:
    if not DATA_FILE.exists():
        return None
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    # File hỏng: thử lần lượt các bản sao lưu mới nhất.
    for backup in list_backups(limit=5):
        try:
            payload = json.loads(backup.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return None


def load_data() -> dict:
    with _LOCK:
        try:
            remote = _redis_get()
        except Exception:
            remote = None
        if remote:
            return _normalise(remote)

        payload = _read_file()
        if payload is not None:
            return _normalise(payload)

        data = default_data()
        save_data(data)
        return data


def save_data(data: dict) -> None:
    with _LOCK:
        data.setdefault("meta", {})
        data["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if _redis_set(data):
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if data.get("settings", {}).get("daily_backup", True):
            _maybe_daily_backup()
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)


def update_data(mutator: Callable[[dict], Any]) -> dict:
    """Đọc – sửa – ghi trong một lần khoá.

    Dùng cho worker để tránh việc một lần ghi khác chen vào giữa lúc đang
    xử lý bài, khiến bài vừa đăng bị "sống lại" hoặc mất khỏi hàng đợi.
    """
    with _LOCK:
        data = load_data()
        mutator(data)
        save_data(data)
        return data


# ---------------------------------------------------------------- tiện ích
def add_log(data: dict, message: str, level: str = "info") -> None:
    data.setdefault("logs", []).append(
        {"ts": datetime.now().isoformat(timespec="seconds"), "level": level, "message": message}
    )
    data["logs"] = data["logs"][-300:]


def get_token(data: dict) -> str:
    """Token ưu tiên lấy từ secrets (an toàn), sau đó tới cấu hình đã lưu."""
    return _secret("THREADS_ACCESS_TOKEN") or str(data.get("settings", {}).get("access_token", "")).strip()


def get_imgbb_key(data: dict) -> str:
    return _secret("IMGBB_API_KEY") or str(data.get("settings", {}).get("imgbb_key", "")).strip()


def get_user_id(data: dict) -> str:
    return str(data.get("settings", {}).get("user_id", "me")).strip() or "me"
