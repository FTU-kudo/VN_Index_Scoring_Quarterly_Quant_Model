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
from src.features.valuation_features import load_market_pepb_history

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
# 2.5. USD/JPY Features (Yen Carry Trade proxy)
# ═══════════════════════════════════════════════════════════════════════════════

def build_jpy_features(df_global: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo features từ USD/JPY để đánh giá rủi ro Yen Carry Trade unwinding.

    Biến tạo ra:
      - delta_usdjpy      : Δ USD/JPY hàng ngày (pct_change)
      - usdjpy_zscore_60d : Z-score 60 ngày để phát hiện Yen mạnh lên bất thường.
      - jpy_carry_risk    : high / low (Yen mạnh lên tức USD/JPY giảm sâu).
    """
    df = df_global.copy()
    if "usdjpy_close" not in df.columns:
        logger.warning("[JPY] Không có cột usdjpy_close — bỏ qua")
        return df

    # Pct change
    df["delta_usdjpy"] = df["usdjpy_close"].pct_change()

    # Z-score 60 ngày
    roll_mean = df["usdjpy_close"].rolling(60, min_periods=20).mean()
    roll_std  = df["usdjpy_close"].rolling(60, min_periods=20).std()
    df["usdjpy_zscore_60d"] = ((df["usdjpy_close"] - roll_mean) /
                                roll_std.replace(0, np.nan))

    # Regime (Yen mạnh lên tương đương USD/JPY giảm mạnh)
    df["jpy_carry_risk"] = df["usdjpy_zscore_60d"].apply(
        lambda z: "high_risk" if (pd.notna(z) and z < -1.5)
                  else "neutral"
    )

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Net Foreign Flow Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_foreign_flow_features(df_ff: pd.DataFrame, df_pepb: pd.DataFrame = None) -> pd.DataFrame:
    """
    Tạo features từ dòng tiền khối ngoại (NFF ex ETF) và ETF Flows.
    Biến tạo ra:
      - nff_ex_etf_pct, etf_flow_pct (chuẩn hóa theo Market Cap)
      - Các rolling sum (5d, 20d) cho ML
      - nff_ex_etf_q_sum, etf_flow_q_sum (tổng lũy kế theo quý)
      - nff_ex_etf_q_zscore, etf_flow_q_zscore (expanding z-score theo quý)
    """
    df = df_ff.copy()
    if "nff_ex_etf_vnd" not in df.columns or "etf_flow_vnd" not in df.columns:
        logger.warning("[NFF] Thiếu cột nff_ex_etf_vnd hoặc etf_flow_vnd — bỏ qua")
        return df

    # Normalize theo market cap
    if df_pepb is not None and "total_mc" in df_pepb.columns:
        df = df.merge(df_pepb[["date", "total_mc"]], on="date", how="left")
        df["total_mc"] = df["total_mc"].ffill()
    else:
        df["total_mc"] = 1.0 # fallback

    # Tính theo % market cap (VD: % vốn hóa HOSE)
    df["nff_ex_etf_pct"] = df["nff_ex_etf_vnd"] / df["total_mc"]
    df["etf_flow_pct"] = df["etf_flow_vnd"] / df["total_mc"]

    # ── Daily Rolling Features (cho ML) ──
    for col in ["nff_ex_etf_pct", "etf_flow_pct"]:
        prefix = col.replace("_pct", "")
        df[f"{prefix}_rolling5d"]  = df[col].rolling(5, min_periods=2).sum()
        df[f"{prefix}_rolling20d"] = df[col].rolling(20, min_periods=5).sum()
        df[f"{prefix}_rolling60d"] = df[col].rolling(60, min_periods=20).sum()
        
        # Streak cho NFF
        if prefix == "nff_ex_etf":
            sell_mask = (df[col] < 0).astype(int)
            streak = []
            count = 0
            for v in sell_mask:
                if v == 1: count += 1
                else: count = 0
                streak.append(count)
            df[f"{prefix}_consecutive_sell_days"] = streak

        # Lags
        for lag in [1, 2, 5]:
            df[f"{prefix}_lag{lag}"] = df[col].shift(lag)

    # ── Quarterly Resampling & Expanding Z-score ──
    df_q = df.set_index("date").resample("Q")[["nff_ex_etf_pct", "etf_flow_pct"]].sum().reset_index()
    df_q = df_q.rename(columns={
        "nff_ex_etf_pct": "nff_ex_etf_q_sum",
        "etf_flow_pct": "etf_flow_q_sum"
    })
    
    # Expanding Z-score (min_periods = 4 quarters ~ 1 năm)
    df_q["nff_ex_etf_q_zscore"] = (df_q["nff_ex_etf_q_sum"] - df_q["nff_ex_etf_q_sum"].expanding(min_periods=4).mean()) / df_q["nff_ex_etf_q_sum"].expanding(min_periods=4).std()
    df_q["etf_flow_q_zscore"] = (df_q["etf_flow_q_sum"] - df_q["etf_flow_q_sum"].expanding(min_periods=4).mean()) / df_q["etf_flow_q_sum"].expanding(min_periods=4).std()

    # Tạo cột Year-Quarter để merge back về daily
    df["YQ"] = df["date"].dt.to_period("Q")
    df_q["YQ"] = df_q["date"].dt.to_period("Q")
    
    # Merge lại với daily df
    df = df.merge(df_q[["YQ", "nff_ex_etf_q_sum", "etf_flow_q_sum", "nff_ex_etf_q_zscore", "etf_flow_q_zscore"]], on="YQ", how="left")
    
    # Vì mỗi ngày trong quý đang được gán bằng TỔNG của CẢ QUÝ (look-ahead) nếu dùng giá trị cuối quý.
    # ĐỂ KHÔNG LOOK-AHEAD TRONG KHI CHẠY MODEL HÀNG NGÀY TRONG QUÝ, 
    # Ta phải tính YTD-Quarter sum cho mỗi ngày, nhưng vì logic yêu cầu z-score dựa trên lịch sử các quý trước.
    # Đúng chuẩn: Z-score của quý hiện tại phải lấy expanding mean/std của (các quý trước).
    
    # Ở đây, ta tính YTD sum trong quý hiện tại cho mỗi dòng:
    df["q_group"] = df["date"].dt.to_period("Q")
    df["nff_ex_etf_q_ytd"] = df.groupby("q_group")["nff_ex_etf_pct"].cumsum()
    df["etf_flow_q_ytd"] = df.groupby("q_group")["etf_flow_pct"].cumsum()
    
    # Lấy expanding mean/std từ các quý ĐÃ KẾT THÚC (shift 1 của df_q)
    df_q["prev_q_mean_nff"] = df_q["nff_ex_etf_q_sum"].expanding(min_periods=4).mean().shift(1)
    df_q["prev_q_std_nff"] = df_q["nff_ex_etf_q_sum"].expanding(min_periods=4).std().shift(1)
    df_q["prev_q_mean_etf"] = df_q["etf_flow_q_sum"].expanding(min_periods=4).mean().shift(1)
    df_q["prev_q_std_etf"] = df_q["etf_flow_q_sum"].expanding(min_periods=4).std().shift(1)
    
    df = df.merge(df_q[["YQ", "prev_q_mean_nff", "prev_q_std_nff", "prev_q_mean_etf", "prev_q_std_etf"]], on="YQ", how="left")
    
    # Tính Live Z-score cho ngày hiện tại trong quý (YTD sum so với mean/std các quý trước)
    df["nff_ex_etf_q_zscore_live"] = (df["nff_ex_etf_q_ytd"] - df["prev_q_mean_nff"]) / df["prev_q_std_nff"]
    df["etf_flow_q_zscore_live"] = (df["etf_flow_q_ytd"] - df["prev_q_mean_etf"]) / df["prev_q_std_etf"]
    
    # Dọn dẹp
    df = df.drop(columns=["YQ", "q_group", "prev_q_mean_nff", "prev_q_std_nff", "prev_q_mean_etf", "prev_q_std_etf"])

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

    # 2.5 JPY features
    if not df_global.empty and "usdjpy_close" in df_global.columns:
        df_jpy = build_jpy_features(df_global)
        jpy_cols = [c for c in df_jpy.columns
                      if "jpy" in c or "delta_usdjpy" in c]
        for col in jpy_cols:
            if col not in result.columns and col in df_jpy.columns:
                result = result.merge(
                    df_jpy[["date", col]], on="date", how="left"
                )

    # 3. Net Foreign Flow features
    if not df_ff.empty:
        # Load market cap history to normalize foreign flows
        try:
            df_pepb = load_market_pepb_history()
        except Exception as e:
            logger.warning(f"[Global] Không load được market pepb history: {e}")
            df_pepb = None
            
        df_nff = build_foreign_flow_features(df_ff, df_pepb)
        nff_cols = [c for c in df_nff.columns if c != "date"]
        result = result.merge(
            df_nff[["date"] + nff_cols], on="date", how="left"
        )

    # 4. Rolling correlations (cần VNI return)
    if "log_return" in df_vni.columns:
        merged_for_corr = result.merge(
            df_vni[["date", "log_return"]], on="date", how="left"
        )
        
        # Use nff_ex_etf_pct for correlation instead of the old net_foreign_flow_b_vnd
        global_cols_for_corr = ["delta_dxy", "delta_us10y"]
        if "nff_ex_etf_pct" in result.columns:
            global_cols_for_corr.append("nff_ex_etf_pct")
            
        corr_df = compute_rolling_correlations(merged_for_corr, global_cols=global_cols_for_corr, window=60)
        corr_cols = [c for c in corr_df.columns if c.startswith("corr_")]
        for col in corr_cols:
            if col in corr_df.columns:
                result[col] = corr_df[col].values

    # Lưu cache
    out_path = FEATURES_DIR / "global_features.parquet"
    result.to_parquet(out_path, index=False)
    logger.info(f"[Global] Đã lưu {len(result)} rows → {out_path}")
    return result
