"""
fetcher.py — Thu thập dữ liệu VN-Index, macro, và global indicators
=====================================================================
Dữ liệu nguồn:
  - vnstock v4 (Unified API)  : OHLCV VNI, giá cổ phiếu, P/B, EPS
  - SBV (State Bank of VN)    : Lãi suất OMO, tỷ giá USD/VND
  - FRED / yfinance            : DXY, US10Y Yield (proxy qua yfinance)
  - HNX / HOSE public data     : Dư nợ margin (báo cáo tháng)
  - Thủ công / tiêu chuẩn      : Net Foreign Flows (từ vnstock price_board)

Lưu ý: Module này KHÔNG đọc file .env — credentials được load bởi config.py
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from src.utils.config import (
    VNSTOCK_API_KEY, RAW_DIR, HISTORY_START, HISTORY_END,
    VNINDEX_TICKER, VN30_TICKERS, get_vn30_tickers
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. VN-Index OHLCV từ vnstock
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_vnindex_ohlcv(
    start: str = HISTORY_START,
    end: str   = HISTORY_END,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Tải dữ liệu OHLCV của VN-Index.

    Returns
    -------
    DataFrame với cột: date, open, high, low, close, volume
    """
    cache_path = RAW_DIR / "vnindex_ohlcv.parquet"

    if use_cache and cache_path.exists():
        df = pd.read_parquet(cache_path)
        # Nếu dữ liệu đã có đến hôm nay, dùng cache
        latest = pd.to_datetime(df["date"]).max()
        if latest >= pd.to_datetime(end) - timedelta(days=5):
            logger.info(f"[VNI] Dùng cache OHLCV (đến {latest.date()})")
            return df

    logger.info("[VNI] Đang tải OHLCV từ vnstock API...")
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol=VNINDEX_TICKER, source="VCI")
        df = q.history(
            start=start, end=end, interval="1D"
        ).reset_index()
        df.columns = [c.lower() for c in df.columns]
        # Chuẩn hóa tên cột
        rename_map = {"time": "date", "ticker": "symbol"}
        df = df.rename(columns=rename_map)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"[VNI] Đã tải {len(df)} phiên, lưu vào {cache_path}")
    except Exception as e:
        logger.error(f"[VNI] Lỗi khi fetch OHLCV: {e}")
        if cache_path.exists():
            logger.warning("[VNI] Fallback về cache cũ")
            df = pd.read_parquet(cache_path)
        else:
            raise

    return df


def compute_vni_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính tỷ suất sinh lợi VNI (daily, weekly, monthly log-returns).

    Parameters
    ----------
    df : DataFrame với cột 'date', 'close'

    Returns
    -------
    DataFrame bổ sung cột: log_return, weekly_return, monthly_return
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    df["log_return"]     = np.log(df["close"] / df["close"].shift(1))
    df["weekly_return"]  = df["close"].pct_change(5)
    df["monthly_return"] = df["close"].pct_change(21)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Net Foreign Flows từ vnstock
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_foreign_flows(
    start: str = HISTORY_START,
    end: str   = HISTORY_END,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Tải dữ liệu mua/bán ròng khối ngoại (HOSE) từ VNDirect API.

    Returns
    -------
    DataFrame: date, nff_ex_etf_vnd (tỷ VND), etf_flow_vnd (tỷ VND)
    """
    import requests
    import time
    
    cache_path = RAW_DIR / "foreign_flows.parquet"
    
    # Load cache if available
    df_cache = None
    if cache_path.exists():
        df_cache = pd.read_parquet(cache_path)
        
    start_date = pd.to_datetime(start)
    if start_date < pd.to_datetime("2021-01-01"):
        start_date = pd.to_datetime("2021-01-01") # API giới hạn từ 2021
        
    end_date = pd.to_datetime(end)
    
    # Xác định ngày bắt đầu fetch để tiết kiệm thời gian nếu đã có cache
    fetch_start = start_date
    if use_cache and df_cache is not None and not df_cache.empty:
        latest = pd.to_datetime(df_cache["date"]).max()
        if latest >= end_date - timedelta(days=5):
            logger.info(f"[FF] Dùng toàn bộ cache foreign flows (đến {latest.date()})")
            return df_cache
        else:
            fetch_start = latest + timedelta(days=1)
            logger.info(f"[FF] Fetch thêm dữ liệu foreign flows từ {fetch_start.date()}...")
    else:
        logger.info("[FF] Đang tải Net Foreign Flows từ VNDirect API (toàn bộ)...")

    url = 'https://api-finfo.vndirect.com.vn/v4/foreigns'
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    all_data = []
    current_start = fetch_start
    
    while current_start <= end_date:
        current_end = min(current_start + pd.DateOffset(months=3), end_date)
        start_str = current_start.strftime('%Y-%m-%d')
        end_str = current_end.strftime('%Y-%m-%d')
        
        q = f'code:STOCK_HNX,STOCK_UPCOM,STOCK_HOSE,ETF_HOSE,IFC_HOSE~tradingDate:gte:{start_str}~tradingDate:lte:{end_str}'
        params = {
            'q': q,
            'sort': 'tradingDate',
            'size': '10000'
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            if 'data' in data and data['data']:
                all_data.extend(data['data'])
            else:
                logger.debug(f"[FF] Không có dữ liệu từ {start_str} đến {end_str}")
        except Exception as e:
            logger.error(f"[FF] Lỗi khi gọi API VNDirect: {e}")
            break
            
        current_start = current_end + pd.Timedelta(days=1)
        time.sleep(0.5)

    if all_data:
        df_new = pd.DataFrame(all_data)
        df_new['tradingDate'] = pd.to_datetime(df_new['tradingDate'])
        # Pivot the data
        df_pivot = df_new.pivot_table(index='tradingDate', columns='code', values='netVal', aggfunc='sum').reset_index()
        
        if 'STOCK_HOSE' not in df_pivot.columns:
            df_pivot['STOCK_HOSE'] = np.nan
        if 'ETF_HOSE' not in df_pivot.columns:
            df_pivot['ETF_HOSE'] = np.nan
            
        # Calculate features in tỷ VND (billion VND)
        df_pivot['nff_ex_etf_vnd'] = (df_pivot['STOCK_HOSE'] - df_pivot['ETF_HOSE'].fillna(0)) / 1e9
        df_pivot['etf_flow_vnd'] = df_pivot['ETF_HOSE'] / 1e9
        
        df_result = df_pivot[['tradingDate', 'nff_ex_etf_vnd', 'etf_flow_vnd']].rename(columns={'tradingDate': 'date'})
        
        if df_cache is not None and not df_cache.empty:
            df = pd.concat([df_cache, df_result]).drop_duplicates(subset=['date'], keep='last')
        else:
            df = df_result
    else:
        logger.warning("[FF] Không lấy được thêm dữ liệu, trả về cache nếu có.")
        df = df_cache if df_cache is not None else pd.DataFrame(columns=['date', 'nff_ex_etf_vnd', 'etf_flow_vnd'])

    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"[FF] Đã lưu cache foreign flows cho {len(df)} ngày")

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Macro Vietnam — Lãi suất, Tỷ giá
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_macro_sbv_manual() -> pd.DataFrame:
    """
    Macro data từ nguồn thủ công / semi-automated.

    Dữ liệu SBV (Ngân hàng Nhà nước) không có public API chuẩn.
    Workflow:
      1. Thu thập thủ công từ sbv.gov.vn → lãi suất OMO, tái cấp vốn
      2. Tỷ giá trung tâm: SBV công bố hàng ngày
      3. File CSV chuẩn được lưu tại: data/raw/macro_sbv.csv

    Schema CSV:
      date, omo_overnight_rate, deposit_12m_rate, usd_vnd_rate

    Returns
    -------
    DataFrame với schema trên, hoặc DataFrame trống nếu file chưa tồn tại.
    """
    csv_path = RAW_DIR / "macro_sbv.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        logger.info(f"[SBV] Loaded {len(df)} records từ {csv_path}")
        return df
    else:
        logger.warning(
            f"[SBV] Không tìm thấy {csv_path}\n"
            "Vui lòng tải dữ liệu từ sbv.gov.vn và lưu vào data/raw/macro_sbv.csv\n"
            "Schema: date, omo_overnight_rate, deposit_12m_rate, usd_vnd_rate\n"
            "Hiện tại trả về DataFrame trống — một số tính toán sẽ bị skip."
        )
        return pd.DataFrame(columns=["date", "omo_overnight_rate",
                                     "deposit_12m_rate", "usd_vnd_rate"])


def fetch_usdvnd_proxy(
    start: str = HISTORY_START,
    end:   str = HISTORY_END,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Tải tỷ giá USD/VND bằng yfinance (mã: USDVND=X) làm proxy.

    Lưu ý: yfinance USDVND=X có thể thiếu liquidity — dùng để tham chiếu,
    kết hợp với dữ liệu SBV thủ công để đối chiếu.

    Returns
    -------
    DataFrame: date, usd_vnd_close, usd_vnd_pct_change
    """
    cache_path = RAW_DIR / "usdvnd_yf.parquet"
    if use_cache and cache_path.exists():
        df = pd.read_parquet(cache_path)
        logger.info(f"[FX] Dùng cache USD/VND ({len(df)} rows)")
        return df

    logger.info("[FX] Đang tải USD/VND từ yfinance...")
    try:
        import yfinance as yf
        ticker = yf.Ticker("USDVND=X")
        raw = ticker.history(start=start, end=end, interval="1d")
        if raw.empty:
            raise ValueError("yfinance USDVND=X trả về DataFrame trống")
        df = raw[["Close"]].reset_index()
        df.columns = ["date", "usd_vnd_close"]
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["usd_vnd_pct_change"] = df["usd_vnd_close"].pct_change()
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"[FX] Đã tải {len(df)} phiên USD/VND")
    except ImportError:
        logger.warning("[FX] yfinance chưa cài — thêm vào requirements.txt")
        df = pd.DataFrame(columns=["date", "usd_vnd_close", "usd_vnd_pct_change"])
    except Exception as e:
        logger.error(f"[FX] Lỗi: {e}")
        df = pd.DataFrame(columns=["date", "usd_vnd_close", "usd_vnd_pct_change"])

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Global Indicators — DXY, US10Y (qua yfinance)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_global_indicators(
    start: str = HISTORY_START,
    end:   str = HISTORY_END,
    use_cache: bool = True
) -> pd.DataFrame:
    """
    Tải DXY, US10Y Yield, và USD/JPY từ yfinance.

    Mã yfinance:
      - DX-Y.NYB : US Dollar Index (proxy cho DXY)
      - ^TNX     : CBOE Interest Rate 10-Year T-Note (US10Y)
      - JPY=X    : Tỷ giá USD/JPY (Yen Carry Trade proxy)

    Returns
    -------
    DataFrame: date, dxy_close, dxy_pct_change, us10y_yield, us10y_delta, usdjpy_close
    """
    cache_path = RAW_DIR / "global_indicators.parquet"
    if use_cache and cache_path.exists():
        df = pd.read_parquet(cache_path)
        logger.info(f"[GLOBAL] Dùng cache global indicators ({len(df)} rows)")
        return df

    logger.info("[GLOBAL] Đang tải DXY, US10Y, USD/JPY từ yfinance...")
    try:
        import yfinance as yf
        # Tải DXY
        dxy_raw = yf.download("DX-Y.NYB", start=start, end=end, interval="1d",
                              progress=False, auto_adjust=True)
        # Tải US10Y
        us10y_raw = yf.download("^TNX", start=start, end=end, interval="1d",
                                progress=False, auto_adjust=True)

        # Tải USD/JPY
        jpy_raw = yf.download("JPY=X", start=start, end=end, interval="1d",
                              progress=False, auto_adjust=True)

        if dxy_raw.empty or us10y_raw.empty or jpy_raw.empty:
            raise ValueError("yfinance trả về dữ liệu trống cho DXY, US10Y hoặc JPY")

        dxy = dxy_raw[["Close"]].rename(columns={"Close": "dxy_close"})
        dxy.index = pd.to_datetime(dxy.index).tz_localize(None)

        us10y = us10y_raw[["Close"]].rename(columns={"Close": "us10y_yield"})
        us10y.index = pd.to_datetime(us10y.index).tz_localize(None)
        
        jpy = jpy_raw[["Close"]].rename(columns={"Close": "usdjpy_close"})
        jpy.index = pd.to_datetime(jpy.index).tz_localize(None)

        df = dxy.join(us10y, how="outer").join(jpy, how="outer").ffill().reset_index()
        df.columns = ["date", "dxy_close", "us10y_yield", "usdjpy_close"]
        df["dxy_pct_change"] = df["dxy_close"].pct_change()
        df["us10y_delta"]    = df["us10y_yield"].diff()
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"[GLOBAL] Đã tải {len(df)} ngày DXY + US10Y + USD/JPY")

    except ImportError:
        logger.warning("[GLOBAL] yfinance chưa cài đặt")
        df = pd.DataFrame(columns=["date", "dxy_close", "dxy_pct_change",
                                   "us10y_yield", "us10y_delta", "usdjpy_close"])
    except Exception as e:
        logger.error(f"[GLOBAL] Lỗi: {e}")
        df = pd.DataFrame(columns=["date", "dxy_close", "dxy_pct_change",
                                   "us10y_yield", "us10y_delta", "usdjpy_close"])

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Margin Debt — dữ liệu thủ công từ HNX/HOSE
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_margin_debt_manual() -> pd.DataFrame:
    """
    Dư nợ margin tổng thị trường (tỷ VND) — báo cáo tháng từ HOSE/HNX.

    HOSE công bố báo cáo thống kê tài chính margin cuối mỗi quý.
    File cần chuẩn bị: data/raw/margin_debt_monthly.csv

    Schema CSV:
      date (YYYY-MM-DD), margin_debt_b_vnd, margin_debt_mom_pct

    Returns
    -------
    DataFrame với schema trên.
    """
    csv_path = RAW_DIR / "margin_debt_monthly.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        logger.info(f"[MARGIN] Loaded {len(df)} tháng dư nợ margin")
        return df
    else:
        logger.warning(
            f"[MARGIN] Không tìm thấy {csv_path}\n"
            "Lấy từ: https://www.hsx.vn/Modules/Listed/Web/FinanceReport\n"
            "Schema: date, margin_debt_b_vnd, margin_debt_mom_pct"
        )
        return pd.DataFrame(columns=["date", "margin_debt_b_vnd",
                                     "margin_debt_mom_pct"])


def fetch_m2_credit_manual() -> pd.DataFrame:
    """
    Cung tiền M2 và tăng trưởng tín dụng — từ SBV báo cáo tháng.

    File cần chuẩn bị: data/raw/m2_credit_monthly.csv

    Schema CSV:
      date, m2_yoy_pct, credit_growth_yoy_pct, m2_b_vnd

    Returns
    -------
    DataFrame với schema trên.
    """
    csv_path = RAW_DIR / "m2_credit_monthly.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        logger.info(f"[M2] Loaded {len(df)} tháng M2/tín dụng")
        return df
    else:
        logger.warning(
            f"[M2] Không tìm thấy {csv_path}\n"
            "Lấy từ: https://www.sbv.gov.vn → Thống kê → Cung tiền & Tín dụng\n"
            "Schema: date, m2_yoy_pct, credit_growth_yoy_pct, m2_b_vnd"
        )
        return pd.DataFrame(columns=["date", "m2_yoy_pct",
                                     "credit_growth_yoy_pct", "m2_b_vnd"])


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Vietnam Bonds — Từ dự án Vietnam_Bonds
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_vietnam_bonds() -> pd.DataFrame:
    """
    Tải dữ liệu đường cong lợi suất trái phiếu chính phủ Việt Nam.
    Dữ liệu lấy trực tiếp từ GitHub repo VN_Bond_Yield_pipeline.

    Returns
    -------
    DataFrame: date, vn1y_yield, vn2y_yield, vn10y_yield
    """
    import requests
    
    # Sử dụng URL từ GitHub Pages thay vì raw.githubusercontent.com để tránh bị kẹt CDN Cache
    # và tránh bị lỗi Rate Limit (403) của GitHub API khi lấy sha commit trên GitHub Actions.
    url = "https://ftu-kudo.github.io/VN_Bond_Yield_pipeline/exports/data/fitted_curve_ns.json"
    logger.info(f"[BONDS] Đang tải dữ liệu trái phiếu từ GitHub Pages: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=["date", "vn1y_yield", "vn2y_yield", "vn10y_yield"])
            
        df["date"] = pd.to_datetime(df["date"])
        
        # Lấy kỳ hạn 1 năm, 2 năm và 10 năm
        df_1y = df[df["tenor_yr"] == 1.0][["date", "yield_pct"]].rename(columns={"yield_pct": "vn1y_yield"})
        df_2y = df[df["tenor_yr"] == 2.0][["date", "yield_pct"]].rename(columns={"yield_pct": "vn2y_yield"})
        df_10y = df[df["tenor_yr"] == 10.0][["date", "yield_pct"]].rename(columns={"yield_pct": "vn10y_yield"})
        
        # Merge lại theo date
        merged = pd.merge(df_10y, df_2y, on="date", how="outer")
        merged = pd.merge(merged, df_1y, on="date", how="outer")
        merged = merged.sort_values("date").reset_index(drop=True)
        logger.info(f"[BONDS] Tải thành công {len(merged)} ngày dữ liệu trái phiếu từ GitHub")
        return merged
    except Exception as e:
        logger.error(f"[BONDS] Lỗi tải dữ liệu trái phiếu từ GitHub: {e}")
        return pd.DataFrame(columns=["date", "vn1y_yield", "vn2y_yield", "vn10y_yield"])

