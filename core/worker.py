"""Tiến trình chạy ngầm: đăng bài đúng giờ, thử lại khi lỗi, tự bổ sung lịch.

Có cơ chế "lease" để chỉ một tiến trình đăng bài tại một thời điểm, tránh
trường hợp vừa chạy app Streamlit vừa chạy worker bên ngoài mà đăng trùng.
"""

from __future__ import annotations

import os
import platform
import threading
import time
import uuid
from datetime import datetime, timedelta

from core import constants as C
from core import planner, store, threads_api

LEASE_SECONDS = 90
TICK_SECONDS = 15
STUCK_MINUTES = 20          # bài "đang đăng" quá lâu coi như bị gián đoạn
MAX_POSTS_PER_TICK = 3      # tránh đăng dồn hàng loạt khi mở app sau nhiều giờ
HOST = platform.node()
OWNER = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"

_started = threading.Event()
_tick_lock = threading.Lock()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _owner_alive(owner: str, host: str) -> bool:
    if host and host != HOST:
        return True  # tiến trình ở máy khác: chỉ dựa vào thời gian heartbeat
    try:
        pid = int(str(owner).split("-")[0])
    except Exception:
        return True
    return _pid_alive(pid)


def _lease_available(data: dict) -> bool:
    worker = data.get("worker") or {}
    owner = worker.get("owner")
    if owner in ("", None, OWNER):
        return True
    try:
        age = (planner.now_vn() - datetime.fromisoformat(worker.get("heartbeat", ""))).total_seconds()
    except Exception:
        return True
    if age > LEASE_SECONDS:
        return True
    # Chủ sở hữu cũ đã tắt (ví dụ vừa restart app) -> tiếp quản ngay.
    if not _owner_alive(str(owner), str(worker.get("host", ""))):
        return True
    return False


def _beat() -> dict:
    return {
        "owner": OWNER,
        "host": HOST,
        "heartbeat": planner.now_vn().isoformat(timespec="seconds"),
    }


def _apply(pid: str, mutator) -> None:
    """Cập nhật nhanh một bài theo id, khoá trong thời gian rất ngắn."""

    def mutate(data: dict) -> None:
        for post in data.get("posts", []):
            if post.get("id") == pid:
                mutator(post)
                return

    store.update_data(mutate)


def publish_one(data: dict, post: dict, token: str, user_id: str) -> bool:
    """Đăng một bài và cập nhật trạng thái ngay vào dữ liệu.

    Không giữ khoá dữ liệu trong lúc gọi mạng, và luôn cập nhật lại trên bản
    dữ liệu mới nhất để không ghi đè thay đổi người dùng vừa thực hiện.
    """
    pid = post.get("id", "")
    text = post.get("text", "")
    images = post.get("image_urls", [])
    _apply(pid, lambda p: p.update({"status": C.ST_PUBLISHING}))

    try:
        ok, message = threads_api.create_and_publish(user_id, token, text, images)
    except Exception as exc:  # không để một bài làm chết cả worker
        ok, message = False, f"Lỗi không xác định: {exc}"

    def finish(fresh: dict) -> None:
        target = next((p for p in fresh.get("posts", []) if p.get("id") == pid), None)
        if target is None:
            return
        now = planner.now_vn()
        target["attempts"] = int(target.get("attempts", 0)) + 1
        if ok:
            target["status"] = C.ST_PUBLISHED
            target["last_error"] = ""
            target["published_id"] = message.split("ID:")[-1].strip() if "ID:" in message else ""
            target["published_at"] = now.isoformat(timespec="seconds")
            store.add_log(fresh, f"Đã đăng bài {pid} – {message}")
            return

        target["last_error"] = message
        settings = fresh.get("settings", {})
        if target["attempts"] >= int(settings.get("max_attempts", 3)):
            target["status"] = C.ST_FAILED
            store.add_log(fresh, f"Bài {pid} lỗi sau {target['attempts']} lần: {message}", "error")
        else:
            delay = int(settings.get("retry_minutes", 20)) * target["attempts"]
            retry_at = now + timedelta(minutes=delay)
            target["status"] = C.ST_PENDING
            target["run_at"] = retry_at.isoformat(timespec="seconds")
            store.add_log(fresh, f"Bài {pid} sẽ thử lại lúc {retry_at:%H:%M}: {message}", "warn")

    store.update_data(finish)
    return ok


def recover_stuck(data: dict) -> int:
    """Bài kẹt ở trạng thái 'đang đăng' (app bị tắt giữa chừng) -> đánh dấu lỗi.

    Không tự đăng lại vì có thể bài đã lên Threads rồi, đăng lại sẽ bị trùng.
    """
    now = planner.now_vn()
    fixed = 0
    for post in data.get("posts", []):
        if post.get("status") != C.ST_PUBLISHING:
            continue
        try:
            started = datetime.fromisoformat(post.get("run_at") or post.get("created_at", ""))
        except Exception:
            started = now - timedelta(hours=2)
        if (now - started).total_seconds() < STUCK_MINUTES * 60:
            continue
        post["status"] = C.ST_FAILED
        post["last_error"] = "Tiến trình đăng bị gián đoạn. Kiểm tra Threads trước khi đăng lại."
        fixed += 1
    if fixed:
        store.add_log(data, f"Đã xử lý {fixed} bài bị kẹt ở trạng thái đang đăng.", "warn")
    return fixed


def process_due(data: dict, force: bool = False) -> int:
    """Đăng các bài đã tới giờ (hoặc toàn bộ nếu force=True)."""
    settings = data.get("settings", {})
    token = store.get_token(data)
    user_id = store.get_user_id(data)
    if not token:
        return 0

    now = planner.now_vn()
    published = 0
    for post in sorted(data.get("posts", []), key=lambda p: p.get("run_at", "")):
        if post.get("status") != C.ST_PENDING:
            continue
        try:
            due = datetime.fromisoformat(post["run_at"])
        except Exception:
            due = now
        if not force and due > now:
            continue
        if int(post.get("attempts", 0)) >= int(settings.get("max_attempts", 3)):
            _apply(post.get("id", ""), lambda p: p.update({"status": C.ST_FAILED}))
            continue

        if publish_one(data, post, token, user_id):
            published += 1
        limit = max(1, int(settings.get("max_posts_per_tick", MAX_POSTS_PER_TICK)))
        if not force and published >= limit:
            store.update_data(
                lambda d: store.add_log(
                    d, "Đã chạm giới hạn số bài mỗi lượt, phần còn lại sẽ đăng ở lượt sau.", "warn"
                )
            )
            break
        time.sleep(3)  # giãn cách giữa các bài để tránh rate limit

    return published


def tick() -> None:
    if not _tick_lock.acquire(blocking=False):
        return  # lượt trước còn đang chạy
    try:
        data = store.load_data()
        settings = data.get("settings", {})
        if not settings.get("enabled", True):
            return
        if not _lease_available(data):
            return

        # Bước nhẹ: phục hồi bài kẹt + bổ sung lịch, giữ khoá thật ngắn.
        def prepare(fresh: dict) -> None:
            recover_stuck(fresh)
            planner.ensure_refill(fresh)
            fresh["worker"] = _beat()

        try:
            data = store.update_data(prepare)
        except Exception:
            data = store.load_data()

        process_due(data)

        def heartbeat(fresh: dict) -> None:
            fresh["worker"] = _beat()

        store.update_data(heartbeat)
    finally:
        _tick_lock.release()


def run_forever() -> None:
    while True:
        try:
            tick()
        except Exception as exc:  # worker không được phép chết
            try:
                data = store.load_data()
                store.add_log(data, f"Worker gặp lỗi: {exc}", "error")
                store.save_data(data)
            except Exception:
                pass
        time.sleep(TICK_SECONDS)


def start_background() -> bool:
    """Khởi động worker trong tiến trình Streamlit (chỉ chạy 1 lần / tiến trình)."""
    if _started.is_set():
        return True
    thread = threading.Thread(target=run_forever, name="threads-worker", daemon=True)
    thread.start()
    _started.set()
    return True
