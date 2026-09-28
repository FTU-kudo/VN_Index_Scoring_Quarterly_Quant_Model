"""
backfill_flows.py — Backfill dòng tiền khối ngoại full-history (2018→nay)
=============================================================================
Phát hiện khi kiểm tra API VNDirect (09/2026, theo đề xuất của user):
  `api-finfo.vndirect.com.vn/v4/foreigns` thực ra có dữ liệu từ **2018-08-30**
  (STOCK_HOSE/ETF_HOSE đủ 588 phiên trước 2021-01-01) — giới hạn "API chỉ từ
  2021" trong `fetch_foreign_flows()` là tự đặt, không phải của API.

Hai hệ quả được fix cùng lúc:
  1. **N/A 5 quý 2021-Q1→2022-Q1**: z-score flows (nff_ex_etf, etf_flow) cần
     4 quý đã kết thúc trước đó; với dữ liệu 2018-Q4 trở về sau, cả 24 quyết
     định quý đều có z thật.
  2. **Số liệu rác trong expanding stats hiện tại**: chuỗi quý cũ bắt đầu
     2021-Q1 — nhưng dataset PE/PB chỉ có số cổ phiếu đầy đủ từ 2021-04-15,
     nên total_mc 2021-Q1 (26 mã, ~11 nghìn tỷ) làm nff_pct quý đó phóng đại
     ~300 lần và bóp méo mean/std của MỌI z đã lưu. Fix: splice vốn hóa HOSE
     công bố (data/external/hose_market_cap_published.csv) cho giai đoạn MC
     ticker không hợp lệ (< 1 triệu tỷ), giữ nguyên MC thật từ 2021-04-15.

Script áp cho LỊCH SỬ mà không chạy lại toàn pipeline. Với mỗi quý (ascending
để percentile expanding không look-ahead):
  1. Đọc JSON export cũ → parse input KHÔNG ĐỔI: dxy/us10y/jpy/oil
     (global_intermarket), ftse/rebalancing/adtv (market_structure).
  2. Tính z + YTD mới của nff/etf từ dữ liệu flows 2018→nay (as-of backward).
  3. Re-score global_intermarket (20%) và market_structure (10%).
  4. Cập nhật total/label/most_divergent/pillar_std/percentile/dispersion.
  5. Ghi parquet + JSON export + audit data/scores/vnindex_quarterly_flows.json.

Pre-check tích hợp (gate — sai là DỪNG):
  - Derived fields replicate trên dữ liệu cũ phải khớp 100%.
  - q_ytd (YTD % of Market Cap) tính lại PHẢI khớp chuỗi đã lưu ở mọi quý có
    dữ liệu (chứng minh flows + MC + pipeline tái lập đúng; chỉ z thay đổi
    do cửa sổ expanding dài hơn — đúng chủ đích).
  - 5 quý từng N/A PHẢI có z thật sau backfill (nếu API thiếu đoạn 2018-2020
    thì DỪNG, không chạy half-backfill).

Sau script này PHẢI chạy (workflow đã nối sẵn):
  python scripts/backfill_calibrated_scores.py
  python scripts/rebuild_html.py
  python scripts/update_readme_results.py

Sandbox không gọi được VNDirect (TLS bị chặn) → chạy trên GitHub Actions:
  .github/workflows/backfill_flows.yml
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

sys.path.append(os.getcwd())

from src.utils.config import SCORES_DIR, EXPORTS_DIR, RAW_DIR, get_score_label
from src.scoring.quarterly_scorer import score_global_intermarket, score_market_structure
from src.features.market_structure_features import (
    parse_market_structure_inputs_from_details,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("backfill_flows")

HISTORY_PATH = SCORES_DIR / "quarterly_scores_history.parquet"
AUDIT_CACHE_PATH = SCORES_DIR / "vnindex_quarterly_flows.json"
FLOWS_CACHE_PATH = RAW_DIR / "foreign_flows.parquet"
TEST_QUARTERS = {"2099-Q1"}

MIN_HIST_FOR_PERCENTILE = 4  # sao chép compute_quarterly_score()

# Chuỗi quý bắt đầu 2018-Q4 → z khả dụng từ 2019-Q3 trở đi → sau backfill
# MỌI quyết định quý (2021-Q1+) đều PHẢI có z thật.


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Dữ liệu flows (cache → fetch live)
# ═══════════════════════════════════════════════════════════════════════════════

def load_flows(force_fetch: bool = False) -> pd.DataFrame:
    """Foreign flows 2018-08-30→nay: cache (đủ 2 đầu) → fetch VNDirect."""
    if not force_fetch and FLOWS_CACHE_PATH.exists():
        df = pd.read_parquet(FLOWS_CACHE_PATH)
        df["date"] = pd.to_datetime(df["date"])
        if len(df) > 0 and df["date"].min() <= pd.Timestamp("2018-09-15"):
            logger.info(
                f"[FF] Cache: {len(df)} ngày, {df['date'].min().date()} → {df['date'].max().date()}"
            )
            return df.sort_values("date").reset_index(drop=True)
        logger.info("[FF] Cache không phủ đoạn 2018 — bỏ cache, fetch lại toàn bộ")

    logger.info("[FF] Fetch foreign flows từ VNDirect (2018-08-01 → nay)...")
    from src.data.fetcher import fetch_foreign_flows
    try:
        df = fetch_foreign_flows(start="2018-08-01", use_cache=False)
    except Exception as e:
        raise SystemExit(
            f"[FF] Fetch thất bại ({e}).\n"
            "  → Sandbox/local không gọi được VNDirect (TLS): chạy GitHub Actions "
            "`.github/workflows/backfill_flows.yml`."
        )
    if df is None or len(df) == 0:
        raise SystemExit("[FF] Fetch trả về DataFrame rỗng.")
    logger.info(
        f"[FF] Fetched: {len(df)} ngày, {df['date'].min().date()} → {df['date'].max().date()}"
    )
    return df.sort_values("date").reset_index(drop=True)


def load_flows_features(df_flows: pd.DataFrame) -> pd.DataFrame:
    """Daily flows features (z/YTD live) — dùng ĐÚNG pipeline production."""
    from src.features.global_features import build_foreign_flow_features
    from src.features.valuation_features import load_market_pepb_history

    df_pepb = load_market_pepb_history()
    if df_pepb.empty:
        raise SystemExit(
            "[PEPB] Không có dữ liệu P/E-P/B (MC) — cần ticker_history.parquet "
            "(cache data/processed/ hoặc GitHub raw trên CI)."
        )
    feat = build_foreign_flow_features(df_flows, df_pepb)
    for col in ["nff_ex_etf_q_zscore_live", "etf_flow_q_zscore_live"]:
        if col not in feat.columns:
            raise SystemExit(f"[FF] Thiếu cột {col} trong flows features.")
    first_z = feat.loc[feat["nff_ex_etf_q_zscore_live"].notna(), "date"].min()
    logger.info(
        f"[FF] Features: {len(feat)} ngày | z đầu tiên: "
        f"{first_z.date() if pd.notna(first_z) else 'KHÔNG CÓ'}"
    )
    if pd.isna(first_z):
        raise SystemExit("[FF] Không tính được z nào — dữ liệu flows/MC không đủ.")
    return feat.sort_values("date").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Parse input KHÔNG ĐỔI từ chuỗi details cũ (point-in-time được bảo toàn)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_global_inputs(details: Dict[str, str]) -> Dict[str, Optional[float]]:
    """dxy_z, us10y, jpy_z, jpy_risk, oil_shock, oil_max — từ detail cũ."""
    out = {}
    m = re.search(r"Z = (-?\d+\.\d+)", details.get("dxy", ""))
    out["dxy_zscore_60d"] = float(m.group(1)) if m else None

    m = re.search(r"(-?\d+\.\d+)%", details.get("us10y", ""))
    out["us10y_yield"] = float(m.group(1)) if m else None

    m = re.search(r"Z = (-?\d+\.\d+) \((\w+)\)", details.get("jpy_carry", ""))
    out["usdjpy_zscore_60d"] = float(m.group(1)) if m else None
    out["jpy_carry_risk"] = m.group(2) if m else "Neutral"

    m = re.search(r"Oil Shock Score = (\d+\.\d+) \(Max Δ5d = (\d+\.\d+)%\)",
                  details.get("oil_shock", ""))
    if m:
        out["oil_shock_score_ytd"] = float(m.group(1))
        out["oil_max_weekly_change_ytd"] = float(m.group(2)) / 100.0
    else:
        out["oil_shock_score_ytd"] = None
        out["oil_max_weekly_change_ytd"] = None
    return out


def parse_old_flows_values(details: Dict[str, str]) -> Dict[str, Optional[float]]:
    """z/q_ytd flows CŨ (so sánh audit) + q_ytd (pre-check tái lập)."""
    out = {}
    for key, col in [("nff_ex_etf", "nff"), ("etf_flow", "etf")]:
        raw = str(details.get(key, ""))
        if raw.startswith("<MISSING>"):
            out[f"{col}_z_old"] = None
        else:
            m = re.search(r"Z = (-?\d+\.\d+)", raw)
            out[f"{col}_z_old"] = float(m.group(1)) if m else None
        raw_ytd = str(details.get(f"{key}_q_ytd", ""))
        m = re.search(r"(-?\d+\.\d+)% of Market Cap", raw_ytd)
        out[f"{col}_ytd_old_pct"] = float(m.group(1)) if m else None
    return out


def asof_row(df: pd.DataFrame, as_of: pd.Timestamp) -> Optional[pd.Series]:
    sub = df[df["date"] <= as_of]
    return sub.iloc[-1] if len(sub) else None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Replicate derived fields của compute_quarterly_score (expanding, no look-ahead)
# ═══════════════════════════════════════════════════════════════════════════════

def derive_percentile(total: float, prior_totals) -> dict:
    out = {"percentile_label": "HOLD", "percentile_p15": None, "percentile_p85": None}
    if len(prior_totals) >= MIN_HIST_FOR_PERCENTILE:
        p15 = float(np.percentile(prior_totals, 15))
        p85 = float(np.percentile(prior_totals, 85))
        out["percentile_p15"] = p15
        out["percentile_p85"] = p85
        if total >= p85:
            out["percentile_label"] = "BUY/ACCUMULATE"
        elif total <= p15:
            out["percentile_label"] = "REDUCE/SELL"
    return out


def derive_dispersion(pillar_std: float, prior_stds) -> str:
    if len(prior_stds) < MIN_HIST_FOR_PERCENTILE:
        return "MEDIUM"
    p33 = float(np.percentile(prior_stds, 33))
    p67 = float(np.percentile(prior_stds, 67))
    if pillar_std >= p67:
        return "HIGH"
    if pillar_std <= p33:
        return "LOW"
    return "MEDIUM"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Backfill chính
# ═══════════════════════════════════════════════════════════════════════════════

def backfill_all(
    flows_feat: pd.DataFrame,
    dry_run: bool = False,
    history_path: Path = HISTORY_PATH,
    exports_dir: Path = EXPORTS_DIR,
    audit_path: Path = AUDIT_CACHE_PATH,
) -> pd.DataFrame:
    if not history_path.exists():
        raise SystemExit(f"[BACKFILL] Missing {history_path}")

    hist = pd.read_parquet(history_path)
    hist = hist[~hist["quarter"].isin(TEST_QUARTERS)].sort_values("quarter").reset_index(drop=True)
    if hist.empty:
        raise SystemExit("[BACKFILL] History parquet rỗng.")

    quarters = hist["quarter"].tolist()
    exports = {}
    for q in quarters:
        path = exports_dir / f"score_{q.replace('-', '_')}.json"
        if not path.exists():
            raise SystemExit(f"[BACKFILL] Thiếu export JSON cho {q}: {path}")
        with open(path, encoding="utf-8") as f:
            exports[q] = json.load(f)

    # ── Pre-check 1: derived fields trên dữ liệu CŨ ──────────────────────────
    prior_totals, prior_stds = [], []
    n_match, n_check = 0, 0
    for q in quarters:
        rec = exports[q]["quarterly_score"]
        total_old = round(float(rec["total_score"]), 2)
        p = derive_percentile(total_old, prior_totals)
        d = derive_dispersion(float(rec["pillar_std"]), prior_stds)
        n_check += 2
        n_match += int(p["percentile_label"] == rec.get("percentile_label"))
        n_match += int(d == rec.get("dispersion_level"))
        prior_totals.append(total_old)
        prior_stds.append(float(rec["pillar_std"]))
    logger.info(f"[PRECHECK] Derived fields trên dữ liệu cũ: {n_match}/{n_check} khớp")
    if n_match < n_check:
        raise SystemExit("[PRECHECK] Logic expanding KHÔNG khớp scorer — dừng.")

    # ── Pre-check 2: q_ytd tính lại phải khớp chuỗi đã lưu ────────────────────
    # (chứng minh flows + MC + pipeline tái lập đúng; z sẽ khác là DO CÙA
    #  cửa sổ expanding dài hơn — đúng chủ đích)
    y_match, y_check = 0, 0
    for q in quarters:
        rec = exports[q]["quarterly_score"]
        as_of = pd.Timestamp(rec["data_as_of"])
        old = parse_old_flows_values(rec["group_details"]["global_intermarket"])
        # etf_flow_q_ytd nằm trong details market_structure
        old_ms = parse_old_flows_values(rec["group_details"]["market_structure"])
        if old["etf_ytd_old_pct"] is None:
            old["etf_ytd_old_pct"] = old_ms["etf_ytd_old_pct"]
        row = asof_row(flows_feat, as_of)
        for col, key in [("nff_ex_etf_q_ytd", "nff_ytd_old_pct"),
                         ("etf_flow_q_ytd", "etf_ytd_old_pct")]:
            if old[key] is not None:
                y_check += 1
                if row is None or pd.isna(row[col]):
                    continue  # sẽ fail ở dưới
                new_pct = float(row[col]) * 100.0
                y_match += int(abs(new_pct - old[key]) <= 0.006)
    logger.info(f"[PRECHECK] q_ytd tính lại vs đã lưu: {y_match}/{y_check} khớp (±0.006pp)")
    if y_match < y_check:
        raise SystemExit(
            "[PRECHECK] q_ytd KHÔNG khớp giá trị đã lưu — dữ liệu flows/MC khác "
            "pipeline gốc. Dừng để không ghi đè sai."
        )

    # ── Vòng chính ───────────────────────────────────────────────────────────
    rows, changes, audit = [], [], []
    prior_totals, prior_stds = [], []

    for q in quarters:
        payload = exports[q]
        rec = payload["quarterly_score"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        as_of = pd.Timestamp(rec["data_as_of"])

        old_glob_w = float(rec["group_scores"]["global_intermarket"]["weighted_score"])
        old_glob_raw = float(rec["group_scores"]["global_intermarket"]["raw_score"])
        old_ms_w = float(rec["group_scores"]["market_structure"]["weighted_score"])
        old_ms_raw = float(rec["group_scores"]["market_structure"]["raw_score"])
        old_total = round(float(rec["total_score"]), 2)
        old_label = rec["label"]
        old_flows = parse_old_flows_values(rec["group_details"]["global_intermarket"])
        old_ms_flows = parse_old_flows_values(rec["group_details"]["market_structure"])

        # 1) Flows z/YTD mới tại as-of (point-in-time)
        row = asof_row(flows_feat, as_of)
        nff_z = None if row is None or pd.isna(row["nff_ex_etf_q_zscore_live"]) \
            else float(row["nff_ex_etf_q_zscore_live"])
        nff_ytd = None if row is None or pd.isna(row["nff_ex_etf_q_ytd"]) \
            else float(row["nff_ex_etf_q_ytd"])
        etf_z = None if row is None or pd.isna(row["etf_flow_q_zscore_live"]) \
            else float(row["etf_flow_q_zscore_live"])
        etf_ytd = None if row is None or pd.isna(row["etf_flow_q_ytd"]) \
            else float(row["etf_flow_q_ytd"])
        flows_date = None if row is None else str(pd.Timestamp(row["date"]).date())

        # 2) Re-score global_intermarket (inputs khác giữ nguyên từ details cũ)
        gi = parse_global_inputs(rec["group_details"]["global_intermarket"])
        df_glob = pd.Series({
            "dxy_zscore_60d": np.nan if gi["dxy_zscore_60d"] is None else gi["dxy_zscore_60d"],
            "us10y_yield": np.nan if gi["us10y_yield"] is None else gi["us10y_yield"],
            "nff_ex_etf_q_zscore_live": np.nan if nff_z is None else nff_z,
            "nff_ex_etf_q_ytd": np.nan if nff_ytd is None else nff_ytd,
            "usdjpy_zscore_60d": np.nan if gi["usdjpy_zscore_60d"] is None else gi["usdjpy_zscore_60d"],
            "jpy_carry_risk": gi["jpy_carry_risk"],
            "oil_shock_score_ytd": np.nan if gi["oil_shock_score_ytd"] is None else gi["oil_shock_score_ytd"],
            "oil_max_weekly_change_ytd": np.nan if gi["oil_max_weekly_change_ytd"] is None else gi["oil_max_weekly_change_ytd"],
        })  # KHÔNG ép dtype=float — jpy_carry_risk là string
        g_glob = score_global_intermarket(df_glob)

        # 3) Re-score market_structure (ftse/rebalancing/adtv giữ cũ, etf z mới)
        inp = parse_market_structure_inputs_from_details(rec["group_details"]["market_structure"])
        if inp["months_to_next_rebalancing"] is None:
            raise SystemExit(f"[BACKFILL] {q}: không parse được months_to_next_rebalancing — dừng.")
        adtv = rec.get("adtv_change_pct", None)
        df_ms = pd.Series({
            "etf_flow_q_zscore_live": np.nan if etf_z is None else etf_z,
            "etf_flow_q_ytd": np.nan if etf_ytd is None else etf_ytd,
        }, dtype=float)
        g_ms = score_market_structure(
            df_latest=df_ms,
            ftse_upgrade_status=inp["ftse_upgrade_status"] or "unknown",
            months_to_next_rebalancing=inp["months_to_next_rebalancing"],
            adtv_change_pct=adtv,
        )

        # 4) Tổng mới: global (20%) + market_structure (10%)
        new_total = round(old_total - old_glob_w + g_glob["weighted_score"]
                          - old_ms_w + g_ms["weighted_score"], 2)
        label, emoji, desc, alloc = get_score_label(new_total)

        # 5) Derived fields — expanding trên giá trị MỚI
        group_raw = {k: float(v["raw_score"]) for k, v in rec["group_scores"].items()}
        group_raw["global_intermarket"] = float(g_glob["raw_score"])
        group_raw["market_structure"] = float(g_ms["raw_score"])
        fund_raw = {k: v for k, v in group_raw.items() if k not in ("quant_model", "ml_forecast")}
        most_div = max(fund_raw, key=lambda k: abs(fund_raw[k] - 50))
        arr = np.array(list(group_raw.values()), dtype=float)
        pstd = round(float(np.std(arr, ddof=1)), 2)
        prange = round(float(np.max(arr) - np.min(arr)), 2)
        pctl = derive_percentile(new_total, prior_totals)
        disp = derive_dispersion(pstd, prior_stds)

        # 6) Cập nhật JSON record
        rec["date_computed"] = now_str
        rec["total_score"] = new_total
        rec["label"] = label
        rec["emoji"] = emoji
        rec["label_description"] = desc
        rec["label_allocation"] = alloc
        rec["most_divergent_pillar"] = most_div
        rec.update(pctl)
        rec["pillar_std"] = pstd
        rec["pillar_range"] = prange
        rec["dispersion_level"] = disp
        rec["group_scores"]["global_intermarket"] = {
            "raw_score": g_glob["raw_score"], "weighted_score": g_glob["weighted_score"],
        }
        merged = dict(rec["group_details"]["global_intermarket"])
        merged.update(g_glob["details"])
        rec["group_details"]["global_intermarket"] = merged
        rec["group_rationale"]["global_intermarket"] = g_glob["rationale"]
        rec["group_scores"]["market_structure"] = {
            "raw_score": g_ms["raw_score"], "weighted_score": g_ms["weighted_score"],
        }
        merged = dict(rec["group_details"]["market_structure"])
        merged.update(g_ms["details"])
        rec["group_details"]["market_structure"] = merged
        rec["group_rationale"]["market_structure"] = g_ms["rationale"]
        payload.setdefault("metadata", {})["flows_backfill"] = {
            "applied_at": now_str,
            "source": "VNDirect api-finfo /v4/foreigns — STOCK_HOSE, ETF_HOSE (2018-08-30→nay)",
            "fix": "bỏ giới hạn fetch 2021 tự đặt; splice MC HOSE công bố trước 2021-04-15",
        }

        # 7) Row parquet
        row_hist = hist[hist["quarter"] == q].iloc[0].to_dict()
        row_hist.update({
            "date_computed": now_str,
            "total_score": new_total,
            "label": label,
            "score_global_intermarket": g_glob["weighted_score"],
            "score_market_structure": g_ms["weighted_score"],
            "percentile_label": pctl["percentile_label"],
            "pillar_std": pstd,
            "pillar_range": prange,
            "dispersion_level": disp,
        })
        rows.append(row_hist)

        audit.append({
            "quarter": q,
            "as_of": rec["data_as_of"],
            "flows_row_date": flows_date,
            "nff_z": None if nff_z is None else round(nff_z, 4),
            "nff_z_old": old_flows["nff_z_old"],
            "nff_ytd_pct": None if nff_ytd is None else round(nff_ytd * 100, 4),
            "etf_z": None if etf_z is None else round(etf_z, 4),
            "etf_z_old": old_ms_flows["etf_z_old"],
            "etf_ytd_pct": None if etf_ytd is None else round(etf_ytd * 100, 4),
            "scores": {
                "global_raw": float(g_glob["raw_score"]),
                "global_raw_old": old_glob_raw,
                "market_structure_raw": float(g_ms["raw_score"]),
                "market_structure_raw_old": old_ms_raw,
            },
        })
        changes.append({
            "quarter": q,
            "nff_z": nff_z, "etf_z": etf_z,
            "glob_raw_old": old_glob_raw, "glob_raw_new": float(g_glob["raw_score"]),
            "ms_raw_old": old_ms_raw, "ms_raw_new": float(g_ms["raw_score"]),
            "total_old": old_total, "total_new": new_total,
            "label_old": old_label, "label_new": label,
            "pctl": pctl["percentile_label"], "disp": disp,
        })
        prior_totals.append(new_total)
        prior_stds.append(pstd)

    # ── Gate: MỌI quý phải có z thật (chuỗi từ 2018-Q4 → z từ 2019-Q3+) ───────
    by_q = {c["quarter"]: c for c in changes}
    missing_z = [q for q in quarters if by_q[q]["nff_z"] is None or by_q[q]["etf_z"] is None]
    if missing_z:
        raise SystemExit(
            f"[GATE] Các quý sau KHÔNG có flows z sau backfill: {missing_z} — "
            "dữ liệu 2018-2020 thiếu. DỪNG (không chạy half-backfill)."
        )

    # ── Bảng tóm tắt ──────────────────────────────────────────────────────────
    print("\n" + "=" * 122)
    print("FLOWS BACKFILL — SO SÁNH TRƯỚC / SAU (global_intermarket 20% + market_structure 10%)")
    print("=" * 122)
    print(f"{'Quarter':<10}{'NFF z (mới)':>12}{'ETF z (mới)':>12}"
          f"{'Global raw (old→new)':>22}{'MS raw (old→new)':>20}{'Total (old→new)':>18}{'Label (old→new)':>22}")
    for c in changes:
        nz = f"{c['nff_z']:+.2f}" if c["nff_z"] is not None else "N/A"
        ez = f"{c['etf_z']:+.2f}" if c["etf_z"] is not None else "N/A"
        gs = f"{c['glob_raw_old']:.1f}→{c['glob_raw_new']:.1f}"
        ms = f"{c['ms_raw_old']:.1f}→{c['ms_raw_new']:.1f}"
        ts = f"{c['total_old']:.2f}→{c['total_new']:.2f}"
        ls = f"{c['label_old']}→{c['label_new']}" if c["label_old"] != c["label_new"] else c["label_new"]
        print(f"{c['quarter']:<10}{nz:>12}{ez:>12}{gs:>22}{ms:>20}{ts:>18}{ls:>22}")
    n_label = sum(1 for c in changes if c["label_old"] != c["label_new"])
    print("-" * 122)
    print(
        f"NFF z có dữ liệu: {sum(1 for c in changes if c['nff_z'] is not None)}/24 | "
        f"ETF z có dữ liệu: {sum(1 for c in changes if c['etf_z'] is not None)}/24 | "
        f"Label raw đổi: {n_label}/24"
    )

    if dry_run:
        print("\n[DRY-RUN] Không ghi gì. Bỏ --dry-run để áp dụng.")
        return pd.DataFrame(rows)

    # ── Ghi parquet + audit + exports ────────────────────────────────────────
    new_hist = pd.DataFrame(rows)
    new_hist = new_hist[[c for c in hist.columns if c in new_hist.columns]]
    new_hist.to_parquet(history_path, index=False)
    logger.info(f"[BACKFILL] Parquet updated → {history_path} ({len(new_hist)} quarters)")

    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump({
            "description": "Flows (VNDirect 2018→nay) z/YTD point-in-time + điểm re-score "
                           "global_intermarket & market_structure — backfill 09/2026",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "quarters": {a["quarter"]: a for a in audit},
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"[BACKFILL] Audit cache → {audit_path}")

    for q in quarters:
        path = exports_dir / f"score_{q.replace('-', '_')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(exports[q], f, ensure_ascii=False, indent=2)
    logger.info(f"[BACKFILL] {len(quarters)} JSON exports updated → {exports_dir}")

    print(
        "\n➡️  BƯỚC KẾ TIẾP (bắt buộc, đúng thứ tự):\n"
        "   python scripts/backfill_calibrated_scores.py\n"
        "   python scripts/rebuild_html.py\n"
        "   python scripts/update_readme_results.py"
    )
    return new_hist


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill flows full-history (2018→nay) — nff/etf z-score"
    )
    ap.add_argument("--dry-run", action="store_true", help="Chỉ in so sánh, không ghi")
    ap.add_argument("--force-fetch", action="store_true",
                    help="Bỏ qua cache flows local, tải lại từ VNDirect")
    args = ap.parse_args()

    flows = load_flows(force_fetch=args.force_fetch)
    flows_feat = load_flows_features(flows)
    backfill_all(flows_feat, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
