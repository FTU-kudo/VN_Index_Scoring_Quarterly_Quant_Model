"""
backfill_market_data.py — Backfill dữ liệu thị trường thật cho 24 quý lịch sử
=============================================================================
Vấn đề (scan 09/2026 — ba nhóm N/A với nguyên nhân gốc):
  1. BONDS  (vn1y_yield, ir_trend, vn_bonds — N/A 7 quý 2021-Q1→2022-Q3):
     `fetch_vietnam_bonds()` dùng `fitted_curve_ns.json` — bản CUT ~1.000 ngày
     cho dashboard (chỉ từ 2022-09-22). Repo VN_Bond_Yield_pipeline còn xuất bản
     `fitted_curve_ns_full.json` (2012-08-06→nay, cùng cache, cùng phương pháp
     Nelson-Siegel) — fetcher giờ ưu tiên bản full.
  2. M2     (m2_yoy_growth — N/A 24/24 quý): không có nguồn tự động. Giờ có
     ADB Key Indicators Database (SDMX `FM2_PTX_PS.VIE`, nguồn gốc SBV) 2000→2024
     + GSO Báo cáo KT-XH quý IV/2025 cho 2025; fallback committed
     `data/external/m2_credit_adb_gso.csv`.
  3. P/E-P_B-EYG Z-score (pe_zscore N/A 10 quý →2023-Q2; eyg_zscore default 50
     âm thầm 24/24 quý): `compute_zscore_rolling` đòi min_periods = window//2
     (2.5 năm) trong khi series P/E ex-Vingroup chỉ bắt đầu ~2020-12 (thiếu
     shares trước đó) → hạ min_periods còn 252 phiên (~1 năm).
     Ngoài ra `run_quarterly.py` không truyền df_macro → EYG không bao giờ được
     tính (đã fix). Giá trị Z của các ngày ≥2.5 năm dữ liệu KHÔNG ĐỔI.

Script này áp các fix cho LỊCH SỬ mà không chạy lại toàn pipeline. Với mỗi quý
(ascending để percentile expanding không look-ahead):
  1. Đọc JSON export cũ → parse input KHÔNG ĐỔI của trụ cột từ chuỗi details:
     usd_vnd_zscore (macro), margin_risk (valuation) — giữ nguyên point-in-time.
  2. Tính lại inputs từ dữ liệu THẬT: bonds full-history (as-of backward +
     Δ VN1Y theo ngày bond liền trước), M2 (as-of backward — giá trị năm gần
     nhất ĐÃ CÔNG BỐ), P/E-P/B-EYG Z (as-of backward trên daily features).
  3. Re-score trụ cột macro_monetary (mọi quý — M2 mới) và valuation_leverage
     (những quý có thành phần mới: pe/pb/eyg z mới).
  4. Cập nhật total_score, label, most_divergent_pillar, pillar_std/range,
     percentile_label/p15/p85, dispersion_level — tuần tự expanding window.
  5. Ghi lại parquet + JSON export; audit cache data/scores/
     vnindex_quarterly_market_data.json (input thật từng quý, kiểm chứng được).

Pre-check tích hợp: giá trị bonds/PẸ-PB-Z tính lại PHẢI trùng 100% với detail
đã lưu ở những quý vốn có dữ liệu (68/68 bonds, 28/28 z-score khi dev) — nếu
không khớp, script DỪNG để không ghi đè sai.

Sau script này PHẢI chạy (workflow đã nối sẵn):
  python scripts/backfill_calibrated_scores.py   # tầng calibrated theo total mới
  python scripts/rebuild_html.py                 # HTML + validators + Excel
  python scripts/update_readme_results.py        # README

Chạy local (đã có cache data/raw/vietnam_bonds_full.parquet + PE/PB history):
  python scripts/backfill_market_data.py            # ghi thật
  python scripts/backfill_market_data.py --dry-run  # chỉ in bảng so sánh
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
from src.scoring.quarterly_scorer import (
    score_macro_monetary,
    score_valuation_leverage,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("backfill_market_data")

HISTORY_PATH = SCORES_DIR / "quarterly_scores_history.parquet"
AUDIT_CACHE_PATH = SCORES_DIR / "vnindex_quarterly_market_data.json"
BONDS_CACHE_PATH = RAW_DIR / "vietnam_bonds_full.parquet"
TEST_QUARTERS = {"2099-Q1"}

MIN_HIST_FOR_PERCENTILE = 4  # sao chép compute_quarterly_score()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Nguồn dữ liệu (cache local → fetch live)
# ═══════════════════════════════════════════════════════════════════════════════

def load_bonds() -> pd.DataFrame:
    """Đường cong lợi suất full-history: cache parquet → fetch (CI có mạng)."""
    if BONDS_CACHE_PATH.exists():
        df = pd.read_parquet(BONDS_CACHE_PATH)
        df["date"] = pd.to_datetime(df["date"])
        logger.info(
            f"[BONDS] Cache: {len(df)} ngày, {df['date'].min().date()} → {df['date'].max().date()}"
        )
        return df.sort_values("date").reset_index(drop=True)

    logger.info("[BONDS] Không có cache — fetch fitted_curve_ns_full.json...")
    from src.data.fetcher import fetch_vietnam_bonds
    df = fetch_vietnam_bonds()
    if df is None or len(df) == 0:
        raise SystemExit(
            "[BONDS] Fetch thất bại. Sandbox/local không có mạng thị trường: "
            "chạy trên GitHub Actions hoặc đặt cache tại data/raw/vietnam_bonds_full.parquet."
        )
    return df.sort_values("date").reset_index(drop=True)


def load_m2() -> pd.DataFrame:
    """M2 YoY: manual → ADB KIDB live → fallback committed (data/external/)."""
    from src.data.fetcher import fetch_m2_credit_auto
    df = fetch_m2_credit_auto()
    if df is None or len(df) == 0:
        raise SystemExit("[M2] Không có nguồn M2 nào khả dụng.")
    return df.sort_values("date").reset_index(drop=True)


def load_pepb_features(df_bonds: pd.DataFrame) -> pd.DataFrame:
    """P/E-P/B history + Z-scores (min_periods=252) + EYG (cần vn10y từ bonds)."""
    from src.features.valuation_features import (
        load_market_pepb_history,
        compute_pe_pb_features,
    )
    pepb = load_market_pepb_history()
    if pepb.empty:
        raise SystemExit(
            "[PEPB] Không có dữ liệu P/E-P/B (cache data/processed/ticker_history.parquet "
            "hoặc fetch GitHub raw trên CI)."
        )
    feat = compute_pe_pb_features(
        pepb, df_bonds[["date", "vn10y_yield"]]
    )
    logger.info(
        f"[PEPB] {len(feat)} ngày | pe_zscore đầu tiên: "
        f"{feat.loc[feat['pe_zscore'].notna(), 'date'].min()}"
    )
    return feat.sort_values("date").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Parse input KHÔNG ĐỔI từ chuỗi details cũ (point-in-time được bảo toàn)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_fx_zscore(details: Dict[str, str]) -> Optional[float]:
    m = re.search(r"Z-score = (-?\d+\.\d+)", details.get("usd_vnd", ""))
    return float(m.group(1)) if m else None


def parse_margin_risk(details: Dict[str, str]) -> Optional[float]:
    m = re.search(r"Risk = (\d+)/100", details.get("margin_risk", ""))
    return float(m.group(1)) if m else None


def parse_old_values(details: Dict[str, str]) -> Dict[str, Optional[float]]:
    """Giá trị đã lưu (dùng cho pre-check khớp dữ liệu)."""
    out: Dict[str, Optional[float]] = {}

    m = re.search(r"(-?\d+\.\d+)% → score", details.get("vn1y_yield", ""))
    out["vn1y_yield"] = float(m.group(1)) if m else None

    m = re.search(r"Δ VN1Y = (-?\d+\.\d+)", details.get("ir_trend", ""))
    out["delta_vn1y_yield"] = float(m.group(1)) if m else None

    m = re.search(r"VN10Y (-?\d+\.\d+)% \| Spread (-?\d+\.\d+)%", details.get("vn_bonds", ""))
    if m:
        out["vn10y_yield"] = float(m.group(1))
        out["vn_yield_spread"] = float(m.group(2))
    else:
        out["vn10y_yield"] = None
        out["vn_yield_spread"] = None

    for key, pat in [
        ("pe_zscore", r"Z = (-?\d+\.\d+)"),
        ("pb_zscore", r"Z = (-?\d+\.\d+)"),
        ("eyg_zscore", r"EYG Z-score = (-?\d+\.\d+)"),
    ]:
        m = re.search(pat, details.get(key, ""))
        out[key] = float(m.group(1)) if m else None
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
    bonds: pd.DataFrame,
    m2: pd.DataFrame,
    pepb_feat: pd.DataFrame,
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

    # Bonds: pre-compute delta & spread trên full history (giữ nguyên logic
    # của build_vietnam_bond_features)
    bonds = bonds.sort_values("date").reset_index(drop=True).copy()
    bonds["delta_vn1y_yield"] = bonds["vn1y_yield"].diff()
    bonds["vn_yield_spread"] = bonds["vn10y_yield"] - bonds["vn2y_yield"]

    # ── Pre-check 1: replicate derived fields trên dữ liệu CŨ ────────────────
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
    logger.info(
        f"[PRECHECK] Derived fields trên dữ liệu cũ: {n_match}/{n_check} khớp"
    )
    if n_match < n_check:
        raise SystemExit("[PRECHECK] Logic expanding KHÔNG khớp scorer — dừng.")

    # ── Pre-check 2: dữ liệu tính lại phải TRÙNG giá trị đã lưu ───────────────
    # (bonds ở những quý vốn có bonds; pe/pb z ở những quý vốn có z)
    tol = {"vn1y_yield": 0.005, "delta_vn1y_yield": 0.0005,
           "vn10y_yield": 0.005, "vn_yield_spread": 0.005,
           "pe_zscore": 0.005, "pb_zscore": 0.005}
    b_match, b_check, z_match, z_check = 0, 0, 0, 0
    for q in quarters:
        rec = exports[q]["quarterly_score"]
        as_of = pd.Timestamp(rec["data_as_of"])
        old = parse_old_values(rec["group_details"]["macro_monetary"])
        row = asof_row(bonds, as_of)
        for key in ["vn1y_yield", "delta_vn1y_yield", "vn10y_yield", "vn_yield_spread"]:
            if old[key] is not None:
                b_check += 1
                b_match += int(abs(old[key] - float(row[key])) < tol[key])
        vz = parse_old_values(rec["group_details"]["valuation_leverage"])
        vrow = asof_row(pepb_feat, as_of)
        for key in ["pe_zscore", "pb_zscore"]:
            if vz[key] is not None:
                z_check += 1
                z_match += int(abs(vz[key] - float(vrow[key])) < tol[key])
    logger.info(
        f"[PRECHECK] Bonds tính lại vs đã lưu: {b_match}/{b_check} | "
        f"PE/PB Z tính lại vs đã lưu: {z_match}/{z_check}"
    )
    if b_match < b_check or z_match < z_check:
        raise SystemExit(
            "[PRECHECK] Dữ liệu nguồn KHÔNG khớp giá trị đã lưu — dừng để không ghi đè sai."
        )

    # ── Vòng chính ───────────────────────────────────────────────────────────
    rows, changes, audit = [], [], []
    prior_totals, prior_stds = [], []

    for q in quarters:
        payload = exports[q]
        rec = payload["quarterly_score"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        as_of = pd.Timestamp(rec["data_as_of"])

        old_macro_w = float(rec["group_scores"]["macro_monetary"]["weighted_score"])
        old_macro_raw = float(rec["group_scores"]["macro_monetary"]["raw_score"])
        old_val_w = float(rec["group_scores"]["valuation_leverage"]["weighted_score"])
        old_val_raw = float(rec["group_scores"]["valuation_leverage"]["raw_score"])
        old_total = round(float(rec["total_score"]), 2)
        old_label = rec["label"]

        # 1) MACRO: bonds (as-of) + FX z (giữ cũ) + M2 (as-of backward)
        bond_row = asof_row(bonds, as_of)
        fx_z = parse_fx_zscore(rec["group_details"]["macro_monetary"])
        m2_row = m2[m2["date"] <= as_of]
        m2_val = float(m2_row.iloc[-1]["m2_yoy_pct"]) if len(m2_row) else np.nan
        m2_year = int(m2_row.iloc[-1]["date"].year) if len(m2_row) else None

        df_macro_latest = pd.Series(
            {
                "vn1y_yield": float(bond_row["vn1y_yield"]),
                "delta_vn1y_yield": float(bond_row["delta_vn1y_yield"]),
                "usd_vnd_zscore": fx_z if fx_z is not None else np.nan,
                "m2_yoy_pct": m2_val,
                "vn10y_yield": float(bond_row["vn10y_yield"]),
                "vn_yield_spread": float(bond_row["vn_yield_spread"]),
            },
            dtype=float,
        )
        g_macro = score_macro_monetary(df_macro_latest)

        # 2) VALUATION: chỉ re-score khi có thành phần MỚI (pe/pb/eyg z)
        val_row = asof_row(pepb_feat, as_of)
        vz_old = parse_old_values(rec["group_details"]["valuation_leverage"])
        new_pe = None if val_row is None or pd.isna(val_row["pe_zscore"]) else float(val_row["pe_zscore"])
        new_pb = None if val_row is None or pd.isna(val_row["pb_zscore"]) else float(val_row["pb_zscore"])
        new_eyg = None if val_row is None or pd.isna(val_row["eyg_zscore"]) else float(val_row["eyg_zscore"])
        pe_newly = (vz_old["pe_zscore"] is None) and (new_pe is not None)
        eyg_newly = (vz_old["eyg_zscore"] is None) and (new_eyg is not None)

        g_val = None
        if pe_newly or eyg_newly:
            margin = parse_margin_risk(rec["group_details"]["valuation_leverage"])
            df_val_latest = pd.Series(
                {
                    "headline_pe": float(val_row.get("headline_pe", np.nan)) if pd.notna(val_row.get("headline_pe", np.nan)) else np.nan,
                    "median_pe": float(val_row.get("median_pe", np.nan)) if pd.notna(val_row.get("median_pe", np.nan)) else np.nan,
                    "ex_vingroup_pe": float(val_row.get("ex_vingroup_pe", np.nan)) if pd.notna(val_row.get("ex_vingroup_pe", np.nan)) else np.nan,
                    "headline_pb": float(val_row.get("headline_pb", np.nan)) if pd.notna(val_row.get("headline_pb", np.nan)) else np.nan,
                    "median_pb": float(val_row.get("median_pb", np.nan)) if pd.notna(val_row.get("median_pb", np.nan)) else np.nan,
                    "ex_vingroup_pb": float(val_row.get("ex_vingroup_pb", np.nan)) if pd.notna(val_row.get("ex_vingroup_pb", np.nan)) else np.nan,
                    "pe_zscore": np.nan if new_pe is None else new_pe,
                    "pb_zscore": np.nan if new_pb is None else new_pb,
                    "eyg_zscore": np.nan if new_eyg is None else new_eyg,
                    "margin_risk_score": np.nan if margin is None else margin,
                    # Composite (rank-based) từ compute_pe_pb_features — scorer
                    # blend 70/30 calculated+composite; phải truyền để khớp pipeline
                    "valuation_composite_score": (
                        float(val_row["valuation_composite_score"])
                        if pd.notna(val_row.get("valuation_composite_score", np.nan)) else np.nan
                    ),
                },
                dtype=float,
            )
            g_val = score_valuation_leverage(df_val_latest)

        # 3) Tổng điểm mới: tổng − weighted cũ + weighted mới (các trụ cột đổi)
        new_total = round(old_total - old_macro_w + g_macro["weighted_score"], 2)
        if g_val is not None:
            new_total = round(new_total - old_val_w + g_val["weighted_score"], 2)
        label, emoji, desc, alloc = get_score_label(new_total)

        # 4) Derived fields — expanding trên giá trị MỚI (không look-ahead)
        group_raw = {k: float(v["raw_score"]) for k, v in rec["group_scores"].items()}
        group_raw["macro_monetary"] = float(g_macro["raw_score"])
        if g_val is not None:
            group_raw["valuation_leverage"] = float(g_val["raw_score"])
        fund_raw = {k: v for k, v in group_raw.items() if k not in ("quant_model", "ml_forecast")}
        most_div = max(fund_raw, key=lambda k: abs(fund_raw[k] - 50))
        arr = np.array(list(group_raw.values()), dtype=float)
        pstd = round(float(np.std(arr, ddof=1)), 2)
        prange = round(float(np.max(arr) - np.min(arr)), 2)
        pctl = derive_percentile(new_total, prior_totals)
        disp = derive_dispersion(pstd, prior_stds)

        # 5) Cập nhật JSON record
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
        rec["group_scores"]["macro_monetary"] = {
            "raw_score": g_macro["raw_score"], "weighted_score": g_macro["weighted_score"],
        }
        merged = dict(rec["group_details"]["macro_monetary"])
        merged.update(g_macro["details"])
        rec["group_details"]["macro_monetary"] = merged
        rec["group_rationale"]["macro_monetary"] = g_macro["rationale"]
        if g_val is not None:
            rec["group_scores"]["valuation_leverage"] = {
                "raw_score": g_val["raw_score"], "weighted_score": g_val["weighted_score"],
            }
            merged = dict(rec["group_details"]["valuation_leverage"])
            merged.update(g_val["details"])
            rec["group_details"]["valuation_leverage"] = merged
            rec["group_rationale"]["valuation_leverage"] = g_val["rationale"]
        payload.setdefault("metadata", {})["market_data_backfill"] = {
            "applied_at": now_str,
            "bonds_source": "VN_Bond_Yield_pipeline — fitted_curve_ns_full.json (2012→nay, Nelson-Siegel)",
            "m2_source": "ADB KIDB FM2_PTX_PS.VIE (nguồn SBV) 2000-2024 + GSO Q4/2025 (22/12/2025)",
            "pepb_eyg": "min_periods Z-score 252 phiên (từ 2.5 năm); EYG wired qua df_macro",
        }

        # 6) Row parquet mới
        row = hist[hist["quarter"] == q].iloc[0].to_dict()
        row.update({
            "date_computed": now_str,
            "total_score": new_total,
            "label": label,
            "score_macro_monetary": g_macro["weighted_score"],
            "percentile_label": pctl["percentile_label"],
            "pillar_std": pstd,
            "pillar_range": prange,
            "dispersion_level": disp,
        })
        if g_val is not None:
            row["score_valuation_leverage"] = g_val["weighted_score"]
        rows.append(row)

        audit.append({
            "quarter": q,
            "as_of": rec["data_as_of"],
            "bonds": {
                "vn1y_yield": round(float(bond_row["vn1y_yield"]), 4),
                "delta_vn1y_yield": round(float(bond_row["delta_vn1y_yield"]), 6),
                "vn10y_yield": round(float(bond_row["vn10y_yield"]), 4),
                "vn_yield_spread": round(float(bond_row["vn_yield_spread"]), 4),
                "bond_date": str(pd.Timestamp(bond_row["date"]).date()),
            },
            "m2": {"year": m2_year, "m2_yoy_pct": None if pd.isna(m2_val) else round(m2_val, 2)},
            "fx_zscore": fx_z,
            "pepb_z": {
                "pe": new_pe, "pb": new_pb, "eyg": new_eyg,
                "composite": (
                    None if val_row is None or pd.isna(val_row.get("valuation_composite_score", np.nan))
                    else round(float(val_row["valuation_composite_score"]), 2)
                ),
            },
            "rescored": {
                "macro_monetary": True,
                "valuation_leverage": g_val is not None,
            },
        })
        changes.append({
            "quarter": q,
            "m2": None if pd.isna(m2_val) else m2_val,
            "vn1y": round(float(bond_row["vn1y_yield"]), 2),
            "macro_raw_old": old_macro_raw, "macro_raw_new": float(g_macro["raw_score"]),
            "val_changed": g_val is not None,
            "val_raw_old": old_val_raw,
            "val_raw_new": None if g_val is None else float(g_val["raw_score"]),
            "pe_z": new_pe, "eyg_z": new_eyg,
            "total_old": old_total, "total_new": new_total,
            "label_old": old_label, "label_new": label,
            "pctl": pctl["percentile_label"], "disp": disp,
        })
        prior_totals.append(new_total)
        prior_stds.append(pstd)

    # ── Bảng tóm tắt trung thực ───────────────────────────────────────────────
    print("\n" + "=" * 118)
    print("MARKET-DATA BACKFILL — SO SÁNH TRƯỚC / SAU (macro 25% + valuation 20% khi có thành phần mới)")
    print("=" * 118)
    print(f"{'Quarter':<10}{'M2 YoY':>8}{'VN1Y%':>7}{'Macro raw (old→new)':>22}"
          f"{'Val raw (old→new)':>21}{'Total (old→new)':>18}{'Label (old→new)':>22}{'Pctl':>10}")
    for c in changes:
        m2_s = f"{c['m2']:.1f}" if c["m2"] is not None else "N/A"
        mac_s = f"{c['macro_raw_old']:.1f}→{c['macro_raw_new']:.1f}"
        val_s = (f"{c['val_raw_old']:.1f}→{c['val_raw_new']:.1f}" if c["val_changed"] else f"{c['val_raw_old']:.1f} (giữ)")
        tot_s = f"{c['total_old']:.2f}→{c['total_new']:.2f}"
        lab_s = f"{c['label_old']}→{c['label_new']}" if c["label_old"] != c["label_new"] else c["label_new"]
        print(f"{c['quarter']:<10}{m2_s:>8}{c['vn1y']:>7.2f}{mac_s:>22}{val_s:>21}"
              f"{tot_s:>18}{lab_s:>22}{c['pctl']:>10}")
    n_label = sum(1 for c in changes if c["label_old"] != c["label_new"])
    n_val = sum(1 for c in changes if c["val_changed"])
    n_pe = sum(1 for c in changes if c["pe_z"] is not None)
    n_eyg = sum(1 for c in changes if c["eyg_z"] is not None)
    print("-" * 118)
    print(
        f"M2 thật: 24/24 | Bonds thật: 24/24 (7 quý thay default) | "
        f"Valuation re-score: {n_val}/24 (pe/pb z mới ở {n_pe}, eyg z mới ở {n_eyg}) | "
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
            "description": "Inputs dữ liệu thật dùng re-score macro_monetary + "
                           "valuation_leverage trong backfill 09/2026 (bonds full-history, "
                           "M2 ADB/GSO, PE/PB/EYG Z min_periods=252)",
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
        "   python scripts/backfill_calibrated_scores.py   # tầng calibrated theo total mới\n"
        "   python scripts/rebuild_html.py                 # HTML + validators + Excel\n"
        "   python scripts/update_readme_results.py        # README"
    )
    return new_hist


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill bonds full-history + M2 (ADB/GSO) + PE/PB/EYG Z-score"
    )
    ap.add_argument("--dry-run", action="store_true", help="Chỉ in so sánh, không ghi")
    args = ap.parse_args()

    bonds = load_bonds()
    m2 = load_m2()
    pepb_feat = load_pepb_features(bonds)

    backfill_all(bonds, m2, pepb_feat, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
