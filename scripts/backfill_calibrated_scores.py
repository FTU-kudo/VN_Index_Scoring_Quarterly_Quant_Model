"""
backfill_calibrated_scores.py — Backfill Calibrated Action Signal cho lịch sử
===============================================================================
Idempotent: chạy nhiều lần cho cùng kết quả. Chỉ THAY ĐỔI lớp calibrated
(calibrated_* + calibration_*) trong dữ liệu lịch sử — KHÔNG bao giờ chạm điểm
thô (total_score), pillar scores hay inputs của bất kỳ quý nào.

Pipeline (tuần tự tăng dần theo quarter — bất biến point-in-time):
  1. data/scores/quarterly_scores_history.parquet:
     - LỌC BỎ row test 2099-Q1 (nếu có)
     - Cập nhật 2 cột: calibrated_score, calibrated_label theo
       src/scoring/calibration_rebuild.calibrate_history_sequentially()
       (expanding window: quý Q chỉ dùng RAW của các quý TRƯỚC Q).
  2. output/exports/score_*.json:
     - Cập nhật field calibrated_* + calibration_* trong record quarterly_score
     - Cập nhật provenance metadata: generated_at, git_commit, config_hash,
       model_hash, status (FINAL/PROVISIONAL theo quy tắc tổng quát,
       không hardcode quý), calibration_method.

Chạy:  python scripts/backfill_calibrated_scores.py
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(os.getcwd())

import pandas as pd

from src.utils.config import SCORES_DIR, EXPORTS_DIR, SCORE_CALIBRATION, MODEL_VERSION
from src.utils.dates import resolve_publication_status
from src.scoring.calibration_rebuild import calibrate_history_sequentially

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_calibrated")

HISTORY_PATH = SCORES_DIR / "quarterly_scores_history.parquet"
TEST_QUARTERS = {"2099-Q1"}   # row test không bao giờ thuộc lịch sử thật


def _provenance_hashes(rec: dict) -> tuple[str, str]:
    """config_hash/model_hash giống hệt logic export_score_json — tái dùng để
    provenance của JSON sau backfill phản chiếu đúng mã hiện hành."""
    config_snapshot = rec.get("model_config", {}) or {}
    config_hash = hashlib.sha256(
        json.dumps(config_snapshot, sort_keys=True, default=str).encode()
    ).hexdigest()
    scorer_path = Path("src/scoring/quarterly_scorer.py")
    model_hash = hashlib.sha256(scorer_path.read_bytes()).hexdigest()
    return config_hash, model_hash


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def build_calibrated_history(df: pd.DataFrame) -> pd.DataFrame:
    """Tính lớp calibrated tuần tự từ cột total_score của lịch sử parquet."""
    df = df.copy()
    df = df[~df["quarter"].isin(TEST_QUARTERS)].sort_values("quarter").reset_index(drop=True)
    rows = [{"quarter": q, "total_score": s} for q, s in zip(df["quarter"], df["total_score"])]
    cal = calibrate_history_sequentially(rows)
    cal_df = pd.DataFrame(cal)
    for col in ("calibrated_score", "calibrated_label", "calibration_applied",
                "calibration_z", "calibration_z_raw", "calibration_hist_mean",
                "calibration_hist_std", "calibration_std_effective",
                "calibration_n_history"):
        df[col] = cal_df[col].values
    return df


def backfill_parquet() -> pd.DataFrame:
    """Cập nhật cột calibrated_* trong parquet lịch sử (in-place file)."""
    if not HISTORY_PATH.exists():
        raise FileNotFoundError(f"Missing {HISTORY_PATH}")

    df = pd.read_parquet(HISTORY_PATH)
    n_test = int(df["quarter"].isin(TEST_QUARTERS).sum())
    if n_test:
        logger.warning(f"[BACKFILL] Dropping {n_test} test row(s) 2099-Q1")
    df = build_calibrated_history(df)
    if df.empty:
        raise ValueError("History parquet is empty — nothing to backfill")
    df.to_parquet(HISTORY_PATH, index=False)
    logger.info(f"[BACKFILL] Parquet updated -> {HISTORY_PATH} ({len(df)} quarters)")
    return df


def backfill_jsons(df: pd.DataFrame) -> int:
    """Cập nhật field calibrated_* + provenance trong toàn bộ score_*.json."""
    updated = 0
    cal_by_quarter = {
        r["quarter"]: r for r in calibrate_history_sequentially(
            [{"quarter": q, "total_score": s} for q, s in zip(df["quarter"], df["total_score"])]
        )
    }
    generated_at = datetime.now().isoformat()
    git_head = _git_commit()

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

        r = cal_by_quarter[q]
        # ── Lớp calibrated (riêng, KHÔNG đụng raw) ──────────────────────────
        for k in ("calibrated_score", "calibrated_label", "calibrated_emoji",
                  "calibrated_description", "calibrated_allocation",
                  "calibration_applied", "calibration_z", "calibration_z_raw",
                  "calibration_hist_mean", "calibration_hist_std",
                  "calibration_std_effective", "calibration_std_floored",
                  "calibration_n_history", "calibration_method"):
            rec[k] = r[k]
        rec["calibrated_score"] = round(float(r["calibrated_score"]), 2)

        # ── Provenance (metadata) ────────────────────────────────────────────
        meta = payload.setdefault("metadata", {})
        config_hash, model_hash = _provenance_hashes(rec)
        meta.update({
            "generated_at": generated_at,
            "git_commit": git_head,
            "model_version": MODEL_VERSION,
            "config_hash": config_hash,
            "model_hash": model_hash,
            "data_as_of": rec.get("data_as_of"),
            "point_in_time": rec.get("point_in_time"),
            # Quy tắc FINAL/PROVISIONAL tổng quát — không hardcode từng quý
            "status": resolve_publication_status(q, rec.get("data_as_of")),
            "calibration_method": r.get("calibration_method"),
        })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        updated += 1

    logger.info(f"[BACKFILL] {updated} JSON exports updated in {EXPORTS_DIR}")
    return updated


def main():
    logger.info(f"[BACKFILL] SCORE_CALIBRATION = {SCORE_CALIBRATION}")
    df = backfill_parquet()
    backfill_jsons(df)

    cal_df = pd.DataFrame(calibrate_history_sequentially(
        [{"quarter": q, "total_score": s} for q, s in zip(df["quarter"], df["total_score"])]
    ))

    raw_dist = df["label"].value_counts().to_dict()
    cal_dist = df["calibrated_label"].value_counts().to_dict()
    print("\n" + "=" * 78)
    print("CALIBRATED ACTION SIGNAL v2 — SEQUENTIAL BACKFILL SUMMARY")
    print("=" * 78)
    print(f"Method : {SCORE_CALIBRATION.get('method')}")
    print(f"Params : center={SCORE_CALIBRATION['center']}, z_scale={SCORE_CALIBRATION['z_scale']}, "
          f"min_std={SCORE_CALIBRATION['min_std']}, z_cap=±{SCORE_CALIBRATION['z_cap']}, "
          f"max_dist_from_raw={SCORE_CALIBRATION['max_dist_from_raw']}, "
          f"clip=[{SCORE_CALIBRATION['clip_low']},{SCORE_CALIBRATION['clip_high']}]")
    print(f"Quarters: {len(df)} ({df['quarter'].iloc[0]} .. {df['quarter'].iloc[-1]})")
    print(f"Raw label distribution      : {raw_dist}")
    print(f"Calibrated label distribution: {cal_dist}")
    print("-" * 78)
    n_applied = 0
    print(f"{'Quarter':10s} {'Raw':>7s} {'RawLbl':>8s} {'Cal':>7s} {'CalLbl':>10s} "
          f"{'z':>7s} {'σ_obs':>6s} {'σ_eff':>6s} {'floor':>6s}")
    merged = cal_df.merge(df[["quarter", "label"]], on="quarter")
    for _, r in merged.iterrows():
        if r["calibration_applied"]:
            n_applied += 1
        z = f"{r['calibration_z']:+.2f}" if r["calibration_applied"] else "   —"
        so = f"{r['calibration_hist_std']:.2f}" if r["calibration_applied"] else "  —"
        se = f"{r['calibration_std_effective']:.2f}" if r["calibration_applied"] else "  —"
        fl = "FLOOR" if r.get("calibration_std_floored") else ""
        print(f"{r['quarter']:10s} {r['total_score']:7.2f} {r['label']:>8s} "
              f"{r['calibrated_score']:7.2f} {r['calibrated_label']:>10s} {z:>7s} {so:>6s} {se:>6s} {fl:>6s}")
    print("-" * 78)
    n_rail = int(((cal_df["calibrated_score"] <= 0.0) | (cal_df["calibrated_score"] >= 100.0)).sum())
    print(f"Calibration applied (expanding z) : {n_applied}/{len(df)} quarters "
          f"(first {SCORE_CALIBRATION['min_history']} quarters keep raw — insufficient history)")
    print(f"Calibrated at rail 0/100          : {n_rail}/{len(df)} quarters "
          f"(v2 guardrails: near-neutral raw cannot be auto-driven to rails)")
    max_dev = float((cal_df["calibrated_score"] - cal_df["total_score"]).abs().max())
    print(f"Max |calibrated − raw|            : {max_dev:.2f} "
          f"(guardrail ≤ {SCORE_CALIBRATION['max_dist_from_raw']:.0f})")
    print("=" * 78)


if __name__ == "__main__":
    main()
