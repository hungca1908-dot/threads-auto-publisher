"""Lập lịch đăng bài theo khung giờ vàng và tự động bổ sung hàng đợi."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

from core import constants as C
from core import content, store

MIN_LEAD_MINUTES = 8     # luôn có ít nhất 8 phút trước giờ đăng
CONFLICT_MINUTES = 12    # tránh 2 bài sát nhau


def now_vn() -> datetime:
    """Giờ Việt Nam, dạng naive để lưu/so sánh thống nhất."""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(C.TIMEZONE)).replace(tzinfo=None)


def _parse_custom(raw: str) -> list[time]:
    out: list[time] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(datetime.strptime(chunk, "%H:%M").time())
        except ValueError:
            continue
    return sorted(out)


def is_blackout(day: date, settings: dict) -> bool:
    """Ngày nghỉ: không lên lịch, không tự bổ sung bài."""
    raw = settings.get("blackout_dates") or []
    if isinstance(raw, str):
        raw = [raw]
    return day.isoformat() in {str(item)[:10] for item in raw}


def slots_for_day(day: date, settings: dict) -> list[time]:
    """Chọn khung giờ đăng cho một ngày, có tính tới cuối tuần và ngày nghỉ."""
    if is_blackout(day, settings):
        return []

    weekend = day.weekday() >= 5
    preset = settings.get("slot_preset", "4 khung giờ vàng")

    if preset == "Tuỳ chỉnh":
        slots = _parse_custom(settings.get("custom_slots", ""))
    elif weekend and preset in C.WEEKEND_PRESETS:
        slots = [datetime.strptime(s, "%H:%M").time() for s in C.WEEKEND_PRESETS[preset]]
    else:
        slots = [datetime.strptime(s, "%H:%M").time() for s in C.SLOT_PRESETS.get(preset, C.SLOT_PRESETS["4 khung giờ vàng"])]

    if not slots:
        slots = [datetime.strptime(s, "%H:%M").time() for s in C.SLOT_PRESETS["4 khung giờ vàng"]]

    wanted = max(1, int(settings.get("posts_per_day", len(slots))))
    if wanted >= len(slots):
        return slots

    # Rải đều các khung giờ trong ngày thay vì dồn hết vào buổi sáng.
    if wanted == 1:
        return [slots[len(slots) // 2]]
    step = (len(slots) - 1) / (wanted - 1)
    return [slots[round(i * step)] for i in range(wanted)]


def _busy_times(data: dict) -> list[datetime]:
    times: list[datetime] = []
    for post in data.get("posts", []):
        if post.get("status") in (C.ST_PENDING, C.ST_PUBLISHING):
            try:
                times.append(datetime.fromisoformat(post["run_at"]))
            except Exception:
                continue
    return times


def plan_times(
    data: dict,
    days: int,
    start: datetime | None = None,
    ignore_pending: bool = False,
) -> list[datetime]:
    """Sinh danh sách thời điểm đăng dự kiến cho `days` ngày tới."""
    settings = data.get("settings", {})
    jitter = int(settings.get("jitter_minutes", 0))
    min_gap = timedelta(hours=float(settings.get("min_gap_hours", 3)))

    current = start or now_vn()
    existing = [] if ignore_pending else _busy_times(data)
    planned: list[datetime] = []

    for offset in range(max(1, days)):
        day = (current + timedelta(days=offset)).date()
        for slot in slots_for_day(day, settings):
            moment = datetime.combine(day, slot)
            if jitter:
                moment += timedelta(minutes=random.randint(-jitter, jitter))
            if moment < current + timedelta(minutes=MIN_LEAD_MINUTES):
                continue

            if planned and moment - planned[-1] < min_gap:
                continue
            if any(abs((moment - busy).total_seconds()) < CONFLICT_MINUTES * 60 for busy in existing):
                continue
            planned.append(moment)

    return planned


def generate_posts(data: dict, days: int, start: datetime | None = None, max_posts: int = 200) -> int:
    """Tạo bài cho các mốc thời gian và thêm vào hàng đợi. Trả về số bài đã tạo."""
    times = plan_times(data, days, start)
    created = 0
    for moment in times:
        if created >= max_posts:
            break
        post = content.build_post(data, run_at=moment)
        if post is None:
            break
        data.setdefault("posts", []).append(post)
        created += 1

    if created:
        store.add_log(data, f"Đã tạo {created} bài cho {days} ngày tới.")
    return created


def pending_count(data: dict, only_future: bool = False) -> int:
    now = now_vn()
    total = 0
    for post in data.get("posts", []):
        if post.get("status") != C.ST_PENDING:
            continue
        if only_future:
            try:
                if datetime.fromisoformat(post["run_at"]) < now:
                    continue
            except Exception:
                continue
        total += 1
    return total


def ensure_refill(data: dict) -> int:
    """Tự bổ sung lịch khi hàng đợi sắp trống (giúp chạy dài ngày không cần vào app)."""
    settings = data.get("settings", {})
    if not settings.get("auto_refill", True):
        return 0

    target = max(1, int(settings.get("refill_days", 2))) * max(1, int(settings.get("posts_per_day", 4)))
    if pending_count(data, only_future=True) >= target:
        return 0

    needed_days = max(1, int(settings.get("refill_days", 2)))
    created = generate_posts(data, needed_days)
    if created:
        store.add_log(data, f"Tự động bổ sung {created} bài để duy trì lịch đăng.")
    return created


def next_post(data: dict) -> dict | None:
    upcoming = [p for p in data.get("posts", []) if p.get("status") == C.ST_PENDING]
    if not upcoming:
        return None
    return min(upcoming, key=lambda p: p.get("run_at", ""))


def optimise_schedule(data: dict, days: int = 7) -> int:
    """Dàn đều toàn bộ bài đang chờ vào các khung giờ vàng còn trống.

    Giữ nguyên thứ tự bài, chỉ đổi thời gian. Trả về số bài đã dời.
    """
    posts = [
        p for p in data.get("posts", [])
        if p.get("status") == C.ST_PENDING and p.get("run_at")
    ]
    if not posts:
        return 0
    posts.sort(key=lambda p: p.get("run_at", ""))

    window = max(1, int(days))
    times = plan_times(data, window, ignore_pending=True)
    guard = 0
    while len(times) < len(posts) and guard < 12:
        window += 7
        times = plan_times(data, window, ignore_pending=True)
        guard += 1
    if not times:
        return 0

    moved = 0
    for post, moment in zip(posts, times):
        new_value = moment.isoformat(timespec="seconds")
        if post.get("run_at") != new_value:
            post["run_at"] = new_value
            moved += 1

    if moved:
        store.add_log(data, f"Đã dàn đều {moved} bài vào khung giờ vàng.")
    return moved


def find_conflicts(data: dict) -> list[tuple[str, list[str]]]:
    """Tìm các bài đang chờ bị trùng giờ (cùng phút)."""
    buckets: dict[str, list[str]] = {}
    for post in data.get("posts", []):
        if post.get("status") != C.ST_PENDING:
            continue
        raw = post.get("run_at", "")
        if not raw:
            continue
        try:
            key = datetime.fromisoformat(raw).strftime("%Y-%m-%dT%H:%M")
        except Exception:
            continue
        buckets.setdefault(key, []).append(post.get("id", "?"))
    return [(key, ids) for key, ids in sorted(buckets.items()) if len(ids) > 1]


def duplicate_texts(data: dict, limit: int = 30) -> list[tuple[str, list[str]]]:
    """Các bài đang chờ có nội dung giống hệt nhau."""
    seen: dict[str, list[str]] = {}
    for post in data.get("posts", []):
        if post.get("status") not in (C.ST_PENDING, C.ST_DRAFT):
            continue
        text = (post.get("text") or "").strip()
        if not text:
            continue
        seen.setdefault(text, []).append(post.get("id", "?"))
    dupes = [(text, ids) for text, ids in seen.items() if len(ids) > 1]
    return dupes[:limit]
