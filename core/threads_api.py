"""Giao tiếp với Threads Graph API và ImgBB."""

from __future__ import annotations

import base64
import time

import requests

from core import constants as C

TIMEOUT = 60


def _err(payload: dict) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error_user_msg") or error)
    return str(error or payload)


def create_and_publish(
    user_id: str,
    token: str,
    text: str,
    image_urls: list[str],
) -> tuple[bool, str]:
    """Tạo container rồi xuất bản lên Threads. Trả về (thành công, thông điệp)."""
    if not token.strip():
        return False, "Chưa có Threads Access Token."

    uid = user_id.strip() or "me"
    tk = token.strip()
    create_url = f"{C.API_BASE}/{uid}/threads"
    image_urls = [u for u in image_urls if u][: C.MAX_IMAGES_PER_POST]
    text = text[: C.MAX_POST_CHARS]

    try:
        if not image_urls:
            res = requests.post(
                create_url,
                data={"media_type": "TEXT", "text": text, "access_token": tk},
                timeout=TIMEOUT,
            ).json()
            if "id" not in res:
                return False, f"Tạo container văn bản thất bại: {_err(res)}"
            creation_id = res["id"]
            time.sleep(3)

        elif len(image_urls) == 1:
            res = requests.post(
                create_url,
                data={"media_type": "IMAGE", "image_url": image_urls[0], "text": text, "access_token": tk},
                timeout=TIMEOUT,
            ).json()
            if "id" not in res:
                return False, f"Tạo container ảnh thất bại: {_err(res)}"
            creation_id = res["id"]
            time.sleep(6)

        else:
            children: list[str] = []
            for idx, img_url in enumerate(image_urls):
                child = requests.post(
                    create_url,
                    data={
                        "media_type": "IMAGE",
                        "image_url": img_url,
                        "is_carousel_item": "true",
                        "access_token": tk,
                    },
                    timeout=TIMEOUT,
                ).json()
                if "id" not in child:
                    return False, f"Ảnh thứ {idx + 1} bị từ chối: {_err(child)}"
                children.append(child["id"])
                time.sleep(2)

            res = requests.post(
                create_url,
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "text": text,
                    "access_token": tk,
                },
                timeout=TIMEOUT,
            ).json()
            if "id" not in res:
                return False, f"Tạo album thất bại: {_err(res)}"
            creation_id = res["id"]
            time.sleep(8)

        publish = requests.post(
            f"{C.API_BASE}/{uid}/threads_publish",
            data={"creation_id": creation_id, "access_token": tk},
            timeout=TIMEOUT,
        ).json()

        if "id" in publish:
            return True, f"Đăng thành công ({len(image_urls)} ảnh) – ID: {publish['id']}"
        return False, f"Xuất bản thất bại: {_err(publish)}"
    except requests.RequestException as exc:
        return False, f"Lỗi mạng: {exc}"


def check_token(token: str) -> tuple[bool, str]:
    if not token.strip():
        return False, "Chưa nhập token."
    try:
        res = requests.get(
            f"{C.API_BASE}/me",
            params={"fields": "id,username", "access_token": token.strip()},
            timeout=30,
        )
        payload = res.json()
        if "id" in payload:
            return True, f"Kết nối OK – @{payload.get('username', 'không rõ')} (ID {payload['id']})"
        return False, _err(payload)
    except requests.RequestException as exc:
        return False, f"Lỗi mạng: {exc}"


def refresh_long_lived_token(token: str) -> tuple[bool, str]:
    """Gia hạn token dài hạn thêm ~60 ngày."""
    if not token.strip():
        return False, "Chưa nhập token."
    try:
        res = requests.get(
            f"{C.API_BASE}/refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": token.strip()},
            timeout=30,
        ).json()
        if res.get("access_token"):
            days = int(res.get("expires_in", 0)) // 86400
            return True, f"{res['access_token']}|Token mới hạn {days} ngày."
        return False, _err(res)
    except requests.RequestException as exc:
        return False, f"Lỗi mạng: {exc}"


def upload_image_to_imgbb(content: bytes, api_key: str) -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    res = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": api_key.strip(), "image": encoded},
        timeout=120,
    ).json()
    if res.get("success"):
        return str(res["data"]["url"])
    raise RuntimeError(f"ImgBB từ chối: {_err(res)}")
