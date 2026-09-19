"""
global_features.py — Feature Engineering cho Biến số Toàn cầu & Dòng vốn Ngoại
=================================================================================
Biến số:
  1. DXY: pct_change, Z-score, regime
  2. US10Y: level, delta, term_premium proxy
  3. Net Foreign Flows: rolling, momentum, regime
  4. Correlation rolling: VNI vs DXY, VNI vs NFF

Lý luận kinh tế:
  - DXY ↑ → USD mạnh → vốn rút khỏi EM (Emerging Markets) → VNI ↓
  - US10Y ↑ → risk-free rate hấp dẫn hơn → phần bù rủi ro EM giảm tính hấp dẫn
  - NFF (Net Foreign Flow) mua ròng → hỗ trợ giá trực tiếp → VNI ↑
  - Correlation NFF-VNI thường +0.3 đến +0.6 trong giai đoạn 2018-2026
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from src.utils.config import FEATURES_DIR

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DXY Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_dxy_features(df_global: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ DXY (US Dollar Index).

    Biến tạo ra:
      - delta_dxy          : Δ DXY hàng ngày (pct_change)
      - dxy_zscore_60d     : Z-score 60 ngày
      - dxy_trend_regime   : strong_dollar / neutral / weak_dollar
      - dxy_momentum_20d   : Momentum DXY 20 ngày (proxy trend)
      - delta_dxy_lag1/5   : Lagged delta

    Ngưỡng phân loại (dựa trên phân phối lịch sử DXY 2018-2026):
      - DXY Z > +1.5 : Strong dollar → nguy hiểm cho EM
      - DXY Z < -1.5 : Weak dollar  → thuận lợi cho EM
    """
    df = df_global.copy()
    if "dxy_close" not in df.columns:
        logger.warning("[DXY] Không có cột dxy_close — bỏ qua")
        return df

    # Pct change
    df["delta_dxy"] = df["dxy_close"].pct_change()

    # Z-score 60 ngày
    roll_mean = df["dxy_close"].rolling(60, min_periods=20).mean()
    roll_std  = df["dxy_close"].rolling(60, min_periods=20).std()
    df["dxy_zscore_60d"] = ((df["dxy_close"] - roll_mean) /
                             roll_std.replace(0, np.nan))

    # Momentum 20 ngày
    df["dxy_momentum_20d"] = df["dxy_close"].pct_change(20)

    # Regime
    df["dxy_trend_regime"] = df["dxy_zscore_60d"].apply(
        lambda z: "strong_dollar" if (pd.notna(z) and z > 1.5)
                  else ("weak_dollar" if (pd.notna(z) and z < -1.5)
                        else "neutral")
    )

    # Lag features
    for lag in [1, 5, 10]:
        df[f"delta_dxy_lag{lag}"] = df["delta_dxy"].shift(lag)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. US10Y Yield Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_us10y_features(df_global: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ lợi suất TPCP Mỹ 10 năm (US10Y).

    Biến tạo ra:
      - delta_us10y        : Δ daily (bps)
      - us10y_level_regime : low (<2%), normal (2-4%), high (>4%)
      - us10y_30d_change   : Thay đổi 30 ngày (monthly momentum)
      - term_premium_proxy : US10Y - Fed Funds Rate proxy (nếu có)

    Lý luận kinh tế:
      - US10Y > 4.5% (mức 2023-2024): cost of capital toàn cầu ↑
      - US10Y ↑ → present value of future earnings ↓ → định giá EV bị nén
      - Tác động mạnh nhất lên VN30 (vốn hóa lớn, định giá DCF nhạy cảm)
    """
    df = df_global.copy()
    if "us10y_yield" not in df.columns:
        logger.warning("[US10Y] Không có cột us10y_yield — bỏ qua")
        return df

    df["delta_us10y"]      = df["us10y_yield"].diff()
    df["us10y_30d_change"] = df["us10y_yield"].diff(21)  # 21 ngày giao dịch

    # Level regime
    df["us10y_level_regime"] = df["us10y_yield"].apply(
        lambda y: "high" if y > 4.5 else ("normal" if y > 2.0 else "low")
        if pd.notna(y) else "unknown"
    )

    # Z-score 252 ngày (1 năm)
    roll_mean = df["us10y_yield"].rolling(252, min_periods=60).mean()
    roll_std  = df["us10y_yield"].rolling(252, min_periods=60).std()
    df["us10y_zscore_1y"] = ((df["us10y_yield"] - roll_mean) /
                              roll_std.replace(0, np.nan))

    # Lag features
    for lag in [1, 5, 10]:
        df[f"delta_us10y_lag{lag}"] = df["delta_us10y"].shift(lag)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Net Foreign Flow Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_foreign_flow_features(df_ff: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ dòng tiền khối ngoại (Net Foreign Flows).

    Biến tạo ra:
      - nff_rolling5d      : Rolling sum 5 ngày (tuần)
      - nff_rolling20d     : Rolling sum 20 ngày (tháng)
      - nff_zscore_60d     : Z-score 60 ngày
      - nff_trend_regime   : strong_buy / mild_buy / neutral / mild_sell / strong_sell
      - nff_momentum       : Momentum (nff_rolling5d - nff_rolling20d / std)
      - nff_consecutive_sell : Số ngày bán ròng liên tiếp (chuỗi)

    Lý luận kinh tế:
      - NFF rolling 5 ngày < -1,000 tỷ VND → tín hiệu xả mạnh
      - Consecutive sell > 10 ngày → áp lực kỹ thuật → VNI giảm điểm
      - Hệ số tương quan NFF vs VNI thường lag 0-2 ngày
    """
    df = df_ff.copy()
    if "net_foreign_flow_b_vnd" not in df.columns:
        logger.warning("[NFF] Không có cột net_foreign_flow_b_vnd — bỏ qua")
        return df

    col = "net_foreign_flow_b_vnd"
    df["nff_rolling5d"]  = df[col].rolling(5,  min_periods=2).sum()
    df["nff_rolling20d"] = df[col].rolling(20, min_periods=5).sum()
    df["nff_rolling60d"] = df[col].rolling(60, min_periods=20).sum()

    # Z-score
    roll_mean = df[col].rolling(60, min_periods=20).mean()
    roll_std  = df[col].rolling(60, min_periods=20).std()
    df["nff_zscore_60d"] = (df[col] - roll_mean) / roll_std.replace(0, np.nan)

    # Momentum: 5d vs 20d (tổng tuần vs tháng)
    df["nff_momentum"] = df["nff_rolling5d"] / (
        df["nff_rolling20d"].abs().replace(0, np.nan)
    )

    # Regime
    def _nff_regime(z: float) -> str:
        if pd.isna(z):
            return "unknown"
        if z >  2.0: return "strong_buy"
        if z >  0.5: return "mild_buy"
        if z < -2.0: return "strong_sell"
        if z < -0.5: return "mild_sell"
        return "neutral"

    df["nff_trend_regime"] = df["nff_zscore_60d"].apply(_nff_regime)

    # Consecutive sell streak (chuỗi bán ròng liên tiếp)
    sell_mask = (df[col] < 0).astype(int)
    streak = []
    count = 0
    for v in sell_mask:
        if v == 1:
            count += 1
        else:
            count = 0
        streak.append(count)
    df["nff_consecutive_sell_days"] = streak

    # Lag features
    for lag in [1, 2, 5]:
        df[f"nff_lag{lag}"] = df[col].shift(lag)

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Correlation Analysis: VNI vs Global Variables
# ═══════════════════════════════════════════════════════════════════════════════

def compute_rolling_correlations(
    df: pd.DataFrame,
    vni_col:    str = "log_return",
    global_cols: Optional[List[str]] = None,
    window: int = 60
) -> pd.DataFrame:
    """
    Tính tương quan rolling giữa VNI return và các biến toàn cầu.

    Đây là input quan trọng cho mô hình VAR — xác định structural relationship.

    Returns
    -------
    DataFrame: date + corr_{col}_{window}d columns
    """
    if global_cols is None:
        global_cols = ["delta_dxy", "delta_us10y", "net_foreign_flow_b_vnd"]

    result = df[["date"]].copy() if "date" in df.columns else df.index.to_frame()

    for col in global_cols:
        if col not in df.columns or vni_col not in df.columns:
            logger.warning(f"[CORR] Thiếu cột {col} hoặc {vni_col} — bỏ qua")
            continue
        corr_col = f"corr_{col}_{window}d"
        result[corr_col] = (
            df[vni_col]
            .rolling(window, min_periods=window // 2)
            .corr(df[col])
        )
        logger.debug(f"[CORR] Tính xong: {corr_col}")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Pipeline Tổng hợp Global Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_global_features(
    df_vni: pd.DataFrame,
    df_global: pd.DataFrame,
    df_ff: pd.DataFrame
) -> pd.DataFrame:
    """
    Pipeline đầy đủ: tổng hợp tất cả global intermarket features.

    Parameters
    ----------
    df_vni    : VNI OHLCV + returns (cột 'date', 'log_return')
    df_global : DXY + US10Y data
    df_ff     : Net Foreign Flows data

    Returns
    -------
    DataFrame: date + tất cả global columns
    """
    logger.info("[Global] Building global intermarket features...")
    result = df_vni[["date"]].copy()
    result["date"] = pd.to_datetime(result["date"])

    # 1. DXY features
    if not df_global.empty and "dxy_close" in df_global.columns:
        df_dxy = build_dxy_features(df_global)
        dxy_cols = [c for c in df_dxy.columns if c not in df_global.columns
                    or c == "date"] + [c for c in df_dxy.columns
                                       if c.startswith("delta_dxy") or "dxy" in c]
        dxy_cols = list(set(["date"] + [c for c in df_dxy.columns if c != "date"]))
        result = result.merge(df_dxy, on="date", how="left")

    # 2. US10Y features
    if not df_global.empty and "us10y_yield" in df_global.columns:
        df_us10y = build_us10y_features(df_global)
        us10y_cols = [c for c in df_us10y.columns
                      if "us10y" in c or "delta_us10y" in c]
        for col in us10y_cols:
            if col not in result.columns and col in df_us10y.columns:
                result = result.merge(
                    df_us10y[["date", col]], on="date", how="left"
                )

    # 3. Net Foreign Flow features
    if not df_ff.empty:
        df_nff = build_foreign_flow_features(df_ff)
        nff_cols = [c for c in df_nff.columns if c != "date"]
        result = result.merge(
            df_nff[["date"] + nff_cols], on="date", how="left"
        )

    # 4. Rolling correlations (cần VNI return)
    if "log_return" in df_vni.columns:
        merged_for_corr = result.merge(
            df_vni[["date", "log_return"]], on="date", how="left"
        )
        corr_df = compute_rolling_correlations(merged_for_corr, window=60)
        corr_cols = [c for c in corr_df.columns if c.startswith("corr_")]
        for col in corr_cols:
            if col in corr_df.columns:
                result[col] = corr_df[col].values

    # Lưu cache
    out_path = FEATURES_DIR / "global_features.parquet"
    result.to_parquet(out_path, index=False)
    logger.info(f"[Global] Đã lưu {len(result)} rows → {out_path}")
    return result
