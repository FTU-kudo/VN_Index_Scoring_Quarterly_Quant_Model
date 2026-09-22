"""
valuation_features.py — Z-score P/E, P/B và phân tích định giá VN-Index
=========================================================================
Phương pháp:
  1. Tính P/E và P/B tổng hợp của VN-Index (market-cap weighted aggregate)
  2. Tính Z-score rolling 5 năm: Z = (X - μ_5Y) / σ_5Y
  3. Phân loại vùng định giá (rẻ / hợp lý / đắt)
  4. Tính margin call risk score dựa trên mức giảm VNI và dư nợ margin

Nguồn dữ liệu:
  - VN_PE_PB_analysis (dự án đã có): sector_history.parquet, ticker_history.parquet
  - Hoặc tính lại từ vnstock Finance.ratio()
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import (
    ZSCORE_WINDOW_YEARS,
    PE_ZSCORE_OVERBOUGHT, PE_ZSCORE_OVERSOLD,
    PB_ZSCORE_OVERBOUGHT, PB_ZSCORE_OVERSOLD,
    MARGIN_CALL_DROP_PCT, MARGIN_CALL_SEVERE_PCT,
    PROCESSED_DIR, FEATURES_DIR
)

logger = logging.getLogger(__name__)

# ── Tham chiếu sang dự án VN_PE_PB_analysis nếu có ──────────────────────────
_PEPB_PROJECT_PATH = Path(__file__).resolve().parents[3].parent / \
                     "VN_PE_PB_analysis" / "data"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Load P/E, P/B lịch sử
# ═══════════════════════════════════════════════════════════════════════════════

def load_market_pepb_history() -> pd.DataFrame:
    """
    Load lịch sử P/E, P/B từ dự án VN_PE_PB_analysis (ticker_history.parquet)
    hoặc từ GitHub.
    Tính toán Headline P/E (Trọng số vốn hóa) và Median P/E.
    
    Returns
    -------
    DataFrame: date, median_pe, median_pb, headline_pe, headline_pb
    """
    # Ưu tiên dùng dữ liệu từ dự án PE/PB đã xây dựng
    external_path = _PEPB_PROJECT_PATH / "ticker_history.parquet"
    local_path    = PROCESSED_DIR / "ticker_history.parquet"
    github_raw_url = "https://raw.githubusercontent.com/FTU-kudo/PE_PB_HOSE_stocks/main/data/ticker_history.parquet"

    if external_path.exists():
        df = pd.read_parquet(external_path)
        logger.info(f"[PE/PB] Load từ VN_PE_PB_analysis: {len(df)} rows")
    elif local_path.exists():
        df = pd.read_parquet(local_path)
        logger.info(f"[PE/PB] Load từ cache local: {len(df)} rows")
    else:
        try:
            logger.info(f"[PE/PB] Fetching remote data từ FTU-kudo/PE_PB_HOSE_stocks (ticker_history)...")
            df = pd.read_parquet(github_raw_url)
            logger.info(f"[PE/PB] Tải thành công từ GitHub: {len(df)} rows")
            # Cache locally to speed up future runs
            df.to_parquet(local_path, index=False)
        except Exception as e:
            logger.warning(
                f"[PE/PB] Không tìm thấy dữ liệu cục bộ và tải từ GitHub thất bại ({e}).\n"
                "Trả về DataFrame trống."
            )
            return pd.DataFrame(columns=["date", "median_pe", "median_pb", "headline_pe", "headline_pb"])

    # Chuẩn hóa
    df["date"] = pd.to_datetime(df["date"])
    
    # Tính Market Cap và Earnings, Book Value
    # Giả sử file có: date, ticker, close, shares, pe, pb
    if "shares" in df.columns and "pe" in df.columns and "pb" in df.columns:
        df["market_cap"] = df["close"] * df["shares"]
        # earnings = market_cap / pe
        df["earnings"] = np.where(df["pe"] > 0, df["market_cap"] / df["pe"], np.nan)
        # book_value = market_cap / pb
        df["book_value"] = np.where(df["pb"] > 0, df["market_cap"] / df["pb"], np.nan)
        
        # Nhóm theo ngày để tính Headline (Trọng số vốn hóa)
        headline_df = df.groupby("date").agg(
            total_mc=("market_cap", "sum"),
            total_ern=("earnings", "sum"),
            total_bv=("book_value", "sum")
        ).reset_index()
        
        headline_df["headline_pe"] = np.where(headline_df["total_ern"] > 0, headline_df["total_mc"] / headline_df["total_ern"], np.nan)
        headline_df["headline_pb"] = np.where(headline_df["total_bv"] > 0, headline_df["total_mc"] / headline_df["total_bv"], np.nan)
        
        # Nhóm theo ngày để tính Median (Loại trừ nhiễu)
        # Lọc các P/E, P/B hợp lý (pe > 0)
        df_valid_pe = df[df["pe"] > 0]
        median_pe_df = df_valid_pe.groupby("date")["pe"].median().reset_index().rename(columns={"pe": "median_pe"})
        
        df_valid_pb = df[df["pb"] > 0]
        median_pb_df = df_valid_pb.groupby("date")["pb"].median().reset_index().rename(columns={"pb": "median_pb"})
        
        # Ex-Vingroup
        df_ex_vingroup = df[~df["ticker"].isin(["VIC", "VHM", "VRE"])]
        ex_vg_df = df_ex_vingroup.groupby("date").agg(
            total_mc=("market_cap", "sum"),
            total_ern=("earnings", "sum"),
            total_bv=("book_value", "sum")
        ).reset_index()
        ex_vg_df["ex_vingroup_pe"] = np.where(ex_vg_df["total_ern"] > 0, ex_vg_df["total_mc"] / ex_vg_df["total_ern"], np.nan)
        ex_vg_df["ex_vingroup_pb"] = np.where(ex_vg_df["total_bv"] > 0, ex_vg_df["total_mc"] / ex_vg_df["total_bv"], np.nan)

        # Gộp lại
        market_df = headline_df[["date", "headline_pe", "headline_pb"]].merge(median_pe_df, on="date", how="left")
        market_df = market_df.merge(median_pb_df, on="date", how="left")
        market_df = market_df.merge(ex_vg_df[["date", "ex_vingroup_pe", "ex_vingroup_pb"]], on="date", how="left")
    else:
        logger.warning("[PE/PB] Schema không khớp — thiếu shares/pe/pb")
        return pd.DataFrame(columns=["date", "median_pe", "median_pb", "headline_pe", "headline_pb", "ex_vingroup_pe", "ex_vingroup_pb"])

    if market_df.duplicated("date").any():
        logger.error("[PE/PB] Data Leakage detected: Multiple rows for the same date after merge. Check grouping logic.")
        raise ValueError("Data Leakage: Duplicate dates in market_df")

    return market_df.sort_values("date").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Tính Z-score Rolling 5 năm
# ═══════════════════════════════════════════════════════════════════════════════

def compute_zscore_rolling(
    series: pd.Series,
    window_years: int = ZSCORE_WINDOW_YEARS,
    trading_days_per_year: int = 252
) -> pd.Series:
    """
    Tính Z-score rolling với cửa sổ n năm.

    Z_t = (X_t - μ_{t-window:t}) / σ_{t-window:t}

    Điều kiện:
      - Yêu cầu tối thiểu window / 2 quan sát để tính (min_periods)
      - Trả về NaN nếu σ = 0

    Parameters
    ----------
    series        : chuỗi thời gian cần tính Z-score
    window_years  : số năm cửa sổ rolling (mặc định 5 năm)
    trading_days_per_year : số phiên giao dịch mỗi năm

    Returns
    -------
    pd.Series Z-score
    """
    window = window_years * trading_days_per_year
    min_p  = window // 2   # Tối thiểu 2.5 năm dữ liệu

    roll_mean = series.rolling(window=window, min_periods=min_p).mean()
    roll_std  = series.rolling(window=window, min_periods=min_p).std()

    # Tránh chia cho 0
    zscore = (series - roll_mean) / roll_std.replace(0, np.nan)
    return zscore


def compute_pe_pb_features(df_pepb: pd.DataFrame, df_macro: pd.DataFrame = None) -> pd.DataFrame:
    """
    Tính Z-score cho P/E và P/B, và phân loại vùng định giá.

    Parameters
    ----------
    df_pepb : DataFrame với cột 'date', 'median_pe', 'median_pb'
    df_macro: DataFrame vĩ mô để lấy vn10y_yield tính EYG

    Returns
    -------
    DataFrame bổ sung:
      - pe_zscore, pb_zscore
      - pe_valuation_zone : {cheap, fair, expensive}
      - pb_valuation_zone : {cheap, fair, expensive}
      - eyg : Earnings Yield Gap
      - eyg_zscore : Z-score của EYG
      - valuation_composite_score (0–100, 100 = rẻ nhất)
    """
    if df_pepb.empty or "median_pe" not in df_pepb.columns:
        logger.warning("[PE/PB] DataFrame rỗng — bỏ qua tính Z-score")
        return df_pepb

    df = df_pepb.copy().sort_values("date").reset_index(drop=True)

    # Z-score rolling (Use Ex-Vingroup if available, else fallback to Median)
    primary_pe = "ex_vingroup_pe" if "ex_vingroup_pe" in df.columns else "median_pe"
    primary_pb = "ex_vingroup_pb" if "ex_vingroup_pb" in df.columns else "median_pb"
    
    df["pe_zscore"] = compute_zscore_rolling(df[primary_pe])
    df["pb_zscore"] = compute_zscore_rolling(df[primary_pb])

    # Phân loại vùng định giá P/E
    def _zone(z: float, ob_thresh: float, os_thresh: float) -> str:
        if pd.isna(z):
            return "unknown"
        if z > ob_thresh:
            return "expensive"   # đắt (overbought về định giá)
        elif z < os_thresh:
            return "cheap"       # rẻ (oversold về định giá)
        else:
            return "fair"

    df["pe_valuation_zone"] = df["pe_zscore"].apply(
        lambda z: _zone(z, PE_ZSCORE_OVERBOUGHT, PE_ZSCORE_OVERSOLD)
    )
    df["pb_valuation_zone"] = df["pb_zscore"].apply(
        lambda z: _zone(z, PB_ZSCORE_OVERBOUGHT, PB_ZSCORE_OVERSOLD)
    )

    # Tính Earnings Yield Gap (EYG) nếu có VN10Y
    if df_macro is not None and "vn10y_yield" in df_macro.columns:
        df = df.merge(df_macro[["date", "vn10y_yield"]], on="date", how="left")
        df["vn10y_yield"] = df["vn10y_yield"].ffill()
        # EYG = (1/PE)*100 - VN10Y
        df["eyg"] = (1 / df[primary_pe]) * 100 - df["vn10y_yield"]
        df["eyg_zscore"] = compute_zscore_rolling(df["eyg"])
    else:
        df["eyg"] = np.nan
        df["eyg_zscore"] = np.nan

    # Composite valuation score (0–100): -Z → score cao = rẻ cho PE/PB, +Z → rẻ cho EYG
    df["pe_score_raw"] = -df["pe_zscore"]
    df["pb_score_raw"] = -df["pb_zscore"]
    df["eyg_score_raw"] = df["eyg_zscore"]
    
    pe_rank = df["pe_score_raw"].rank(pct=True)
    pb_rank = df["pb_score_raw"].rank(pct=True)
    eyg_rank = df["eyg_score_raw"].rank(pct=True)

    if df["eyg_zscore"].notna().any():
        df["valuation_composite_score"] = (pe_rank * 0.4 + pb_rank * 0.3 + eyg_rank * 0.3) * 100
    else:
        df["valuation_composite_score"] = (pe_rank * 0.6 + pb_rank * 0.4) * 100

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Margin Debt Risk Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def compute_margin_risk_score(
    df_vni: pd.DataFrame,
    df_margin: pd.DataFrame
) -> pd.DataFrame:
    """
    Tính margin risk score dựa trên:
      1. Tỷ lệ margin/market_cap (đòn bẩy toàn thị trường)
      2. Xác suất margin call dựa trên biến động VNI

    Phương pháp:
      - Margin call trigger: VNI giảm > MARGIN_CALL_DROP_PCT (-12%)
        kể từ đỉnh gần nhất (rolling 60 ngày)
      - Score 0–100: 0 = rủi ro thấp, 100 = rủi ro cực cao

    Parameters
    ----------
    df_vni    : DataFrame VNI với 'date', 'close'
    df_margin : DataFrame margin với 'date', 'margin_debt_b_vnd'

    Returns
    -------
    DataFrame: date, margin_debt_b_vnd, drawdown_from_peak,
               margin_call_risk_flag, margin_risk_score
    """
    df = df_vni[["date", "close"]].copy().sort_values("date")

    # Rolling peak (60 ngày) và drawdown
    df["rolling_peak_60"] = df["close"].rolling(60, min_periods=20).max()
    df["drawdown_from_peak"] = (df["close"] / df["rolling_peak_60"] - 1)

    # Flag margin call risk
    df["margin_call_risk_flag"] = df["drawdown_from_peak"].apply(
        lambda x: "severe" if x <= MARGIN_CALL_SEVERE_PCT
                  else ("warning" if x <= MARGIN_CALL_DROP_PCT else "normal")
    )

    # Merge với margin debt (monthly → forward fill)
    if not df_margin.empty and "margin_debt_b_vnd" in df_margin.columns:
        df_margin = df_margin.copy()
        df_margin["date"] = pd.to_datetime(df_margin["date"])
        df = df.merge(df_margin[["date", "margin_debt_b_vnd"]],
                      on="date", how="left")
        df["margin_debt_b_vnd"] = df["margin_debt_b_vnd"].ffill()
    else:
        df["margin_debt_b_vnd"] = np.nan

    # Tính margin risk score (0–100)
    # Drawdown component: 0% = score 0, -18% = score 80
    drawdown_score = df["drawdown_from_peak"].clip(
        MARGIN_CALL_SEVERE_PCT, 0
    ).apply(lambda x: min(80, abs(x / abs(MARGIN_CALL_SEVERE_PCT)) * 80))

    # Điều chỉnh với tốc độ tăng margin debt (nếu có)
    if "margin_debt_b_vnd" in df.columns and df["margin_debt_b_vnd"].notna().any():
        margin_growth = df["margin_debt_b_vnd"].pct_change(3).fillna(0)
        margin_component = margin_growth.clip(0, 0.3).apply(
            lambda x: x / 0.3 * 20  # Tăng 30% trong 3 tháng = +20 điểm risk
        )
        df["margin_risk_score"] = (drawdown_score + margin_component).clip(0, 100)
    else:
        df["margin_risk_score"] = drawdown_score

    return df.reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Pipeline tổng hợp Valuation & Leverage Features
# ═══════════════════════════════════════════════════════════════════════════════

def build_valuation_leverage_features(
    df_vni: pd.DataFrame,
    df_margin: pd.DataFrame,
    df_macro: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Pipeline đầy đủ: tổng hợp tất cả valuation và leverage features.

    Returns
    -------
    DataFrame: date + tất cả valuation & leverage columns
    """
    logger.info("[ValLev] Building valuation & leverage features...")

    # 1. P/E, P/B Z-score và EYG
    df_pepb = load_market_pepb_history()
    if not df_pepb.empty:
        df_pepb = compute_pe_pb_features(df_pepb, df_macro)
    else:
        # Tạo empty frame để pipeline không bị lỗi
        df_pepb = pd.DataFrame({
            "date": df_vni["date"],
            "median_pe": np.nan, "median_pb": np.nan,
            "headline_pe": np.nan, "headline_pb": np.nan,
            "ex_vingroup_pe": np.nan, "ex_vingroup_pb": np.nan,
            "pe_zscore": np.nan, "pb_zscore": np.nan,
            "pe_valuation_zone": "unknown",
            "pb_valuation_zone": "unknown",
            "eyg": np.nan, "eyg_zscore": np.nan,
            "valuation_composite_score": 50.0
        })

    # 2. Margin risk score
    df_margin_risk = compute_margin_risk_score(df_vni, df_margin)

    # 3. Merge
    df_vl = df_vni[["date"]].copy()
    
    cols_to_merge = [
        "date", "median_pe", "median_pb", "headline_pe", "headline_pb", 
        "ex_vingroup_pe", "ex_vingroup_pb", "pe_zscore", "pb_zscore",
        "pe_valuation_zone", "pb_valuation_zone", 
        "eyg", "eyg_zscore", "valuation_composite_score"
    ]
    # Filter only columns that actually exist in df_pepb to avoid KeyError
    cols_to_merge = [c for c in cols_to_merge if c in df_pepb.columns]
    
    df_vl = df_vl.merge(
        df_pepb[cols_to_merge],
        on="date", how="left"
    )
    df_vl = df_vl.merge(
        df_margin_risk[["date", "margin_debt_b_vnd", "drawdown_from_peak",
                         "margin_call_risk_flag", "margin_risk_score"]],
        on="date", how="left"
    )
    if "margin_debt_b_vnd" in df_vl.columns:
        df_vl["delta_margin_debt_pct"] = df_vl["margin_debt_b_vnd"].pct_change(fill_method=None)
        df_vl["delta_margin_debt"] = df_vl["delta_margin_debt_pct"]

    # Lưu features
    out_path = FEATURES_DIR / "valuation_leverage_features.parquet"
    df_vl.to_parquet(out_path, index=False)
    logger.info(f"[ValLev] Đã lưu {len(df_vl)} rows → {out_path}")

    return df_vl
