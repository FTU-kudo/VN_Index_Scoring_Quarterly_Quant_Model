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
    SCORING_WEIGHTS, SCORE_LABELS, SCORE_LABEL_RANGES, get_score_label,
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

    # ── Chính sách tiền tệ ngắn hạn (Lợi suất TPCP 1Y proxy) ───────────────
    vn1y = df_latest.get("vn1y_yield", np.nan)
    if pd.notna(vn1y):
        # Thang điểm: 1% = 100, 8% = 0 (tuyến tính, tương tự OMO)
        vn1y_score = _clamp_score(100 - (vn1y - 1.0) * 14.0)
        scores["vn1y_rate_score"] = vn1y_score
        details["vn1y_yield"] = f"{vn1y:.2f}% → score {vn1y_score:.0f}"
    else:
        vn1y_score = 50.0
        details["vn1y_yield"] = "<MISSING> N/A → default 50"

    # ── Xu hướng lãi suất (Δ VN1Y Yield) ────────────────────────────────────────────
    d_vn1y = df_latest.get("delta_vn1y_yield", np.nan)
    if pd.notna(d_vn1y):
        # Giảm lãi suất → +10, tăng → -10
        trend_bonus = _clamp_score(50 - d_vn1y * 100)
        scores["ir_trend_score"] = trend_bonus
        dir_str = "↓ Cut" if d_vn1y < -0.15 else ("↑ Hike" if d_vn1y > 0.15 else "→ Hold")
        details["ir_trend"] = f"Δ VN1Y = {d_vn1y:.4f} ({dir_str}) → score {trend_bonus:.0f}"
    else:
        trend_bonus = 50.0
        details["ir_trend"] = "<MISSING> N/A → default 50"

    # ── Tỷ giá USD/VND ────────────────────────────────────────────────────────
    fx_z = df_latest.get("usd_vnd_zscore", np.nan)
    if pd.notna(fx_z):
        # fx_z > 0 → VND yếu → điểm thấp
        fx_score = _clamp_score(50 - fx_z * 15)
        scores["fx_score"] = fx_score
        details["usd_vnd"] = f"Z-score = {fx_z:.2f} → score {fx_score:.0f}"
    else:
        fx_score = 50.0
        details["usd_vnd"] = "<MISSING> N/A → default 50"

    # ── M2 Growth ──────────────────────────────────────────────────────────────
    m2 = df_latest.get("m2_yoy_pct", np.nan)
    if pd.notna(m2):
        # Optimal: 12% → score 80. <5% or >20% → score giảm
        m2_score = _clamp_score(80 - abs(m2 - 12) * 4)
        scores["m2_score"] = m2_score
        details["m2_yoy_growth"] = f"{m2:.1f}% YoY → score {m2_score:.0f}"
    else:
        m2_score = 50.0
        details["m2_yoy_growth"] = "<MISSING> N/A → default 50"

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
        details["vn_bonds"] = "<MISSING> N/A → default 50"

    # ── Tổng điểm nhóm Macro ─────────────────────────────────────────────────
    raw = np.mean([vn1y_score, trend_bonus, fx_score, m2_score, bond_score])
    raw = _clamp_score(raw)

    return {
        "group":         "macro_monetary",
        "raw_score":     round(raw, 2),
        "weight":        SCORING_WEIGHTS["macro_monetary"],
        "weighted_score": round(raw * SCORING_WEIGHTS["macro_monetary"], 2),
        "sub_scores":    scores,
        "details":       details,
        "rationale":     _macro_rationale(vn1y, d_vn1y, fx_z, m2, raw, df_latest)
    }

def _macro_rationale(vn1y, d_vn1y, fx_z, m2, score, df_latest) -> str:
    parts = []
    if pd.notna(vn1y):
        parts.append(f"VN1Y rate {vn1y:.2f}% ({'low/favorable' if vn1y < 4.0 else 'elevated'})")
    if pd.notna(d_vn1y) and abs(d_vn1y) > 0.15:
        parts.append(f"SBV proxy {'hikes' if d_vn1y > 0 else 'cuts'} short-term rate (Δ={d_vn1y:.2f}%)")
    if pd.notna(fx_z):
        parts.append(f"USD/VND z={fx_z:.1f} ({'pressure' if fx_z > 1 else 'stable'})")
    if pd.notna(m2):
        parts.append(f"M2 growth {m2:.1f}% YoY ({'strong' if m2 > 15 else ('weak' if m2 < 8 else 'normal')})")
    
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
        details["dxy"] = "<MISSING> N/A → default 50"

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
        details["us10y"] = "<MISSING> N/A → default 50"

    # ── Net Foreign Flow (ex ETF) ─────────────────────────────────────────────
    nff_z = df_latest.get("nff_ex_etf_q_zscore_live", np.nan)
    nff_q_sum = df_latest.get("nff_ex_etf_q_ytd", np.nan)
    
    if pd.notna(nff_z):
        nff_score = _clamp_score(50 + nff_z * 15)  # z > 0 → mua ròng → điểm cao
        scores["nff_score"] = nff_score
        dir_str = "NET BUY" if nff_z > 0.5 else ("NET SELL" if nff_z < -0.5 else "Neutral")
        details["nff_ex_etf"] = f"Z = {nff_z:.2f} ({dir_str}) → score {nff_score:.0f}"
        if pd.notna(nff_q_sum):
            details["nff_ex_etf_q_ytd"] = f"{nff_q_sum:.2%} of Market Cap (YTD in Q)"
    else:
        # Nếu năm 2021 chưa đủ dữ liệu cho expanding Z-score
        nff_score = 50.0
        details["nff_ex_etf"] = "<MISSING> Not enough data for Z-score (2021) → default 50"

    # ── JPY Carry Trade ───────────────────────────────────────────────────────
    jpy_z = df_latest.get("usdjpy_zscore_60d", np.nan)
    jpy_risk = df_latest.get("jpy_carry_risk", "Neutral")
    jpy_risk_str = str(jpy_risk).title() if pd.notna(jpy_risk) else "Neutral"
    if pd.notna(jpy_z):
        # Yen mạnh lên (Z âm) → Rủi ro Carry Trade Unwind → Điểm thấp
        jpy_score = _clamp_score(50 + jpy_z * 15)
        scores["jpy_score"] = jpy_score
        details["jpy_carry"] = f"Z = {jpy_z:.2f} ({jpy_risk_str}) → score {jpy_score:.0f}"
    else:
        jpy_score = 50.0
        jpy_z = np.nan
        details["jpy_carry"] = "<MISSING> N/A → default 50"

    # ── Oil Shock (Geopolitical risk) ────────────────────────────────────────
    oil_shock = df_latest.get("oil_shock_score_ytd", np.nan)
    if pd.notna(oil_shock) and oil_shock > 0:
        # Nếu có sốc, trừ điểm. Thang oil_shock > 0
        # Trọng số khiêm tốn: score giảm tương ứng với shock
        oil_score = _clamp_score(100 - oil_shock) # Nếu shock=45 -> score 55. Nếu shock=0 -> score 100 (tuy nhiên ta chỉ tính khi có shock)
        scores["oil_score"] = oil_score
        max_c = df_latest.get("oil_max_weekly_change_ytd", 0)
        details["oil_shock"] = f"Oil Shock Score = {oil_shock:.1f} (Max Δ5d = {max_c:.1%}) → score {oil_score:.0f}"
    else:
        oil_score = 50.0
        details["oil_shock"] = "No Geopolitical Oil Shock Detected (Score = 0)"

    # Trọng số khiêm tốn cho Oil: ta sẽ trung bình nó với các biến chính nếu có shock
    components = [dxy_score, us10y_score, nff_score, jpy_score]
    if pd.notna(oil_shock) and oil_shock > 0:
        components.append(oil_score)
        
    raw = np.mean(components)
    
    # Áp dụng ngưỡng cảnh báo (cap) nếu JPY giảm sốc (Carry Trade Unwind)
    if pd.notna(jpy_z) and jpy_z < -2.0:
        raw = min(raw, 20.0)  # Rủi ro cao, cap điểm ở mức 20

    raw = _clamp_score(raw)
    
    # Chuẩn bị rationale safely
    rat_parts = []
    if pd.notna(dxy_z): rat_parts.append(f"DXY={dxy_z:.1f}σ")
    if pd.notna(us10y): rat_parts.append(f"US10Y={us10y:.2f}%")
    if pd.notna(nff_z): rat_parts.append(f"NFF-Z={nff_z:.1f}σ")
    if pd.notna(jpy_z): rat_parts.append(f"JPY-Z={jpy_z:.1f}σ")
    if pd.notna(oil_shock) and oil_shock > 0: rat_parts.append(f"OIL-SHOCK={oil_shock:.1f}")

    return {
        "group":          "global_intermarket",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["global_intermarket"],
        "weighted_score": round(raw * SCORING_WEIGHTS["global_intermarket"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      "Global: " + " | ".join(rat_parts) if rat_parts else "Global: Incomplete data"
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

    headline_pe = df_latest.get("headline_pe", np.nan)
    median_pe = df_latest.get("median_pe", np.nan)
    ex_vingroup_pe = df_latest.get("ex_vingroup_pe", np.nan)
    headline_pb = df_latest.get("headline_pb", np.nan)
    median_pb = df_latest.get("median_pb", np.nan)
    ex_vingroup_pb = df_latest.get("ex_vingroup_pb", np.nan)

    pe_str = f"P/E Headline: {headline_pe:.2f} | Median: {median_pe:.2f} | Ex-VG: {ex_vingroup_pe:.2f}" if pd.notna(headline_pe) and pd.notna(median_pe) else ""
    pb_str = f"P/B Headline: {headline_pb:.2f} | Median: {median_pb:.2f} | Ex-VG: {ex_vingroup_pb:.2f}" if pd.notna(headline_pb) and pd.notna(median_pb) else ""

    # ── P/E Z-score ───────────────────────────────────────────────────────────
    pe_z = df_latest.get("pe_zscore", np.nan)
    if pd.notna(pe_z):
        pe_score = _clamp_score(50 - pe_z * 25)   # Z âm → rẻ → score cao
        scores["pe_score"] = pe_score
        zone = "OVERVALUED" if pe_z > PE_ZSCORE_OVERBOUGHT else ("UNDERVALUED" if pe_z < PE_ZSCORE_OVERSOLD else "FAIR VALUE")
        details["pe_zscore"] = f"{pe_str}<br>Z = {pe_z:.2f} ({zone}) → score {pe_score:.0f}" if pe_str else f"Z = {pe_z:.2f} ({zone}) → score {pe_score:.0f}"
    else:
        pe_score = 50.0
        details["pe_zscore"] = "<MISSING> N/A → default 50"

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
            else "Valuation: Incomplete P/E, P/B, EYG, or margin data"
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
        details["mlr_forecast"] = "<MISSING> No MLR forecast"

    # ── VAR Forecast ─────────────────────────────────────────────────────────
    if var_forecast is not None and pd.notna(var_forecast):
        var_score = _clamp_score(50 + var_forecast * 3000)
        scores["var_signal_score"] = var_score
        details["var_forecast"] = f"VAR T+5 return = {var_forecast:.4f} → score {var_score:.0f}"
    else:
        var_score = 50.0
        details["var_forecast"] = "<MISSING> No VAR forecast"

    # ── Model Quality Bonus ───────────────────────────────────────────────────
    if mlr_adj_r2 is not None and pd.notna(mlr_adj_r2):
        # Adj-R² cao → bonus confidence (max +10 điểm)
        quality_bonus = min(mlr_adj_r2 * 10, 10)
        details["mlr_adj_r2"] = f"Adj-R² = {mlr_adj_r2:.4f} → confidence bonus {quality_bonus:.1f}"
    else:
        quality_bonus = 0
        details["mlr_adj_r2"] = "<MISSING> N/A"

    # ── Granger Leader Count ──────────────────────────────────────────────────
    if granger_leaders is not None:
        details["granger_leaders"] = (
            f"{granger_leaders} vars Granger-cause VNI (p<5%)"
        )
        granger_bonus = min(granger_leaders * 3, 15)
    else:
        granger_bonus = 0
        details["granger_leaders"] = "<MISSING> N/A"

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
    else:
        details["model_quality"] = "<MISSING> N/A"
    scores["ml_quality_score"] = qual_score

    # ── Directional Signal ────────────────────────────────────────────────────
    signal_score = 50.0
    if ml_pred_class is not None:
        if ml_pred_class == 1:    # UP
            signal_score = 80.0
            conf_str = f" (conf={ml_confidence:.0%})" if ml_confidence else ""
            details["ml_signal"] = f"Forecast: UP{conf_str}"
        elif ml_pred_class == -1: # DOWN
            signal_score = 20.0
            conf_str = f" (conf={ml_confidence:.0%})" if ml_confidence else ""
            details["ml_signal"] = f"Forecast: DOWN{conf_str}"
        else:                     # NEUTRAL
            signal_score = 50.0
            details["ml_signal"] = "Forecast: NEUTRAL"
    else:
        details["ml_signal"] = "<MISSING> ML prediction not run"

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
        "rationale":      f"ML: {details.get('ml_signal', 'N/A').replace('<MISSING> ', '')} | Quality={qual_score:.0f}"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Market Structure & FTSE Upgrade Score (0–100)
# ═══════════════════════════════════════════════════════════════════════════════

def score_market_structure(
    df_latest: pd.Series,
    ftse_upgrade_status: str = "pending",  # 'pending', 'confirmed', 'completed'
    months_to_next_rebalancing: int = None,
    adtv_change_pct: Optional[float] = None,   # % change ADTV QoQ
) -> Dict[str, Any]:
    """
    Score Market Structure & FTSE Upgrade pillar (weight 10%).

    Parameters
    ----------
    df_latest : Series chứa các features hiện tại, bao gồm etf_flow_q_zscore_live
    ftse_upgrade_status : 'pending', 'confirmed', 'completed'
    months_to_next_rebalancing : Months until next FTSE rebalancing (REQUIRED).
        Rebalancing schedule: March, June, September, December.
        Raises ValueError if not provided — prevents silent Q-specific assumptions.
    adtv_change_pct : % change in ADTV vs previous quarter (positive = good).
        If None, defaults to neutral score (50).
    """
    if months_to_next_rebalancing is None:
        raise ValueError(
            "months_to_next_rebalancing is required. "
            "Calculate from current date and FTSE rebalancing months [3,6,9,12]. "
            "Do NOT rely on hardcoded quarter-specific defaults."
        )

    scores = {}
    details = {}

    # ── FTSE Status Score ─────────────────────────────────────────────────────
    ftse_score_map = {
        "completed":  85,   # Completed → inflows active → very good
        "confirmed":  75,   # Confirmed → high expectations → good
        "pending":    55,   # Pending → uncertain → neutral
        "unknown":    50,
    }
    ftse_score = ftse_score_map.get(ftse_upgrade_status, 50)
    scores["ftse_status_score"] = ftse_score

    details["ftse_upgrade"] = (
        f"Status: {ftse_upgrade_status} → score {ftse_score}\n"
        f"  Est passive inflow: ${FTSE_PASSIVE_INFLOW_BASE_USD/1e9:.1f}B USD\n"
        f"  Effect: Sentiment premium VN30 +15-25% during rebalancing"
    )

    # ── Rebalancing Proximity Bonus ───────────────────────────────────────────
    if months_to_next_rebalancing <= 1:
        rebal_bonus = 20     # Within rebalancing month
    elif months_to_next_rebalancing <= 2:
        rebal_bonus = 12     # 2 months before
    elif months_to_next_rebalancing <= 3:
        rebal_bonus = 6      # 1 quarter before
    else:
        rebal_bonus = 0
    details["rebalancing"] = (
        f"{months_to_next_rebalancing} months to rebalancing → bonus +{rebal_bonus}"
    )

    # ── ADTV Improvement ─────────────────────────────────────────────────────
    if adtv_change_pct is not None and pd.notna(adtv_change_pct):
        adtv_score = _clamp_score(50 + adtv_change_pct * 100)
        scores["adtv_score"] = adtv_score
        details["adtv"] = f"ADTV change {adtv_change_pct:+.1%} QoQ → score {adtv_score:.0f}"
    else:
        adtv_score = 50.0   # Neutral when data unavailable
        details["adtv"] = "<MISSING> ADTV data unavailable → neutral score 50"
        
    # ── ETF Passive Flows ────────────────────────────────────────────────────
    etf_z = df_latest.get("etf_flow_q_zscore_live", np.nan)
    etf_q_sum = df_latest.get("etf_flow_q_ytd", np.nan)
    
    if pd.notna(etf_z):
        etf_score = _clamp_score(50 + etf_z * 15)
        scores["etf_flow_score"] = etf_score
        dir_str = "NET BUY" if etf_z > 0.5 else ("NET SELL" if etf_z < -0.5 else "Neutral")
        details["etf_flow"] = f"Z = {etf_z:.2f} ({dir_str}) → score {etf_score:.0f}"
        if pd.notna(etf_q_sum):
            details["etf_flow_q_ytd"] = f"{etf_q_sum:.2%} of Market Cap (YTD in Q)"
    else:
        etf_score = 50.0
        details["etf_flow"] = "<MISSING> Not enough data for Z-score (2021) → default 50"

    # Cập nhật công thức tính raw score có include etf_score (với tỷ trọng phù hợp)
    raw = _clamp_score(np.mean([ftse_score + rebal_bonus, adtv_score, etf_score]))

    rat_parts = [f"FTSE: {ftse_upgrade_status.upper()}"]
    if adtv_change_pct: rat_parts.append(f"ADTV: {adtv_change_pct:+.0%}")
    if pd.notna(etf_z): rat_parts.append(f"ETF-Z: {etf_z:.1f}σ")

    return {
        "group":          "market_structure",
        "raw_score":      round(raw, 2),
        "weight":         SCORING_WEIGHTS["market_structure"],
        "weighted_score": round(raw * SCORING_WEIGHTS["market_structure"], 2),
        "sub_scores":     scores,
        "details":        details,
        "rationale":      " | ".join(rat_parts)
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
    months_to_next_rebalancing: Optional[int] = None,
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

    # Get from parameter, fallback to calculating it if missing to prevent failure
    if months_to_next_rebalancing is None:
        # Lấy tháng và ngày thực tế từ dữ liệu cuối cùng thay vì datetime.now() để backtest chính xác
        try:
            current_month = df_latest["date"].month
            current_day = df_latest["date"].day
        except Exception:
            try:
                current_month = df_latest.name.month
                current_day = df_latest.name.day
            except Exception:
                now = datetime.now()
                current_month = now.month
                current_day = now.day

        rebal_months = [3, 6, 9, 12]
        months_to_next_rebalancing = min(((m - current_month) % 12) or 12 for m in rebal_months)
        
        if current_month in rebal_months:
            # Thông thường các đợt cơ cấu quỹ kết thúc vào thứ 6 tuần thứ 3 (quanh ngày 20).
            # Nếu chạy mô hình vào ngày cuối quý (VD: 31/03, 30/06, 30/09) thì đợt cơ cấu đã xong!
            # Đợt tiếp theo sẽ là 3 tháng nữa.
            if current_day > 25:
                months_to_next_rebalancing = 3
            else:
                months_to_next_rebalancing = 0
            
    g6 = score_market_structure(
        df_latest=df_latest,
        ftse_upgrade_status=ftse_upgrade_status,
        months_to_next_rebalancing=months_to_next_rebalancing,
        adtv_change_pct=adtv_change_pct
    )

    groups = [g1, g2, g3, g4, g5, g6]

    # ── Tổng điểm có trọng số ─────────────────────────────────────────────────
    total_weighted = sum(g["weighted_score"] for g in groups)
    total_raw_avg  = np.mean([g["raw_score"] for g in groups])

    # ── Phân loại (Single Source of Truth: get_score_label() từ config.py) ──────
    # KHÔNG hardcode ngưỡng ở đây — chỉ gọi get_score_label() duy nhất
    label, emoji, label_desc, label_alloc = get_score_label(total_weighted)

    # ── Most Divergent Pillar ──────────────────────────────────────────────────
    # NOTE: This is a simple heuristic — the pillar whose raw score deviates
    # most from neutral (50). This is NOT based on Granger causality or IRF.
    # Granger tests are used separately in the VAR model for variable ranking.
    group_raw = {g["group"]: g["raw_score"] for g in groups}
    most_divergent_pillar = max(group_raw, key=lambda k: abs(group_raw[k] - 50))

    # ── Pillar Dispersion (Fix #3) ────────────────────────────────────────────
    # Độ lệch chuẩn giữa 6 raw_score — đo lường "sự bất đồng" giữa các trụ cột
    raw_scores_arr = np.array([g["raw_score"] for g in groups])
    pillar_std   = float(np.std(raw_scores_arr, ddof=1))   # sample std
    pillar_range = float(np.max(raw_scores_arr) - np.min(raw_scores_arr))

    # ── Percentile Label (expanding window, Fix #2) ────────────────────────────
    # Đọc lịch sử hiện có để tính percentile expanding (không nhìn tương lai)
    history_path = SCORES_DIR / "quarterly_scores_history.parquet"
    _percentile_label = "HOLD"     # default trước khi đủ dữ liệu
    _dispersion_level = "MEDIUM"   # default
    _percentile_p15   = None
    _percentile_p85   = None
    if history_path.exists():
        _hist = pd.read_parquet(history_path)
        # Expanding: chỉ nhìn các quý TRƯỚC quý hiện tại
        _hist = _hist[_hist["quarter"] < quarter].sort_values("quarter")
        if len(_hist) >= 4:  # Cần ít nhất 4 điểm để percentile có ý nghĩa
            _scores_hist = _hist["total_score"].values
            _percentile_p15 = float(np.percentile(_scores_hist, 15))
            _percentile_p85 = float(np.percentile(_scores_hist, 85))
            if total_weighted >= _percentile_p85:
                _percentile_label = "BUY/ACCUMULATE"
            elif total_weighted <= _percentile_p15:
                _percentile_label = "REDUCE/SELL"
            else:
                _percentile_label = "HOLD"

            # Dispersion percentile (expanding window)
            if "pillar_std" in _hist.columns:
                _disp_hist = _hist["pillar_std"].dropna().values
                if len(_disp_hist) >= 4:
                    _disp_p33 = float(np.percentile(_disp_hist, 33))
                    _disp_p67 = float(np.percentile(_disp_hist, 67))
                    if pillar_std >= _disp_p67:
                        _dispersion_level = "HIGH"
                    elif pillar_std <= _disp_p33:
                        _dispersion_level = "LOW"
                    else:
                        _dispersion_level = "MEDIUM"

    # ── Lưu lịch sử ──────────────────────────────────────────────────────────
    score_record = {
        "quarter":               quarter,
        "date_computed":         datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_score":           round(total_weighted, 2),
        "label":                 label,
        "emoji":                 emoji,
        "label_description":     label_desc,
        "most_divergent_pillar": most_divergent_pillar,
        # Fix #2: Nhãn percentile động (expanding window)
        "percentile_label":      _percentile_label,
        "percentile_p15":        _percentile_p15,
        "percentile_p85":        _percentile_p85,
        # Fix #3: Độ phân tán giữa 6 pillar
        "pillar_std":            round(pillar_std, 2),
        "pillar_range":          round(pillar_range, 2),
        "dispersion_level":      _dispersion_level,
        # Allocation gợi ý từ SCORE_LABELS
        "label_allocation":      label_alloc,
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

    # Append vào lịch sử parquet (gồm cả cột percentile + dispersion mới)
    new_row = pd.DataFrame([{
        "quarter":          quarter,
        "date_computed":    score_record["date_computed"],
        "total_score":      total_weighted,
        "label":            label,
        "percentile_label": _percentile_label,
        "pillar_std":       round(pillar_std, 2),
        "pillar_range":     round(pillar_range, 2),
        "dispersion_level": _dispersion_level,
        **{f"score_{g['group']}": g["weighted_score"] for g in groups}
    }])
    if history_path.exists():
        existing = pd.read_parquet(history_path)
        existing = existing[existing["quarter"] != quarter]
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row

    combined = combined.sort_values("quarter").reset_index(drop=True)
    combined.to_parquet(history_path, index=False)

    logger.info(
        f"[SCORER] {quarter}: {emoji} {label} — {total_weighted:.1f}/100\n"
        f"  Most divergent pillar: {most_divergent_pillar} ({group_raw[most_divergent_pillar]:.1f})"
    )
    return score_record
