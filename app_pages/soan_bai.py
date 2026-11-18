from datetime import datetime, time, timedelta

import streamlit as st

from core import constants as C
from core import content, planner, store, threads_api, ui

data = store.load_data()
settings = data.get("settings", {})
links = data.get("resources", {}).get("links", [])
image_urls = [img["url"] for img in data.get("resources", {}).get("images", []) if img.get("url")]

ui.page_header(":material/edit_note: Soạn bài", "Tạo bài viết thủ công hoặc để hệ thống gợi ý nội dung từ thư viện.")

if not links:
    st.warning("Kho link Shopee đang trống. Vào trang Tài nguyên để thêm link trước.", icon=":material/link_off:")

templates = data.get("templates", [])
template_labels = {"__auto__": "Tự động chọn (đa dạng chủ đề)"}
for tmpl in templates:
    if tmpl.get("enabled", True):
        template_labels[tmpl["id"]] = f"{C.THEME_LABELS.get(tmpl.get('theme', ''), tmpl.get('theme', ''))} · {tmpl['id']}"

with st.container(border=True):
    st.markdown("**1. Chọn nguồn nội dung**")
    col1, col2, col3 = st.columns([1.3, 1.3, 1], vertical_alignment="bottom")
    with col1:
        template_id = st.selectbox(
            "Mẫu nội dung",
            options=list(template_labels.keys()),
            format_func=lambda k: template_labels[k],
        )
    with col2:
        link_mode = st.segmented_control("Nguồn link", ["Ngẫu nhiên", "Chọn link"], default="Ngẫu nhiên")
    with col3:
        img_count = st.number_input(
            "Số ảnh", min_value=0, max_value=C.MAX_IMAGES_PER_POST,
            value=int(settings.get("images_per_post", 3)),
        )

    chosen_link: str | None = None
    if link_mode == "Chọn link":
        chosen_link = st.selectbox(
            "Link Shopee",
            options=links,
            format_func=lambda u: u if len(u) <= 60 else u[:57] + "…",
            disabled=not links,
        )

    if st.button("Tạo nội dung", type="primary", icon=":material/auto_awesome:"):
        tmpl = None if template_id == "__auto__" else next((t for t in templates if t["id"] == template_id), None)
        fresh = store.load_data()
        draft = content.build_post(
            fresh,
            template=tmpl,
            link=chosen_link,
            images=content.pick_images(fresh, int(img_count)),
        )
        if draft is None:
            st.error("Chưa có mẫu nội dung nào được bật. Hãy bật mẫu trong Thư viện nội dung.")
        else:
            st.session_state.draft = draft
            store.save_data(fresh)
            st.rerun()

draft = st.session_state.get("draft")
if not draft:
    st.info("Bấm **Tạo nội dung** để hệ thống gợi ý một bài viết hoàn chỉnh.", icon=":material/lightbulb:")
    st.stop()

post_id = draft["id"]
st.divider()
st.markdown("**2. Xem lại và chỉnh sửa**")

text = st.text_area(
    "Nội dung bài đăng",
    value=draft["text"],
    height=190,
    max_chars=C.MAX_POST_CHARS,
    key=f"text_{post_id}",
)
st.caption(f"{len(text)}/{C.MAX_POST_CHARS} ký tự · Link: {draft.get('link', '—')}")

picked_images = st.multiselect(
    "Hình ảnh đính kèm",
    options=image_urls,
    default=[u for u in draft.get("image_urls", []) if u in image_urls],
    format_func=lambda u: f"Ảnh {image_urls.index(u) + 1}",
    key=f"imgs_{post_id}",
    help="Threads hiển thị tối đa 20 ảnh cho một bài (album).",
)
if picked_images:
    cols = st.columns(min(len(picked_images), 4))
    for idx, url in enumerate(picked_images):
        cols[idx % 4].image(url, width="stretch", alt=f"Ảnh đính kèm {idx + 1}")

st.markdown("**3. Thời điểm đăng**")
next_slot = planner.plan_times(data, 2)
default_dt = next_slot[0] if next_slot else planner.now_vn() + timedelta(hours=1)

mode = st.segmented_control("Hình thức", ["Hẹn giờ", "Đăng ngay", "Lưu nháp"], default="Hẹn giờ")
run_date, run_time = default_dt.date(), default_dt.time()
run_at_choice: datetime | None = None

if mode in (None, "Hẹn giờ"):
    suggestions = next_slot[:3]
    labels = [f"{dt:%H:%M · %d/%m}" for dt in suggestions]
    quick = st.pills(
        "Khung giờ vàng gợi ý",
        options=[*labels, "Tự chọn giờ khác"],
        default=labels[0] if labels else "Tự chọn giờ khác",
        help="Hệ thống đã tính sẵn các khung giờ vàng còn trống, tránh trùng bài khác.",
    )
    if quick and quick != "Tự chọn giờ khác":
        run_at_choice = suggestions[labels.index(quick)]
        st.caption(f"Sẽ đăng lúc **{ui.fmt_dt(run_at_choice)}**")
    else:
        c1, c2 = st.columns(2)
        with c1:
            run_date = st.date_input("Ngày đăng", value=default_dt.date())
        with c2:
            run_time = st.time_input("Giờ đăng", value=default_dt.time().replace(second=0, microsecond=0))
        run_at_choice = datetime.combine(run_date, run_time)
        st.caption(f"Sẽ đăng lúc **{ui.fmt_dt(run_at_choice)}**")

with st.container(horizontal=True):
    submit_label = {"Đăng ngay": "Đăng ngay", "Lưu nháp": "Lưu vào nháp"}.get(mode or "", "Thêm vào lịch")
    submit = st.button(
        submit_label,
        type="primary",
        icon={None: ":material/schedule:", "Hẹn giờ": ":material/schedule:", "Đăng ngay": ":material/send:",
              "Lưu nháp": ":material/save:"}.get(mode, ":material/schedule:"),
    )
    discard = st.button("Bỏ bản nháp", icon=":material/delete:")

if discard:
    st.session_state.pop("draft", None)
    st.rerun()

if submit:
    token = store.get_token(data)
    final_text = text.strip()
    is_draft = mode == "Lưu nháp"
    run_at = run_at_choice if mode in (None, "Hẹn giờ") else planner.now_vn()

    if not final_text:
        st.error("Nội dung bài viết đang trống.")
    elif is_draft:
        record = dict(draft)
        record.update({
            "text": final_text,
            "image_urls": picked_images,
            "run_at": "",
            "status": C.ST_DRAFT,
            "attempts": 0,
            "last_error": "",
        })
        fresh = store.load_data()
        fresh.setdefault("posts", []).append(record)
        store.add_log(fresh, f"Đã lưu nháp bài {post_id}.")
        store.save_data(fresh)
        st.success("Đã lưu vào Nháp. Vào trang Lịch đăng để hẹn giờ hoặc đăng.", icon=":material/check_circle:")
        st.session_state.pop("draft", None)
    elif not token:
        st.error("Chưa có Threads Access Token. Thêm trong trang Cài đặt hoặc secrets.")
    elif mode != "Đăng ngay" and (run_at is None or run_at <= planner.now_vn()):
        st.error("Thời gian hẹn giờ phải ở tương lai.")
    elif mode == "Đăng ngay":
        with st.spinner("Đang xuất bản lên Threads…"):
            ok, message = threads_api.create_and_publish(
                store.get_user_id(data), token, final_text, picked_images
            )
        record = dict(draft)
        record.update({
            "text": final_text,
            "image_urls": picked_images,
            "status": C.ST_PUBLISHED if ok else C.ST_FAILED,
            "attempts": 1,
            "last_error": "" if ok else message,
            "published_at": planner.now_vn().isoformat(timespec="seconds") if ok else "",
        })
        fresh = store.load_data()
        fresh.setdefault("posts", []).append(record)
        store.add_log(fresh, message, "info" if ok else "error")
        store.save_data(fresh)
        if ok:
            st.success(message, icon=":material/check_circle:")
            st.session_state.pop("draft", None)
        else:
            st.error(message)
    else:
        record = dict(draft)
        record.update({
            "text": final_text,
            "image_urls": picked_images,
            "run_at": run_at.isoformat(timespec="seconds"),
            "status": C.ST_PENDING,
            "attempts": 0,
            "last_error": "",
        })
        fresh = store.load_data()
        fresh.setdefault("posts", []).append(record)
        store.add_log(fresh, f"Đã lên lịch bài {post_id} lúc {run_at:%H:%M %d/%m}.")
        store.save_data(fresh)
        st.success(f"Đã thêm vào lịch: **{ui.fmt_dt(run_at)}**", icon=":material/check_circle:")
        st.session_state.pop("draft", None)
