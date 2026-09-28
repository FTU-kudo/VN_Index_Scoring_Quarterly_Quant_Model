"""
inject_vnindex_chart.py — Validator/Injector: VN-Index overlay trong HTML reports
================================================================================
TRƯỚC ĐÂY: post-processing string-replacement sau khi build HTML — dễ gãy âm
thầm khi template đổi (pattern không khớp thì chart biến mất không báo lỗi).

HIỆN NAY: logic overlay VN-Index + toggle đã được TÍCH HỢP thẳng vào
src/reporting/report_builder.py (build_html_report). Script này chỉ:
  1. VALIDATE mọi output/reports/*/index.html có đủ feature (toggle + dataset).
  2. Với file cũ chưa có: thử inject theo cách legacy (string-replacement)
     nhưng BÁO LỖI LOUD + exit code != 0 khi pattern không khớp — không còn
     im lặng bỏ qua.

Exit code: 0 = mọi report OK | 1 = có report thiếu feature và không inject được.
"""

import glob
import os
import re
import sys

import pandas as pd

PRICE_CACHE_PATH = os.path.join("data", "scores", "vnindex_quarterly_close.json")

# Feature markers phải tồn tại trong HTML sau khi build đúng
REQUIRED_MARKERS = [
    'id="toggleVNIndex"',       # toggle checkbox
    "label: 'VN-Index'",        # dataset trong chartDataLine
    "'y1'",                     # trục y1 (giá VN-Index)
]


def get_vnindex_quarterly_prices():
    """Giá VN-Index theo quý — ủy quyền cho report_builder (single source)."""
    from src.reporting.report_builder import _load_vnindex_quarterly_prices
    scores = pd.read_parquet("data/scores/quarterly_scores_history.parquet")
    scores = scores[scores["quarter"] != "2099-Q1"]
    return _load_vnindex_quarterly_prices(scores["quarter"].tolist())


def try_legacy_injection(html: str, prices_json: str) -> "tuple[str, bool]":
    """Fallback inject cho HTML cũ (build trước khi tích hợp vào report_builder).
    Trả về (html mới, thành công?). KHÔNG im lặng khi pattern không khớp."""
    old_header = '<h2>📈 <span class="lang-en">Historical Score Trend</span><span class="lang-vi">Lịch sử Điểm số Theo Quý</span></h2>'
    new_header = '''<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <h2 style="margin-bottom: 0;">📈 <span class="lang-en">Historical Score Trend</span><span class="lang-vi">Lịch sử Điểm số Theo Quý</span></h2>
            <div style="display:flex; gap:16px; justify-content: flex-end;">
              <label style="cursor:pointer; display:flex; align-items:center; gap:6px; font-size:14px; font-weight:500; color:var(--text-muted);">
                <input type="checkbox" id="toggleCompositeScore" checked style="width:16px; height:16px; accent-color: var(--color-amber);">
                <span class="lang-en">Composite Score</span><span class="lang-vi">Composite Score</span>
              </label>
              <label style="cursor:pointer; display:flex; align-items:center; gap:6px; font-size:14px; font-weight:500; color:var(--text-muted);">
                <input type="checkbox" id="toggleVNIndex" style="width:16px; height:16px; accent-color: var(--color-blue);">
                <span class="lang-en">VN-Index</span><span class="lang-vi">VN-Index</span>
              </label>
            </div>
          </div>'''

    if old_header not in html:
        return html, False   # pattern không khớp → caller báo lỗi loud

    html = html.replace(old_header, new_header)

    js_injection = f'''
  <script>
    // Legacy injection: VN-Index dataset (builder-integrated depuis PR calibration)
    if (typeof window !== 'undefined' && window.chartDataLine && window.chartDataLine.datasets) {{
        if (!window.chartDataLine.datasets.some(d => d.label === 'VN-Index')) {{
            window.chartDataLine.datasets.push({{
                label: 'VN-Index',
                data: {prices_json},
                borderColor: '#10b981',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                yAxisID: 'y1',
                hidden: true
            }});
        }}
    }}
    const toggleVN = document.getElementById('toggleVNIndex');
    if (toggleVN) {{
        toggleVN.addEventListener('change', function(e) {{
            if (typeof lineChartInstance !== 'undefined' && lineChartInstance) {{
                const vniDs = lineChartInstance.data.datasets.find(d => d.label === 'VN-Index');
                if (vniDs) {{
                    vniDs.hidden = !e.target.checked;
                    if (lineChartInstance.options.scales.y1) lineChartInstance.options.scales.y1.display = e.target.checked;
                    lineChartInstance.update();
                }}
            }}
        }});
    }}
    const toggleCS = document.getElementById('toggleCompositeScore');
    if (toggleCS) {{
        toggleCS.addEventListener('change', function(e) {{
            if (typeof lineChartInstance !== 'undefined' && lineChartInstance) {{
                if (lineChartInstance.data.datasets.length > 0) {{
                    lineChartInstance.data.datasets[0].hidden = !e.target.checked;
                    lineChartInstance.options.scales.y.display = e.target.checked;
                    lineChartInstance.update();
                }}
            }}
        }});
    }}
  </script>
</body>'''
    html = html.replace("</body>", js_injection, 1)
    return html, True


def main() -> int:
    reports_dir = os.path.join("output", "reports")
    html_files = sorted(glob.glob(os.path.join(reports_dir, "**", "index.html"), recursive=True))
    html_files = [f for f in html_files if os.path.dirname(f) != reports_dir]  # bỏ dashboard root

    if not html_files:
        print("ERROR: no quarterly report HTML found under output/reports/*/ — nothing to validate.")
        return 1

    ok, injected, failed = 0, 0, 0
    for path in html_files:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        missing = [m for m in REQUIRED_MARKERS if m not in html]
        if not missing:
            ok += 1
            continue

        # HTML cũ → thử legacy injection
        print(f"WARN: {path} missing VN-Index overlay markers: {missing} — attempting legacy injection")
        try:
            prices = get_vnindex_quarterly_prices()
            prices_json = "[" + ", ".join(map(str, prices or [])) + "]"
            html, success = try_legacy_injection(html, prices_json)
        except Exception as exc:
            print(f"ERROR: {path}: cannot load VN-Index prices: {exc}")
            success = False

        if not success:
            print(f"ERROR: {path}: legacy pattern not found — rebuild via scripts/rebuild_html.py "
                  f"instead of relying on injection. FAILING LOUDLY (exit 1).")
            failed += 1
            continue

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        injected += 1

    print(f"VN-Index overlay validation: {ok} already OK, {injected} injected, {failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
