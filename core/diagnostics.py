"""Kiểm tra sức khoẻ hệ thống: token, lưu trữ, ảnh, hàng đợi."""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime

import requests

from core import constants as C
from core import planner, store


def environment() -> dict[str, str]:
    return {
        "Python": sys.version.split()[0],
        "Hệ điều hành": platform.platform(),
        "Thư mục dữ liệu": str(store.DATA_FILE),
        "Chế độ lưu trữ": store.storage_mode(),
    }


def check_storage() -> tuple[bool, str]:
    """Ghi thử một khoá nhỏ rồi đọc lại để chắc chắn lưu trữ hoạt động."""
    try:
        data = store.load_data()
        before = data.get("meta", {}).get("updated_at", "")
        data.setdefault("meta", {})["storage_check_at"] = planner.now_vn().isoformat(timespec="seconds")
        store.save_data(data)
        again = store.load_data()
        stamp = again.get("meta", {}).get("storage_check_at", "")
        if not stamp:
            return False, "Ghi được nhưng đọc lại không thấy dữ liệu."
        return True, f"Đọc/ghi OK (cập nhật trước đó: {before or '—'})."
    except Exception as exc:
        return False, f"Lỗi lưu trữ: {exc}"


def check_images(urls: list[str], limit: int = 25, timeout: int = 12) -> list[dict]:
    """Kiểm tra nhanh các URL ảnh có truy cập được không."""
    results: list[dict] = []
    for url in list(dict.fromkeys(urls))[:limit]:
        started = time.perf_counter()
        ok = False
        detail = ""
        try:
            res = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
            detail = f"HTTP {res.status_code}"
            content_type = res.headers.get("Content-Type", "")
            ok = res.ok and (content_type.startswith("image/") or not content_type)
            if ok and not content_type:
                detail += " (không rõ Content-Type)"
            res.close()
        except requests.RequestException as exc:
            detail = f"Lỗi mạng: {type(exc).__name__}"
        results.append({
            "url": url,
            "ok": ok,
            "detail": detail,
            "ms": int((time.perf_counter() - started) * 1000),
        })
    return results


def overdue_posts(data: dict) -> list[dict]:
    now = planner.now_vn()
    out = []
    for post in data.get("posts", []):
        if post.get("status") != C.ST_PENDING:
            continue
        try:
            if datetime.fromisoformat(post["run_at"]) < now:
                out.append(post)
        except Exception:
            continue
    return out


def health_summary(data: dict) -> dict:
    posts = data.get("posts", [])
    worker = data.get("worker") or {}
    heartbeat = worker.get("heartbeat", "")
    age = None
    if heartbeat:
        try:
            age = (planner.now_vn() - datetime.fromisoformat(heartbeat)).total_seconds()
        except Exception:
            age = None
    return {
        "enabled": bool(data.get("settings", {}).get("enabled", True)),
        "worker_age": age,
        "pending": sum(1 for p in posts if p.get("status") == C.ST_PENDING),
        "draft": sum(1 for p in posts if p.get("status") == C.ST_DRAFT),
        "failed": sum(1 for p in posts if p.get("status") == C.ST_FAILED),
        "stuck": sum(1 for p in posts if p.get("status") == C.ST_PUBLISHING),
        "overdue": len(overdue_posts(data)),
        "conflicts": planner.find_conflicts(data),
        "token": bool(store.get_token(data)),
        "max_attempts": int(data.get("settings", {}).get("max_attempts", 3)),
    }
