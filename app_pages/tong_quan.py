from datetime import datetime

import streamlit as st

from core import constants as C
from core import planner, store, ui, worker

data = store.load_data()
settings = data.get("settings", {})
posts = data.get("posts", [])

ui.page_header(
    ":material/dashboard: Tổng quan",
    "Tự động đăng bài tiếp thị liên kết Shopee lên Threads theo khung giờ vàng.",
)

today = planner.now_vn().date()


def _published_today() -> int:
    total = 0
    for post in posts:
        if post.get("status") != C.ST_PUBLISHED:
            continue
        try:
            if datetime.fromisoformat(post.get("published_at", "")).date() == today:
                total += 1
        except Exception:
            continue
    return total


pending = sum(1 for p in posts if p.get("status") == C.ST_PENDING)
published = sum(1 for p in posts if p.get("status") == C.ST_PUBLISHED)
failed = sum(1 for p in posts if p.get("status") == C.ST_FAILED)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Đang chờ", pending, border=True, icon=":material/schedule:")
m2.metric("Đã đăng hôm nay", _published_today(), border=True, icon=":material/check_circle:")
m3.metric("Tổng đã đăng", published, border=True, icon=":material/trending_up:")
m4.metric("Bài lỗi", failed, border=True, icon=":material/error:")


@st.fragment(run_every="20s")
def live_status() -> None:
    fresh = store.load_data()
    nxt = planner.next_post(fresh)
    heartbeat = (fresh.get("worker") or {}).get("heartbeat", "")
    with st.container(border=True):
        left, right = st.columns([2, 1])
        with left:
            st.markdown("**Bài đăng kế tiếp**")
            if nxt:
                st.markdown(f"### {ui.fmt_dt(nxt['run_at'])}")
                st.caption(f"Còn {ui.relative(nxt['run_at'])} · {len(nxt.get('image_urls', []))} ảnh · "
                           f"{C.THEME_LABELS.get(nxt.get('theme', ''), 'Nội dung')}")
                st.write(nxt.get("text", "")[:220] + ("…" if len(nxt.get("text", "")) > 220 else ""))
            else:
                st.info("Hàng đợi đang trống. Bấm “Tạo lịch tự động” bên dưới nhé.", icon=":material/inbox:")
        with right:
            st.markdown("**Worker 24/7**")
            if heartbeat:
                try:
                    age = (planner.now_vn() - datetime.fromisoformat(heartbeat)).total_seconds()
                except Exception:
                    age = None
                if age is not None and age < 60:
                    st.badge("Đang hoạt động", icon=":material/bolt:", color="green")
                else:
                    st.badge("Không phản hồi", icon=":material/warning:", color="orange")
            else:
                st.badge("Chưa khởi động", icon=":material/hourglass_empty:", color="gray")
            st.caption(f"Cập nhật: {ui.fmt_dt(heartbeat) if heartbeat else '—'}")
            st.caption(f"Tự bổ sung lịch: {'Bật' if settings.get('auto_refill') else 'Tắt'}")


live_status()

conflicts = planner.find_conflicts(data)
now_vn = planner.now_vn()
overdue = 0
for post in posts:
    if post.get("status") != C.ST_PENDING:
        continue
    try:
        if datetime.fromisoformat(post.get("run_at", "")) < now_vn:
            overdue += 1
    except Exception:
        continue

if conflicts or overdue:
    with st.container(border=True):
        st.markdown("**:material/warning: Cần chú ý**")
        if overdue:
            st.caption(f"{overdue} bài đã quá giờ đăng. Worker sẽ đăng bù ở lượt kiểm tra tới.")
        if conflicts:
            st.caption(f"{len(conflicts)} khung giờ bị trùng bài: "
                       + ", ".join(ui.fmt_dt(key) for key, _ in conflicts[:3]))
        with st.container(horizontal=True):
            if st.button("Dàn đều lịch đang chờ", icon=":material/straighten:", type="primary"):
                fresh = store.load_data()
                moved = planner.optimise_schedule(fresh, days=max(3, int(settings.get("refill_days", 2)) * 2))
                store.save_data(fresh)
                st.toast(f"Đã dời {moved} bài vào khung giờ vàng.")
                st.rerun()
            if st.button("Chạy worker ngay", icon=":material/bolt:"):
                with st.spinner("Đang xử lý…"):
                    worker.tick()
                st.rerun()

st.subheader("Thao tác nhanh")
with st.container(border=True):
    c1, c2, c3 = st.columns([1.1, 1.1, 1], vertical_alignment="bottom")
    with c1:
        days = st.number_input("Số ngày cần tạo lịch", min_value=1, max_value=30, value=7)
        if st.button("Tạo lịch tự động", type="primary", width="stretch", icon=":material/auto_awesome:"):
            fresh = store.load_data()
            created = planner.generate_posts(fresh, int(days))
            store.save_data(fresh)
            if created:
                st.success(f"Đã thêm {created} bài trong {int(days)} ngày tới.", icon=":material/check_circle:")
            else:
                st.warning("Không có khung giờ trống phù hợp. Thử tăng số ngày hoặc giảm khoảng cách tối thiểu.")
    with c2:
        st.caption("Đăng ngay các bài đã tới giờ (bỏ qua thời gian chờ)")
        if st.button("Đăng bài tới giờ", width="stretch", icon=":material/send:"):
            fresh = store.load_data()
            count = worker.process_due(fresh)
            if count:
                st.success(f"Đã đăng {count} bài.", icon=":material/check_circle:")
            else:
                st.info("Không có bài nào tới giờ hoặc thiếu token.")
    with c3:
        st.caption(f"{len(data.get('resources', {}).get('links', []))} link · "
                   f"{len(data.get('resources', {}).get('images', []))} ảnh")
        st.page_link("app_pages/tai_nguyen.py", label="Mở kho tài nguyên", icon=":material/folder_open:")

if not settings.get("enabled", True):
    st.warning("Hệ thống đang tạm dừng. Bật lại trong trang Cài đặt.", icon=":material/pause_circle:")

upcoming = sorted(
    [p for p in posts if p.get("status") == C.ST_PENDING], key=lambda p: p.get("run_at", "")
)[:6]
if upcoming:
    st.subheader("Sắp đăng")
    st.dataframe(
        [
            {
                "Thời gian": ui.fmt_dt(p["run_at"]),
                "Chủ đề": C.THEME_LABELS.get(p.get("theme", ""), "—"),
                "Ảnh": len(p.get("image_urls", [])),
                "Nội dung": (p.get("text", "")[:90] + "…") if len(p.get("text", "")) > 90 else p.get("text", ""),
            }
            for p in upcoming
        ],
        hide_index=True,
        alt="Danh sách bài sắp đăng",
    )
    st.page_link("app_pages/lich_dang.py", label="Xem toàn bộ lịch đăng", icon=":material/calendar_month:")

with st.expander("Nhật ký hoạt động", icon=":material/receipt_long:"):
    ui.log_panel(data, limit=15)
