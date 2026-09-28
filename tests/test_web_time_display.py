"""
test_web_time_display.py — Khóa chặt hiển thị giờ trên web reports.

Yêu cầu người dùng (09/2026):
  1. Nhãn giờ 'ICT' → 'UTC+7' trên toàn bộ web reports
  2. Emoji đồng hồ (🕛..🕚) bên cạnh giờ, đổi theo giờ hiện tại (VN) — clock chạy real-time
  3. README.md song ngữ (English mặc định + Tiếng Việt) như web reports (EN mặc định,
     nút 🇻🇳 VI chuyển tiếng Việt)

Test chỉ đọc file đã commit — không cần build lại HTML.
"""

import os
import re

ROOT = os.getcwd()
BUILDER = os.path.join(ROOT, "src", "reporting", "report_builder.py")


# ── 1. Nguồn: report_builder.py ──────────────────────────────────────────────
def test_builder_has_no_ict_label():
    """Không còn chuỗi ' ICT' (nhãn giờ cũ) trong builder."""
    src = open(BUILDER, encoding="utf-8").read()
    assert "' ICT" not in src and " ICT'" not in src


def test_builder_clock_uses_utc_plus_7_and_emoji():
    """Clock JS: UTC+7 + CLOCK_EMOJIS theo giờ Việt Nam, update mỗi giây."""
    src = open(BUILDER, encoding="utf-8").read()
    assert "UTC+7" in src
    assert "CLOCK_EMOJIS" in src
    # đủ 12 mặt đồng hồ (00→🕛, 01→🕐, ... 23→🕚)
    m = re.search(r"CLOCK_EMOJIS = \[(.*?)\]", src)
    assert m, "thiếu mảng CLOCK_EMOJIS"
    emojis = re.findall(r"[\U0001F550-\U0001F55B]", m.group(1))
    assert len(emojis) >= 12, f"thiếu mặt đồng hồ: {len(emojis)}/12"
    # giờ Việt Nam lấy từ Asia/Ho_Chi_Minh và clock tick mỗi giây
    assert "Asia/Ho_Chi_Minh" in src
    assert "setInterval(updateClock, 1000)" in src


def test_builder_landing_page_has_clock_element_and_css():
    """Dashboard root cũng có element clock (id=clock) + CSS .clock."""
    src = open(BUILDER, encoding="utf-8").read()
    assert '<div class="clock" id="clock">Loading time...</div>' in src
    assert ".clock {{" in src or ".clock {" in src


# ── 2. HTML đã build (nếu tồn tại) ───────────────────────────────────────────
def _report_files():
    d = os.path.join(ROOT, "output", "reports")
    if not os.path.isdir(d):
        return []
    out = []
    for sub in sorted(os.listdir(d)):
        p = os.path.join(d, sub, "index.html") if sub != "index.html" else os.path.join(d, "index.html")
        if os.path.isfile(p):
            out.append(p)
    return out


def test_built_html_no_ict_utc7_emoji():
    files = _report_files()
    assert len(files) >= 25, f"thiếu báo cáo HTML: {len(files)}/25"
    for p in files:
        html = open(p, encoding="utf-8").read()
        assert " ICT'" not in html and "' ICT" not in html, p
        assert "UTC+7" in html, p
        assert "CLOCK_EMOJIS" in html, p
        assert 'id="clock"' in html, p


# ── 3. README song ngữ ───────────────────────────────────────────────────────
def test_readme_bilingual_structure():
    p = os.path.join(ROOT, "README.md")
    txt = open(p, encoding="utf-8").read()
    # 2 anchor chuyển ngôn ngữ
    assert '<a id="english"></a>' in txt
    assert '<a id="tieng-viet"></a>' in txt
    # nav ngôn ngữ ở đầu file
    assert "[🇬🇧 English](#english)" in txt
    assert "[🇻🇳 Tiếng Việt](#tieng-viet)" in txt
    # marker AUTO đúng 1 cặp (script update_readme_results.py cần thế)
    assert txt.count("<!-- AUTO_RESULTS_START -->") == 1
    assert txt.count("<!-- AUTO_RESULTS_END -->") == 1


def test_readme_uses_utc_plus_7_not_ict():
    txt = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "ICT" not in txt
    assert "UTC+7" in txt
