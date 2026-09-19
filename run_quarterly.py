"""
run_quarterly.py — Entry Point: Chạy Full Pipeline Theo Quý
============================================================
Sử dụng:
  python run_quarterly.py --quarter 2026-Q3

Pipeline:
  1. Fetch / load dữ liệu (OHLCV, macro, global, margin)
  2. Feature engineering (6 nhóm)
  3. Fit MLR model → bảng beta + diagnostics
  4. Fit VAR model → Granger causality + FEVD
  5. Walk-Forward Validation ML (XGBoost)
  6. Tính quarterly score (6 nhóm × trọng số)
  7. Xuất báo cáo HTML + JSON
"""

import argparse
import logging
import sys
from pathlib import Path

# Thêm project root vào PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import LOG_FILE, LOG_LEVEL

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger("run_quarterly")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VN-Index Quarterly Quantitative Scoring Pipeline"
    )
    parser.add_argument(
        "--quarter", type=str, default="2026-Q3",
        help="Quý cần phân tích (định dạng: YYYY-QN, ví dụ: 2026-Q3)"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Bỏ qua cache, tải lại tất cả dữ liệu"
    )
    parser.add_argument(
        "--skip-ml", action="store_true",
        help="Bỏ qua bước ML (nhanh hơn, dùng khi test)"
    )
    parser.add_argument(
        "--skip-var", action="store_true",
        help="Bỏ qua bước VAR (nhanh hơn)"
    )
    parser.add_argument(
        "--ftse-status", type=str, default="confirmed",
        choices=["pending", "confirmed", "completed"],
        help="Trạng thái nâng hạng FTSE"
    )
    return parser.parse_args()


def run_pipeline(args: argparse.Namespace) -> None:
    quarter   = args.quarter
    use_cache = not args.no_cache

    logger.info(f"{'='*60}")
    logger.info(f"VN-INDEX QUARTERLY SCORING PIPELINE — {quarter}")
    logger.info(f"{'='*60}")

    # ── Step 1: Fetch dữ liệu ─────────────────────────────────────────────────
    logger.info("[1/7] Fetching dữ liệu...")
    from src.data.fetcher import (
        fetch_vnindex_ohlcv, compute_vni_returns,
        fetch_foreign_flows, fetch_macro_sbv_manual,
        fetch_usdvnd_proxy, fetch_global_indicators,
        fetch_margin_debt_manual, fetch_m2_credit_manual
    )

    df_vni     = fetch_vnindex_ohlcv(use_cache=use_cache)
    df_vni     = compute_vni_returns(df_vni)
    df_ff      = fetch_foreign_flows(use_cache=use_cache)
    df_macro   = fetch_macro_sbv_manual()
    df_fx      = fetch_usdvnd_proxy(use_cache=use_cache)
    df_global  = fetch_global_indicators(use_cache=use_cache)
    df_margin  = fetch_margin_debt_manual()
    df_m2      = fetch_m2_credit_manual()

    # ── Step 2: Feature Engineering ───────────────────────────────────────────
    logger.info("[2/7] Feature engineering...")
    from src.features.macro_features import build_macro_features
    from src.features.global_features import build_global_features
    from src.features.valuation_features import build_valuation_leverage_features

    df_macro_feat = build_macro_features(df_vni, df_macro, df_fx, df_m2)
    df_global_feat = build_global_features(df_vni, df_global, df_ff)
    df_val_feat = build_valuation_leverage_features(df_vni, df_margin)

    # Merge tất cả features
    import pandas as pd
    df_all = df_vni.copy()
    for df_feat in [df_macro_feat, df_global_feat, df_val_feat]:
        feat_cols = [c for c in df_feat.columns if c != "date"]
        df_all = df_all.merge(
            df_feat[["date"] + feat_cols], on="date", how="left"
        )
    logger.info(f"[FE] Master dataset: {len(df_all)} rows × {len(df_all.columns)} cols")

    # ── Step 3: MLR Model ─────────────────────────────────────────────────────
    logger.info("[3/7] Fitting MLR model...")
    mlr_summary  = None
    mlr_pred     = None
    mlr_adj_r2   = None

    try:
        from src.models.regression.mlr_model import MLRModel
        mlr = MLRModel()
        mlr.fit(df_all)

        mlr_summary = mlr.summary_table()
        diag = mlr.diagnostics()
        mlr_adj_r2 = mlr.adj_r2_

        # Dự báo trên 30 ngày cuối
        mlr_preds = mlr.predict(df_all.tail(30))
        mlr_pred  = float(mlr_preds.mean()) if len(mlr_preds) > 0 else None

        logger.info(f"[MLR] Adj-R² = {mlr_adj_r2:.4f}")
        logger.info(f"[MLR] Durbin-Watson = {diag.get('durbin_watson', 'N/A')}")
        logger.info(f"[MLR] ADF residuals p-value = {diag.get('adf_residuals_pvalue', 'N/A')}")

    except Exception as e:
        logger.warning(f"[MLR] Bỏ qua do lỗi: {e}")

    # ── Step 4: VAR Model ─────────────────────────────────────────────────────
    var_forecast   = None
    granger_df     = None
    granger_leaders = None

    if not args.skip_var:
        logger.info("[4/7] Fitting VAR model...")
        try:
            from src.models.var.var_model import VARModel
            from src.utils.config import VAR_VARIABLES

            # Rename để khớp VAR_VARIABLES
            df_var_input = df_all.copy()
            rename_map = {"log_return": "vni_return"}
            df_var_input = df_var_input.rename(columns=rename_map)

            available_var_cols = [c for c in VAR_VARIABLES
                                  if c in df_var_input.columns]
            if len(available_var_cols) >= 3:
                var_model = VARModel(variable_cols=available_var_cols)
                var_model.fit(df_var_input)

                # Granger causality
                granger_df = var_model.granger_causality(caused="vni_return")
                granger_leaders = int(
                    (granger_df["granger_causes_vni"] == True).sum()
                )

                # Forecast T+5
                last_rows = df_var_input[available_var_cols].dropna().tail(
                    var_model.optimal_lag_
                ).values
                if len(last_rows) == var_model.optimal_lag_:
                    forecast_df = var_model.forecast(last_rows, steps=5)
                    if "vni_return" in forecast_df.columns:
                        var_forecast = float(forecast_df["vni_return"].mean())

                logger.info(f"[VAR] {granger_leaders} Granger leaders, "
                            f"VAR forecast T+5 = {var_forecast}")
            else:
                logger.warning(f"[VAR] Chỉ có {len(available_var_cols)} biến khả dụng — cần ≥3")

        except Exception as e:
            logger.warning(f"[VAR] Bỏ qua do lỗi: {e}")
    else:
        logger.info("[4/7] Skip VAR (--skip-var flag)")

    # ── Step 5: ML Walk-Forward Validation ───────────────────────────────────
    wfv_summary = None
    fi_df       = None
    ml_pred_class = None
    ml_confidence = None

    if not args.skip_ml:
        logger.info("[5/7] Running ML Walk-Forward Validation...")
        try:
            from src.models.ml.ml_model import (
                build_ml_features, create_target_variable,
                evaluate_wfv, get_feature_importance
            )

            df_ml = build_ml_features(df_all)
            df_ml = create_target_variable(df_ml)

            # Lấy danh sách feature columns cho ML
            exclude = {"date", "open", "high", "low", "close", "volume",
                       "target", "target_binary", "forward_return",
                       "log_return", "weekly_return", "monthly_return"}
            feature_cols = [c for c in df_ml.columns
                            if c not in exclude
                            and df_ml[c].dtype in ["float64", "float32", "int64"]]

            if len(feature_cols) > 5:
                wfv_summary = evaluate_wfv(
                    df_ml, feature_cols, model_type="xgboost"
                )
                fi_df = get_feature_importance(
                    df_ml, feature_cols, model_type="xgboost"
                )
            else:
                logger.warning(f"[ML] Chỉ có {len(feature_cols)} features — bỏ qua WFV")

        except Exception as e:
            logger.warning(f"[ML] Bỏ qua do lỗi: {e}")
    else:
        logger.info("[5/7] Skip ML (--skip-ml flag)")

    # ── Step 6: Quarterly Scoring ─────────────────────────────────────────────
    logger.info("[6/7] Computing quarterly score...")
    from src.scoring.quarterly_scorer import compute_quarterly_score

    # Lấy giá trị indicators mới nhất
    latest = df_all.iloc[-1].copy() if len(df_all) > 0 else pd.Series()

    score_record = compute_quarterly_score(
        quarter=quarter,
        df_latest=latest,
        mlr_pred=mlr_pred,
        var_forecast=var_forecast,
        mlr_adj_r2=mlr_adj_r2,
        granger_leaders=granger_leaders,
        ml_accuracy=wfv_summary.get("mean_accuracy") if wfv_summary else None,
        ml_f1=wfv_summary.get("mean_f1") if wfv_summary else None,
        ml_pred_class=ml_pred_class,
        ml_confidence=ml_confidence,
        ftse_upgrade_status=args.ftse_status,
    )

    # ── Step 7: Build Reports ─────────────────────────────────────────────────
    logger.info("[7/7] Building reports...")
    from src.reporting.report_builder import build_html_report, export_score_json

    # Load score history
    from src.utils.config import SCORES_DIR
    history_path = SCORES_DIR / "quarterly_scores_history.parquet"
    score_history = None
    if history_path.exists():
        try:
            score_history = pd.read_parquet(history_path)
        except Exception:
            pass

    html_path = build_html_report(
        score_record=score_record,
        quarter=quarter,
        mlr_summary=mlr_summary,
        granger_df=granger_df,
        wfv_summary=wfv_summary,
        fi_df=fi_df,
        score_history=score_history,
    )
    json_path = export_score_json(
        score_record=score_record,
        quarter=quarter,
        mlr_summary=mlr_summary,
        granger_df=granger_df,
        wfv_summary=wfv_summary,
        fi_df=fi_df,
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"HOÀN THÀNH — {quarter}")
    logger.info(f"Tổng điểm   : {score_record['total_score']:.1f}/100")
    logger.info(f"Phân loại   : {score_record['emoji']} {score_record['label']}")
    logger.info(f"Khuyến nghị : {score_record['label_description']}")
    logger.info(f"Leading     : {score_record['leading_indicator']}")
    logger.info(f"HTML report : {html_path}")
    logger.info(f"JSON export : {json_path}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)
