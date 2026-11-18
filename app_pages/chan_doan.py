import json
from pathlib import Path

import streamlit as st

from core import constants as C
from core import diagnostics, planner, store, threads_api, ui, worker

data = store.load_data()
settings = data.get("settings", {})
summary = diagnostics.health_summary(data)

ui.page_header(
    ":material/health_and_safety: Chẩn đoán hệ thống",
    "Kiểm tra token, lưu trữ, ảnh và hàng đợi. Sửa lỗi ngay tại chỗ, không cần mở file dữ liệu.",
)

m1, m2, m3, m4 = st.columns(4)
age = summary["worker_age"]
if not summary["enabled"]:
    worker_label = "Tạm dừng"
elif age is not None and age < 60:
    worker_label = "Đang chạy"
elif age is not None:
    worker_label = f"Trễ {int(age // 60)} phút"
else:
    worker_label = "Chưa chạy"
m1.metric("Worker", worker_label, border=True, icon=":material/bolt:")
m2.metric("Bài đang chờ", summary["pending"], border=True, icon=":material/schedule:")
m3.metric("Khung giờ trùng", len(summary["conflicts"]), border=True, icon=":material/content_copy:")
m4.metric("Token", "Có" if summary["token"] else "Thiếu", border=True, icon=":material/key:")

alerts = []
if not summary["token"]:
    alerts.append(":material/key_off: Chưa có Threads token – worker sẽ không đăng được bài nào.")
if summary["worker_age"] is None or (summary["worker_age"] or 0) > 90:
    alerts.append(":material/warning: Worker chưa phản hồi trong 90 giây gần nhất.")
if summary["overdue"]:
    alerts.append(f":material/schedule: Có **{summary['overdue']}** bài đã quá giờ mà chưa đăng.")
if summary["conflicts"]:
    alerts.append(f":material/content_copy: Có **{len(summary['conflicts'])}** khung giờ bị trùng bài.")
if summary["stuck"]:
    alerts.append(f":material/pause_circle: Có **{summary['stuck']}** bài kẹt ở trạng thái “đang đăng”.")
if not summary["enabled"]:
    alerts.append(":material/pause: Hệ thống đang tạm dừng theo cài đặt.")

if alerts:
    for note in alerts:
        st.warning(note)
else:
    st.success("Không phát hiện vấn đề nghiêm trọng.", icon=":material/verified:")

tab_overview, tab_media, tab_backup = st.tabs(["Tổng quan", "Ảnh & link", "Sao lưu & phục hồi"], on_change="rerun")

# ---------------------------------------------------------------- TỔNG QUAN
if tab_overview.open:
    st.subheader("Kiểm tra nhanh")
    rows = []

    def add_check(name: str, ok: bool, detail: str) -> None:
        rows.append({"Hạng mục": name, "Kết quả": "OK" if ok else "Cần chú ý", "Chi tiết": detail})

    add_check("Dữ liệu", True, f"{len(data.get('posts', []))} bài · lưu tại {store.storage_mode()}")
    add_check("Token", summary["token"], "Đã cấu hình" if summary["token"] else "Thiếu token – vào Cài đặt")
    add_check(
        "Worker",
        summary["worker_age"] is not None and summary["worker_age"] < 90,
        f"Phản hồi gần nhất: {ui.fmt_dt((data.get('worker') or {}).get('heartbeat'))}",
    )
    add_check("Tự động đăng", summary["enabled"], "Đang bật" if summary["enabled"] else "Đang tạm dừng")
    add_check("Tự bổ sung lịch", bool(settings.get("auto_refill", True)),
              f"Giữ {settings.get('refill_days', 2)} ngày bài" if settings.get("auto_refill", True) else "Đang tắt")
    add_check("Bài quá giờ", summary["overdue"] == 0, f"{summary['overdue']} bài đang chờ đăng bù")
    add_check("Trùng giờ", not summary["conflicts"],
              ", ".join(f"{ui.fmt_dt(key)} ({len(ids)} bài)" for key, ids in summary["conflicts"][:3]) or "Không có")
    add_check("Bài kẹt", summary["stuck"] == 0, f"{summary['stuck']} bài ở trạng thái đang đăng")
    st.dataframe(rows, hide_index=True, width="stretch", alt="Bảng kiểm tra hệ thống")

    st.divider()
    st.subheader("Sửa nhanh")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Kiểm tra token", width="stretch", icon=":material/wifi_tethering:"):
            ok, message = threads_api.check_token(store.get_token(data))
            (st.success if ok else st.error)(message)
    with c2:
        if st.button("Chạy một vòng worker", width="stretch", icon=":material/bolt:"):
            with st.spinner("Đang xử lý…"):
                worker.tick()
            st.toast("Đã chạy xong một vòng.")
            st.rerun()
    with c3:
        if st.button("Kiểm tra đọc/ghi dữ liệu", width="stretch", icon=":material/database:"):
            ok, message = diagnostics.check_storage()
            (st.success if ok else st.error)(message)

    c4, c5, c6 = st.columns(3)
    with c4:
        if st.button(
            f"Dàn đều {summary['pending']} bài đang chờ",
            width="stretch",
            icon=":material/straighten:",
            disabled=summary["pending"] == 0,
            help="Xếp lại toàn bộ bài chờ vào các khung giờ vàng còn trống, giữ nguyên thứ tự.",
        ):
            fresh = store.load_data()
            moved = planner.optimise_schedule(fresh, days=max(3, settings.get("refill_days", 2) * 2))
            store.save_data(fresh)
            st.toast(f"Đã dời {moved} bài vào khung giờ vàng.")
            st.rerun()
    with c5:
        if st.button(
            "Xử lý bài bị kẹt",
            width="stretch",
            icon=":material/healing:",
            disabled=summary["stuck"] == 0,
        ):
            def fix(d: dict) -> None:
                for post in d.get("posts", []):
                    if post.get("status") == C.ST_PUBLISHING:
                        post["status"] = C.ST_FAILED
                        post["last_error"] = "Đã đánh dấu lỗi thủ công. Kiểm tra Threads trước khi đăng lại."

            store.update_data(fix)
            st.toast("Đã chuyển các bài bị kẹt sang trạng thái Lỗi.")
            st.rerun()
    with c6:
        if st.button(
            "Chuyển bài lỗi về nháp",
            width="stretch",
            icon=":material/edit_note:",
            disabled=summary["failed"] == 0,
        ):
            def to_draft(d: dict) -> None:
                for post in d.get("posts", []):
                    if post.get("status") == C.ST_FAILED:
                        post.update({"status": C.ST_DRAFT, "run_at": "", "attempts": 0, "last_error": ""})

            store.update_data(to_draft)
            st.toast("Đã chuyển bài lỗi về Nháp.")
            st.rerun()

    if summary["conflicts"]:
        with st.expander("Chi tiết các khung giờ trùng", icon=":material/content_copy:"):
            for key, ids in summary["conflicts"]:
                st.markdown(f"- **{ui.fmt_dt(key)}** · mã: `{'`, `'.join(ids)}`")

    duplicates = planner.duplicate_texts(data)
    if duplicates:
        with st.expander(f"Nội dung trùng nhau ({len(duplicates)} nhóm)", icon=":material/file_copy:"):
            for text, ids in duplicates:
                st.markdown(f"`{'`, `'.join(ids)}`")
                st.caption(text[:160] + ("…" if len(text) > 160 else ""))

    st.divider()
    st.subheader("Môi trường")
    env = diagnostics.environment()
    st.dataframe(
        [{"Thành phần": key, "Giá trị": value} for key, value in env.items()],
        hide_index=True,
        width="stretch",
        alt="Thông tin môi trường chạy",
    )

# ---------------------------------------------------------------- ẢNH & LINK
if tab_media.open:
    resources = data.get("resources", {})
    images = [img for img in resources.get("images", []) if img.get("url")]
    links = resources.get("links", [])

    st.subheader(f"Ảnh công khai ({len(images)})")
    st.caption("Threads chỉ nhận ảnh có URL công khai. Ảnh lỗi sẽ làm bài đăng thất bại.")
    if st.button("Kiểm tra toàn bộ ảnh", icon=":material/image_search:", type="primary"):
        with st.spinner(f"Đang kiểm tra {min(len(images), 25)} ảnh…"):
            st.session_state["image_check"] = diagnostics.check_images([img["url"] for img in images])

    results = st.session_state.get("image_check")
    if results:
        rows = [
            {
                "Ảnh": f"Ảnh {idx + 1}",
                "Trạng thái": "OK" if item["ok"] else "Lỗi",
                "Phản hồi": item["detail"],
                "Thời gian (ms)": item["ms"],
                "URL": item["url"],
            }
            for idx, item in enumerate(results)
        ]
        st.dataframe(rows, hide_index=True, width="stretch", alt="Kết quả kiểm tra ảnh")
        broken = [item["url"] for item in results if not item["ok"]]
        if broken:
            st.error(f"{len(broken)} ảnh không truy cập được. Nên tải lại ảnh lên ImgBB hoặc loại bỏ.")
            if st.button(f"Loại bỏ {len(broken)} ảnh lỗi", icon=":material/delete_sweep:"):
                broken_set = set(broken)

                def clean(d: dict) -> None:
                    res = d.setdefault("resources", {})
                    res["images"] = [img for img in res.get("images", []) if img.get("url") not in broken_set]
                    res["image_deck"] = [u for u in res.get("image_deck", []) if u not in broken_set]
                    for post in d.get("posts", []):
                        post["image_urls"] = [u for u in post.get("image_urls", []) if u not in broken_set]

                store.update_data(clean)
                st.session_state.pop("image_check", None)
                st.toast("Đã loại bỏ ảnh lỗi khỏi kho và khỏi các bài đang chờ.")
                st.rerun()
        else:
            st.success("Tất cả ảnh đều truy cập được.", icon=":material/check_circle:")

    st.divider()
    st.subheader(f"Link Shopee ({len(links)})")
    unique_links = len(set(links))
    c1, c2 = st.columns(2)
    c1.metric("Link đang có", len(links), border=True, icon=":material/link:")
    c2.metric("Link không trùng", unique_links, border=True, icon=":material/fingerprint:")
    if len(links) != unique_links:
        st.warning(f"Có {len(links) - unique_links} link bị lặp. Nên dọn bớt để nội dung đa dạng hơn.")
        if st.button("Loại bỏ link trùng", icon=":material/cleaning_services:"):
            def dedupe(d: dict) -> None:
                res = d.setdefault("resources", {})
                seen: set[str] = set()
                kept = []
                for link in res.get("links", []):
                    if link in seen:
                        continue
                    seen.add(link)
                    kept.append(link)
                res["links"] = kept
                res["link_deck"] = [x for x in res.get("link_deck", []) if x in seen]

            store.update_data(dedupe)
            st.toast("Đã dọn link trùng.")
            st.rerun()
    else:
        st.caption("Không có link trùng.")

# ---------------------------------------------------------------- SAO LƯU
if tab_backup.open:
    st.subheader("Sao lưu dữ liệu")
    st.caption("Dữ liệu gồm bài viết, lịch đăng, cài đặt, mẫu nội dung và tài nguyên.")
    backup_age = store.backup_age_hours()
    c1, c2 = st.columns(2)
    c1.metric("Bản sao lưu gần nhất", f"{backup_age:.1f} giờ trước" if backup_age is not None else "Chưa có",
              border=True, icon=":material/backup:")
    c2.metric("Số bản đang giữ", len(store.list_backups()), border=True, icon=":material/history:")
    st.caption(f"Tự sao lưu hằng ngày: {'Bật' if settings.get('daily_backup', True) else 'Tắt'} "
               f"· Thư mục: `{store.BACKUP_DIR}`")

    if st.button("Tạo bản sao lưu ngay", type="primary", icon=":material/add_circle:"):
        path = store.create_backup("manual")
        if path:
            st.toast(f"Đã tạo: {path.name}")
            st.rerun()
        else:
            st.error("Không tạo được bản sao lưu.")

    backups = store.list_backups()
    if backups:
        st.divider()
        st.subheader("Phục hồi")
        st.warning("Phục hồi sẽ thay thế dữ liệu hiện tại. Hệ thống tự tạo một bản sao lưu trước khi khôi phục.")
        choice = st.selectbox(
            "Chọn bản sao lưu",
            options=[str(p) for p in backups],
            format_func=lambda p: Path(p).name,
        )
        with st.expander("Xem trước nội dung bản sao lưu", icon=":material/visibility:"):
            try:
                preview = json.loads(Path(choice).read_text(encoding="utf-8"))
                st.caption(
                    f"{len(preview.get('posts', []))} bài · "
                    f"{len(preview.get('templates', []))} mẫu · "
                    f"{len(preview.get('resources', {}).get('links', []))} link · "
                    f"cập nhật {preview.get('meta', {}).get('updated_at', '—')}"
                )
            except Exception as exc:
                st.error(f"Không đọc được bản sao lưu: {exc}")

        confirm = st.text_input("Gõ `RESTORE` để xác nhận phục hồi", value="")
        if st.button("Phục hồi từ bản này", icon=":material/settings_backup_restore:",
                     disabled=confirm.strip().upper() != "RESTORE"):
            if store.restore_backup(choice):
                st.toast("Đã phục hồi dữ liệu.")
                st.rerun()
            else:
                st.error("Phục hồi thất bại – file không hợp lệ.")
    else:
        st.info("Chưa có bản sao lưu nào. Bấm “Tạo bản sao lưu ngay” để bắt đầu.", icon=":material/backup:")

    st.divider()
    with st.expander("Nhật ký hoạt động gần đây", icon=":material/receipt_long:"):
        ui.log_panel(data, limit=30)
