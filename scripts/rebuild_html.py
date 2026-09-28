"""
rebuild_html.py — Rebuild toàn bộ báo cáo HTML + dashboard + Excel
===================================================================
Đọc output/exports/score_*.json (đã có field calibrated sau khi chạy
scripts/backfill_calibrated_scores.py) và dựng lại:
  1. 24 báo cáo quý output/reports/YYYY_QN/index.html
     (hero 2 tầng: raw composite + chip HÀNH ĐỘNG calibrated,
      chart lịch sử: calibrated line + raw dashed + VN-Index overlay,
      navbar quarter-select tích hợp sẵn trong builder).
  2. Dashboard root output/reports/index.html (timeline calibrated).
  3. Chạy 2 validator (inject_vnindex_chart.py, inject_navbar.py) —
     fail loudly (exit != 0) nếu thiếu feature thay vì im lặng bỏ qua.
  4. Excel Quant Factor Workbook (output/exports/VN_Index_Quant_Factor_Analysis.xlsx).

Chạy:  python scripts/rebuild_html.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.append(os.getcwd())
from src.reporting.report_builder import build_html_report, build_root_index_html

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    exports_dir = Path("output/exports")
    json_files = sorted(exports_dir.glob("score_*.json"))
    if not json_files:
        print("ERROR: no score_*.json exports found — nothing to rebuild.")
        return 1

    history_path = Path("data/scores/quarterly_scores_history.parquet")
    score_history = None
    if history_path.exists():
        score_history = pd.read_parquet(history_path)
        # Bảo vệ: không bao giờ đưa row test vào chart lịch sử
        score_history = score_history[score_history["quarter"] != "2099-Q1"]

    for json_file in json_files:
        quarter = json_file.stem.replace("score_", "").replace("_", "-")
        with open(json_file, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        score_record = export_data.get("quarterly_score", {})
        mlr_df = pd.DataFrame(export_data.get("mlr_regression", []))
        granger_df = pd.DataFrame(export_data.get("granger_causality", []))

        wfv_dict = export_data.get("ml_walk_forward_validation", {})
        fi_df = pd.DataFrame(export_data.get("feature_importance", []))

        report_dir = Path("output/reports") / quarter.replace("-", "_")
        report_dir.mkdir(parents=True, exist_ok=True)
        build_html_report(score_record, quarter, mlr_df, granger_df, wfv_dict, fi_df, score_history)
        print(f"Rebuilt {quarter}")

    build_root_index_html()

    # ── Post-build VALIDATION (không còn inject string-replacement mù) ──────
    # Builder đã tích hợp sẵn VN-Index overlay + navbar; các script dưới đây
    # chỉ verify — exit code != 0 nếu feature thiếu (chống gãy âm thầm).
    for validator in ("scripts/inject_vnindex_chart.py", "scripts/inject_navbar.py"):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / validator)],
                                cwd=str(PROJECT_ROOT))
        if result.returncode != 0:
            print(f"ERROR: validator {validator} failed (exit {result.returncode}).")
            return result.returncode

    # ── Excel Quant Factor Workbook ─────────────────────────────────────────
    result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts/generate_excel_report.py")],
                            cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"ERROR: Excel generation failed (exit {result.returncode}).")
        return result.returncode

    print("Rebuild complete: reports + dashboard + validators + Excel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
