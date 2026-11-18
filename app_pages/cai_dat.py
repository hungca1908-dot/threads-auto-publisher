from datetime import date, timedelta

import streamlit as st

from core import constants as C
from core import planner, store, threads_api, ui, worker

data = store.load_data()
settings = data.get("settings", {})

ui.page_header(":material/settings: Cài đặt", "Kết nối Threads, chỉnh nhịp đăng và cấu hình chạy 24/7.")

tab_conn, tab_schedule, tab_deploy = st.tabs(["Kết nối", "Nhịp đăng", "Chạy 24/7"], on_change="rerun")

if tab_conn.open:
    st.subheader("Threads API")
    st.caption("Token dài hạn có hạn khoảng 60 ngày. Nên gia hạn định kỳ để hệ thống không ngừng đăng.")

    user_id = st.text_input("Threads User ID", value=settings.get("user_id", "me"), help="Thường để “me”.")
    token_input = st.text_input(
        "Threads Access Token",
        value=settings.get("access_token", ""),
        type="password",
        help="Ưu tiên khai báo trong secrets (THREADS_ACCESS_TOKEN). Token lưu ở đây chỉ dùng khi không có secrets.",
    )
    imgbb_key = st.text_input(
        "ImgBB API Key (tuỳ chọn)",
        value=settings.get("imgbb_key", ""),
        type="password",
        help="Chỉ cần khi bạn muốn tải ảnh từ máy lên.",
    )

    expires_raw = str(settings.get("token_expires_at", "") or "")[:10]
    token_expiry = None
    if expires_raw:
        try:
            token_expiry = st.date_input("Ngày hết hạn token", value=date.fromisoformat(expires_raw))
        except ValueError:
            token_expiry = None
    days_left = ui.token_days_left(settings)
    if days_left is not None:
        if days_left <= 7:
            st.warning(f"Token còn khoảng **{max(days_left, 0)} ngày**. Bấm “Gia hạn token 60 ngày” ngay.", icon=":material/key:")
        else:
            st.caption(f"Token còn khoảng **{days_left} ngày**.")
    else:
        st.caption("Chưa lưu ngày hết hạn token. Sau khi bấm gia hạn, hệ thống sẽ tự ghi lại.")

    with st.container(horizontal=True):
        if st.button("Lưu kết nối", type="primary", icon=":material/save:"):
            fresh = store.load_data()
            fresh["settings"].update({
                "user_id": user_id.strip() or "me",
                "access_token": token_input.strip(),
                "imgbb_key": imgbb_key.strip(),
            })
            if token_expiry:
                fresh["settings"]["token_expires_at"] = token_expiry.isoformat()
            store.save_data(fresh)
            st.success("Đã lưu cấu hình.", icon=":material/check_circle:")

        if st.button("Kiểm tra kết nối", icon=":material/wifi_tethering:"):
            ok, message = threads_api.check_token(store.get_token(data))
            (st.success if ok else st.error)(message)

        if st.button("Gia hạn token 60 ngày", icon=":material/autorenew:"):
            ok, message = threads_api.refresh_long_lived_token(store.get_token(data))
            if ok:
                new_token, note = message.split("|", 1)
                fresh = store.load_data()
                fresh["settings"]["access_token"] = new_token
                try:
                    days = int("".join(ch for ch in note.split("hạn")[-1].split("ngày")[0] if ch.isdigit()) or 60)
                except Exception:
                    days = 60
                fresh["settings"]["token_expires_at"] = (planner.now_vn().date() + timedelta(days=days)).isoformat()
                store.add_log(fresh, "Đã gia hạn Threads access token.")
                store.save_data(fresh)
                st.success(note)
                st.caption("Nếu bạn dùng secrets, hãy cập nhật lại THREADS_ACCESS_TOKEN bằng token mới.")
            else:
                st.error(message)

    st.divider()
    st.caption(f"Lưu trữ: **{store.storage_mode()}** · Dữ liệu: `{store.DATA_FILE}`")

if tab_schedule.open:
    st.subheader("Khung giờ và nhịp đăng")
    st.caption("Hệ thống chia đều bài trong ngày theo khung giờ vàng, tránh đăng dồn và tránh trùng giờ.")

    enabled = st.toggle("Bật tự động đăng bài", value=bool(settings.get("enabled", True)))
    preset = st.selectbox(
        "Khung giờ",
        options=[*C.SLOT_PRESETS.keys(), "Tuỳ chỉnh"],
        index=[*C.SLOT_PRESETS.keys(), "Tuỳ chỉnh"].index(settings.get("slot_preset", "4 khung giờ vàng")),
        help="Cuối tuần hệ thống tự đẩy khung sáng trễ hơn vì mọi người dậy muộn.",
    )
    custom_slots = settings.get("custom_slots", "")
    if preset == "Tuỳ chỉnh":
        custom_slots = st.text_input(
            "Các mốc giờ, cách nhau bằng dấu phẩy",
            value=custom_slots or "07:20, 11:45, 17:40, 20:50",
            placeholder="07:20, 11:45, 17:40, 20:50",
        )
    else:
        st.caption("Mốc giờ: " + ", ".join(C.SLOT_PRESETS[preset]))

    c1, c2, c3 = st.columns(3)
    posts_per_day = c1.number_input(
        "Số bài mỗi ngày", min_value=1, max_value=10, value=int(settings.get("posts_per_day", 4))
    )
    jitter = c2.number_input(
        "Dao động ngẫu nhiên (phút)", min_value=0, max_value=60, value=int(settings.get("jitter_minutes", 12))
    )
    min_gap = c3.number_input(
        "Cách nhau tối thiểu (giờ)", min_value=1.0, max_value=12.0, value=float(settings.get("min_gap_hours", 3)), step=0.5
    )

    c4, c5, c6 = st.columns(3)
    images_per_post = c4.number_input(
        "Số ảnh mỗi bài", min_value=0, max_value=C.MAX_IMAGES_PER_POST, value=int(settings.get("images_per_post", 3))
    )
    max_attempts = c5.number_input(
        "Số lần thử lại khi lỗi", min_value=1, max_value=10, value=int(settings.get("max_attempts", 3))
    )
    retry_minutes = c6.number_input(
        "Chờ bao lâu rồi thử lại (phút)", min_value=1, max_value=180, value=int(settings.get("retry_minutes", 20))
    )

    st.markdown("**Tự động bổ sung lịch**")
    auto_refill = st.toggle("Tự tạo thêm bài khi hàng đợi sắp trống", value=bool(settings.get("auto_refill", True)))
    refill_days = st.number_input(
        "Luôn giữ sẵn số ngày bài", min_value=1, max_value=14, value=int(settings.get("refill_days", 2)),
        disabled=not auto_refill,
    )

    st.markdown("**Ngày nghỉ & an toàn dữ liệu**")
    today = planner.now_vn().date()
    day_options = [today + timedelta(days=offset) for offset in range(1, 91)]
    allowed = set(day_options)
    current_blackout: list[date] = []
    for raw in settings.get("blackout_dates", []) or []:
        try:
            parsed = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if parsed in allowed:
            current_blackout.append(parsed)
    weekday_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    blackout_days = st.multiselect(
        "Ngày không đăng bài (nghỉ lễ, đi vắng…)",
        options=day_options,
        default=current_blackout,
        format_func=lambda d: f"{d:%d/%m/%Y} · {weekday_names[d.weekday()]}",
        help="Hệ thống sẽ không lên lịch và không tự bổ sung bài vào những ngày này.",
    )
    daily_backup = st.toggle(
        "Tự sao lưu dữ liệu mỗi ngày",
        value=bool(settings.get("daily_backup", True)),
        help="Giữ 14 bản gần nhất trong data/backups, giúp phục hồi khi dữ liệu bị lỗi.",
    )
    max_per_tick = st.number_input(
        "Tối đa số bài đăng mỗi lượt kiểm tra", min_value=1, max_value=20,
        value=int(settings.get("max_posts_per_tick", 3)),
        help="Giúp không đăng dồn hàng loạt nếu mở app sau nhiều giờ.",
    )

    if st.button("Lưu cài đặt", type="primary", icon=":material/save:"):
        fresh = store.load_data()
        fresh["settings"].update({
            "enabled": enabled,
            "slot_preset": preset,
            "custom_slots": custom_slots,
            "posts_per_day": int(posts_per_day),
            "jitter_minutes": int(jitter),
            "min_gap_hours": float(min_gap),
            "images_per_post": int(images_per_post),
            "max_attempts": int(max_attempts),
            "retry_minutes": int(retry_minutes),
            "auto_refill": auto_refill,
            "refill_days": int(refill_days),
            "blackout_dates": [d.isoformat() for d in blackout_days],
            "daily_backup": daily_backup,
            "max_posts_per_tick": int(max_per_tick),
        })
        store.add_log(fresh, "Cập nhật cài đặt nhịp đăng.")
        store.save_data(fresh)
        st.success("Đã lưu. Lịch đang chờ vẫn giữ nguyên, chỉ áp dụng cho bài tạo mới.", icon=":material/check_circle:")

    st.divider()
    st.subheader("Chạy thử")
    with st.container(border=True):
        st.caption(f"Worker gần nhất phản hồi: {ui.fmt_dt((data.get('worker') or {}).get('heartbeat'))}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Chạy một vòng worker ngay", width="stretch", icon=":material/bolt:"):
                with st.spinner("Đang xử lý…"):
                    worker.tick()
                st.success("Đã chạy xong một vòng.")
                st.rerun()
        with col2:
            st.caption("Bài tới giờ sẽ được đăng, lịch sẽ được bổ sung nếu bật tự động.")

if tab_deploy.open:
    st.subheader("Để hệ thống chạy khi tắt máy")
    st.markdown(
        """
Streamlit chỉ chạy khi có tiến trình Python đang sống. Muốn tắt máy mà bài vẫn đăng, hãy đưa app lên cloud.
"""
    )

    st.markdown("**Cách 1 · Streamlit Community Cloud (miễn phí, khuyến nghị)**")
    st.markdown(
        """
1. Tạo repository GitHub riêng tư và tải cả thư mục này lên (gồm `threads_app.py`, `core/`, `app_pages/`, `data/`, ảnh).
2. Vào [share.streamlit.io](https://share.streamlit.io) → New app → chọn repo, main file `threads_app.py`.
3. Trong **Settings → Secrets**, dán:
"""
    )
    st.code(
        'THREADS_ACCESS_TOKEN = "token_cua_ban"\nIMGBB_API_KEY = ""\n# Tuỳ chọn: lưu dữ liệu bền vững, không mất khi app khởi động lại\nUPSTASH_REDIS_REST_URL = ""\nUPSTASH_REDIS_REST_TOKEN = ""',
        language="toml",
    )
    st.markdown(
        """
4. Bật **UptimeRobot** (hoặc cron ping) gọi URL app mỗi 5 phút để app không bị ngủ — worker trong app sẽ tiếp tục chạy.
5. App free chỉ có ổ đĩa tạm: nếu không dùng Upstash Redis, dữ liệu có thể mất khi app redeploy/khởi động lại.
"""
    )

    st.markdown("**Cách 2 · Worker chạy nền trên VPS / máy chủ luôn bật**")
    st.code("python scheduler_worker.py", language="bash")
    st.caption(
        "Worker đọc cùng file dữ liệu (hoặc cùng Upstash), tự đăng đúng giờ, tự thử lại và tự bổ sung lịch. "
        "Chạy song song với app Streamlit cũng an toàn nhờ cơ chế khoá."
    )

    st.markdown("**Cách 3 · Windows: tự chạy khi khởi động máy**")
    st.caption("Tạo Scheduled Task chạy `python scheduler_worker.py` với thư mục làm việc là thư mục này, "
               "chọn “Run whether user is logged on or not”.")

    st.divider()
    st.subheader("Vùng nguy hiểm")
    confirm = st.text_input("Gõ `RESET` để xoá toàn bộ bài trong hàng đợi và nhật ký", value="")
    if st.button("Xoá hàng đợi", icon=":material/delete_forever:", disabled=confirm.strip().upper() != "RESET"):
        fresh = store.load_data()
        fresh["posts"] = []
        fresh["logs"] = []
        store.save_data(fresh)
        st.success("Đã xoá hàng đợi.")
        st.rerun()
