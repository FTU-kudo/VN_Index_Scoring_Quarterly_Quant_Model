"""
update_readme_results.py — Auto-generate "KẾT QUẢ THỰC NGHIỆM MẪU" section in README.md
================================================================================
Reads the latest score JSON from output/exports/ and replaces the section
between <!-- AUTO_RESULTS_START --> and <!-- AUTO_RESULTS_END --> markers
in README.md with actual data.

Usage:
  python scripts/update_readme_results.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_latest_score_json() -> Path:
    """Find most recent score_*.json or live_score_*.json in exports dir."""
    exports_dir = PROJECT_ROOT / "output" / "exports"
    candidates = sorted(exports_dir.glob("score_*.json"), reverse=True)
    if not candidates:
        candidates = sorted(exports_dir.glob("live_score_*.json"), reverse=True)
    if not candidates:
        print("[ERROR] No score JSON found in output/exports/")
        sys.exit(1)
    return candidates[0]


def extract_results(data: dict) -> str:
    """Build markdown results block from score JSON data."""
    # Support both pipeline format and live_scoring format
    qs = data.get("quarterly_score", data)
    meta = data.get("metadata", {})
    market = data.get("latest_market_data", {})
    mlr = data.get("mlr_results", data.get("mlr_regression", {}))
    wfv = data.get("wfv_results", data.get("ml_walk_forward_validation", {}))

    # Extract values with fallbacks
    quarter = meta.get("quarter", qs.get("quarter", "N/A"))
    gen_at = meta.get("generated_at", qs.get("computed_at", qs.get("date_computed", "N/A")))

    vni_close = market.get("vni_close", "N/A")
    us10y = market.get("us10y", "N/A")
    dxy = market.get("dxy", "N/A")

    # Score
    total = qs.get("total_score", "N/A")
    label = qs.get("label", "N/A")
    emoji = qs.get("emoji", "")
    desc = qs.get("description", qs.get("label_description", ""))

    # MLR
    r2 = mlr.get("r2", "N/A") if mlr else "N/A"
    adj_r2 = mlr.get("adj_r2", "N/A") if mlr else "N/A"
    n_obs = mlr.get("n_obs", "N/A") if mlr else "N/A"

    # WFV
    wfv_acc = wfv.get("mean_accuracy", "N/A") if wfv else "N/A"
    wfv_folds = wfv.get("n_folds", "N/A") if wfv else "N/A"
    wfv_pred = wfv.get("latest_prediction", "N/A") if wfv else "N/A"

    # RSI from latest_vni or group_details
    rsi = "N/A"
    latest_vni = qs.get("latest_vni", {})
    if latest_vni:
        rsi = latest_vni.get("rsi_14", "N/A")

    # Group scores
    groups = qs.get("groups", qs.get("group_scores", {}))
    group_lines = []
    for gname, gdata in groups.items():
        if isinstance(gdata, dict):
            raw = gdata.get("raw", gdata.get("raw_score", "N/A"))
            weight = gdata.get("weight", gdata.get("weighted_score", "N/A"))
            if raw is not None:
                group_lines.append(f"  • {gname:30s}: raw={raw:>6.1f}  weight={weight}")

    # Format numbers safely
    def fmt(v, decimals=2):
        if isinstance(v, (int, float)):
            return f"{v:.{decimals}f}"
        return str(v)

    block = f"""## 📊 KẾT QUẢ THỰC NGHIỆM MẪU (AUTO-GENERATED)

> **⚠️ Section này được tạo TỰ ĐỘNG bởi `scripts/update_readme_results.py` từ dữ liệu output thực tế.**
> **Không chỉnh sửa thủ công — sẽ bị ghi đè khi chạy pipeline.**

```text
======================================================================
     VN-INDEX QUANTITATIVE SCORING — {quarter}
     Generated: {gen_at}
======================================================================
[MARKET DATA]
  • VN-Index Close         : {fmt(vni_close)}
  • US 10Y Yield           : {fmt(us10y)}%
  • DXY Index              : {fmt(dxy)}
  • RSI (14D)              : {fmt(rsi)}

[ECONOMETRICS: MLR MODEL]
  • N observations         : {n_obs}
  • R-squared              : {fmt(r2, 4)} (R-adj = {fmt(adj_r2, 4)})

[MACHINE LEARNING: WALK-FORWARD VALIDATION]
  • XGBoost Accuracy       : {fmt(wfv_acc, 4)}
  • N Folds (WFV)          : {wfv_folds}
  • Latest Prediction      : {wfv_pred}

[COMPOSITE SCORE & ALLOCATION]
  • Total Score            : {fmt(total)} / 100
  • Classification         : {emoji} {label} — {desc}

[GROUP BREAKDOWN]
{chr(10).join(group_lines) if group_lines else "  (No group data available)"}
======================================================================
```"""
    return block


def update_readme(results_block: str):
    """Replace content between AUTO_RESULTS markers in README.md."""
    readme_path = PROJECT_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    start_marker = "<!-- AUTO_RESULTS_START -->"
    end_marker = "<!-- AUTO_RESULTS_END -->"

    if start_marker in content and end_marker in content:
        before = content[:content.index(start_marker)]
        after = content[content.index(end_marker) + len(end_marker):]
        new_content = before + start_marker + "\n" + results_block + "\n" + end_marker + after
    else:
        # Find the old section and replace it
        old_header = "## 📊 KẾT QUẢ THỰC NGHIỆM MẪU"
        if old_header in content:
            idx = content.index(old_header)
            # Find the next ## section or ---
            rest = content[idx:]
            next_section = -1
            for marker in ["\n## ", "\n---"]:
                pos = rest.find(marker, len(old_header))
                if pos != -1 and (next_section == -1 or pos < next_section):
                    next_section = pos

            if next_section != -1:
                before = content[:idx]
                after = content[idx + next_section:]
                new_content = before + start_marker + "\n" + results_block + "\n" + end_marker + "\n" + after
            else:
                new_content = content  # Can't find boundary
        else:
            # Append before DISCLAIMER section
            disc = "## ⚠️ TUYÊN BỐ MIỄN TRỪ"
            if disc in content:
                idx = content.index(disc)
                new_content = content[:idx] + start_marker + "\n" + results_block + "\n" + end_marker + "\n\n---\n\n" + content[idx:]
            else:
                new_content = content + "\n\n" + start_marker + "\n" + results_block + "\n" + end_marker

    readme_path.write_text(new_content, encoding="utf-8")
    print(f"[OK] README.md updated with latest results")


def main():
    json_path = find_latest_score_json()
    print(f"[INFO] Using: {json_path.name}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    results = extract_results(data)
    update_readme(results)


if __name__ == "__main__":
    main()
