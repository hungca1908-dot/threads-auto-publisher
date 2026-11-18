"""Threads Auto Publisher – điểm khởi chạy Streamlit.

Chạy trên máy:      streamlit run threads_app.py
Triển khai cloud:   đẩy cả thư mục lên GitHub -> Streamlit Community Cloud
"""

from __future__ import annotations

import os

import streamlit as st

from core import store, ui, worker

st.set_page_config(
    page_title="Threads Auto Publisher",
    page_icon="🧵",
    layout="wide",
)

# Đưa secrets vào biến môi trường để thread chạy ngầm cũng đọc được.
for _key in ("THREADS_ACCESS_TOKEN", "IMGBB_API_KEY", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
    if _key not in os.environ:
        try:
            _value = st.secrets.get(_key, "")
        except Exception:
            _value = ""
        if _value:
            os.environ[_key] = str(_value)


@st.cache_resource
def _bootstrap() -> bool:
    store.load_data()          # khởi tạo dữ liệu lần đầu
    worker.start_background()  # worker đăng bài chạy ngầm 24/7
    return True


_bootstrap()

pages = [
    st.Page("app_pages/tong_quan.py", title="Tổng quan", icon=":material/dashboard:", default=True),
    st.Page("app_pages/soan_bai.py", title="Soạn bài", icon=":material/edit_note:"),
    st.Page("app_pages/lich_dang.py", title="Lịch đăng", icon=":material/calendar_month:"),
    st.Page("app_pages/chan_doan.py", title="Chẩn đoán", icon=":material/health_and_safety:"),
    st.Page("app_pages/noi_dung.py", title="Thư viện nội dung", icon=":material/auto_awesome:"),
    st.Page("app_pages/tai_nguyen.py", title="Tài nguyên", icon=":material/folder_open:"),
    st.Page("app_pages/cai_dat.py", title="Cài đặt", icon=":material/settings:"),
]

page = st.navigation(pages, position="sidebar", expanded=True)
ui.sidebar_status()
page.run()
