import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data.fetcher import load_data
from src.features.global_features import build_global_features
from src.features.macro_features import build_macro_features
from src.features.technical_features import build_technical_features
from src.features.valuation_features import build_valuation_leverage_features
from src.models.ml.ml_model import build_ml_features, create_target_variable, evaluate_wfv

def test_leakage():
    print("Loading data...")
    df_vni, df_macro, df_fdi, df_world, df_margin = load_data()
    print("Building features...")
    df_tech = build_technical_features(df_vni)
    df_macro_feat = build_macro_features(df_vni, df_macro, df_fdi)
    df_val = build_valuation_leverage_features(df_vni, df_margin, df_macro_feat)
    df_glob = build_global_features(df_vni, df_world)

    df_all = df_vni.copy()
    for df_feat in [df_tech, df_macro_feat, df_val, df_glob]:
        if not df_feat.empty:
            df_all = df_all.merge(df_feat, on="date", how="left")

    print(f"Total rows after merge: {len(df_all)}")
    if df_all.duplicated("date").any():
        print("FAIL: Duplicate dates found!")
        sys.exit(1)
    else:
        print("SUCCESS: No duplicate dates. Data leakage fixed.")
    
    # ML Benchmarks
    df_ml = build_ml_features(df_all)
    df_ml = create_target_variable(df_ml)
    exclude = {"date", "open", "high", "low", "close", "volume",
               "index", "target", "target_binary", "forward_return",
               "log_return", "weekly_return", "monthly_return"}
    feature_cols = [c for c in df_ml.columns if c not in exclude and df_ml[c].dtype in ["float64", "float32", "int64", "int32"]]
    feature_cols = [c for c in feature_cols if float(pd.to_numeric(df_ml[c], errors="coerce").std(skipna=True) or 0) > 1e-10]

    # Evaluate for standard benchmarks
    print("\nRunning Walk-Forward Validation benchmarks...")
    wfv_summary = evaluate_wfv(df_ml, feature_cols, model_type="xgboost")
    print(f"Mean Accuracy: {wfv_summary['mean_accuracy']:.2f}")
    print(f"Mean F1: {wfv_summary['mean_f1']:.2f}")

if __name__ == "__main__":
    test_leakage()
