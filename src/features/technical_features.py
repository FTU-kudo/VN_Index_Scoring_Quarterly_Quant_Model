"""
technical_features.py — Chỉ báo kỹ thuật thuần pandas/numpy từ OHLCV VN-Index.
Dùng cho MLR fallback và ML khi P/E, margin, NFF lịch sử bị thiếu.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def add_technical_indicators(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """Bổ sung RSI, MACD, BB, realized vol, drawdown nếu chưa có."""
    if price_col not in df.columns:
        logger.warning("[TA] Thiếu cột %s — bỏ qua technical indicators", price_col)
        return df

    out = df.copy()
    close = out[price_col].astype(float)

    if "rsi_14" not in out.columns:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta.clip(upper=0))
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        out["rsi_14"] = 100 - (100 / (1 + rs))

    if "macd_hist" not in out.columns:
        ema12 = close.ewm(span=12, min_periods=12).mean()
        ema26 = close.ewm(span=26, min_periods=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, min_periods=9).mean()
        out["macd_line"] = macd
        out["macd_signal"] = signal
        out["macd_hist"] = macd - signal

    if "bb_pct" not in out.columns:
        mid = close.rolling(20, min_periods=10).mean()
        std = close.rolling(20, min_periods=10).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        denom = (upper - lower).replace(0, np.nan)
        out["bb_pct"] = (close - lower) / denom

    if "log_return" in out.columns:
        if "rvol_20d" not in out.columns:
            out["rvol_20d"] = out["log_return"].rolling(20, min_periods=10).std() * np.sqrt(252)
        if "log_return_lag1" not in out.columns:
            out["log_return_lag1"] = out["log_return"].shift(1)
        if "log_return_lag5" not in out.columns:
            out["log_return_lag5"] = out["log_return"].shift(5)

    if "drawdown_from_peak" not in out.columns:
        peak = close.rolling(60, min_periods=20).max()
        out["drawdown_from_peak"] = close / peak - 1.0

    if "price_vs_ma200" not in out.columns:
        ma200 = close.rolling(200, min_periods=100).mean()
        out["price_vs_ma200"] = close / ma200 - 1.0

    logger.info("[TA] Technical indicators sẵn sàng (%d cột)", len(out.columns))
    return out
