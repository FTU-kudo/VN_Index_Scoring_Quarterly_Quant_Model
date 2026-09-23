import json
import os
from pathlib import Path
import pandas as pd
import sys
sys.path.append(os.getcwd())
from src.reporting.report_builder import build_html_report, build_root_index_html

exports_dir = Path("output/exports")
for json_file in exports_dir.glob("score_*.json"):
    quarter = json_file.stem.replace("score_", "").replace("_", "-")
    with open(json_file, "r", encoding="utf-8") as f:
        export_data = json.load(f)
    
    score_record = export_data.get("quarterly_score", {})
    mlr_df = pd.DataFrame(export_data.get("mlr_regression", []))
    granger_df = pd.DataFrame(export_data.get("granger_causality", []))
    
    wfv_dict = export_data.get("ml_walk_forward_validation", {})
    fi_df = pd.DataFrame(export_data.get("feature_importance", []))
    
    # Load score history
    history_path = Path("data/scores/quarterly_scores_history.parquet")
    score_history = None
    if history_path.exists():
        score_history = pd.read_parquet(history_path)

    report_dir = Path("output/reports") / quarter.replace("-", "_")
    report_dir.mkdir(parents=True, exist_ok=True)
    build_html_report(score_record, quarter, mlr_df, granger_df, wfv_dict, fi_df, score_history)
    print(f"Rebuilt {quarter}")

build_root_index_html()
