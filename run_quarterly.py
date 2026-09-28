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
from datetime import datetime

# Thêm project root vào PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import LOG_FILE, LOG_LEVEL, VAR_VARIABLES, SCORES_DIR
from src.utils.dates import resolve_quarter_dates
from src.data.fetcher import (
    fetch_vnindex_ohlcv, compute_vni_returns,
    fetch_foreign_flows, fetch_macro_sbv_manual,
    fetch_usdvnd_proxy, fetch_global_indicators,
    fetch_margin_debt_manual, fetch_m2_credit_manual,
    fetch_vietnam_bonds, fetch_brent_oil
)
from src.features.macro_features import build_macro_features
from src.features.global_features import build_global_features
from src.features.valuation_features import build_valuation_leverage_features
from src.features.technical_features import add_technical_indicators
from src.features.market_structure_features import compute_adtv_change_pct
from src.models.regression.mlr_model import MLRModel
from src.models.var.var_model import VARModel
from src.models.ml.ml_model import (
    build_ml_features, create_target_variable,
    evaluate_wfv, get_feature_importance
)
from src.scoring.quarterly_scorer import compute_quarterly_score
from src.reporting.report_builder import build_html_report, export_score_json
import pandas as pd
import subprocess

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


def get_current_quarter() -> str:
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{q}"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VN-Index Quarterly Quantitative Scoring Pipeline"
    )
    parser.add_argument(
        "--quarter", type=str, default=get_current_quarter(),
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
        "--ftse-status", type=str, default="auto",
        choices=["auto", "pending", "confirmed", "completed", "unknown"],
        help="Tình trạng nâng hạng FTSE hiện tại (auto = tự động dựa trên mốc lịch sử)"
    )
    parser.add_argument(
        "--as-of", type=str, default=None, metavar="YYYY-MM-DD",
        help=(
            "Ngày 'hiện tại' giả định cho lần chạy giám sát GIỮA quý. "
            "Mặc định (khuyến nghị): point-in-time tại ĐẦU quý — chỉ dùng "
            "dữ liệu đến hết quý trước, đúng thông tin quỹ có khi ra quyết định. "
            "KHÔNG dùng flag này khi backfill/backtest lịch sử."
        )
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


    df_vni     = fetch_vnindex_ohlcv(use_cache=use_cache)
    df_vni     = compute_vni_returns(df_vni)
    df_ff      = fetch_foreign_flows(use_cache=use_cache)
    df_macro   = fetch_macro_sbv_manual()
    df_fx      = fetch_usdvnd_proxy(use_cache=use_cache)
    df_global  = fetch_global_indicators(use_cache=use_cache)
    df_margin  = fetch_margin_debt_manual()
    df_m2      = fetch_m2_credit_manual()
    df_bonds   = fetch_vietnam_bonds()
    df_oil     = fetch_brent_oil(use_cache=use_cache)

    # ── Step 2: Feature Engineering ───────────────────────────────────────────
    logger.info("[2/7] Feature engineering...")


    df_macro_feat = build_macro_features(df_vni, df_macro, df_fx, df_m2, df_bonds=df_bonds)
    df_global_feat = build_global_features(df_vni, df_global, df_ff, df_oil)
    df_val_feat = build_valuation_leverage_features(df_vni, df_margin)

    # Merge tất cả features

    df_all = df_vni.copy()
    for df_feat in [df_macro_feat, df_global_feat, df_val_feat]:
        feat_cols = [c for c in df_feat.columns if c != "date"]
        df_all = df_all.merge(
            df_feat[["date"] + feat_cols], on="date", how="left"
        )

    # Lọc bỏ các dòng quá cũ
    if "date" in df_all.columns:
        df_all = df_all[df_all["date"] >= "2012-01-01"].reset_index(drop=True)

    # ── Point-in-time cut-off (nguyên tắc buy-side) ──────────────────────────
    # Quyết định phân bổ được ra vào NGÀY ĐẦU QUÝ → mọi dữ liệu chấm điểm
    # chỉ được dùng thông tin đến hết quý TRƯỚC. Áp dụng cho CẢ live lẫn
    # backfill (nếu backfill dùng dữ liệu trong quý → look-ahead bias,
    # backtest lịch sử vô giá trị đối với quỹ).
    #
    # df_train       : dữ liệu đến cuối quý trước — train MLR/VAR/ML
    # df_latest_full : dữ liệu đến latest_cutoff — lấy chỉ báo "latest"
    #   Mặc định latest_cutoff = cuối quý trước (point-in-time đầu quý).
    #   Chỉ khác khi chạy giám sát giữa quý với --as-of (không dùng backtest).
    # Lưu ý: các feature *_q_ytd tại cut-off này = giá trị cộng dồn TRỌN
    #   quý vừa kết thúc (thông tin hợp lệ, đã biết tại đầu quý mới).
    try:
        qd = resolve_quarter_dates(quarter, as_of=args.as_of)
        train_end_date = qd["train_end_date"]
        latest_cutoff  = qd["latest_cutoff"]
        logger.info(
            f"[DATA] Training cut-off : đến {train_end_date.date()} (không leakage)\n"
            f"[DATA] Latest indicators: đến {latest_cutoff.date()} "
            f"({'point-in-time ĐẦU QUÝ — không look-ahead' if qd['point_in_time'] else 'as-of GIỮA quý (--as-of) — KHÔNG dùng cho backtest'})"
        )
    except ValueError as e:
        logger.warning(f"[DATA] Không thể parse quarter {quarter}: {e}")
        qd = None
        train_end_date = None
        latest_cutoff = None

    # df_train: không chứa dữ liệu của quý đang dự báo → no leakage
    if train_end_date is not None:
        df_train = df_all[df_all["date"] <= train_end_date].reset_index(drop=True)
    else:
        df_train = df_all.copy()

    # df_latest_full: cắt tại latest_cutoff (mặc định = point-in-time đầu quý)
    if latest_cutoff is not None:
        df_latest_full = df_all[df_all["date"] <= latest_cutoff].reset_index(drop=True)
    else:
        df_latest_full = df_all.copy()

    df_train = df_train.dropna(subset=["log_return"]).reset_index(drop=True)
    df_latest_full = df_latest_full.dropna(subset=["log_return"]).reset_index(drop=True)

    # Apply technical indicators và feature engineering lên cả 2 dataframe
    df_train = add_technical_indicators(df_train)
    df_latest_full = add_technical_indicators(df_latest_full)

    for df_ in [df_train, df_latest_full]:
        if "net_foreign_flow_b_vnd" in df_.columns and "net_foreign_flow" not in df_.columns:
            df_["net_foreign_flow"] = df_["net_foreign_flow_b_vnd"]
        if "delta_margin_debt_pct" in df_.columns and "delta_margin_debt" not in df_.columns:
            df_["delta_margin_debt"] = df_["delta_margin_debt_pct"]

    # Điền khuyết an toàn (ffill causal)
    for df_ in [df_train, df_latest_full]:
        numeric_cols = [
            c for c in df_.columns
            if c not in ("date", "open", "high", "low", "close", "volume")
            and pd.api.types.is_numeric_dtype(df_[c])
        ]
        if numeric_cols:
            df_[numeric_cols] = df_[numeric_cols].ffill()
            df_[numeric_cols] = df_[numeric_cols].infer_objects(copy=False)

    # df_all vẫn trỏ về df_train cho backward-compat với steps MLR/VAR
    df_all = df_train
    logger.info(
        f"[FE] df_train: {len(df_train)} rows × {len(df_train.columns)} cols (no leakage)\n"
        f"[FE] df_latest_full: {len(df_latest_full)} rows (point-in-time cutoff)"
    )

    # ── Step 3: MLR Model ─────────────────────────────────────────────────────
    logger.info("[3/7] Fitting MLR model...")
    mlr_summary  = None
    mlr_pred     = None
    mlr_adj_r2   = None

    try:

        mlr = MLRModel()
        mlr.fit(df_all)

        mlr_summary = mlr.summary_table()
        diag = mlr.diagnostics()
        mlr_adj_r2 = mlr.adj_r2_

        # DỰ BÁO FORWARD thật: features tại các phiên cuối cùng TRƯỚC quý mới
        # (point-in-time) → dự báo mean log-return/ngày của ~1 tháng giao dịch
        # kế tiếp. Lấy trung bình 5 phiên cuối để giảm nhiễu 1 phiên đơn lẻ.
        mlr_preds = mlr.predict(df_all.tail(5))
        mlr_pred  = float(mlr_preds.mean()) if len(mlr_preds) > 0 else None

        logger.info(f"[MLR] Adj-R² (train) = {mlr_adj_r2:.4f} | horizon = {mlr.horizon} phiên")
        logger.info(f"[MLR] OOS (25% holdout) = {diag.get('oos', 'N/A')}")
        logger.info(f"[MLR] Forward forecast (log-return/ngày) = {mlr_pred}")
        logger.info(f"[MLR] Durbin-Watson = {diag.get('durbin_watson', 'N/A')}")
        logger.info(f"[MLR] ADF residuals p-value = {diag.get('adf_residuals_pvalue', 'N/A')}")

    except Exception as e:
        logger.warning(f"[MLR] Bỏ qua do lỗi: {e}", exc_info=True)

    # ── Step 4: VAR Model ─────────────────────────────────────────────────────
    var_forecast   = None
    granger_df     = None
    granger_leaders = None

    if not args.skip_var:
        logger.info("[4/7] Fitting VAR model...")
        try:


            df_var_input = df_all.copy()
            df_var_input = df_var_input.rename(columns={"log_return": "vni_return"})

            var_model = VARModel(variable_cols=VAR_VARIABLES)
            var_model.fit(df_var_input)

            granger_df = var_model.granger_causality(caused="vni_return")
            granger_leaders = int(
                (granger_df["granger_causes_vni"] == True).sum()
            ) if granger_df is not None and len(granger_df) else 0

            if var_model.data_ is not None and var_model.optimal_lag_:
                last_rows = var_model.data_.tail(var_model.optimal_lag_).values
                if len(last_rows) == var_model.optimal_lag_:
                    forecast_df = var_model.forecast(last_rows, steps=5)
                    if "vni_return" in forecast_df.columns:
                        var_forecast = float(forecast_df["vni_return"].mean())

            logger.info(f"[VAR] {granger_leaders} Granger leaders, "
                        f"VAR forecast T+5 = {var_forecast}")

        except Exception as e:
            logger.warning(f"[VAR] Bỏ qua do lỗi: {e}", exc_info=True)
    else:
        logger.info("[4/7] Skip VAR (--skip-var flag)")

    # ── Step 5: ML Walk-Forward Validation ───────────────────────────────────
    # QUAN TRỌNG: ML train trên df_train (no leakage), KHÔNG phải df_latest_full.
    # Dự báo latest_pred được thực hiện trên điểm dữ liệu cuối cùng của df_train.
    wfv_summary = None
    fi_df       = None
    ml_pred_class = None
    ml_confidence = None

    if not args.skip_ml:
        logger.info("[5/7] Running ML Walk-Forward Validation (on df_train, no leakage)...")
        try:
            import traceback as _tb
            # Build ML features từ df_train (không leakage)
            df_ml = build_ml_features(df_train)
            df_ml = create_target_variable(df_ml)

            logger.info(f"[ML] df_ml sau build_ml_features: {len(df_ml)} rows, {len(df_ml.columns)} cols")

            # Lấy danh sách feature columns cho ML
            exclude = {"date", "open", "high", "low", "close", "volume",
                       "index", "target", "target_binary", "forward_return",
                       "log_return", "weekly_return", "monthly_return"}
            feature_cols = [c for c in df_ml.columns
                            if c not in exclude
                            and df_ml[c].dtype in ["float64", "float32", "int64", "int32"]
                            and float(pd.to_numeric(df_ml[c], errors="coerce").std(skipna=True) or 0) > 1e-10]

            logger.info(f"[ML] Feature cols: {len(feature_cols)} cols eligible for WFV")

            if len(feature_cols) > 5:
                wfv_summary = evaluate_wfv(
                    df_ml, feature_cols, model_type="xgboost"
                )
                fi_cols = (
                    wfv_summary.get("features_used", feature_cols)
                    if wfv_summary else feature_cols
                )
                fi_df = get_feature_importance(
                    df_ml, fi_cols, model_type="xgboost"
                )
                if wfv_summary:
                    ml_pred_class = wfv_summary.get("latest_pred_class")
                    ml_confidence = wfv_summary.get("latest_confidence")
                    logger.info(
                        f"[ML] WFV OK: accuracy={wfv_summary.get('mean_accuracy', 'N/A'):.1%} "
                        f"f1={wfv_summary.get('mean_f1', 'N/A'):.4f} "
                        f"pred={wfv_summary.get('latest_prediction', 'N/A')}"
                    )
                else:
                    logger.error(
                        f"[ML] evaluate_wfv trả về dict rỗng cho {quarter}! "
                        f"n_rows={len(df_ml)}, n_features={len(feature_cols)}. "
                        f"Kiểm tra log [ML-WFV] phía trên để biết nguyên nhân."
                    )
            else:
                logger.error(
                    f"[ML] Chỉ có {len(feature_cols)} features hợp lệ (cần >5) — bỏ qua WFV. "
                    f"Danh sách features có: {feature_cols}"
                )

        except Exception as e:
            # LOG ĐẦY ĐỦ TRACEBACK — không được nuốt lỗi trong im lặng
            logger.error(
                f"[ML] EXCEPTION khi chạy Walk-Forward Validation cho {quarter}:\n"
                f"{_tb.format_exc()}"
            )
    else:
        logger.info("[5/7] Skip ML (--skip-ml flag)")

    # ── Step 6: Quarterly Scoring ─────────────────────────────────────────────
    logger.info("[6/7] Computing quarterly score...")

    # Lấy giá trị indicators mới nhất từ df_latest_full (point-in-time).
    # Mặc định, hàng cuối = phiên giao dịch cuối của quý TRƯỚC — đúng thông
    # tin quỹ có tại ngày đầu quý. Các cột *_q_ytd khi đó = cộng dồn trọn
    # quý vừa kết thúc (NFF/ETF/Oil của quý gần nhất đã hoàn tất).
    latest = df_latest_full.iloc[-1].copy() if len(df_latest_full) > 0 else pd.Series(dtype=float)
    logger.info(
        f"[SCORE] Lấy latest từ df_latest_full: ngày {latest.get('date', 'N/A')} "
        f"| nff_ex_etf_q_ytd={latest.get('nff_ex_etf_q_ytd', 'N/A')} "
        f"| etf_flow_q_ytd={latest.get('etf_flow_q_ytd', 'N/A')}"
    )

    # ── ADTV: khối lượng giao dịch bình quân mỗi phiên (point-in-time) ──────
    # ADTV(Q−1)/ADTV(Q−2) − 1 — chỉ dùng 2 quý ĐÃ KẾT THÚC trước quý đang chấm.
    # Trước đây chưa bao giờ truyền → chỉ báo ADTV luôn N/A trong trụ cột
    # Market Structure. Dữ liệu volume lấy từ chính OHLCV vnstock đã fetch.
    adtv_change_pct = (
        compute_adtv_change_pct(df_latest_full, quarter)
        if len(df_latest_full) > 0 else None
    )
    if adtv_change_pct is None:
        logger.warning(
            f"[ADTV] Không tính được ADTV change cho {quarter} — "
            "chỉ báo ADTV sẽ bị loại khỏi trung bình trụ cột Market Structure (không dùng 50 giả)."
        )

    # ── Xác định tình trạng FTSE theo lịch sử (nếu auto) ─────────────────────
    if args.ftse_status == "auto":
        y_str, q_str = quarter.split("-Q")
        y = int(y_str)
        q = int(q_str)
        if y < 2025 or (y == 2025 and q < 3):
            actual_ftse_status = "unknown"
        elif (y == 2025 and q >= 3) or (y == 2026 and q < 4):
            actual_ftse_status = "pending"
        else: # >= 2026 Q4
            actual_ftse_status = "confirmed"
        logger.info(f"[FTSE] Auto-detected historical FTSE status for {quarter}: {actual_ftse_status}")
    else:
        actual_ftse_status = args.ftse_status

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
        ftse_upgrade_status=actual_ftse_status,
        adtv_change_pct=adtv_change_pct,
    )

    # ── Minh bạch point-in-time ───────────────────────────────────────────────
    # Ghi rõ ngày dữ liệu thực tế dùng để chấm điểm vào record (JSON + parquet)
    # để mọi báo cáo đều audit được: điểm quý Q dựa trên thông tin đến ngày nào.
    _latest_date = latest.get("date", None)
    score_record["data_as_of"] = (
        str(pd.to_datetime(_latest_date).date()) if _latest_date is not None else None
    )
    score_record["point_in_time"] = bool(qd["point_in_time"]) if qd else None
    if qd and not qd["point_in_time"]:
        logger.warning(
            f"[SCORE] Điểm {quarter} tính với --as-of GIỮA quý "
            f"(data_as_of={score_record['data_as_of']}) — KHÔNG dùng làm backtest."
        )

    # ── ASSERT chặn tái diễn lỗi ML "not run" ────────────────────────────────
    # Đây là lần thứ 2 lỗi ML không chạy bị publish report mà không ai biết.
    # Nếu ML bị missing, fail loudly thay vì âm thầm publish report sai.
    ml_forecast_details = score_record.get("group_details", {}).get("ml_forecast", {})
    ml_signal_val = ml_forecast_details.get("ml_signal", "")
    ml_quality_val = ml_forecast_details.get("model_quality", "")
    if "<MISSING>" in str(ml_signal_val) or "<MISSING>" in str(ml_quality_val):
        logger.error(
            f"[ASSERT FAIL] ML Forecast bị MISSING cho {quarter}!\n"
            f"  ml_signal   = {ml_signal_val!r}\n"
            f"  model_quality = {ml_quality_val!r}\n"
            f"Kiểm tra traceback [ML] EXCEPTION ở trên. Workflow sẽ FAIL để ngăn publish report sai."
        )
        # Raise để GitHub Actions workflow fail với exit code != 0
        raise RuntimeError(
            f"[ML ASSERT] ML Forecast not run for {quarter}. "
            f"ml_signal={ml_signal_val!r}. See [ML] EXCEPTION log above."
        )
    else:
        logger.info(
            f"[ASSERT PASS] ML Forecast OK cho {quarter}: "
            f"signal={ml_signal_val!r} | quality={ml_quality_val!r}"
        )

    # ── Step 7: Build Reports ─────────────────────────────────────────────────
    logger.info("[7/7] Building reports...")


    # Load score history

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
    logger.info(f"Tổng điểm (raw composite) : {score_record['total_score']:.1f}/100 → {score_record['emoji']} {score_record['label']}")
    if score_record.get("calibration_applied"):
        logger.info(
            f"HÀNH ĐỘNG (calibrated)    : {score_record['calibrated_score']:.1f}/100 → "
            f"{score_record['calibrated_emoji']} {score_record['calibrated_label']} "
            f"(z={score_record['calibration_z']:+.2f} vs {score_record['calibration_n_history']} quý trước)"
        )
    else:
        logger.info(f"HÀNH ĐỘNG (calibrated)    : chưa đủ lịch sử — giữ nguyên raw")
    logger.info(f"Khuyến nghị : {score_record.get('calibrated_description', score_record['label_description'])}")
    logger.info(f"Phân bổ     : {score_record.get('calibrated_allocation', score_record.get('label_allocation', 'N/A'))}")
    logger.info(f"Leading     : {score_record.get('most_divergent_pillar', score_record.get('leading_indicator', 'N/A'))}")
    logger.info(f"HTML report : {html_path}")
    logger.info(f"JSON export : {json_path}")
    logger.info(f"{'='*60}")

    # ── Auto-update README and Sync all HTML reports ───────────────────────────
    try:
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "update_readme_results.py")],
            cwd=str(PROJECT_ROOT), check=True
        )
        logger.info("[README] Auto-updated results section")
        
        # Đồng bộ lịch sử cho tất cả các HTML báo cáo cũ
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "rebuild_html.py")],
            cwd=str(PROJECT_ROOT), check=True
        )
        logger.info("[HTML] Auto-synced historical charts for all quarters")
    except Exception as e:
        logger.warning(f"[AUTO-SYNC] Could not auto-sync files: {e}")


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)
