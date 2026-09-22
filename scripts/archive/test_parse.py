import re

test_cases = [
    "<MISSING> N/A N/A → default 50",
    "Z = 0.91 (FAIR VALUE) → score 27",
    "P/E Headline: 12.86 | Median: 10.16 | Ex-VG: 10.25 | Z = 0.91 (FAIR VALUE) → score 27",
    "Forecast log-return = 0.0003 → score 51",
    "US10Y: 5.00% → score 0",
    "DXY: Z=0.14 → score 47",
    "<MISSING> N/A → default 50"
]

def parse_val(v):
    val_text = str(v)
    is_missing = False
    
    if val_text.startswith("<MISSING>"):
        is_missing = True
        val_text = val_text.replace("<MISSING>", "").strip()
        # Remove any leading N/A
        val_text = re.sub(r"^(?:N/A\s*)+", "", val_text).strip()
        val_text = re.sub(r"^(?:→|->)\s*", "", val_text).strip()
        if val_text.startswith("default"):
            val_text = val_text.replace("default", "Mặc định trung lập / Default neutral").strip()

    # Extract score
    score_match = re.search(r"(?:→|->)\s*(?:score|default)\s*([\d\.]+)", val_text)
    score_val = None
    if score_match:
        score_val = float(score_match.group(1))
        val_text = val_text[:score_match.start()].strip()
        if val_text.endswith("|"): val_text = val_text[:-1].strip()

    # Handle the remaining val_text if it's just "Mặc định trung lập / Default neutral 50"
    if is_missing and not val_text:
        val_text = "Mặc định trung lập / Default neutral"
    elif is_missing and "50" in val_text:
        val_text = val_text.replace(" 50", "").strip()

    # Format parts
    if "|" in val_text:
        parts = [p.strip() for p in val_text.split("|") if p.strip()]
        val_text_html = "<ul style='margin:0; padding-left:20px; color:var(--text-muted); font-size: 14px;'>"
        for p in parts:
            if ":" in p:
                lbl, val = p.split(":", 1)
                val_text_html += f"<li style='margin-bottom:4px;'><span style='color:var(--text-main); font-weight:600;'>{lbl}:</span> {val}</li>"
            else:
                val_text_html += f"<li style='margin-bottom:4px;'>{p}</li>"
        val_text_html += "</ul>"
    else:
        val_text_html = val_text

    return is_missing, val_text_html, score_val

import sys
sys.stdout.reconfigure(encoding='utf-8')
for c in test_cases:
    print(c)
    print("  -> ", parse_val(c))
