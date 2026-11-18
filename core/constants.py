"""Hằng số dùng chung: trạng thái bài đăng, khung giờ vàng, thư viện nội dung."""

from __future__ import annotations

APP_NAME = "Threads Auto Publisher"
TIMEZONE = "Asia/Ho_Chi_Minh"
MAX_POST_CHARS = 500          # Giới hạn ký tự của Threads
MAX_IMAGES_PER_POST = 20      # Giới hạn ảnh / album của Threads
API_BASE = "https://graph.threads.net/v1.0"

# ---------------- Trạng thái bài đăng ----------------
ST_DRAFT = "draft"
ST_PENDING = "pending"
ST_PUBLISHING = "publishing"
ST_PUBLISHED = "published"
ST_FAILED = "failed"

STATUS_LABELS = {
    ST_DRAFT: "Nháp",
    ST_PENDING: "Đang chờ",
    ST_PUBLISHING: "Đang đăng",
    ST_PUBLISHED: "Đã đăng",
    ST_FAILED: "Lỗi",
}

STATUS_ICONS = {
    ST_DRAFT: ":material/edit_note:",
    ST_PENDING: ":material/schedule:",
    ST_PUBLISHING: ":material/sync:",
    ST_PUBLISHED: ":material/check_circle:",
    ST_FAILED: ":material/error:",
}

# ---------------- Khung giờ vàng (giờ Việt Nam) ----------------
# Người dùng Việt lướt Threads mạnh nhất: sáng đi làm, trưa, tan làm, tối.
SLOT_PRESETS = {
    "4 khung giờ vàng": ["07:20", "11:45", "17:40", "20:50"],
    "3 khung giờ chính": ["08:00", "12:15", "20:45"],
    "5 khung giờ cao điểm": ["07:00", "10:00", "12:15", "17:30", "21:00"],
    "2 khung giờ nhẹ nhàng": ["09:00", "20:30"],
}

# Cuối tuần mọi người dậy muộn hơn -> đẩy khung sáng trễ lại.
WEEKEND_PRESETS = {
    "4 khung giờ vàng": ["08:15", "12:00", "17:00", "21:00"],
    "3 khung giờ chính": ["08:45", "12:30", "21:00"],
    "5 khung giờ cao điểm": ["08:00", "10:30", "12:30", "17:00", "21:00"],
    "2 khung giờ nhẹ nhàng": ["09:30", "21:00"],
}

THEME_LABELS = {
    "san_sale": "Săn sale",
    "meo": "Mẹo tiết kiệm",
    "ma_giam_gia": "Mã giảm giá",
    "tuong_tac": "Hỏi đáp – tương tác",
    "review": "Review – trải nghiệm",
    "hoan_tien": "Hoàn tiền",
}

DEFAULT_SETTINGS = {
    "user_id": "me",
    "access_token": "",
    "imgbb_key": "",
    "enabled": True,
    "slot_preset": "4 khung giờ vàng",
    "custom_slots": "",           # "07:20, 11:45, 17:40, 20:50"
    "posts_per_day": 4,
    "jitter_minutes": 12,
    "min_gap_hours": 3,
    "images_per_post": 3,
    "auto_refill": True,
    "refill_days": 2,
    "max_attempts": 3,
    "retry_minutes": 20,
    "blackout_dates": [],         # ["2026-12-25", ...] – ngày không đăng bài
    "daily_backup": True,         # tự sao lưu dữ liệu mỗi ngày
    "token_expires_at": "",       # ISO date, để cảnh báo token sắp hết hạn
    "max_posts_per_tick": 3,      # tránh đăng dồn khi mở app sau nhiều giờ
}

# ---------------- Thư viện nội dung ----------------
# Cú pháp xoay chữ: {lựa chọn 1|lựa chọn 2} - mỗi lần đăng sẽ chọn ngẫu nhiên 1.
# {link} sẽ được thay bằng 1 link Shopee ngẫu nhiên trong kho tài nguyên.
DEFAULT_TEMPLATES = [
    ("t01", "san_sale", """Săn sale {không cần|chẳng phải} thức nửa đêm 😌
Mình có sẵn mã 100K cho đơn đầu tiên, áp vào là trừ thẳng.
Cùng một món đồ, người mua đắt hơn chỉ vì thiếu đúng một cái mã.
👉 Lấy mã: {link}
Số lượng có hạn, ai nhanh tay trước nha!"""),
    ("t02", "san_sale", """Ba thứ nên chuẩn bị trước khi bấm “Mua ngay”:
1. Món đồ thật sự cần
2. Mã giảm giá
3. Một chút bình tĩnh 😆
Thiếu cái số 2 là dễ mất tiền oan nhất.
Mã 100K đây: {link}"""),
    ("t03", "san_sale", """Sự thật hơi đau: đợi đến ngày sale mới đi tìm mã thì thường… hết mã 😭
Chuẩn bị trước một phút, tiết kiệm cả trăm nghìn.
Ai cần mã 100K thì lấy ở đây: {link}"""),
    ("t04", "san_sale", """Ví mỏng không phải cái tội, mua đắt mới là tội 😌
Cùng shop, cùng sản phẩm, khác nhau đúng một cái mã giảm giá.
Mình để mã 100K ở đây, ai nhanh được: {link}"""),
    ("t05", "san_sale", """Đừng mua 10 món rẻ, hãy mua 3 món thật cần.
Nhưng nếu 3 món đó có mã giảm 100K thì… càng nên mua 😄
Mã đây: {link}"""),
    ("t06", "san_sale", """Mấy đứa hay khoe “mua rẻ hơn bạn” không giỏi mặc cả đâu, tụi nó chỉ có sẵn mã 🤫
Mã 100K đơn đầu, dùng là trừ luôn, không điều kiện rườm rà.
{link}"""),
    ("t07", "san_sale", """Tháng này bạn đã dùng mã giảm giá nào chưa?
Nếu chưa thì đây là dấu hiệu bạn đang chi tiêu hơi phóng khoáng 😌
Mã 100K cho đơn đầu: {link}"""),
    ("t08", "san_sale", """Người khôn ngoan không chờ sale, họ chuẩn bị mã trước ngày sale.
Mình chuẩn bị sẵn rồi, phần bạn là bấm vào đây: {link}"""),
    ("t09", "meo", """Mẹo nhỏ mà tiết kiệm thật: trước khi thanh toán, luôn bấm vào ô “mã giảm giá”.
Nhiều shop để mã ẩn ở đó, không bấm là mất.
Mình có sẵn mã 100K cho bạn: {link}"""),
    ("t10", "meo", """Cách mình giảm 30% hoá đơn mỗi tháng:
1. Bỏ đồ vào giỏ, đợi đúng ngày sale
2. Săn mã trước giờ G
3. Không mua gì ngoài danh sách
Bước 2 khó nhất, nên mình để mã sẵn đây: {link}"""),
    ("t11", "meo", """Mua online mà không dùng mã giảm giá thì giống đi chợ mà không trả giá vậy đó 😅
{link}"""),
    ("t12", "meo", """Tâm lý học bán hàng: freeship khiến bạn mua thêm 2 món.
Mã giảm 100K cũng vậy 😆
Ít nhất lần này bạn tiết kiệm thật: {link}"""),
    ("t13", "meo", """Đừng để đồ trong giỏ quá 3 ngày.
Không phải vì shop hết hàng, mà vì bạn sẽ quên mất mình đã có mã giảm giá 😌
{link}"""),
    ("t14", "meo", """Quy tắc 24h của mình: món gì sau 24h vẫn thấy cần thì mua kèm mã.
Món gì quên luôn thì đã tiết kiệm được 100%.
Món cần thật thì đây: {link}"""),
    ("t15", "ma_giam_gia", """Mã 100K đơn đầu tiên, ai chưa dùng thì phí lắm.
Áp vào là trừ thẳng vào đơn, không cần đợi sale.
Lấy tại: {link}
Mình không giữ được lâu đâu nha."""),
    ("t16", "ma_giam_gia", """Hỏi thật: lần cuối bạn được giảm giá 100K là khi nào?
Nếu không nhớ nổi thì thử cái này xem: {link}"""),
    ("t17", "ma_giam_gia", """Không phải cứ chờ 11/11 mới rẻ.
Ngày thường + đúng mã = vẫn rẻ hơn sale.
Mã đây: {link}"""),
    ("t18", "ma_giam_gia", """Mình vừa tiết kiệm được 100K chỉ vì bấm vào một chỗ.
Chỗ đó đây: {link}
Bạn thử xem còn không, nhanh tay nha."""),
    ("t19", "ma_giam_gia", """Nếu bạn đang định mua gì đó trên Shopee, dừng lại 10 giây.
Áp mã trước đã.
Mã 100K: {link}"""),
    ("t20", "tuong_tac", """Nếu chỉ được chọn một món dưới 100K mà dùng được cả năm, bạn chọn gì?
Comment cho mình xem, biết đâu thành danh sách mua sắm chung 😄
Gợi ý của mình: mã giảm giá, rẻ mà dùng được nhiều lần: {link}"""),
    ("t21", "tuong_tac", """Team “thêm vào giỏ rồi để đó” điểm danh 🙋
Bạn đang giữ bao nhiêu món trong giỏ?
Mình vừa dọn giỏ và tiết kiệm được 100K nhờ cái này: {link}"""),
    ("t22", "tuong_tac", """Chuyện buồn nhất của người mua online:
Đợi 3 ngày sale, đến giờ G thì… quên áp mã.
Đừng như mình. Mã đây: {link}"""),
    ("t23", "tuong_tac", """Bạn thuộc kiểu người nào?
A. Thấy sale là mua
B. Bỏ giỏ rồi quên
C. Săn mã trước rồi mới mua
Team C comment “1” để mình gửi mã cho: {link}"""),
    ("t24", "tuong_tac", """Món đồ bạn mua nhiều lần nhất trên Shopee là gì?
Mình là… mã giảm giá 😆 Rẻ mà lần nào cũng có lời.
{link}"""),
    ("t25", "tuong_tac", """Cuối tuần rồi, dọn giỏ hàng thôi.
Nhớ áp mã trước khi thanh toán nha, đừng để mất tiền oan.
Mã 100K: {link}"""),
    ("t26", "review", """Review thật: tháng trước mình mua 5 đơn, đơn nào cũng áp mã.
Tổng tiết kiệm gần 400K, đủ đi ăn một bữa ngon 😌
Bí quyết chỉ có một: có mã trước khi mua. {link}"""),
    ("t27", "review", """Đồ tốt không cần đắt, chỉ cần mua đúng lúc.
Mình canh mã từ sáng, tối về chốt đơn, rẻ hơn hẳn.
{link}"""),
    ("t28", "review", """Món mình mua nhiều nhất tháng này: đồ gia dụng nhỏ.
Cái nào cũng có mã, cái nào cũng rẻ hơn giá hiển thị.
Link lấy mã: {link}"""),
    ("t29", "hoan_tien", """Mua hàng mà không có mã, không hoàn tiền thì đang nuôi shop hơi nhiều rồi đó 😅
Bắt đầu từ cái mã 100K này cho dễ: {link}"""),
    ("t30", "hoan_tien", """Tiền không tự sinh ra, nhưng có thể ở lại trong ví lâu hơn nếu bạn biết áp mã.
{link}"""),
]
