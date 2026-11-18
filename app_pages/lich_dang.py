import calendar
import csv
import io
import uuid
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core import constants as C
from core import planner, store, ui, worker

data = store.load_data()
posts = data.get("posts", [])
project_links = data.get("resources", {}).get("links", [])
project_images = [i["url"] for i in data.get("resources", {}).get("images", []) if i.get("url")]

ui.page_header(
    ":material/calendar_month: Lịch đăng & quản lý bài viết",
    "Hẹn giờ, sửa nội dung, đổi ảnh, nhân bản và theo dõi toàn bộ bài viết ở một nơi.",
)

if not posts:
    st.info("Chưa có bài nào. Vào Tổng quan để tạo lịch tự động hoặc Soạn bài để viết bài mới.", icon=":material/inbox:")
    st.stop()


def sort_key(post: dict) -> str:
    return post.get("run_at") or post.get("created_at", "")


def duplicate_post(pid: str) -> None:
    fresh = store.load_data()
    source = next((p for p in fresh["posts"] if p.get("id") == pid), None)
    if not source:
        return
    copy = dict(source)
    copy.update({
        "id": uuid.uuid4().hex[:12],
        "status": C.ST_DRAFT,
        "run_at": "",
        "attempts": 0,
        "last_error": "",
        "published_id": "",
        "published_at": "",
        "created_at": planner.now_vn().isoformat(timespec="seconds"),
    })
    fresh["posts"].append(copy)
    store.add_log(fresh, f"Nhân bản bài {pid} thành bản nháp mới.")
    store.save_data(fresh)


counts = {status: sum(1 for p in posts if p.get("status") == status) for status in C.STATUS_LABELS}
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Tổng số bài", len(posts), border=True, icon=":material/list_alt:")
m2.metric("Đang chờ", counts[C.ST_PENDING], border=True, icon=":material/schedule:")
m3.metric("Nháp", counts[C.ST_DRAFT], border=True, icon=":material/edit_note:")
m4.metric("Đã đăng", counts[C.ST_PUBLISHED], border=True, icon=":material/check_circle:")
m5.metric("Lỗi", counts[C.ST_FAILED], border=True, icon=":material/error:")

conflicts = planner.find_conflicts(data)
if conflicts:
    with st.container(border=True):
        st.markdown(f"**:material/content_copy: {len(conflicts)} khung giờ bị trùng bài**")
        st.caption("Các bài cùng giờ: " + ", ".join(
            f"{ui.fmt_dt(key)} ({len(ids)} bài)" for key, ids in conflicts[:4]
        ))
        if st.button("Dàn đều lịch đang chờ", icon=":material/straighten:", type="primary"):
            fresh = store.load_data()
            moved = planner.optimise_schedule(
                fresh, days=max(3, int(data.get("settings", {}).get("refill_days", 2)) * 2)
            )
            store.save_data(fresh)
            st.toast(f"Đã dời {moved} bài vào khung giờ vàng.")
            st.rerun()

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("Làm mới", icon=":material/refresh:"):
        st.rerun()
    action = st.menu_button(
        "Thao tác hàng loạt",
        options=[
            "Đăng toàn bộ bài đang chờ",
            "Dời tất cả bài chờ +30 phút",
            "Dàn đều lịch đang chờ",
            "Tạo bản sao lưu",
            "Chuyển bài lỗi về nháp",
            "Xoá bài đã đăng",
            "Xoá bài nháp",
            "Xoá bài lỗi",
            "Xoá tất cả",
        ],
        icon=":material/bolt:",
    )

if action == "Đăng toàn bộ bài đang chờ":
    fresh = store.load_data()
    with st.spinner("Đang đăng toàn bộ bài đang chờ…"):
        count = worker.process_due(fresh, force=True)
    st.success(f"Đã xử lý {count} bài.", icon=":material/check_circle:")
    st.rerun()
elif action == "Dàn đều lịch đang chờ":
    fresh = store.load_data()
    moved = planner.optimise_schedule(fresh, days=max(3, int(data.get("settings", {}).get("refill_days", 2)) * 2))
    store.save_data(fresh)
    st.toast(f"Đã dời {moved} bài vào khung giờ vàng.")
    st.rerun()
elif action == "Tạo bản sao lưu":
    path = store.create_backup("manual")
    if path:
        st.success(f"Đã tạo bản sao lưu: {path.name}", icon=":material/backup:")
    else:
        st.error("Không tạo được bản sao lưu.")
elif action == "Dời tất cả bài chờ +30 phút":
    fresh = store.load_data()
    for post in fresh.get("posts", []):
        if post.get("status") == C.ST_PENDING:
            try:
                post["run_at"] = (datetime.fromisoformat(post["run_at"]) + timedelta(minutes=30)).isoformat(
                    timespec="seconds"
                )
            except Exception:
                continue
    store.save_data(fresh)
    st.toast("Đã dời toàn bộ bài đang chờ thêm 30 phút.")
    st.rerun()
elif action == "Chuyển bài lỗi về nháp":
    fresh = store.load_data()
    for post in fresh.get("posts", []):
        if post.get("status") == C.ST_FAILED:
            post.update({"status": C.ST_DRAFT, "run_at": "", "attempts": 0, "last_error": ""})
    store.save_data(fresh)
    st.toast("Đã chuyển các bài lỗi về Nháp.")
    st.rerun()
elif action in ("Xoá bài đã đăng", "Xoá bài nháp", "Xoá bài lỗi", "Xoá tất cả"):
    fresh = store.load_data()
    mapping = {
        "Xoá bài đã đăng": C.ST_PUBLISHED,
        "Xoá bài nháp": C.ST_DRAFT,
        "Xoá bài lỗi": C.ST_FAILED,
    }
    target_status = mapping.get(action)
    fresh["posts"] = [] if target_status is None else [p for p in fresh["posts"] if p.get("status") != target_status]
    store.save_data(fresh)
    st.rerun()

st.divider()

tab_posts, tab_calendar, tab_stats = st.tabs(["Bài viết", "Lịch tháng", "Thống kê"], on_change="rerun")

# ------------------------------------------------------------------ TAB BÀI VIẾT
if tab_posts.open:
    filters_left, filters_right = st.columns([2, 1], vertical_alignment="bottom")
    with filters_left:
        query = st.text_input(
            "Tìm trong nội dung, link hoặc mã bài",
            placeholder="Nhập từ khoá…",
            type="search",
            live=True,
        )
    with filters_right:
        page_size = st.selectbox("Số bài mỗi trang", options=[6, 12, 24], index=0)

    view = st.pills(
        "Lọc theo trạng thái",
        options=["Tất cả", "Đang chờ", "Nháp", "Đã đăng", "Lỗi"],
        default="Tất cả",
    ) or "Tất cả"

    with st.expander("Bộ lọc nâng cao", icon=":material/tune:"):
        today = planner.now_vn().date()
        date_range = st.date_input(
            "Khoảng ngày đăng (bỏ trống để xem tất cả)",
            value=(today, today + timedelta(days=14)),
        )

    status_map = {
        "Đang chờ": C.ST_PENDING,
        "Nháp": C.ST_DRAFT,
        "Đã đăng": C.ST_PUBLISHED,
        "Lỗi": C.ST_FAILED,
    }

    def matches(post: dict) -> bool:
        if view != "Tất cả" and post.get("status") != status_map.get(view):
            return False
        if query:
            haystack = f"{post.get('text', '')} {post.get('link', '')} {post.get('id', '')}".lower()
            if query.lower().strip() not in haystack:
                return False
        if post.get("status") == C.ST_DRAFT:
            return True
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            try:
                run_date = datetime.fromisoformat(post.get("run_at", "")).date()
            except Exception:
                return False
            if not (date_range[0] <= run_date <= date_range[1]):
                return False
        return True

    visible = [p for p in sorted(posts, key=sort_key) if matches(p)]

    pages = max(1, (len(visible) + page_size - 1) // page_size)
    page = 1
    if pages > 1:
        page = st.selectbox("Trang", options=list(range(1, pages + 1)), format_func=lambda n: f"Trang {n}/{pages}")
    st.caption(f"Hiển thị {len(visible)} bài phù hợp · {counts[C.ST_PENDING]} bài đang chờ · "
               f"{counts[C.ST_DRAFT]} bản nháp")

    start = (page - 1) * page_size
    for post in visible[start:start + page_size]:
        pid = post.get("id", "")
        status = post.get("status", C.ST_PENDING)
        is_draft = status == C.ST_DRAFT
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                when = ui.fmt_dt(post.get("run_at")) if not is_draft else "Chưa hẹn giờ"
                extra = f" · còn {ui.relative(post.get('run_at'))}" if status == C.ST_PENDING else ""
                st.markdown(f"**{when}**{extra}")
                st.caption(
                    f"{C.THEME_LABELS.get(post.get('theme', ''), 'Nội dung')} · "
                    f"{len(post.get('image_urls', []))} ảnh · {len(post.get('text', ''))} ký tự · mã `{pid}`"
                )
            with right:
                ui.status_badge(status)

            if status == C.ST_FAILED and post.get("last_error"):
                st.caption(f":material/error: {post['last_error']} (đã thử {post.get('attempts', 0)} lần)")

            st.write(post.get("text", ""))
            imgs = post.get("image_urls", [])
            if imgs:
                with st.expander(f"Xem {len(imgs)} ảnh", icon=":material/imagesmode:"):
                    cols = st.columns(min(len(imgs), 4))
                    for idx, url in enumerate(imgs):
                        cols[idx % 4].image(url, width="stretch", alt=f"Ảnh {idx + 1} của bài {pid}")

            with st.container(horizontal=True, wrap=True):
                if status in (C.ST_PENDING, C.ST_DRAFT):
                    if st.button("Đăng ngay", key=f"pub_{pid}", icon=":material/send:"):
                        fresh = store.load_data()
                        item = next((p for p in fresh["posts"] if p.get("id") == pid), None)
                        if item:
                            with st.spinner("Đang đăng…"):
                                worker.publish_one(fresh, item, store.get_token(fresh), store.get_user_id(fresh))
                            st.rerun()

                if status == C.ST_PENDING:
                    if st.button("Dời +30 phút", key=f"delay_{pid}", icon=":material/snooze:"):
                        fresh = store.load_data()
                        item = next((p for p in fresh["posts"] if p.get("id") == pid), None)
                        if item:
                            item["run_at"] = (datetime.fromisoformat(item["run_at"]) + timedelta(minutes=30)).isoformat(
                                timespec="seconds"
                            )
                            store.save_data(fresh)
                            st.rerun()
                    if st.button("Về nháp", key=f"draft_{pid}", icon=":material/edit_note:"):
                        fresh = store.load_data()
                        item = next((p for p in fresh["posts"] if p.get("id") == pid), None)
                        if item:
                            item.update({"status": C.ST_DRAFT, "run_at": ""})
                            store.save_data(fresh)
                            st.rerun()

                if status == C.ST_FAILED:
                    if st.button("Thử lại", key=f"retry_{pid}", icon=":material/replay:"):
                        fresh = store.load_data()
                        item = next((p for p in fresh["posts"] if p.get("id") == pid), None)
                        if item:
                            item.update({
                                "status": C.ST_PENDING,
                                "attempts": 0,
                                "last_error": "",
                                "run_at": (planner.now_vn() + timedelta(minutes=2)).isoformat(timespec="seconds"),
                            })
                            store.save_data(fresh)
                            st.rerun()

                if st.button("Sửa" if not is_draft else "Lên lịch / Sửa", key=f"edit_{pid}", icon=":material/edit:"):
                    st.session_state[f"editing_{pid}"] = not st.session_state.get(f"editing_{pid}", False)

                if st.button("Nhân bản", key=f"dup_{pid}", icon=":material/content_copy:"):
                    duplicate_post(pid)
                    st.rerun()

                if st.button("Xoá", key=f"del_{pid}", icon=":material/delete:"):
                    fresh = store.load_data()
                    fresh["posts"] = [p for p in fresh["posts"] if p.get("id") != pid]
                    store.save_data(fresh)
                    st.rerun()

            if st.session_state.get(f"editing_{pid}"):
                with st.container(border=True):
                    new_text = st.text_area(
                        "Nội dung", value=post.get("text", ""), max_chars=C.MAX_POST_CHARS,
                        key=f"newtext_{pid}", height=150,
                    )
                    image_options = list(dict.fromkeys(project_images + imgs))
                    new_images = st.multiselect(
                        "Hình ảnh đính kèm",
                        options=image_options,
                        default=[u for u in imgs if u in image_options],
                        format_func=lambda u: f"Ảnh {image_options.index(u) + 1}",
                        key=f"newimgs_{pid}",
                    )
                    try:
                        current_dt = datetime.fromisoformat(post.get("run_at", ""))
                    except Exception:
                        suggested = planner.plan_times(data, 1)
                        current_dt = suggested[0] if suggested else planner.now_vn() + timedelta(hours=1)

                    c1, c2 = st.columns(2)
                    new_date = c1.date_input("Ngày đăng", value=current_dt.date(), key=f"newdate_{pid}")
                    new_time = c2.time_input(
                        "Giờ đăng", value=current_dt.time().replace(second=0, microsecond=0), key=f"newtime_{pid}"
                    )
                    schedule_it = True
                    if is_draft:
                        schedule_it = st.checkbox("Đưa vào lịch đăng ngay", value=True, key=f"schedule_{pid}")

                    if st.button("Lưu thay đổi", key=f"save_{pid}", type="primary", icon=":material/save:"):
                        run_at = datetime.combine(new_date, new_time)
                        fresh = store.load_data()
                        item = next((p for p in fresh["posts"] if p.get("id") == pid), None)
                        if item:
                            if not new_text.strip():
                                st.error("Nội dung không được để trống.")
                            elif schedule_it and run_at <= planner.now_vn():
                                st.error("Thời gian hẹn giờ phải ở tương lai.")
                            else:
                                item["text"] = new_text
                                item["image_urls"] = new_images
                                item["run_at"] = run_at.isoformat(timespec="seconds") if schedule_it else ""
                                item["status"] = C.ST_PENDING if schedule_it else C.ST_DRAFT
                                item["attempts"] = 0
                                item["last_error"] = ""
                                store.add_log(fresh, f"Cập nhật bài {pid}.")
                                store.save_data(fresh)
                                st.session_state[f"editing_{pid}"] = False
                                st.rerun()

    if not visible:
        st.info(f"Không có bài nào khớp bộ lọc hiện tại.", icon=":material/filter_alt_off:")

# ------------------------------------------------------------------ TAB LỊCH THÁNG
if tab_calendar.open:
    today = planner.now_vn().date()
    picked = st.date_input("Chọn tháng (bấm ngày bất kỳ trong tháng)", value=today.replace(day=1))
    year, month = picked.year, picked.month
    st.caption(f"Lịch tháng {month:02d}/{year} · :material/schedule: đang chờ · :material/check_circle: đã đăng")

    day_stats: dict[date, dict[str, int]] = {}
    for post in posts:
        if not post.get("run_at"):
            continue
        try:
            day = datetime.fromisoformat(post["run_at"]).date()
        except Exception:
            continue
        bucket = day_stats.setdefault(day, {})
        status = post.get("status", C.ST_PENDING)
        bucket[status] = bucket.get(status, 0) + 1

    header = st.columns(7)
    for idx, label in enumerate(["T2", "T3", "T4", "T5", "T6", "T7", "CN"]):
        header[idx].markdown(f"**{label}**")

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    for week in weeks:
        cols = st.columns(7)
        for idx, day_num in enumerate(week):
            with cols[idx]:
                if day_num == 0:
                    st.write("")
                    continue
                day = date(year, month, day_num)
                stats = day_stats.get(day, {})
                has_items = any(stats.values())
                with st.container(border=has_items, height=104):
                    label = f"**{day_num}**" if day != today else f"**:orange[{day_num}]**"
                    st.markdown(label)
                    if stats.get(C.ST_PENDING):
                        st.caption(f":material/schedule: {stats[C.ST_PENDING]} bài")
                    if stats.get(C.ST_PUBLISHED):
                        st.caption(f":material/check_circle: {stats[C.ST_PUBLISHED]} đã đăng")
                    if stats.get(C.ST_FAILED):
                        st.caption(f":material/error: {stats[C.ST_FAILED]} lỗi")

    st.divider()
    st.caption("Bài nháp chưa có thời gian nên không hiện trên lịch. Vào tab Bài viết để hẹn giờ cho nháp.")

# ------------------------------------------------------------------ TAB THỐNG KÊ
if tab_stats.open:
    published = counts[C.ST_PUBLISHED]
    failed = counts[C.ST_FAILED]
    done = published + failed
    success_rate = (published / done * 100) if done else 0.0

    c1, c2, c3 = st.columns(3)
    c1.metric("Tỷ lệ đăng thành công", f"{success_rate:.0f}%", border=True, icon=":material/insights:")
    c2.metric("Bài chờ + nháp", counts[C.ST_PENDING] + counts[C.ST_DRAFT], border=True, icon=":material/pending_actions:")
    upcoming = [p for p in posts if p.get("status") == C.ST_PENDING and p.get("run_at")]
    c3.metric("Bài đã lên lịch", len(upcoming), border=True, icon=":material/event_available:")

    st.subheader("Số bài theo ngày (14 ngày tới)")
    today = planner.now_vn().date()
    rows = []
    for offset in range(14):
        day = today + timedelta(days=offset)
        total = sum(
            1
            for p in upcoming
            if p.get("run_at") and datetime.fromisoformat(p["run_at"]).date() == day
        )
        rows.append({"Ngày": day.strftime("%d/%m"), "Số bài": total})
    st.bar_chart(pd.DataFrame(rows), x="Ngày", y="Số bài", alt="Số bài đã lên lịch theo từng ngày")

    st.subheader("Phân bố trạng thái")
    status_rows = [
        {"Trạng thái": C.STATUS_LABELS[status], "Số bài": counts[status]}
        for status in C.STATUS_LABELS
    ]
    st.bar_chart(pd.DataFrame(status_rows), x="Trạng thái", y="Số bài", alt="Số bài theo trạng thái")

    st.subheader("Xuất dữ liệu")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Mã", "Thời gian", "Trạng thái", "Chủ đề", "Link", "Số ảnh", "Nội dung", "Lỗi gần nhất"])
    for post in sorted(posts, key=sort_key):
        writer.writerow([
            post.get("id", ""),
            post.get("run_at", ""),
            C.STATUS_LABELS.get(post.get("status", ""), post.get("status", "")),
            C.THEME_LABELS.get(post.get("theme", ""), ""),
            post.get("link", ""),
            len(post.get("image_urls", [])),
            post.get("text", "").replace("\n", " "),
            post.get("last_error", ""),
        ])
    st.download_button(
        "Tải CSV toàn bộ bài viết",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name=f"threads_posts_{planner.now_vn():%Y%m%d_%H%M}.csv",
        mime="text/csv",
        icon=":material/download:",
    )
