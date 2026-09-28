"""
test_action_chip_markup.py — Regression tests cho bug chip "⚡ HÀNH ĐỘNG".

Bối cảnh:
  Helper t() trong report_builder.py trả về HTML
  (`<span class="lang-en">...</span><span class="lang-vi">...</span>`).
  HTML đó từng bị nhét vào attribute `title="{t(...)}"` của chip action-chip trong
  hero → các dấu " bên trong đóng attribute sớm → browser parse vỡ, lộ text rác
  `"> ⚡ HÀNH ĐỘNG: ...` và tooltip hiện mã HTML thô. Ảnh hưởng đúng 24 báo cáo quý.

Fix: title chuyển sang text thuần song ngữ (EN · VI), không chứa HTML.

Các test:
  a. Builder không bao giờ inject t() vào bất kỳ attribute nào
     (title, alt, aria-label, placeholder).
  b. Title của action-chip trong builder là text thuần (không < hay >),
     chứa cả "Calibrated Action Signal" lẫn "Tín hiệu hành động".
  c. Cả 24 HTML đã build: không attribute title="..." nào chứa `<span`.
  d. Cả 24 HTML: chip khớp regex hero mong đợi.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PROJECT_ROOT / "src" / "reporting" / "report_builder.py"
REPORTS_DIR = PROJECT_ROOT / "output" / "reports"

QUARTER_RE = re.compile(r"^\d{4}_Q[1-4]$")


def _quarter_html_files():
    files = sorted(
        p / "index.html"
        for p in REPORTS_DIR.iterdir()
        if p.is_dir() and QUARTER_RE.match(p.name)
    )
    return [f for f in files if f.exists()]


# ---------------------------------------------------------------------------
# a. Builder không bao giờ inject t() vào attribute nào
# ---------------------------------------------------------------------------
def test_builder_never_injects_t_into_attributes():
    src = BUILDER.read_text(encoding="utf-8")
    for attr in ("title", "alt", "aria-label", "placeholder"):
        assert f'{attr}="{{t(' not in src, (
            f'Builder nhét t() (HTML) vào attribute {attr}="..." — '
            f"HTML trong attribute sẽ làm vỡ markup."
        )


# ---------------------------------------------------------------------------
# b. Title action-chip trong builder là text thuần song ngữ
# ---------------------------------------------------------------------------
def test_builder_action_chip_title_is_plain_bilingual_text():
    src = BUILDER.read_text(encoding="utf-8")
    # Tìm block <span class="action-chip" ... title="...">
    m = re.search(
        r'<span class="action-chip"[^>]*?title="([^"]*)"',
        src,
        re.DOTALL,
    )
    assert m is not None, "Không tìm thấy action-chip có attribute title trong builder."
    title = m.group(1)
    assert "<" not in title and ">" not in title, (
        f"Title action-chip chứa HTML (< hoặc >): {title!r}"
    )
    assert "Calibrated Action Signal" in title, "Title thiếu phần tiếng Anh."
    assert "Tín hiệu hành động" in title, "Title thiếu phần tiếng Việt."


# ---------------------------------------------------------------------------
# c. Cả 24 HTML: không title="..." nào chứa <span
# ---------------------------------------------------------------------------
def test_built_html_no_title_contains_span():
    files = _quarter_html_files()
    assert len(files) == 24, f"Kỳ vọng 24 báo cáo quý, thấy {len(files)}."
    offenders = []
    title_attr_re = re.compile(r'title="([^"]*)"')
    for f in files:
        html = f.read_text(encoding="utf-8")
        for val in title_attr_re.findall(html):
            if "<span" in val:
                offenders.append(f.parent.name)
                break
    assert not offenders, (
        f"Các báo cáo có title chứa <span (markup vỡ): {offenders}"
    )


# ---------------------------------------------------------------------------
# d. Cả 24 HTML: chip khớp regex hero mong đợi
# ---------------------------------------------------------------------------
def test_built_html_action_chip_matches_expected_markup():
    files = _quarter_html_files()
    assert len(files) == 24, f"Kỳ vọng 24 báo cáo quý, thấy {len(files)}."
    chip_re = re.compile(
        r"<span class=\"action-chip\"[^>]*>\s*"
        r"⚡ HÀNH ĐỘNG: (🔴 SELL|🟠 REDUCE|🟡 HOLD|🔵 ACCUMULATE|🟢 BUY) — [\d.]+\s*"
        r"</span>",
        re.DOTALL,
    )
    for f in files:
        html = f.read_text(encoding="utf-8")
        assert chip_re.search(html), (
            f"Chip action-chip trong {f.parent.name} không khớp markup mong đợi."
        )
