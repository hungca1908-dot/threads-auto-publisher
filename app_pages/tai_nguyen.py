import re
from pathlib import Path

import streamlit as st

from core import store, threads_api, ui

data = store.load_data()
resources = data.get("resources", {})
links = list(resources.get("links", []))
images = list(resources.get("images", []))
app_dir = Path(__file__).resolve().parent.parent

ui.page_header(":material/folder_open: Tài nguyên", "Kho link tiếp thị liên kết Shopee và thư viện ảnh dùng để đăng bài.")

c1, c2, c3 = st.columns(3)
c1.metric("Link Shopee", len(links), border=True, icon=":material/link:")
c2.metric("Hình ảnh", len(images), border=True, icon=":material/image:")
c3.metric("Ảnh có URL công khai", sum(1 for i in images if i.get("url")), border=True, icon=":material/public:")

tab_links, tab_images = st.tabs(["Link Shopee", "Hình ảnh"], on_change="rerun")

if tab_links.open:
    st.caption("Dán mỗi dòng một link. Hệ thống xoay vòng lần lượt để mọi link đều được dùng, không lặp liên tục.")
    raw = st.text_area(
        "Danh sách link",
        value="\n".join(links),
        height=320,
        placeholder="https://s.shopee.vn/abc123\nhttps://s.shopee.vn/def456",
    )

    uploaded = st.file_uploader("Hoặc tải file .txt chứa danh sách link", type=["txt", "csv"])
    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        found = re.findall(r"https?://[^\s,]+", text)
        if found:
            st.info(f"Tìm thấy {len(found)} link trong file. Bấm “Lưu danh sách” bên dưới để nhập vào kho.")

    with st.container(horizontal=True):
        if st.button("Lưu danh sách", type="primary", icon=":material/save:"):
            new_links = [line.strip() for line in raw.splitlines() if line.strip()]
            fresh = store.load_data()
            fresh["resources"]["links"] = new_links
            fresh["resources"]["link_deck"] = []
            fresh["resources"]["link_cursor"] = 0
            store.add_log(fresh, f"Cập nhật kho link: {len(new_links)} link.")
            store.save_data(fresh)
            st.success(f"Đã lưu {len(new_links)} link.", icon=":material/check_circle:")
            st.rerun()

        if st.button("Lọc trùng", icon=":material/filter_alt:"):
            unique = list(dict.fromkeys(line.strip() for line in raw.splitlines() if line.strip()))
            fresh = store.load_data()
            fresh["resources"]["links"] = unique
            fresh["resources"]["link_deck"] = []
            fresh["resources"]["link_cursor"] = 0
            store.save_data(fresh)
            st.success(f"Đã lọc trùng, còn {len(unique)} link.", icon=":material/check_circle:")
            st.rerun()

        if st.button("Xoá toàn bộ link", icon=":material/delete:"):
            fresh = store.load_data()
            fresh["resources"]["links"] = []
            fresh["resources"]["link_deck"] = []
            fresh["resources"]["link_cursor"] = 0
            store.save_data(fresh)
            st.rerun()

    if links:
        st.caption(f"Đang dùng: {resources.get('link_cursor', 0)}/{len(links)} link trong vòng xoay hiện tại.")

if tab_images.open:
    st.caption("Ảnh cần có URL công khai (https) để Threads tải về. Ảnh trong thư mục đã được ghép sẵn URL i.ibb.co.")

    with st.container(border=True):
        st.markdown("**Thêm ảnh**")
        new_url = st.text_input("Dán URL ảnh (https://…)", placeholder="https://i.ibb.co/…/anh.jpg")
        if st.button("Thêm URL", icon=":material/add_link:"):
            if not new_url.startswith("http"):
                st.error("URL phải bắt đầu bằng http:// hoặc https://")
            elif any(i.get("url") == new_url.strip() for i in images):
                st.warning("Ảnh này đã có trong kho.")
            else:
                fresh = store.load_data()
                fresh["resources"]["images"].append({"file": "", "url": new_url.strip(), "added": ""})
                fresh["resources"]["image_deck"] = []
                fresh["resources"]["image_cursor"] = 0
                store.save_data(fresh)
                st.success("Đã thêm ảnh.", icon=":material/check_circle:")
                st.rerun()

        st.caption("Hoặc tải ảnh từ máy lên ImgBB (cần ImgBB API Key trong Cài đặt):")
        files = st.file_uploader("Chọn ảnh", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
        if files and st.button("Tải lên ImgBB", icon=":material/cloud_upload:"):
            key = store.get_imgbb_key(data)
            if not key:
                st.error("Thiếu ImgBB API Key. Thêm trong trang Cài đặt trước.")
            else:
                fresh = store.load_data()
                progress = st.progress(0.0, text="Đang tải ảnh…")
                added = 0
                for idx, item in enumerate(files, start=1):
                    try:
                        url = threads_api.upload_image_to_imgbb(item.getvalue(), key)
                        fresh["resources"]["images"].append({"file": item.name, "url": url, "added": ""})
                        added += 1
                    except Exception as exc:
                        st.warning(f"{item.name}: {exc}")
                    progress.progress(idx / len(files))
                fresh["resources"]["image_deck"] = []
                fresh["resources"]["image_cursor"] = 0
                store.save_data(fresh)
                st.success(f"Đã thêm {added} ảnh.", icon=":material/check_circle:")
                st.rerun()

        if st.button("Quét lại thư mục để thêm ảnh mới", icon=":material/folder_copy:"):
            fresh = store.load_data()
            known = {str(i.get("file", "")) for i in fresh["resources"]["images"]}
            added = 0
            for path in sorted(app_dir.glob("*")):
                if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or path.name in known:
                    continue
                fresh["resources"]["images"].append({"file": path.name, "url": "", "added": ""})
                added += 1
            if added:
                store.save_data(fresh)
                st.success(f"Đã thêm {added} ảnh từ thư mục (cần bổ sung URL công khai).")
            else:
                st.info("Không có ảnh mới trong thư mục.")

    if images:
        st.subheader("Thư viện ảnh")
        cols = st.columns(4)
        for idx, image in enumerate(images):
            with cols[idx % 4]:
                url = image.get("url")
                if url:
                    st.image(url, width="stretch", alt=f"Ảnh {idx + 1} trong kho")
                else:
                    st.container(height=120, border=True).caption("Chưa có URL công khai")
                st.caption(f"Ảnh {idx + 1}")
                if url:
                    st.caption(url[:42] + "…" if len(url) > 42 else url)

        to_remove = st.multiselect(
            "Xoá ảnh khỏi kho",
            options=[f"Ảnh {i + 1}" for i in range(len(images))],
        )
        if to_remove and st.button("Xoá ảnh đã chọn", icon=":material/delete:"):
            remove_idx = {int(label.split()[1]) - 1 for label in to_remove}
            fresh = store.load_data()
            fresh["resources"]["images"] = [
                img for i, img in enumerate(fresh["resources"]["images"]) if i not in remove_idx
            ]
            fresh["resources"]["image_deck"] = []
            fresh["resources"]["image_cursor"] = 0
            store.save_data(fresh)
            st.rerun()
