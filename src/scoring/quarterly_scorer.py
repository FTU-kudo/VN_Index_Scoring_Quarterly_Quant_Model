"""
quarterly_scorer.py — Hệ thống Chấm điểm Tổng hợp Theo Quý
============================================================
Hệ thống chấm điểm 6 nhóm (tổng 100 điểm) cho VN-Index mỗi quý.
Mỗi nhóm được tính điểm 0–100 rồi nhân trọng số.

Phân loại kết quả:
  80–100 → BUY        🟢
  60–79  → ACCUMULATE 🔵
  40–59  → HOLD       🟡
  20–39  → REDUCE     🟠
  0–19   → SELL       🔴

Thiết kế: Mỗi nhóm có hàm scorer riêng, nhận DataFrame features và trả về
  dict(raw_score=0-100, weighted_score, details=dict, rationale=str)
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.utils.config import (
    SCORING_WEIGHTS, SCORE_LABELS,
    PE_ZSCORE_OVERBOUGHT, PE_ZSCORE_OVERSOLD,
    PB_ZSCORE_OVERBOUGHT, PB_ZSCORE_OVERSOLD,
    SCORES_DIR, FTSE_PASSIVE_INFLOW_BASE_USD
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Normalize → 0–100
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp_score(s: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Giới hạn điểm trong [lo, hi]."""
    return max(lo, min(hi, float(s) if not np.isnan(s) else 50.0))


def _invert(score: float) -> float:
    """Đảo chiều: 100 → 0, 0 → 100."""
    return 100.0 - score


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Macro & Monetary Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_macro_monetary(df_latest: pd.Series) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Vĩ mô & Tiền tệ (trọng số 25%).

    Logic:
      - Lãi suất OMO: Thấp/giảm → điểm cao (môi trường nới lỏng thuận lợi)
      - Lãi suất huy động 12T: Tương tự OMO
      - Tỷ giá USD/VND: Ổn định/VND mạnh → điểm cao
      - M2 growth: Moderate (10-15%) → điểm cao, quá cao hoặc quá thấp → ↓
      - Credit growth: Phù hợp GDP target → điểm cao

    Returns
    -------
    dict với raw_score (0–100), sub_scores, rationale
    """
    scores = {}
    details = {}

    # ── Lãi suất OMO ────────────────────────────────────────────────────────
    omo = df_latest.get("omo_overnight_rate", np.nan)
    if pd.notna(omo):
        # Thang điểm: 0% = 100, 8% = 0 (tuyến tính)
        omo_score = _clamp_score(100 - omo * 12.5)
        scores["omo_rate_score"] = omo_score
        details["omo_overnight_rate"] = f"{omo:.2f}% → score {omo_score:.0f}"
    else:
        omo_score = 50.0
        details["omo_overnight_rate"] = "N/A → default 50"

    # ── Xu hướng lãi suất (Δ OMO) ────────────────────────────────────────────
    d_omo = df_latest.get("delta_omo_rate", np.nan)
    if pd.notna(d_omo):
        # Giảm lãi suất → +10, tăng → -10
        trend_bonus = _clamp_score(50 - d_omo * 1000)
        scores["ir_trend_score"] = trend_bonus
        dir_str = "↓ Cut" if d_omo < -0.05 else ("↑ Hike" if d_omo > 0.05 else "→ Hold")
        details["ir_trend"] = f"Δ OMO = {d_omo:.4f} ({dir_str}) → score {trend_bonus:.0f}"
    else:
        trend_bonus = 50.0

    # ── Tỷ giá USD/VND ────────────────────────────────────────────────────────
    fx_z = df_latest.get("usd_vnd_zscore", np.nan)
    if pd.notna(fx_z):
        # fx_z > 0 → VND yếu → điểm thấp
        fx_score = _clamp_score(50 - fx_z * 15)
        scores["fx_score"] = fx_score
        details["usd_vnd"] = f"Z-score = {fx_z:.2f} → score {fx_score:.0f}"
    else:
        fx_score = 50.0
        details["usd_vnd"] = "N/A → default 50"

    # ── M2 Growth ──────────────────────────────────────────────────────────────
    m2 = df_latest.get("m2_yoy_pct", np.nan)
    if pd.notna(m2):
        # Optimal: 12% → score 80. <5% or >20% → score giảm
        m2_score = _clamp_score(80 - abs(m2 - 12) * 4)
        scores["m2_score"] = m2_score
        details["m2_yoy_growth"] = f"{m2:.1f}% YoY → score {m2_score:.0f}"
    else:
        m2_score = 50.0

    # ── VN Bonds (10Y Yield & Spread) ──────────────────────────────────────────
    vn10y = df_latest.get("vn10y_yield", np.nan)
    vn_spread = df_latest.get("vn_yield_spread", np.nan)
    if pd.notna(vn10y) and pd.notna(vn_spread):
        # VN10Y > 6% = 0, < 2.5% = 100
        vn10y_score = _clamp_score(100 - (vn10y - 2.5) * 28.5)
        # Spread < 0 = inverted curve (rủi ro), Spread > 1.5% = tốt
        spread_score = _clamp_score((vn_spread + 0.2) * 58)
        bond_score = (vn10y_score + spread_score) / 2
        scores["bond_market_score"] = bond_score
        details["vn_bonds"] = f"VN10Y {vn10y:.2f}% | Spread {vn_spread:.2f}% → score {bond_score:.0f}"
    else:
        bond_score = 50.0

    # ── Tổng điểm nhóm Macro ─────────────────────────────────────────────────
    raw = np.mean([omo_score, trend_bonus, fx_score, m2_score, bond_score])
    raw = _clamp_score(raw)

    return {
        "group":         "macro_monetary",
        "raw_score":     round(raw, 2),
        "weight":        SCORING_WEIGHTS["macro_monetary"],
        "weighted_score": round(raw * SCORING_WEIGHTS["macro_monetary"], 2),
        "sub_scores":    scores,
        "details":       details,
        "rationale":     _macro_rationale(omo, d_omo, fx_z, m2, raw, df_latest)
    }


def _macro_rationale(omo, d_omo, fx_z, m2, score, df_latest) -> str:
    parts = []
    if pd.notna(omo):
        parts.append(f"OMO rate {omo:.2f}% ({'low/favorable' if omo < 5 else 'elevated'})")
    if pd.notna(d_omo) and abs(d_omo) > 0.05:
        parts.append(f"SBV {'tăng' if d_omo > 0 else 'cắt giảm'} OMO rate (Δ={d_omo:.2f}%)")
    if pd.notna(fx_z):
        parts.append(f"USD/VND z={fx_z:.1f} ({'pressure' if fx_z > 1 else 'stable'})")
    if pd.notna(m2):
        parts.append(f"M2 tăng {m2:.1f}% YoY ({'mạnh' if m2 > 15 else ('yếu' if m2 < 8 else 'bình thường')})")
    
    vn10y = df_latest.get("vn10y_yield", np.nan)
    vn_spread = df_latest.get("vn_yield_spread", np.nan)
    if pd.notna(vn10y) and pd.notna(vn_spread):
        parts.append(f"VN10Y {vn10y:.2f}% (Spread {vn_spread:.2f}%)")
        
    label = "FAVORABLE" if score > 65 else ("NEUTRAL" if score > 40 else "UNFAVORABLE")
    return f"Macro: {label} — " + " | ".join(parts) if parts else f"Macro: {label}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Global Intermarket Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_global_intermarket(df_latest: pd.Series) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Biến số Toàn cầu & Dòng vốn Ngoại (trọng số 20%).

    Logic:
      - DXY Z-score thấp (USD yếu) → thuận lợi cho EM → điểm cao
      - US10Y yield thấp → môi trường risk-on → điểm cao
      - Net Foreign Flow dương/mua ròng → điểm cao
    """
    scores = {}
    details = {}

    # ── DXY ──────────────────────────────────────────────────────────────────
    dxy_z = df_latest.get("dxy_zscore_60d", np.nan)
    if pd.notna(dxy_z):
        dxy_score = _clamp_score(50 - dxy_z * 20)  # z > 0 → điểm thấp
        scores["dxy_score"] = dxy_score
        details["dxy"] = f"Z = {dxy_z:.2f} → score {dxy_score:.0f}"
    else:
        dxy_score = 50.0

    # ── US10Y ────────────────────────────────────────────────────────────────
    us10y = df_latest.get("us10y_yield", np.nan)
    d_us10y = df_latest.get("delta_us10y", np.nan)
    if pd.notna(us10y):
        # US10Y > 5% = rất bất lợi (điểm = 0), US10Y < 2% = thuận lợi (điểm = 100)
        us10y_score = _clamp_score(100 - us10y * 20)
        scores["us10y_score"] = us10y_score
        details["us10y"] = f"{us10y:.2f}% → score {us10y_score:.0f}"
    else:
        us10y_score = 50.0

    # ── Net Foreign Flow ──────────────────────────────────────────────────────
    nff_z = df_latest.get("nff_zscore_60d", np.nan)
    nff_5d = df_latest.get("nff_rolling5d", np.nan)
    if pd.notna(nff_z):
        nff_score = _clamp_score(50 + nff_z * 15)  # z > 0 → mua ròng → điểm cao
        scores["nff_score"] = nff_score
        dir_str = "NET BUY" if nff_z > 0.5 else ("NET SELL" if nff_z < -0.5 else "Neutral")
        details["nff"] = f"Z = {nff_z:.2f} ({dir_str}) → score {nff_score:.0f}"
        if pd.notna(nff_5d):
            details["nff_5d_rolling"] = f"{nff_5d:.0f} tỷ VND (tuần)"
    else:
        nff_score = 50.0

    raw = np.mean([dxy_score, us10y_score, nff_score])
    raw = _clamp_score(raw)

    return {
        "group":          "global_intermarket",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["global_intermarket"],
        "weighted_score": round(raw * SCORING_WEIGHTS["global_intermarket"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      f"Global: DXY={dxy_z:.1f}σ | US10Y={us10y:.2f}% | NFF-Z={nff_z:.1f}σ"
            if all(pd.notna(v) for v in [dxy_z, us10y, nff_z])
            else "Global: Dữ liệu không đầy đủ — cần DXY, US10Y, NFF"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Valuation & Leverage Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_valuation_leverage(df_latest: pd.Series) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Định giá & Đòn bẩy (trọng số 20%).

    Logic:
      - P/E Z-score âm (rẻ) → điểm cao
      - P/B Z-score âm (rẻ) → điểm cao
      - Margin risk score thấp → điểm cao (ít rủi ro giải chấp)
    """
    scores = {}
    details = {}

    # ── P/E Z-score ───────────────────────────────────────────────────────────
    pe_z = df_latest.get("pe_zscore", np.nan)
    if pd.notna(pe_z):
        pe_score = _clamp_score(50 - pe_z * 25)   # Z âm → rẻ → score cao
        scores["pe_score"] = pe_score
        zone = "OVERVALUED" if pe_z > PE_ZSCORE_OVERBOUGHT else ("UNDERVALUED" if pe_z < PE_ZSCORE_OVERSOLD else "FAIR VALUE")
        details["pe_zscore"] = f"Z = {pe_z:.2f} ({zone}) → score {pe_score:.0f}"
    else:
        pe_score = 50.0

    # ── P/B Z-score ───────────────────────────────────────────────────────────
    pb_z = df_latest.get("pb_zscore", np.nan)
    if pd.notna(pb_z):
        pb_score = _clamp_score(50 - pb_z * 25)
        scores["pb_score"] = pb_score
        zone = "OVERVALUED" if pb_z > PB_ZSCORE_OVERBOUGHT else ("UNDERVALUED" if pb_z < PB_ZSCORE_OVERSOLD else "FAIR VALUE")
        details["pb_zscore"] = f"Z = {pb_z:.2f} ({zone}) → score {pb_score:.0f}"
    else:
        pb_score = 50.0

    # ── Margin Risk ───────────────────────────────────────────────────────────
    mrisk = df_latest.get("margin_risk_score", np.nan)
    if pd.notna(mrisk):
        # Margin risk cao → nguy hiểm → điểm THẤP (đảo chiều)
        margin_score = _clamp_score(_invert(mrisk))
        scores["margin_risk_score"] = margin_score
        risk_label = ("DANGER" if mrisk > 60 else
                      ("WARNING" if mrisk > 30 else "SAFE"))
        details["margin_risk"] = f"Risk = {mrisk:.0f}/100 ({risk_label}) → score {margin_score:.0f}"
    else:
        margin_score = 50.0

    # ── Earnings Yield Gap (EYG) ──────────────────────────────────────────────
    eyg_z = df_latest.get("eyg_zscore", np.nan)
    if pd.notna(eyg_z):
        # z > 0 (EYG cao, chứng khoán rẻ hơn trái phiếu) -> score cao
        eyg_score = _clamp_score(50 + eyg_z * 25)
        scores["eyg_score"] = eyg_score
        details["eyg_zscore"] = f"EYG Z-score = {eyg_z:.2f} → score {eyg_score:.0f}"
    else:
        eyg_score = 50.0

    raw = np.mean([pe_score, pb_score, margin_score, eyg_score])
    raw = _clamp_score(raw)

    # Valuation composite từ valuation_features.py (nếu có)
    val_comp = df_latest.get("valuation_composite_score", np.nan)
    if pd.notna(val_comp):
        # Blend 70% calculated + 30% composite
        raw = raw * 0.7 + val_comp * 0.3

    return {
        "group":          "valuation_leverage",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["valuation_leverage"],
        "weighted_score": round(raw * SCORING_WEIGHTS["valuation_leverage"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      (f"PE Z={pe_z:.2f} | EYG Z={eyg_z:.2f} | Margin risk={mrisk:.0f}")
            if all(pd.notna(v) for v in [pe_z, eyg_z, mrisk])
            else "Valuation: Dữ liệu P/E, P/B, EYG hoặc margin không đầy đủ"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Quant Model Score (MLR + VAR signals) (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_quant_model(
    mlr_pred:          Optional[float] = None,
    var_forecast:      Optional[float] = None,
    mlr_adj_r2:        Optional[float] = None,
    granger_leaders:   Optional[int]   = None,   # Số vars Granger-cause VNI
) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Mô hình Định lượng (MLR + VAR) (trọng số 15%).

    Parameters
    ----------
    mlr_pred        : Dự báo return từ MLR model (log-return)
    var_forecast    : Dự báo return từ VAR model T+5
    mlr_adj_r2      : Adjusted R² của MLR (chất lượng model)
    granger_leaders : Số biến có Granger-cause VNI (p < 0.05)

    Logic:
      - MLR/VAR dự báo dương → điểm cao
      - Adj-R² cao → model reliable → tăng confidence
      - Nhiều biến Granger-cause → hệ thống có thông tin dự báo tốt
    """
    scores = {}
    details = {}

    # ── MLR Prediction ────────────────────────────────────────────────────────
    if mlr_pred is not None and pd.notna(mlr_pred):
        # Chuẩn hóa: return +2% = điểm 80, -2% = điểm 20
        mlr_score = _clamp_score(50 + mlr_pred * 3000)
        scores["mlr_signal_score"] = mlr_score
        details["mlr_forecast"] = f"Forecast log-return = {mlr_pred:.4f} → score {mlr_score:.0f}"
    else:
        mlr_score = 50.0
        details["mlr_forecast"] = "No MLR forecast"

    # ── VAR Forecast ─────────────────────────────────────────────────────────
    if var_forecast is not None and pd.notna(var_forecast):
        var_score = _clamp_score(50 + var_forecast * 3000)
        scores["var_signal_score"] = var_score
        details["var_forecast"] = f"VAR T+5 return = {var_forecast:.4f} → score {var_score:.0f}"
    else:
        var_score = 50.0

    # ── Model Quality Bonus ───────────────────────────────────────────────────
    if mlr_adj_r2 is not None and pd.notna(mlr_adj_r2):
        # Adj-R² cao → bonus confidence (max +10 điểm)
        quality_bonus = min(mlr_adj_r2 * 10, 10)
        details["mlr_adj_r2"] = f"Adj-R² = {mlr_adj_r2:.4f} → confidence bonus {quality_bonus:.1f}"
    else:
        quality_bonus = 0

    # ── Granger Leader Count ──────────────────────────────────────────────────
    if granger_leaders is not None:
        details["granger_leaders"] = (
            f"{granger_leaders} vars Granger-cause VNI (p<5%)"
        )
        granger_bonus = min(granger_leaders * 3, 15)
    else:
        granger_bonus = 0

    raw = (mlr_score * 0.5 + var_score * 0.5) + quality_bonus + granger_bonus
    raw = _clamp_score(raw)

    r2_str = f"{mlr_adj_r2:.3f}" if mlr_adj_r2 is not None and pd.notna(mlr_adj_r2) else "N/A"
    granger_str = str(granger_leaders) if granger_leaders is not None else "N/A"

    return {
        "group":          "quant_model",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["quant_model"],
        "weighted_score": round(raw * SCORING_WEIGHTS["quant_model"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      (f"MLR={mlr_score:.0f} | VAR={var_score:.0f} | "
                          f"R²={r2_str} | Granger={granger_str}")
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ML Forecast Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_ml_forecast(
    ml_accuracy:    Optional[float] = None,
    ml_f1:          Optional[float] = None,
    ml_pred_class:  Optional[int]   = None,    # 1=UP, 0=NEUTRAL, -1=DOWN
    ml_confidence:  Optional[float] = None,    # predict_proba max
) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Dự báo ML (XGBoost/LightGBM) (trọng số 10%).
    """
    scores = {}
    details = {}

    # ── Prediction Quality ────────────────────────────────────────────────────
    qual_score = 50.0
    if ml_accuracy is not None and ml_f1 is not None:
        qual_score = _clamp_score((ml_accuracy + ml_f1) / 2 * 100)
        details["model_quality"] = (f"Accuracy={ml_accuracy:.1%} "
                                    f"F1={ml_f1:.3f} → quality {qual_score:.0f}")
    scores["ml_quality_score"] = qual_score

    # ── Directional Signal ────────────────────────────────────────────────────
    signal_score = 50.0
    if ml_pred_class is not None:
        if ml_pred_class == 1:    # UP
            signal_score = 80.0
            conf_str = f" (conf={ml_confidence:.0%})" if ml_confidence else ""
            details["ml_signal"] = f"Dự báo: UP{conf_str}"
        elif ml_pred_class == -1: # DOWN
            signal_score = 20.0
            conf_str = f" (conf={ml_confidence:.0%})" if ml_confidence else ""
            details["ml_signal"] = f"Dự báo: DOWN{conf_str}"
        else:                     # NEUTRAL
            signal_score = 50.0
            details["ml_signal"] = "Dự báo: NEUTRAL"
    else:
        details["ml_signal"] = "ML prediction not run"

    scores["ml_signal_score"] = signal_score

    # Confidence adjustment
    if ml_confidence and ml_confidence > 0.6:
        conf_bonus = (ml_confidence - 0.6) * 50  # max +20 nếu confidence 100%
        signal_score = _clamp_score(signal_score + conf_bonus)

    raw = (qual_score * 0.3 + signal_score * 0.7)
    raw = _clamp_score(raw)

    return {
        "group":          "ml_forecast",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["ml_forecast"],
        "weighted_score": round(raw * SCORING_WEIGHTS["ml_forecast"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      f"ML: {details.get('ml_signal', 'N/A')} | Quality={qual_score:.0f}"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Market Structure & FTSE Upgrade Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_market_structure(
    ftse_upgrade_status: str = "pending",  # 'pending', 'confirmed', 'completed'
    months_to_next_rebalancing: Optional[int] = None,
    adtv_change_pct: Optional[float] = None,   # % change ADTV QoQ
) -> Dict[str, Any]:
    """
    Chấm điểm nhóm Cấu trúc Thị trường & Nâng hạng FTSE (trọng số 10%).

    Context Q3/2026:
      - FTSE Russell đã xác nhận VN-Index vào danh sách Secondary Emerging Market
      - Rebalancing schedule: tháng 3, 6, 9, 12 → gần nhất: tháng 9/2026
      - Dòng vốn passive ETF ước tính $6.4 tỷ USD phân bổ vào VN
      - Effect tâm lý (sentiment premium) lên VN30 trước kỳ rebalancing

    Parameters
    ----------
    ftse_upgrade_status : 'pending', 'confirmed', 'completed'
    months_to_next_rebalancing : Số tháng đến kỳ rebalancing tiếp theo
    adtv_change_pct : % change ADTV so với quý trước (positive = tốt)
    """
    scores = {}
    details = {}

    # ── FTSE Status Score ─────────────────────────────────────────────────────
    ftse_score_map = {
        "completed":  85,   # Đã hoàn thành → dòng vốn đang vào → rất tốt
        "confirmed":  75,   # Đã xác nhận → kỳ vọng cao → tốt
        "pending":    55,   # Đang chờ → kỳ vọng không chắc chắn → trung bình
        "unknown":    50,
    }
    ftse_score = ftse_score_map.get(ftse_upgrade_status, 50)
    scores["ftse_status_score"] = ftse_score

    # Q3/2026 context: FTSE đã confirmed vào March 2025, rebalancing nhiều đợt
    # Thêm điểm cụ thể cho Q3/2026
    details["ftse_upgrade"] = (
        f"Status: {ftse_upgrade_status} → score {ftse_score}\n"
        f"  Est passive inflow: ${FTSE_PASSIVE_INFLOW_BASE_USD/1e9:.1f}B USD\n"
        f"  Effect: Sentiment premium VN30 +15-25% trong giai đoạn rebalancing"
    )

    # ── Rebalancing Proximity Bonus ───────────────────────────────────────────
    if months_to_next_rebalancing is not None:
        # Gần rebalancing → sentiment premium cao → điểm cao
        if months_to_next_rebalancing <= 1:
            rebal_bonus = 20     # Đang trong tháng rebalancing
        elif months_to_next_rebalancing <= 2:
            rebal_bonus = 12     # 2 tháng trước
        elif months_to_next_rebalancing <= 3:
            rebal_bonus = 6      # 1 quý trước
        else:
            rebal_bonus = 0
        details["rebalancing"] = (
            f"{months_to_next_rebalancing} months to rebalancing → bonus +{rebal_bonus}"
        )
    else:
        rebal_bonus = 5   # Q3/2026: đang trong tháng 9 rebalancing
        details["rebalancing"] = "Tháng 9/2026 là kỳ FTSE rebalancing → bonus +5"

    # ── ADTV Improvement ─────────────────────────────────────────────────────
    if adtv_change_pct is not None and pd.notna(adtv_change_pct):
        # ADTV tăng → thanh khoản tốt hơn → điểm cao
        adtv_score = _clamp_score(50 + adtv_change_pct * 100)
        scores["adtv_score"] = adtv_score
        details["adtv"] = f"ADTV change {adtv_change_pct:+.1%} QoQ → score {adtv_score:.0f}"
    else:
        adtv_score = 60.0   # Q3/2026: ADTV tăng do upgrade
        details["adtv"] = "ADTV Q3/2026: Est increase ~30% due to foreign flow"

    raw = _clamp_score(ftse_score + rebal_bonus + (adtv_score - 50) * 0.3)

    return {
        "group":          "market_structure",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["market_structure"],
        "weighted_score": round(raw * SCORING_WEIGHTS["market_structure"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      (
            f"FTSE: {ftse_upgrade_status.upper()} | "
            f"Rebalancing bonus: +{rebal_bonus} | "
            f"ADTV: {adtv_change_pct:+.0%}" if adtv_change_pct else
            "FTSE Secondary EM upgrade đang tạo structural tailwind cho VN-Index"
        )
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Master Scorer — Tổng hợp 6 nhóm → Final Score
# ═══════════════════════════════════════════════════════════════════════════════

def compute_quarterly_score(
    quarter: str,
    df_latest: pd.Series,
    mlr_pred:             Optional[float] = None,
    var_forecast:         Optional[float] = None,
    mlr_adj_r2:           Optional[float] = None,
    granger_leaders:      Optional[int]   = None,
    ml_accuracy:          Optional[float] = None,
    ml_f1:                Optional[float] = None,
    ml_pred_class:        Optional[int]   = None,
    ml_confidence:        Optional[float] = None,
    ftse_upgrade_status:  str = "confirmed",
    adtv_change_pct:      Optional[float] = None,
) -> Dict[str, Any]:
    """
    Hàm master: tính điểm tổng hợp VN-Index cho một quý.

    Parameters
    ----------
    quarter    : Chuỗi quý (VD: "2026-Q3")
    df_latest  : pd.Series chứa tất cả indicators mới nhất

    Returns
    -------
    dict đầy đủ với điểm từng nhóm, tổng điểm, phân loại, và khuyến nghị
    """
    logger.info(f"[SCORER] Chấm điểm {quarter}...")

    # ── Chạy 6 nhóm scorer ───────────────────────────────────────────────────
    g1 = score_macro_monetary(df_latest)
    g2 = score_global_intermarket(df_latest)
    g3 = score_valuation_leverage(df_latest)
    g4 = score_quant_model(mlr_pred, var_forecast, mlr_adj_r2, granger_leaders)
    g5 = score_ml_forecast(ml_accuracy, ml_f1, ml_pred_class, ml_confidence)

    # FTSE rebalancing tháng 9/2026 = months_to_next_rebalancing = 0
    g6 = score_market_structure(
        ftse_upgrade_status=ftse_upgrade_status,
        months_to_next_rebalancing=0,   # Q3/2026: đang trong tháng 9
        adtv_change_pct=adtv_change_pct
    )

    groups = [g1, g2, g3, g4, g5, g6]

    # ── Tổng điểm có trọng số ─────────────────────────────────────────────────
    total_weighted = sum(g["weighted_score"] for g in groups)
    total_raw_avg  = np.mean([g["raw_score"] for g in groups])

    # ── Phân loại ────────────────────────────────────────────────────────────
    label, emoji, label_desc = "HOLD", "🟡", "Trung lập"
    for (lo, hi), (lbl, em, desc) in SCORE_LABELS.items():
        if lo <= total_weighted <= hi:
            label, emoji, label_desc = lbl, em, desc
            break

    # ── Xác định Leading Indicator mạnh nhất ─────────────────────────────────
    group_raw = {g["group"]: g["raw_score"] for g in groups}
    leading_indicator = max(group_raw, key=lambda k: abs(group_raw[k] - 50))

    # ── Lưu lịch sử ──────────────────────────────────────────────────────────
    score_record = {
        "quarter":               quarter,
        "date_computed":         datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_score":           round(total_weighted, 2),
        "label":                 label,
        "emoji":                 emoji,
        "label_description":     label_desc,
        "leading_indicator":     leading_indicator,
        "group_scores": {
            g["group"]: {
                "raw_score":      g["raw_score"],
                "weighted_score": g["weighted_score"]
            } for g in groups
        },
        "group_details": {
            g["group"]: g["details"] for g in groups
        },
        "group_rationale": {
            g["group"]: g["rationale"] for g in groups
        }
    }

    # Append vào lịch sử JSON
    history_path = SCORES_DIR / "quarterly_scores_history.parquet"
    new_row = pd.DataFrame([{
        "quarter": quarter,
        "date_computed": score_record["date_computed"],
        "total_score": total_weighted,
        "label": label,
        **{f"score_{g['group']}": g["weighted_score"] for g in groups}
    }])
    if history_path.exists():
        existing = pd.read_parquet(history_path)
        # Xóa record cũ cho quý này nếu có
        existing = existing[existing["quarter"] != quarter]
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row
    combined.to_parquet(history_path, index=False)

    logger.info(
        f"[SCORER] {quarter}: {emoji} {label} — {total_weighted:.1f}/100\n"
        f"  Leading indicator: {leading_indicator} ({group_raw[leading_indicator]:.1f})"
    )
    return score_record
