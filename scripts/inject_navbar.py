"""
inject_navbar.py — Validator/Injector: quarter navigation trong HTML reports
============================================================================
TRƯỚC ĐÂY: post-processing string-replacement (navbar ◀ select ▶) — dễ gãy
âm thầm khi template đổi.

HIỆN NAY: navbar quarter-select + phím tắt ←/→ đã được TÍCH HỢP thẳng vào
src/reporting/report_builder.py (build_html_report). Script này chỉ:
  1. VALIDATE mọi output/reports/YYYY_QN/index.html có navbar navigation.
  2. Với file cũ chưa có: thử inject legacy nhưng BÁO LỖI LOUD + exit code
     != 0 khi pattern không khớp.

Exit code: 0 = mọi report OK | 1 = có report thiếu feature và không inject được.
"""

import os
import re
import sys

reports_dir = os.path.join("output", "reports")

REQUIRED_MARKERS = [
    'id="quarter-select"',
    'id="prev-quarter-btn"',
    'id="next-quarter-btn"',
]

old_nav = """<div class="nav-right">
        <button class="btn" id="lang-btn">"""
new_nav = """<div class="nav-right">
        <button class="btn" id="prev-quarter-btn" title="Previous Quarter" style="padding: 6px 10px;">◀</button>
        <select class="btn" id="quarter-select" style="max-width: 150px; cursor: pointer;"></select>
        <button class="btn" id="next-quarter-btn" title="Next Quarter" style="padding: 6px 10px;">▶</button>
        <button class="btn" id="lang-btn">"""

js_template = """  <script>
    // Quarter Navigation Logic (legacy injection — builder-integrated since calibration PR)
    (async function() {{
      const currentQuarter = "{quarter}";
      const select = document.getElementById("quarter-select");
      const prevBtn = document.getElementById("prev-quarter-btn");
      const nextBtn = document.getElementById("next-quarter-btn");
      try {{
        const response = await fetch("../quarters.json");
        if (!response.ok) throw new Error("Failed to fetch quarters.json");
        const quarters = await response.json();
        if (!quarters || quarters.length === 0) return;
        quarters.forEach(q => {{
          const option = document.createElement("option");
          option.value = q;
          option.textContent = q.replace("_", "/");
          if (q.replace("_", "-") === currentQuarter) option.selected = true;
          select.appendChild(option);
        }});
        const currentIndex = quarters.findIndex(q => q.replace("_", "-") === currentQuarter);
        const navigateTo = (index) => {{
          if (index >= 0 && index < quarters.length) window.location.href = "../" + quarters[index] + "/index.html";
        }};
        select.addEventListener("change", (e) => window.location.href = "../" + e.target.value + "/index.html");
        prevBtn.addEventListener("click", () => navigateTo(currentIndex + 1));
        nextBtn.addEventListener("click", () => navigateTo(currentIndex - 1));
      }} catch (err) {{
        console.error("Quarter navigation error:", err);
      }}
    }})();
  </script>
</body>"""


def main() -> int:
    if not os.path.isdir(reports_dir):
        print(f"ERROR: {reports_dir} not found.")
        return 1

    ok, injected, failed = 0, 0, 0
    for dirname in sorted(os.listdir(reports_dir)):
        dir_path = os.path.join(reports_dir, dirname)
        if not (os.path.isdir(dir_path) and re.match(r"20\d\d_Q\d", dirname)):
            continue
        html_file = os.path.join(dir_path, "index.html")
        if not os.path.exists(html_file):
            print(f"WARN: {dirname}/index.html missing — skipped")
            continue

        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()

        missing = [m for m in REQUIRED_MARKERS if m not in content]
        if not missing:
            ok += 1
            continue

        print(f"WARN: {dirname} missing navbar markers: {missing} — attempting legacy injection")
        if old_nav not in content:
            print(f"ERROR: {dirname}: legacy navbar pattern not found — rebuild via "
                  f"scripts/rebuild_html.py. FAILING LOUDLY (exit 1).")
            failed += 1
            continue

        quarter = dirname.replace("_", "-")
        content = content.replace(old_nav, new_nav, 1)
        content = content.replace("</body>", js_template.format(quarter=quarter), 1)
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(content)
        injected += 1

    print(f"Navbar validation: {ok} already OK, {injected} injected, {failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
