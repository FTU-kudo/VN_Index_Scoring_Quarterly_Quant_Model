"""
backfill_calibrated_scores.py — Backfill Calibrated Action Signal cho lịch sử
===============================================================================
Idempotent: chạy nhiều lần cho cùng kết quả. Chỉ THÊM cột/field calibrated
vào dữ liệu lịch sử — KHÔNG sửa đổi điểm thô (total_score) hay bất kỳ cột
nào khác trong parquet / JSON exports.

Việc làm:
  1. data/scores/quarterly_scores_history.parquet:
     - LỌC BỎ row test 2099-Q1 (nếu có — di sản của pytest trước fix test hygiene)
     - Thêm 2 cột: calibrated_score, calibrated_label
     - Tính theo expanding window: quý Q chỉ dùng các quý TRƯỚC Q (point-in-time,
       không look-ahead) — giống hệt logic compute_quarterly_score() lúc chạy live.
  2. output/exports/score_*.json:
     - Chèn field calibrated_* + calibration_* vào record quarterly_score
       (cùng schema như compute_quarterly_score() xuất ra).

Chạy:  python scripts/backfill_calibrated_scores.py
"""

import json
import logging
import os
import sys
from pathlib import Path

sys.path.append(os.getcwd())

import pandas as pd

from src.utils.config import SCORES_DIR, EXPORTS_DIR, SCORE_CALIBRATION, get_score_label
from src.scoring.quarterly_scorer import calibrate_total_score

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_calibrated")

HISTORY_PATH = SCORES_DIR / "quarterly_scores_history.parquet"
TEST_QUARTERS = {"2099-Q1"}   # row test không bao giờ thuộc lịch sử thật


def backfill_parquet() -> pd.DataFrame:
    """Thêm/cập nhật cột calibrated_score + calibrated_label trong parquet."""
    if not HISTORY_PATH.exists():
        raise FileNotFoundError(f"Missing {HISTORY_PATH}")

    df = pd.read_parquet(HISTORY_PATH)

    # ── Lọc row test (idempotent + bảo vệ dữ liệu thật) ─────────────────────
    n_test = int(df["quarter"].isin(TEST_QUARTERS).sum())
    if n_test:
        logger.warning(f"[BACKFILL] Dropping {n_test} test row(s) {sorted(df[df['quarter'].isin(TEST_QUARTERS)]['quarter'])}")
        df = df[~df["quarter"].isin(TEST_QUARTERS)].copy()

    df = df.sort_values("quarter").reset_index(drop=True)
    if df.empty:
        raise ValueError("History parquet is empty — nothing to backfill")

    # ── Expanding window: mỗi quý chỉ nhìn các quý TRƯỚC nó ─────────────────
    cal_scores, cal_labels = [], []
    diagnostics = []
    for i, row in df.iterrows():
        q = row["quarter"]
        total = float(row["total_score"])
        hist = df.loc[df["quarter"] < q, "total_score"].tolist()
        hist = [h for h in hist if h is not None and not pd.isna(h)]
        res = calibrate_total_score(total, hist)
        cal_scores.append(res["calibrated_score"])
        if res["applied"]:
            cal_labels.append(get_score_label(res["calibrated_score"])[0])
        else:
            cal_labels.append(get_score_label(total)[0])   # fallback: nhãn raw
        diagnostics.append((q, total, res))

    df["calibrated_score"] = cal_scores
    df["calibrated_label"] = cal_labels
    df.to_parquet(HISTORY_PATH, index=False)
    logger.info(f"[BACKFILL] Parquet updated -> {HISTORY_PATH} ({len(df)} quarters)")

    return df


def backfill_jsons(df: pd.DataFrame) -> int:
    """Chèn field calibrated_* vào toàn bộ output/exports/score_*.json."""
    updated = 0
    for q in df["quarter"]:
        path = EXPORTS_DIR / f"score_{q.replace('-', '_')}.json"
        if not path.exists():
            logger.warning(f"[BACKFILL] No export JSON for {q} — skipped")
            continue

        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        rec = payload.get("quarterly_score")
        if not isinstance(rec, dict):
            logger.warning(f"[BACKFILL] {path.name} has no quarterly_score record — skipped")
            continue

        row = df[df["quarter"] == q].iloc[0]
        total = float(row["total_score"])
        hist = df.loc[df["quarter"] < q, "total_score"].tolist()
        hist = [h for h in hist if h is not None and not pd.isna(h)]
        res = calibrate_total_score(total, hist)

        # Nhãn theo single source of truth get_score_label()
        if res["applied"]:
            cal_label, cal_emoji, cal_desc, cal_alloc = get_score_label(res["calibrated_score"])
        else:
            cal_label, cal_emoji, cal_desc, cal_alloc = get_score_label(total)

        rec["calibrated_score"] = round(float(res["calibrated_score"]), 2)
        rec["calibrated_label"] = cal_label
        rec["calibrated_emoji"] = cal_emoji
        rec["calibrated_description"] = cal_desc
        rec["calibrated_allocation"] = cal_alloc
        rec["calibration_applied"] = bool(res["applied"])
        rec["calibration_z"] = res["calibration_z"]
        rec["calibration_hist_mean"] = res["calibration_hist_mean"]
        rec["calibration_hist_std"] = res["calibration_hist_std"]
        rec["calibration_n_history"] = res["calibration_n_history"]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        updated += 1

    logger.info(f"[BACKFILL] {updated} JSON exports updated in {EXPORTS_DIR}")
    return updated


def main():
    logger.info(f"[BACKFILL] SCORE_CALIBRATION = {SCORE_CALIBRATION}")
    df = backfill_parquet()
    backfill_jsons(df)

    # ── Báo cáo phân bố nhãn (trung thực, không tô hồng) ────────────────────
    raw_dist = df["label"].value_counts().to_dict()
    cal_dist = df["calibrated_label"].value_counts().to_dict()
    print("\n" + "=" * 68)
    print("CALIBRATED ACTION SIGNAL — BACKFILL SUMMARY")
    print("=" * 68)
    print(f"Quarters: {len(df)} ({df['quarter'].iloc[0]} .. {df['quarter'].iloc[-1]})")
    print(f"Raw label distribution      : {raw_dist}")
    print(f"Calibrated label distribution: {cal_dist}")
    print("-" * 68)
    n_applied = 0
    print(f"{'Quarter':10s} {'Raw':>7s} {'RawLbl':>8s} {'Cal':>7s} {'CalLbl':>10s} {'z':>7s}")
    for _, r in df.iterrows():
        q = r["quarter"]
        hist = df.loc[df["quarter"] < q, "total_score"].tolist()
        res = calibrate_total_score(float(r["total_score"]), hist)
        if res["applied"]:
            n_applied += 1
        z = f"{res['calibration_z']:+.2f}" if res["applied"] else "   —"
        print(f"{q:10s} {r['total_score']:7.2f} {r['label']:>8s} "
              f"{r['calibrated_score']:7.2f} {r['calibrated_label']:>10s} {z:>7s}")
    print("-" * 68)
    print(f"Calibration applied (expanding z) : {n_applied}/{len(df)} quarters "
          f"(first {SCORE_CALIBRATION['min_history']} quarters keep raw — insufficient history)")
    print("=" * 68)


if __name__ == "__main__":
    main()
