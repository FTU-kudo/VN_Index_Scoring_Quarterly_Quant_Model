"""
market_structure_features.py — Features cho trụ cột Market Structure & FTSE
============================================================================
ADTV (Average Daily Trading Volume) — khối lượng giao dịch bình quân mỗi phiên
của VN-Index, tính từ dữ liệu OHLCV (cột `volume`) mà pipeline đã fetch qua
vnstock.

Nguyên tắc point-in-time (BẤT BIẾN — giống toàn bộ dự án):
  Khi chấm điểm quý Q, quyết định được ra vào ĐẦU quý Q → chỉ số "mới nhất"
  là quý vừa KẾT THÚC (Q−1). Do đó:
      adtv_change_pct(Q) = ADTV(Q−1) / ADTV(Q−2) − 1
  Hàm chỉ đọc 2 cửa sổ Q−1 và Q−2 — không bao giờ nhìn dữ liệu trong Q.

Trước đây `run_quarterly.py` không bao giờ truyền `adtv_change_pct` cho
scorer (dù scorer hỗ trợ sẵn) → chỉ báo ADTV hiện N/A ở 24/24 quý.
Module này + wiring trong run_quarterly.py đóng gap đó.
"""

import logging
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Số phiên tối thiểu để một quý được coi là có đủ dữ liệu ADTV tin cậy
# (quý đầy đủ ~60 phiên; ngưỡng thấp chấp nhận quý bị cắt đầu dữ liệu)
MIN_SESSIONS_PER_QUARTER = 10

VOLUME_COLUMN_CANDIDATES = ("volume", "Volume", "match_value", "value")


def quarter_bounds(quarter: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """'2026-Q3' → (2026-07-01, 2026-09-30). Raise ValueError nếu sai format."""
    try:
        y_str, q_str = quarter.strip().split("-Q")
        y, q = int(y_str), int(q_str)
        if q < 1 or q > 4:
            raise ValueError
    except Exception:
        raise ValueError(f"Sai định dạng quarter: {quarter!r} (expect 'YYYY-QN')")
    start_month = 3 * (q - 1) + 1
    end_month = 3 * q
    start = pd.Timestamp(year=y, month=start_month, day=1)
    end = pd.Timestamp(year=y, month=end_month, day=1) + pd.offsets.MonthEnd(0)
    return start, end


def previous_quarter(quarter: str) -> str:
    """'2026-Q1' → '2025-Q4'."""
    y_str, q_str = quarter.strip().split("-Q")
    y, q = int(y_str), int(q_str)
    if q == 1:
        return f"{y-1}-Q4"
    return f"{y}-Q{q-1}"


def _pick_volume_column(df: pd.DataFrame) -> Optional[str]:
    for c in VOLUME_COLUMN_CANDIDATES:
        if c in df.columns:
            return c
    return None


def compute_quarterly_adtv(
    df: pd.DataFrame,
    quarter: str,
    volume_col: Optional[str] = None,
) -> Optional[Dict]:
    """
    ADTV của MỘT quý cụ thể = trung bình khối lượng giao dịch mỗi phiên.

    Returns
    -------
    dict(adtv, n_sessions, start, end) hoặc None nếu không đủ dữ liệu.
    """
    if df is None or len(df) == 0 or "date" not in df.columns:
        return None
    if volume_col is None:
        volume_col = _pick_volume_column(df)
    if volume_col is None:
        logger.warning("[ADTV] DataFrame không có cột volume — bỏ qua")
        return None

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    start, end = quarter_bounds(quarter)
    win = d[(d["date"] >= start) & (d["date"] <= end)]
    vol = pd.to_numeric(win[volume_col], errors="coerce").dropna()
    vol = vol[vol > 0]
    if len(vol) < MIN_SESSIONS_PER_QUARTER:
        return None
    return {
        "adtv": float(vol.mean()),
        "n_sessions": int(len(vol)),
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }


def compute_adtv_change_pct(
    df: pd.DataFrame,
    quarter: str,
    volume_col: Optional[str] = None,
) -> Optional[float]:
    """
    % thay đổi QoQ của ADTV cho quý đang chấm điểm Q — POINT-IN-TIME:

        adtv_change_pct = ADTV(Q−1) / ADTV(Q−2) − 1

    Q = quý đang chấm điểm. Hàm CHỈ đọc 2 cửa sổ Q−1 và Q−2 (dữ liệu của
    quý Q không bao giờ được dùng — kể cả khi df chứa đến hiện tại).
    Trả về None khi thiếu dữ liệu (scorer sẽ loại ADTV khỏi trung bình trụ cột).
    """
    q_prev = previous_quarter(quarter)      # Q−1: quý vừa kết thúc
    q_prev2 = previous_quarter(q_prev)      # Q−2

    a1 = compute_quarterly_adtv(df, q_prev, volume_col)
    a2 = compute_quarterly_adtv(df, q_prev2, volume_col)
    if a1 is None or a2 is None:
        logger.info(
            f"[ADTV] {quarter}: không đủ dữ liệu ADTV "
            f"({q_prev}={'OK' if a1 else 'MISSING'}, {q_prev2}={'OK' if a2 else 'MISSING'})"
        )
        return None
    if a2["adtv"] <= 0:
        return None
    change = a1["adtv"] / a2["adtv"] - 1.0
    logger.info(
        f"[ADTV] {quarter}: ADTV({q_prev})={a1['adtv']:,.0f} ({a1['n_sessions']} phiên) "
        f"vs ADTV({q_prev2})={a2['adtv']:,.0f} ({a2['n_sessions']} phiên) → {change:+.1%} QoQ"
    )
    return float(change)


def build_adtv_history_cache(
    df: pd.DataFrame,
    quarters,
    volume_col: Optional[str] = None,
) -> Dict[str, Dict]:
    """
    Cache ADTV theo quý (cho rebuild offline + audit): {quarter: {adtv, n_sessions}}.
    `quarters` là danh sách KỲ LỊCH SỬ (đã hoàn tất) — không chứa quý tương lai.
    """
    if volume_col is None:
        volume_col = _pick_volume_column(df)
    cache: Dict[str, Dict] = {}
    for q in quarters:
        rec = compute_quarterly_adtv(df, q, volume_col)
        if rec is not None:
            cache[q] = {
                "adtv": round(rec["adtv"], 2),
                "n_sessions": rec["n_sessions"],
            }
    return cache


# ═══════════════════════════════════════════════════════════════════════════════
# Parse lại input của trụ cột market_structure từ JSON export cũ (cho backfill)
# ═══════════════════════════════════════════════════════════════════════════════

import re  # noqa: E402  (đặt gần nhóm parser để dễ thấy)


def parse_market_structure_inputs_from_details(details: Dict) -> Dict:
    """
    Trích lại các input của score_market_structure() từ `group_details.market_structure`
    trong JSON export cũ — để backfill ADTV chỉ re-score ĐÚNG trụ cột này mà
    không cần chạy lại toàn pipeline.

    Chuỗi gốc (xem quarterly_scorer.score_market_structure):
      ftse_upgrade: "Status: confirmed → score 75\\n  Est passive inflow: ..."
      rebalancing:  "0 months to rebalancing → bonus +20"
      etf_flow:     "Z = -0.21 (Neutral) → score 47"   (hoặc "<MISSING> ...")
    """
    details = details or {}
    ftse_status = None
    months = None
    etf_z = None

    m = re.search(r"Status:\s*(\w+)", str(details.get("ftse_upgrade", "")))
    if m:
        ftse_status = m.group(1)

    m = re.search(r"(\d+)\s*months", str(details.get("rebalancing", "")))
    if m:
        months = int(m.group(1))

    etf_raw = str(details.get("etf_flow", ""))
    if not etf_raw.strip().startswith("<MISSING>"):
        m = re.search(r"Z\s*=\s*(-?[\d.]+)", etf_raw)
        if m:
            etf_z = float(m.group(1))

    return {
        "ftse_upgrade_status": ftse_status,
        "months_to_next_rebalancing": months,
        "etf_flow_q_zscore_live": etf_z,
    }
