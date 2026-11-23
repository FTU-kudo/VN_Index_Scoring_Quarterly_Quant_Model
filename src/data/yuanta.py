# src/data/yuanta.py
"""Market-data client for the supplied price-board and daily-history endpoints."""
import re
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE = "https://ysradar.yuanta.com.vn"
ALLOWED_HOSTS = {"ysradar.yuanta.com.vn", "ysradarapi.yuanta.com.vn"}


def _get_json(path, params=None):
    session = requests.Session()
    url = BASE + path
    for hop in range(4):
        response = session.get(url, params=params, timeout=20, allow_redirects=False)
        response.raise_for_status()
        target = response.headers.get("Location") if 300 <= response.status_code < 400 else None
        if not target and "json" not in response.headers.get("Content-Type", "").lower():
            match = re.search(r'window\.location\.href\s*=\s*["\']([^"\']+)', response.text)
            target = match.group(1) if match else None
        if target:
            url = urljoin(response.url, target)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or hop == 3:
                raise ValueError("Unsafe or excessive market-data redirect")
            params = None
            continue
        return response.json()
    raise ValueError("Market-data redirect limit exceeded")


def vn30_constituents():
    payload = _get_json("/api/v3/market_data/price_board/stock/list_stock_info", {"index_code": "VN30"})
    if payload.get("success") is not True or not isinstance(payload.get("response"), list):
        raise ValueError("Invalid constituents response")
    symbols = sorted({str(row.get("StockCode", "")).strip().upper() for row in payload["response"] if row.get("StockCode")})
    if len(symbols) < 30:
        raise ValueError(f"Incomplete VN30 response: {len(symbols)} symbols")
    return symbols


def daily_history(symbol, start, end, now=None):
    start_date = pd.Timestamp(start).date()
    end_date = pd.Timestamp(end).date()
    if start_date > end_date:
        raise ValueError("start must not be later than end")
    # Future bound is required by the observed API; filter to the requested end below.
    to_date = end_date + timedelta(days=2)
    params = {"symbol": symbol, "resolution": "1D", "from": int(datetime.combine(start_date, time.min, timezone.utc).timestamp()),
              "to": int(datetime.combine(to_date, time.min, timezone.utc).timestamp()), "limit": 100000}
    payload = _get_json("/v2/tradingview/history", params)
    if payload.get("s") != "ok" or not isinstance(payload.get("bars"), list):
        raise ValueError("Invalid daily history response")
    df = pd.DataFrame(payload["bars"])
    if df.empty or not {"t", "o", "h", "l", "c", "v"}.issubset(df.columns):
        raise ValueError("Empty or incomplete daily history")
    df = df.rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"], unit="s", utc=True, errors="coerce").dt.tz_localize(None).dt.normalize()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("date").drop_duplicates("date", keep="last")
    df = df[(df.date >= pd.Timestamp(start_date)) & (df.date <= pd.Timestamp(end_date))]
    vn_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    if vn_now.time() < time(15, 15):
        df = df[df.date != pd.Timestamp(vn_now.date())]
    if df.empty:
        raise ValueError("No completed daily bars in requested range")
    return df.reset_index(drop=True)
