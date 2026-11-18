"""Sinh nội dung bài đăng: xoay chữ, chọn link Shopee và chọn ảnh không trùng."""

from __future__ import annotations

import random
import re
import uuid
from datetime import datetime

from core import constants as C

SPIN_RE = re.compile(r"\{([^{}|]+(?:\|[^{}]+)+)\}")
LINK_TOKEN = "{link}"


def render_spin(text: str) -> str:
    """Thay các cụm {a|b|c} bằng một lựa chọn ngẫu nhiên."""
    for _ in range(10):
        if not SPIN_RE.search(text):
            break
        text = SPIN_RE.sub(lambda m: random.choice(m.group(1).split("|")).strip(), text)
    return text


def _deck_pick(data: dict, items: list[str], deck_key: str, cursor_key: str) -> str | None:
    """Rút lần lượt từng phần tử trong bộ bài đã xáo, hết thì xáo lại.

    Nhờ vậy mọi link/ảnh đều được dùng đều, không bị lặp liên tục.
    """
    if not items:
        return None
    res = data.setdefault("resources", {})
    valid = set(items)
    deck = [x for x in res.get(deck_key, []) if x in valid]
    if len(deck) != len(items):
        deck = list(items)
        random.shuffle(deck)
        res[deck_key] = deck
        res[cursor_key] = 0
    cursor = int(res.get(cursor_key, 0))
    if cursor >= len(deck):
        random.shuffle(deck)
        res[deck_key] = deck
        cursor = 0
    picked = deck[cursor]
    res[cursor_key] = cursor + 1
    return picked


def pick_link(data: dict) -> str:
    links = data.get("resources", {}).get("links", [])
    return _deck_pick(data, links, "link_deck", "link_cursor") or ""


def pick_images(data: dict, count: int) -> list[str]:
    res = data.get("resources", {})
    urls = [img["url"] for img in res.get("images", []) if img.get("url")]
    count = max(0, min(count, len(urls), C.MAX_IMAGES_PER_POST))
    chosen: list[str] = []
    guard = 0
    while len(chosen) < count and guard < len(urls) * 2:
        candidate = _deck_pick(data, urls, "image_deck", "image_cursor")
        guard += 1
        if candidate and candidate not in chosen:
            chosen.append(candidate)
    return chosen


def enabled_templates(data: dict) -> list[dict]:
    return [t for t in data.get("templates", []) if t.get("enabled", True) and t.get("text", "").strip()]


def choose_template(data: dict, theme: str | None = None) -> dict | None:
    """Chọn mẫu nội dung, tránh lặp lại chủ đề của bài gần nhất."""
    pool = enabled_templates(data)
    if theme:
        filtered = [t for t in pool if t["theme"] == theme]
        pool = filtered or pool
    if not pool:
        return None

    last_theme = ""
    posts = data.get("posts", [])
    if posts:
        last = sorted(posts, key=lambda p: p.get("created_at", ""))[-1]
        last_theme = last.get("theme", "")

    candidates = [t for t in pool if t["theme"] != last_theme] or pool
    return random.choice(candidates)


def fit_text(body: str, link: str) -> str:
    """Ghép nội dung + link, đảm bảo không vượt 500 ký tự của Threads."""
    body = body.strip()
    if not link:
        return body.replace(LINK_TOKEN, "").strip()[: C.MAX_POST_CHARS]

    if LINK_TOKEN in body:
        text = body.replace(LINK_TOKEN, link).strip()
    else:
        text = f"{body}\n👉 {link}".strip() if body else link

    if len(text) <= C.MAX_POST_CHARS:
        return text

    # Cắt bớt phần thân, luôn giữ nguyên link ở cuối.
    tail = f"\n👉 {link}" if link and link not in body else f"\n{link}"
    room = C.MAX_POST_CHARS - len(tail) - 1
    body = body.replace(LINK_TOKEN, "").strip()
    return f"{body[:max(room, 0)].rstrip()}…{tail}"


def build_post(
    data: dict,
    template: dict | None = None,
    link: str | None = None,
    images: list[str] | None = None,
    run_at: datetime | None = None,
) -> dict | None:
    """Tạo một bài đăng hoàn chỉnh (chưa lưu vào hàng đợi)."""
    tmpl = template or choose_template(data)
    if tmpl is None:
        return None

    recent = {
        (p.get("text") or "").strip()
        for p in data.get("posts", [])[-25:]
        if p.get("status") in (C.ST_PENDING, C.ST_DRAFT, C.ST_PUBLISHED)
    }

    chosen_link = link if link is not None else pick_link(data)
    text = ""
    for _ in range(6):
        body = render_spin(tmpl.get("text", ""))
        text = fit_text(body, chosen_link)
        # Tránh lặp y nguyên một bài gần đây (khi chọn ngẫu nhiên).
        if link is not None or text not in recent:
            break

    count = int(data.get("settings", {}).get("images_per_post", 3))
    chosen_images = images if images is not None else pick_images(data, count)

    return {
        "id": uuid.uuid4().hex[:12],
        "text": text,
        "link": chosen_link,
        "image_urls": chosen_images,
        "template_id": tmpl.get("id", ""),
        "theme": tmpl.get("theme", ""),
        "run_at": (run_at or datetime.now()).isoformat(timespec="seconds"),
        "status": C.ST_PENDING,
        "attempts": 0,
        "last_error": "",
        "published_id": "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def preview(template_text: str, data: dict) -> str:
    link = (data.get("resources", {}).get("links") or [""])[0]
    return fit_text(render_spin(template_text), link)
