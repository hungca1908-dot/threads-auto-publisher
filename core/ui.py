"""Thành phần giao diện dùng chung cho các trang."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import constants as C
from core import planner, store

STATUS_COLORS = {
    C.ST_DRAFT: "gray",
    C.ST_PENDING: "orange",
    C.ST_PUBLISHING: "blue",
    C.ST_PUBLISHED: "green",
    C.ST_FAILED: "red",
}


def page_header(title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def status_badge(status: str) -> None:
    st.badge(
        C.STATUS_LABELS.get(status, status),
        icon=C.STATUS_ICONS.get(status, ":material/help:"),
        color=STATUS_COLORS.get(status, "gray"),
    )


def fmt_dt(value: str | datetime | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    except Exception:
        return str(value)
    return dt.strftime("%H:%M · %d/%m/%Y")


def relative(iso_value: str | None) -> str:
    if not iso_value:
        return "—"
    try:
        delta = (datetime.fromisoformat(iso_value) - planner.now_vn()).total_seconds()
    except Exception:
        return "—"
    if delta < 0:
        minutes = int(-delta // 60)
        return f"trễ {minutes} phút" if minutes else "vừa tới giờ"
    hours, rem = divmod(int(delta), 3600)
    minutes = rem // 60
    if hours >= 24:
        return f"{hours // 24} ngày {hours % 24} giờ"
    return f"{hours} giờ {minutes} phút" if hours else f"{minutes} phút"


def sidebar_status() -> None:
    data = store.load_data()
    settings = data.get("settings", {})
    posts = data.get("posts", [])
    pending = sum(1 for p in posts if p.get("status") == C.ST_PENDING)
    drafts = sum(1 for p in posts if p.get("status") == C.ST_DRAFT)
    failed = sum(1 for p in posts if p.get("status") == C.ST_FAILED)
    worker = data.get("worker", {})
    heartbeat = worker.get("heartbeat", "")
    age = None
    if heartbeat:
        try:
            age = (planner.now_vn() - datetime.fromisoformat(heartbeat)).total_seconds()
        except Exception:
            age = None

    st.sidebar.subheader(":material/monitor_heart: Trạng thái")
    if not settings.get("enabled", True):
        st.sidebar.badge("Đang tạm dừng", icon=":material/pause_circle:", color="gray")
    elif age is not None and age < 60:
        st.sidebar.badge("Worker đang chạy", icon=":material/bolt:", color="green")
    else:
        st.sidebar.badge("Worker chưa chạy", icon=":material/warning:", color="orange")

    if settings.get("enabled", True):
        if st.sidebar.button("Tạm dừng đăng bài", icon=":material/pause:", width="stretch"):
            _set_enabled(False)
            st.rerun()
    else:
        if st.sidebar.button("Tiếp tục đăng bài", icon=":material/play_arrow:", type="primary", width="stretch"):
            _set_enabled(True)
            st.rerun()

    st.sidebar.caption(f"Lưu trữ: {store.storage_mode()}")
    st.sidebar.caption(f":material/schedule: Chờ **{pending}** · :material/edit_note: Nháp **{drafts}** · Lỗi **{failed}**")
    nxt = planner.next_post(data)
    if nxt:
        st.sidebar.caption(f":material/notifications: Bài tới: **{fmt_dt(nxt['run_at'])}** ({relative(nxt['run_at'])})")
    st.sidebar.caption(f":material/link: {len(data.get('resources', {}).get('links', []))} link · "
                       f":material/image: {len(data.get('resources', {}).get('images', []))} ảnh")
    if not store.get_token(data):
        st.sidebar.warning("Chưa có access token", icon=":material/key_off:")

    days_left = token_days_left(settings)
    if days_left is not None and days_left <= 7:
        st.sidebar.warning(f"Token còn {max(days_left, 0)} ngày – vào Cài đặt để gia hạn.", icon=":material/key:")

    conflicts = planner.find_conflicts(data)
    if conflicts:
        st.sidebar.warning(f"{len(conflicts)} khung giờ bị trùng bài.", icon=":material/content_copy:")

    st.sidebar.caption(f"Giờ VN: {planner.now_vn():%H:%M:%S · %d/%m/%Y}")


def _set_enabled(enabled: bool) -> None:
    def mutate(d: dict) -> None:
        d.setdefault("settings", {})["enabled"] = enabled

    store.update_data(mutate)


def token_days_left(settings: dict) -> int | None:
    raw = settings.get("token_expires_at") or ""
    if not raw:
        return None
    try:
        expires = datetime.fromisoformat(str(raw)[:10]).date()
    except Exception:
        return None
    return (expires - planner.now_vn().date()).days



def log_panel(data: dict, limit: int = 12) -> None:
    logs = list(reversed(data.get("logs", [])))[:limit]
    if not logs:
        st.caption("Chưa có hoạt động nào.")
        return
    icons = {"info": ":material/info:", "warn": ":material/warning:", "error": ":material/error:"}
    for entry in logs:
        icon = icons.get(entry.get("level", "info"), ":material/info:")
        st.markdown(f"{icon} {entry.get('message', '')}")
        st.caption(fmt_dt(entry.get("ts")))
