"""
run_daily_update.py — Entry Point: Cập nhật Daily Indicators
=============================================================
Chạy hàng ngày sau giờ đóng cửa (16:05 ICT) để cập nhật:
  - VNI OHLCV mới nhất
  - Foreign flows
  - Global indicators (DXY, US10Y)
  - Tính nhanh các leading indicators
  - Alert nếu có tín hiệu bất thường
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import LOG_FILE, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger("run_daily_update")


def run_daily() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"{'='*50}")
    logger.info(f"DAILY UPDATE — {today}")
    logger.info(f"{'='*50}")

    # 1. Tải VNI mới nhất (force refresh)
    from src.data.fetcher import (
        fetch_vnindex_ohlcv, compute_vni_returns,
        fetch_foreign_flows, fetch_global_indicators
    )
    df_vni    = fetch_vnindex_ohlcv(use_cache=False)
    df_vni    = compute_vni_returns(df_vni)
    df_ff     = fetch_foreign_flows(use_cache=False)
    df_global = fetch_global_indicators(use_cache=False)

    import pandas as pd

    # 2. Cảnh báo nhanh: VNI change, NFF, DXY
    if len(df_vni) > 1:
        last_ret  = df_vni["log_return"].iloc[-1]
        last_vni  = df_vni["close"].iloc[-1]
        prev_vni  = df_vni["close"].iloc[-2]
        dd_60     = df_vni["close"].rolling(60).max().iloc[-1]
        drawdown  = (last_vni / dd_60 - 1) if dd_60 > 0 else 0

        logger.info(f"VNI hôm nay  : {last_vni:,.2f} ({last_ret:+.2%})")
        logger.info(f"Drawdown 60D : {drawdown:+.2%}")

        # Alert nếu giảm mạnh
        if last_ret < -0.02:
            logger.warning(f"🔴 ALERT: VNI giảm {last_ret:.2%} — Theo dõi margin calls!")
        if drawdown < -0.10:
            logger.warning(f"🟠 ALERT: VNI trong drawdown {drawdown:.2%} từ peak 60 ngày")

    # 3. NFF alert
    if len(df_ff) > 0 and "net_foreign_flow_b_vnd" in df_ff.columns:
        last_nff = df_ff["net_foreign_flow_b_vnd"].iloc[-1]
        nff_5d   = df_ff["net_foreign_flow_b_vnd"].tail(5).sum()
        logger.info(f"NFF hôm nay  : {last_nff:+,.0f} tỷ VND")
        logger.info(f"NFF rolling5D: {nff_5d:+,.0f} tỷ VND")
        if nff_5d < -3000:
            logger.warning(f"⚠️ ALERT: Ngoại bán ròng mạnh {nff_5d:.0f} tỷ (5D)")

    # 4. Global alert
    if not df_global.empty:
        if "dxy_close" in df_global.columns:
            dxy_last = df_global["dxy_close"].iloc[-1]
            dxy_5d   = df_global["dxy_close"].pct_change(5).iloc[-1]
            logger.info(f"DXY: {dxy_last:.2f} ({dxy_5d:+.2%} 5D)")
            if dxy_5d > 0.015:
                logger.warning(f"⚠️ DXY tăng mạnh {dxy_5d:.2%} trong 5 ngày — EM pressure")
        if "us10y_yield" in df_global.columns:
            us10y_last = df_global["us10y_yield"].iloc[-1]
            logger.info(f"US10Y: {us10y_last:.2f}%")

    logger.info(f"[Daily] Cập nhật xong lúc {datetime.now().strftime('%H:%M')}")


if __name__ == "__main__":
    run_daily()
