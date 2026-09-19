"""
macro_features.py — Feature Engineering cho Nhóm Biến số Vĩ mô & Tiền tệ
==========================================================================
Biến số xây dựng:
  1. Δ Lãi suất OMO overnight (first-difference, lag 1-4 tuần)
  2. Δ Lãi suất huy động 12 tháng
  3. Δ Tỷ giá USD/VND (pct_change, lag)
  4. Độ trễ chính sách tiền tệ (monetary policy transmission lag: 1-3 tháng)
  5. M2 YoY growth, credit growth YoY
  6. Liquidity spread: credit_growth - m2_growth (credit/M2 ratio)
"""

import logging
from typing import List

import numpy as np
import pandas as pd

from src.utils.config import (
    MLR_LAG_PERIODS, FEATURES_DIR
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Lag Features — Tạo biến trễ (Lagged Variables)
# ═══════════════════════════════════════════════════════════════════════════════

def create_lag_features(
    df: pd.DataFrame,
    columns: List[str],
    lags: List[int] = MLR_LAG_PERIODS
) -> pd.DataFrame:
    """
    Tạo biến trễ (lag) cho danh sách các cột.

    Ý nghĩa kinh tế: Lãi suất không tác động tức thì lên thị trường —
    có độ trễ truyền dẫn (transmission lag) từ 1-12 tuần.

    Parameters
    ----------
    df      : DataFrame đầu vào
    columns : Danh sách tên cột cần tạo lag
    lags    : Danh sách số phiên lag (1-4 tuần = [5, 10, 15, 20] hoặc [1,2,3,4] tuần)

    Returns
    -------
    DataFrame bổ sung các cột: {col}_lag{n}
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            logger.warning(f"[LAG] Cột '{col}' không tồn tại — bỏ qua")
            continue
        for lag in lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def create_rolling_features(
    df: pd.DataFrame,
    columns: List[str],
    windows: List[int] = [5, 10, 20, 60]
) -> pd.DataFrame:
    """
    Tạo rolling mean và rolling std cho các cột.

    Dùng cho:
      - Rolling volatility của VNI (GARCH proxy)
      - Rolling mean lãi suất (xu hướng trung bình)

    Parameters
    ----------
    windows : [5=1tuần, 10=2tuần, 20=1tháng, 60=1quý]
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        for w in windows:
            df[f"{col}_rmean{w}"] = df[col].rolling(w, min_periods=w//2).mean()
            df[f"{col}_rstd{w}"]  = df[col].rolling(w, min_periods=w//2).std()
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Interest Rate Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_interest_rate_features(df_macro: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ lãi suất.

    Biến tạo ra:
      - delta_omo_rate      : Δ Lãi suất OMO (bps), first-difference
      - delta_deposit_12m   : Δ Lãi suất huy động 12T (bps)
      - ir_policy_shift     : Phân loại +1 (tăng), 0 (giữ), -1 (giảm)
      - rate_level_regime   : low (<5%), normal (5-7%), high (>7%)
      - delta_omo_lag5      : Lag 1 tuần (5 phiên)
      - delta_omo_lag10     : Lag 2 tuần
      - delta_omo_lag20     : Lag 1 tháng

    Lý luận kinh tế:
      - Khi SBV tăng OMO rate → chi phí vốn ngân hàng ↑ → tín dụng thu hẹp
        → margin call pressure ↑ → VNI downside pressure (β₁ < 0)
      - Độ trễ truyền dẫn: 4–8 tuần theo nghiên cứu Phạm Thế Anh (2014)
    """
    df = df_macro.copy()
    needed = ["omo_overnight_rate", "deposit_12m_rate"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        logger.warning(f"[IR] Thiếu cột: {missing} — bỏ qua interest rate features")
        return df

    # First difference (delta, tính bằng bps nếu cần)
    df["delta_omo_rate"]    = df["omo_overnight_rate"].diff()
    df["delta_deposit_12m"] = df["deposit_12m_rate"].diff()

    # Phân loại chính sách tiền tệ
    df["ir_policy_shift"] = df["delta_omo_rate"].apply(
        lambda x: 1 if x > 0.05 else (-1 if x < -0.05 else 0)
    )

    # Regime lãi suất
    df["rate_level_regime"] = df["omo_overnight_rate"].apply(
        lambda r: "low" if r < 5.0 else ("high" if r > 7.0 else "normal")
    )

    # Lag features
    df = create_lag_features(df, ["delta_omo_rate", "delta_deposit_12m"],
                             lags=[5, 10, 20])

    # Cumulative rate change 3 tháng (proxy monetary policy momentum)
    df["omo_rate_3m_cumchange"] = df["delta_omo_rate"].rolling(60, min_periods=20).sum()

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FX Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_fx_features(df_fx: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ tỷ giá USD/VND.

    Biến tạo ra:
      - usd_vnd_pct_change   : Pct thay đổi hàng ngày
      - usd_vnd_zscore       : Z-score 60 ngày (volatility adjusted)
      - fx_devaluation_flag  : 1 nếu VND mất giá > 0.5% trong 5 ngày
      - fx_pressure_regime   : stable / mild_pressure / severe_pressure

    Lý luận kinh tế:
      - VND mất giá → nhà đầu tư nước ngoài mất lợi nhuận thực → rút vốn
      - DXY tăng mạnh → áp lực tỷ giá toàn khu vực EM → VNI downside
      - Ngưỡng cảnh báo: SBV thường can thiệp khi USD/VND vượt biên ±3%
    """
    df = df_fx.copy()
    if "usd_vnd_close" not in df.columns:
        logger.warning("[FX] Không có cột usd_vnd_close — bỏ qua FX features")
        return df

    df["usd_vnd_pct_change"] = df["usd_vnd_close"].pct_change()

    # Z-score 60 ngày
    roll_mean = df["usd_vnd_close"].rolling(60, min_periods=20).mean()
    roll_std  = df["usd_vnd_close"].rolling(60, min_periods=20).std()
    df["usd_vnd_zscore"] = (df["usd_vnd_close"] - roll_mean) / roll_std.replace(0, np.nan)

    # Flag VND mất giá
    df["fx_5d_change"] = df["usd_vnd_close"].pct_change(5)
    df["fx_devaluation_flag"] = (df["fx_5d_change"] > 0.005).astype(int)

    # Regime
    df["fx_pressure_regime"] = df["usd_vnd_zscore"].apply(
        lambda z: "severe_pressure" if z > 2.0
                  else ("mild_pressure" if z > 1.0 else "stable")
        if pd.notna(z) else "unknown"
    )

    # Lag features
    df = create_lag_features(df, ["usd_vnd_pct_change", "usd_vnd_zscore"],
                             lags=[1, 5, 10])
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4. M2 & Credit Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_m2_credit_features(df_m2: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ M2 và tăng trưởng tín dụng.

    Biến tạo ra:
      - m2_acceleration     : Δ M2 YoY (tốc độ thay đổi của growth rate)
      - credit_m2_spread    : credit_growth - m2_growth (liquidity surplus)
      - liquidity_injection  : Phân loại {bơm mạnh, trung lập, hút vốn}

    Lý luận kinh tế:
      - M2 tăng → thanh khoản dư thừa → một phần vào TTCK → VNI up
      - credit_growth > m2_growth → credit/M2 ratio ↑ → leverage risk ↑
      - Độ trễ: tác động M2 lên VNI thường 2-3 tháng (nghiên cứu IMF 2019)
    """
    df = df_m2.copy()
    if df_m2.empty or "m2_yoy_pct" not in df_m2.columns:
        logger.warning("[M2] DataFrame rỗng hoặc thiếu cột — bỏ qua")
        return df

    # Acceleration (Δ growth rate)
    df["m2_acceleration"]    = df["m2_yoy_pct"].diff()
    df["credit_m2_spread"]   = df["credit_growth_yoy_pct"] - df["m2_yoy_pct"]

    # Regime thanh khoản
    df["liquidity_injection"] = df["m2_yoy_pct"].apply(
        lambda m: "strong_inject" if m > 15.0
                  else ("moderate_inject" if m > 10.0
                        else ("tight" if m < 5.0 else "neutral"))
    )

    # Lag 1, 2, 3 tháng
    df = create_lag_features(df, ["m2_yoy_pct", "credit_growth_yoy_pct",
                                  "credit_m2_spread"], lags=[1, 2, 3])
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Vietnam Bonds Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_vietnam_bond_features(df_bonds: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ lợi suất trái phiếu chính phủ Việt Nam.

    Biến tạo ra:
      - vn_yield_spread : Độ dốc đường cong lợi suất (10Y - 2Y)
      - vn10y_zscore    : Z-score 60 ngày của VN10Y
    """
    df = df_bonds.copy()
    if df.empty or "vn10y_yield" not in df.columns or "vn2y_yield" not in df.columns:
        logger.warning("[BONDS] DataFrame rỗng hoặc thiếu cột — bỏ qua")
        return df

    # Độ dốc đường cong lợi suất
    df["vn_yield_spread"] = df["vn10y_yield"] - df["vn2y_yield"]

    # Z-score 60 ngày cho VN10Y (đo lường sự bất thường)
    roll_mean = df["vn10y_yield"].rolling(60, min_periods=20).mean()
    roll_std  = df["vn10y_yield"].rolling(60, min_periods=20).std()
    df["vn10y_zscore"] = (df["vn10y_yield"] - roll_mean) / roll_std.replace(0, np.nan)

    # Lag features
    df = create_lag_features(df, ["vn10y_yield", "vn_yield_spread", "vn10y_zscore"],
                             lags=[5, 10, 20])
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Pipeline Tổng hợp Macro Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_macro_features(
    df_vni_dates: pd.DataFrame,
    df_macro_sbv: pd.DataFrame,
    df_fx: pd.DataFrame,
    df_m2: pd.DataFrame,
    df_bonds: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Pipeline đầy đủ: merge tất cả macro features theo ngày giao dịch VNI.

    Parameters
    ----------
    df_vni_dates : DataFrame với cột 'date' (ngày giao dịch)
    df_macro_sbv : DataFrame từ fetch_macro_sbv_manual()
    df_fx        : DataFrame từ fetch_usdvnd_proxy()
    df_m2        : DataFrame từ fetch_m2_credit_manual()

    Returns
    -------
    DataFrame: date + tất cả macro columns (forward-filled cho monthly data)
    """
    logger.info("[Macro] Building macro features...")
    result = df_vni_dates[["date"]].copy()
    result["date"] = pd.to_datetime(result["date"])

    # 1. Interest Rate features
    if not df_macro_sbv.empty:
        df_ir = build_interest_rate_features(df_macro_sbv)
        result = result.merge(df_ir, on="date", how="left")

    # 2. FX features
    if not df_fx.empty:
        df_fx_feat = build_fx_features(df_fx)
        fx_cols = [c for c in df_fx_feat.columns if c != "date"]
        result = result.merge(df_fx_feat[["date"] + fx_cols], on="date", how="left")

    # 3. M2 & Credit features (monthly → forward fill)
    if not df_m2.empty:
        df_m2_feat = build_m2_credit_features(df_m2)
        m2_cols = [c for c in df_m2_feat.columns if c != "date"]
        result = result.merge(df_m2_feat[["date"] + m2_cols], on="date", how="left")
        # Forward fill monthly data xuống daily
        for col in m2_cols:
            if col in result.columns:
                result[col] = result[col].ffill()

    # 4. Vietnam Bonds features
    if df_bonds is not None and not df_bonds.empty:
        df_bonds_feat = build_vietnam_bond_features(df_bonds)
        bond_cols = [c for c in df_bonds_feat.columns if c != "date"]
        result = result.merge(df_bonds_feat[["date"] + bond_cols], on="date", how="left")
        # Forward fill in case bond data is slightly delayed
        for col in bond_cols:
            if col in result.columns:
                result[col] = result[col].ffill()

    # Lưu cache
    out_path = FEATURES_DIR / "macro_features.parquet"
    result.to_parquet(out_path, index=False)
    logger.info(f"[Macro] Đã lưu {len(result)} rows, {len(result.columns)} cols → {out_path}")
    return result
