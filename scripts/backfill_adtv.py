"""
backfill_adtv.py — Backfill chỉ báo ADTV (Market Structure) cho 24 quý lịch sử
===============================================================================
Vấn đề: `run_quarterly.py` TRƯỚC ĐÂY không bao giờ truyền `adtv_change_pct` cho
`score_market_structure()` dù scorer hỗ trợ sẵn → chỉ báo ADTV N/A ở 24/24 quý
(trụ cột Market Structure chỉ còn FTSE + rebalancing + ETF flow).

Fix (commit này): `run_quarterly.py` giờ tính ADTV point-in-time
    ADTV(Q−1) / ADTV(Q−2) − 1   (Q = quý đang chấm, chỉ dùng 2 quý ĐÃ KẾT THÚC)
từ cột `volume` của chính OHLCV VN-Index đã fetch qua vnstock (VCI).

Script này áp dụng fix cho LỊCH SỬ mà không chạy lại toàn pipeline (ML/VAR/
macro... không đổi). Với mỗi quý (đi TỪ XƯA ĐẾN MỚI để percentile expanding
không look-ahead):
  1. Đọc JSON export cũ → parse lại input của trụ cột market_structure
     (FTSE status, months-to-rebalancing, ETF z) từ chuỗi details.
  2. Tính ADTV change point-in-time từ OHLCV (window Q−1, Q−2).
  3. Re-score ĐÚNG trụ cột market_structure bằng scorer hiện hành
     (renormalize khi thiếu cấu phần — ADTV thật thay cho placeholder).
  4. Cập nhật total_score, label, most_divergent_pillar, pillar_std/range,
     percentile_label/p15/p85, dispersion_level — tuần tự expanding window.
  5. Ghi lại parquet + JSON export; lưu cache audit data/scores/vnindex_quarterly_adtv.json.

Sau script này PHẢI chạy (workflow đã nối sẵn):
  python scripts/backfill_calibrated_scores.py   # tầng calibrated theo total mới
  python scripts/rebuild_html.py                 # HTML + validators + Excel
  python scripts/update_readme_results.py        # README

Sandbox không có mạng thị trường → chạy trên GitHub Actions:
  .github/workflows/backfill_adtv.yml (workflow_dispatch)

Chạy local (nếu đã có data/raw/vnindex_ohlcv.parquet):
  python scripts/backfill_adtv.py            # ghi thật
  python scripts/backfill_adtv.py --dry-run  # chỉ in bảng so sánh
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

sys.path.append(os.getcwd())

from src.utils.config import SCORES_DIR, EXPORTS_DIR, RAW_DIR, get_score_label
from src.scoring.quarterly_scorer import score_market_structure
from src.features.market_structure_features import (
    compute_adtv_change_pct,
    compute_quarterly_adtv,
    parse_market_structure_inputs_from_details,
    previous_quarter,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("backfill_adtv")

HISTORY_PATH = SCORES_DIR / "quarterly_scores_history.parquet"
ADTV_CACHE_PATH = SCORES_DIR / "vnindex_quarterly_adtv.json"
TEST_QUARTERS = {"2099-Q1"}

# Percentile logic sao chép NGUYÊN VẸN compute_quarterly_score()
# (expanding, ≥4 quý TRƯỚC, p15/p85 cho total & p33/p67 cho pillar_std).
MIN_HIST_FOR_PERCENTILE = 4


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Dữ liệu OHLCV (volume) — nguồn của ADTV
# ═══════════════════════════════════════════════════════════════════════════════

def load_ohlcv(force_fetch: bool = False) -> pd.DataFrame:
    """Cache parquet nếu có; không thì fetch qua vnstock (chỉ chạy được trên CI)."""
    cache_path = RAW_DIR / "vnindex_ohlcv.parquet"
    if not force_fetch and cache_path.exists():
        df = pd.read_parquet(cache_path)
        logger.info(f"[OHLCV] Cache: {len(df)} phiên, {df['date'].min().date()} → {df['date'].max().date()}")
        return df

    logger.info("[OHLCV] Không có cache (hoặc --force-fetch) — tải qua vnstock...")
    from src.data.fetcher import fetch_vnindex_ohlcv
    try:
        df = fetch_vnindex_ohlcv(use_cache=not force_fetch)
    except Exception as e:
        raise SystemExit(
            f"[OHLCV] Fetch thất bại ({e}).\n"
            f"  → Sandbox/local không có mạng thị trường: hãy chạy GitHub Actions "
            f"`.github/workflows/backfill_adtv.yml` (workflow_dispatch)."
        )
    if df is None or len(df) == 0:
        raise SystemExit("[OHLCV] Fetch trả về DataFrame rỗng.")
    return df


def validate_volume(ohlcv: pd.DataFrame, quarters_needed) -> None:
    """Fail loudly (exit ≠ 0) nếu cột volume không dùng được cho index."""
    if "volume" not in ohlcv.columns:
        raise SystemExit("[OHLCV] KHÔNG có cột volume — không tính được ADTV.")
    vol = pd.to_numeric(ohlcv["volume"], errors="coerce")
    n_valid = int((vol > 0).sum())
    logger.info(
        f"[OHLCV] volume: {n_valid}/{len(ohlcv)} phiên > 0 "
        f"({n_valid/len(ohlcv):.0%} coverage)"
    )
    if n_valid < 100:
        raise SystemExit(
            f"[OHLCV] Cột volume gần như rỗng ({n_valid} phiên > 0) — "
            "nguồn không cung cấp khối lượng cho VN-Index. Dừng để không ghi đè sai."
        )
    missing = [q for q in quarters_needed if compute_quarterly_adtv(ohlcv, q) is None]
    if missing:
        raise SystemExit(
            f"[ADTV] Thiếu ADTV cho các quý: {missing} — volume không phủ đủ window "
            "(cần ≥10 phiên/quý). Dừng để không ghi đè sai."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Replicate derived fields của compute_quarterly_score (expanding, no look-ahead)
# ═══════════════════════════════════════════════════════════════════════════════

def derive_percentile(total: float, prior_totals) -> dict:
    """Sao chép logic percentile_label của scorer (expanding, ≥4 quý TRƯỚC)."""
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
    """Sao chép logic dispersion_level của scorer (p33/p67 expanding, ≥4 quý)."""
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
# 3. Backfill chính
# ═══════════════════════════════════════════════════════════════════════════════

def backfill_all(
    ohlcv: Optional[pd.DataFrame],
    dry_run: bool = False,
    history_path: Path = HISTORY_PATH,
    exports_dir: Path = EXPORTS_DIR,
    adtv_cache_path: Path = ADTV_CACHE_PATH,
    adtv_changes: Optional[Dict[str, Optional[float]]] = None,
) -> pd.DataFrame:
    """
    ohlcv        : DataFrame OHLCV (cần cột volume) — hoặc None khi truyền
                   adtv_changes dựng sẵn (chế độ offline --from-cache).
    adtv_changes : {quarter: change_pct} — nếu có thì bỏ qua ohlcv.
    """
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

    if adtv_changes is None:
        # Window ADTV cần phủ: Q−1 và Q−2 của MỌI quý trong lịch sử
        need = sorted({w for q in quarters for w in (previous_quarter(q), previous_quarter(previous_quarter(q)))})
        logger.info(f"[ADTV] Windows cần phủ: {need[0]} → {need[-1]} ({len(need)} quý)")
        validate_volume(ohlcv, need)
    else:
        missing = [q for q in quarters if q not in adtv_changes]
        if missing:
            raise SystemExit(f"[BACKFILL] Cache ADTV thiếu các quý: {missing}")
        logger.info(f"[ADTV] Dùng cache {len(adtv_changes)} quý — không cần OHLCV (offline)")

    # ── Pre-check: replicate derived fields trên dữ liệu CŨ ──────────────────
    # Nếu trùng khớp stored JSON → logic expanding là bản sao trung thực của scorer.
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
        f"[PRECHECK] Replicate derived fields trên dữ liệu cũ: {n_match}/{n_check} khớp "
        f"({n_match/n_check:.0%}) — xác nhận logic expanding sao chép đúng scorer"
    )

    # ── Vòng chính: re-score market_structure + ADTV, ascending ──────────────
    rows, changes, audit = [], [], []
    prior_totals, prior_stds = [], []

    # Chế độ from-cache: giữ lại windows cũ cho audit (không có OHLCV để tính lại)
    old_cache_windows: Dict[str, Dict] = {}
    if adtv_changes is not None and adtv_cache_path.exists():
        try:
            _old = json.load(open(adtv_cache_path, encoding="utf-8"))
            old_cache_windows = {q: a.get("windows", {}) for q, a in _old.get("quarters", {}).items()}
        except Exception as e:
            logger.warning(f"[BACKFILL] Không đọc được cache cũ ({e}) — audit sẽ thiếu windows")

    for q in quarters:
        payload = exports[q]
        rec = payload["quarterly_score"]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Giữ giá trị cũ cho bảng so sánh TRƯỚC khi mutate
        old_ms_weighted = float(rec["group_scores"]["market_structure"]["weighted_score"])
        old_ms_raw = float(rec["group_scores"]["market_structure"]["raw_score"])
        old_total = round(float(rec["total_score"]), 2)
        old_label = rec["label"]

        # 1) Input cũ của trụ cột market_structure
        inp = parse_market_structure_inputs_from_details(rec["group_details"]["market_structure"])
        if inp["months_to_next_rebalancing"] is None:
            raise SystemExit(f"[BACKFILL] {q}: không parse được months_to_next_rebalancing — dừng.")

        # 2) ADTV point-in-time — từ OHLCV hoặc từ cache (--from-cache)
        q1, q2 = previous_quarter(q), previous_quarter(previous_quarter(q))
        if adtv_changes is not None:
            adtv_change = adtv_changes[q]
            a1 = a2 = None
        else:
            adtv_change = compute_adtv_change_pct(ohlcv, q)
            a1 = compute_quarterly_adtv(ohlcv, q1)
            a2 = compute_quarterly_adtv(ohlcv, q2)

        # 3) Re-score trụ cột bằng scorer hiện hành
        df_latest = pd.Series(
            {"etf_flow_q_zscore_live": inp["etf_flow_q_zscore_live"]},
            dtype=float,
        )
        g6 = score_market_structure(
            df_latest=df_latest,
            ftse_upgrade_status=inp["ftse_upgrade_status"] or "unknown",
            months_to_next_rebalancing=inp["months_to_next_rebalancing"],
            adtv_change_pct=adtv_change,
        )

        # 4) Tổng điểm mới: chỉ trụ cột market_structure thay đổi (weight 10%)
        new_total = round(old_total - old_ms_weighted + g6["weighted_score"], 2)
        label, emoji, desc, alloc = get_score_label(new_total)

        # 5) Derived fields — expanding trên giá trị MỚI (không look-ahead)
        group_raw = {k: float(v["raw_score"]) for k, v in rec["group_scores"].items()}
        group_raw["market_structure"] = float(g6["raw_score"])
        fund_raw = {k: v for k, v in group_raw.items() if k not in ("quant_model", "ml_forecast")}
        most_div = max(fund_raw, key=lambda k: abs(fund_raw[k] - 50))
        arr = np.array(list(group_raw.values()), dtype=float)
        pstd = round(float(np.std(arr, ddof=1)), 2)
        prange = round(float(np.max(arr) - np.min(arr)), 2)
        pctl = derive_percentile(new_total, prior_totals)
        disp = derive_dispersion(pstd, prior_stds)

        # 6) Cập nhật JSON record (giữ mọi field khác — metadata, model outputs)
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
        rec["adtv_change_pct"] = None if adtv_change is None else round(adtv_change, 6)
        rec["group_scores"]["market_structure"] = {
            "raw_score": g6["raw_score"], "weighted_score": g6["weighted_score"],
        }
        # details: dict mới thắng, giữ key phụ cũ (vd etf_flow_q_ytd)
        merged_details = dict(rec["group_details"]["market_structure"])
        merged_details.update(g6["details"])
        rec["group_details"]["market_structure"] = merged_details
        rec["group_rationale"]["market_structure"] = g6["rationale"]
        payload.setdefault("metadata", {})["adtv_backfill"] = {
            "applied_at": now_str,
            "source": "vnindex_ohlcv.volume (vnstock VCI)",
            "definition": "ADTV(Q-1)/ADTV(Q-2) - 1, point-in-time",
        }

        # 7) Row parquet mới
        row = hist[hist["quarter"] == q].iloc[0].to_dict()
        row.update({
            "date_computed": now_str,
            "total_score": new_total,
            "label": label,
            "score_market_structure": g6["weighted_score"],
            "percentile_label": pctl["percentile_label"],
            "pillar_std": pstd,
            "pillar_range": prange,
            "dispersion_level": disp,
        })
        rows.append(row)

        if a1 is not None or q in old_cache_windows:
            windows = {
                q1: ({"adtv": round(a1["adtv"], 2), "n_sessions": a1["n_sessions"]} if a1
                     else old_cache_windows.get(q, {}).get(q1)),
                q2: ({"adtv": round(a2["adtv"], 2), "n_sessions": a2["n_sessions"]} if a2
                     else old_cache_windows.get(q, {}).get(q2)),
            }
        else:
            windows = {q1: None, q2: None}
        audit.append({
            "quarter": q,
            "adtv_change_pct": None if adtv_change is None else round(adtv_change, 6),
            "windows": windows,
        })
        changes.append({
            "quarter": q, "adtv": adtv_change,
            "ms_raw_old": old_ms_raw, "ms_raw": float(g6["raw_score"]),
            "total_old": old_total, "total_new": new_total,
            "label_old": old_label, "label_new": label,
            "pctl": pctl["percentile_label"], "disp": disp,
        })
        prior_totals.append(new_total)
        prior_stds.append(pstd)

    # ── Bảng tóm tắt trung thực ───────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("ADTV BACKFILL — SO SÁNH TRƯỚC / SAU (trụ cột Market Structure & FTSE, weight 10%)")
    print("=" * 100)
    print(f"{'Quarter':<10}{'ADTV QoQ':>10}{'MS raw (old→new)':>20}{'Total (old→new)':>19}"
          f"{'Label (old→new)':>20}{'Pctl':>13}{'Disp':>7}")
    for c in changes:
        adtv_s = f"{c['adtv']:+.1%}" if c["adtv"] is not None else "N/A"
        ms_s = f"{c['ms_raw_old']:.1f}→{c['ms_raw']:.1f}"
        tot_s = f"{c['total_old']:.2f}→{c['total_new']:.2f}"
        lab_s = f"{c['label_old']}→{c['label_new']}" if c["label_old"] != c["label_new"] else c["label_new"]
        print(f"{c['quarter']:<10}{adtv_s:>10}{ms_s:>20}{tot_s:>19}{lab_s:>20}{c['pctl']:>13}{c['disp']:>7}")
    n_adtv = sum(1 for c in changes if c["adtv"] is not None)
    n_label = sum(1 for c in changes if c["label_old"] != c["label_new"])
    print("-" * 100)
    print(f"ADTV có dữ liệu: {n_adtv}/{len(changes)} quý | Label raw đổi: {n_label}/{len(changes)}")

    if dry_run:
        print("\n[DRY-RUN] Không ghi gì. Bỏ --dry-run để áp dụng.")
        return pd.DataFrame(rows)

    # ── Ghi parquet + cache ──────────────────────────────────────────────────
    new_hist = pd.DataFrame(rows)
    # Giữ nguyên bộ cột của file cũ (calibrated_* giữ giá trị cũ tạm —
    # backfill_calibrated_scores.py tính lại NGAY sau theo total mới)
    new_hist = new_hist[[c for c in hist.columns if c in new_hist.columns]]
    new_hist.to_parquet(history_path, index=False)
    logger.info(f"[BACKFILL] Parquet updated → {history_path} ({len(new_hist)} quarters)")

    with open(adtv_cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "description": "ADTV (avg daily volume) theo quý — từ vnindex_ohlcv.volume; "
                           "change = ADTV(Q-1)/ADTV(Q-2)-1 dùng cho quý Q (point-in-time)",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "quarters": {a["quarter"]: a for a in audit},
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"[BACKFILL] ADTV audit cache → {adtv_cache_path}")

    # Ghi JSON exports SAU cùng (đã mutate payload trong vòng lặp)
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
    ap = argparse.ArgumentParser(description="Backfill ADTV cho market_structure pillar")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ in so sánh, không ghi")
    ap.add_argument("--force-fetch", action="store_true",
                    help="Bỏ qua cache OHLCV local, tải lại từ vnstock")
    ap.add_argument("--from-cache", action="store_true",
                    help="Dùng adtv_change_pct từ data/scores/vnindex_quarterly_adtv.json "
                         "(offline — không cần OHLCV/mạng; hữu ích khi cần refresh label "
                         "hoặc chạy lại derived fields)")
    args = ap.parse_args()

    adtv_changes = None
    if args.from_cache:
        if not ADTV_CACHE_PATH.exists():
            raise SystemExit(
                f"[BACKFILL] Missing {ADTV_CACHE_PATH} — chạy lần đầu với OHLCV "
                "(trên CI hoặc máy có mạng) trước khi dùng --from-cache."
            )
        cache = json.load(open(ADTV_CACHE_PATH, encoding="utf-8"))
        adtv_changes = {q: a["adtv_change_pct"] for q, a in cache["quarters"].items()}
        logger.info(f"[BACKFILL] --from-cache: {len(adtv_changes)} quý từ cache")
        ohlcv = None
    else:
        ohlcv = load_ohlcv(force_fetch=args.force_fetch)

    backfill_all(ohlcv, dry_run=args.dry_run, adtv_changes=adtv_changes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
