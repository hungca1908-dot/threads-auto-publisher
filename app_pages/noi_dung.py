import uuid

import streamlit as st

from core import constants as C
from core import content, store, ui

data = store.load_data()
templates = list(data.get("templates", []))
links = data.get("resources", {}).get("links", [])

ui.page_header(
    ":material/auto_awesome: Thư viện nội dung",
    "Mỗi mẫu có thể chứa {link} và các cụm xoay chữ {kiểu 1|kiểu 2} để bài viết không bị trùng lặp.",
)

total = len(templates)
enabled = sum(1 for t in templates if t.get("enabled", True))
themes = {t.get("theme") for t in templates}
c1, c2, c3 = st.columns(3)
c1.metric("Tổng số mẫu", total, border=True, icon=":material/description:")
c2.metric("Đang bật", enabled, border=True, icon=":material/toggle_on:")
c3.metric("Chủ đề", len(themes), border=True, icon=":material/category:")

st.subheader("Chỉnh sửa mẫu")
rows = [
    {
        "id": t.get("id", ""),
        "theme": t.get("theme", "san_sale"),
        "enabled": bool(t.get("enabled", True)),
        "text": t.get("text", ""),
    }
    for t in templates
]
edited = st.data_editor(
    rows,
    hide_index=True,
    num_rows="dynamic",
    width="stretch",
    column_config={
        "id": st.column_config.TextColumn("Mã", width="small", help="Để trống sẽ tự sinh mã"),
        "theme": st.column_config.SelectboxColumn(
            "Chủ đề", options=list(C.THEME_LABELS.keys()), required=True
        ),
        "enabled": st.column_config.CheckboxColumn("Bật"),
        "text": st.column_config.TextColumn("Nội dung mẫu", width="large"),
    },
    key="template_editor",
)
st.caption("Mẹo: dùng `{link}` ở vị trí muốn chèn link Shopee. Nếu không có `{link}`, hệ thống tự nối link vào cuối bài.")

with st.container(horizontal=True):
    if st.button("Lưu thay đổi", type="primary", icon=":material/save:"):
        cleaned = []
        records = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
        for record in records:
            text = str(record.get("text") or "").strip()
            if not text:
                continue
            tid = str(record.get("id") or "").strip() or f"t{uuid.uuid4().hex[:5]}"
            theme = str(record.get("theme") or "san_sale")
            cleaned.append({"id": tid, "theme": theme, "text": text, "enabled": bool(record.get("enabled", True))})
        fresh = store.load_data()
        fresh["templates"] = cleaned
        store.add_log(fresh, f"Cập nhật thư viện nội dung ({len(cleaned)} mẫu).")
        store.save_data(fresh)
        st.success(f"Đã lưu {len(cleaned)} mẫu nội dung.", icon=":material/check_circle:")
        st.rerun()

    if st.button("Bật tất cả", icon=":material/toggle_on:"):
        fresh = store.load_data()
        for t in fresh.get("templates", []):
            t["enabled"] = True
        store.save_data(fresh)
        st.rerun()

    if st.menu_button("Khôi phục mặc định", options=["Khôi phục 30 mẫu gốc"], icon=":material/restart_alt:"):
        fresh = store.load_data()
        fresh["templates"] = [
            {"id": tid, "theme": theme, "text": text, "enabled": True}
            for tid, theme, text in C.DEFAULT_TEMPLATES
        ]
        store.save_data(fresh)
        st.rerun()

st.divider()
st.subheader("Xem thử nội dung")
sample_link = links[0] if links else "https://s.shopee.vn/xxxx"
options = [t for t in templates if t.get("enabled", True)] or templates
if options:
    chosen = st.selectbox(
        "Chọn mẫu để xem thử",
        options=[t["id"] for t in options],
        format_func=lambda tid: next(
            (f"{C.THEME_LABELS.get(t['theme'], t['theme'])} · {t['id']}" for t in options if t["id"] == tid), tid
        ),
    )
    template = next((t for t in options if t["id"] == chosen), options[0])
    st.caption(f"{len(template['text'])} ký tự mẫu · sau khi ghép link sẽ nằm trong giới hạn 500 ký tự.")
    for idx in range(3):
        with st.container(border=True):
            st.caption(f"Biến thể {idx + 1}")
            st.write(content.fit_text(content.render_spin(template["text"]), sample_link))
else:
    st.info("Chưa có mẫu nào. Bấm khôi phục mặc định để lấy 30 mẫu có sẵn.", icon=":material/info:")
