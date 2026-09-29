"""
calibration_rebuild.py — Sequential expanding calibration cho toàn bộ lịch sử
==============================================================================
Mục đích: rebuild Calibrated Action Signal của N quý MỘT CÁCH TUẦN TỰ TĂNG DẦN
từ chuỗi điểm THÔ (total_score) — dùng cho:

  - scripts/backfill_calibrated_scores.py (rebuild parquet + score_*.json)
  - tests (sequential 24-quarter rebuild, mở rộng tới quý tương lai vd 2027-Q1)

Bất biến được module này bảo đảm (kiểm chứng bằng tests):

  1. POINT-IN-TIME / KHÔNG LOOK-AHEAD: calibration của quý t CHỈ dùng raw score
     của các quý STRICTLY TRƯỚC t — không dùng chính quý t, không dùng quý sau.
  2. CHỈ STACK RAW: lịch sử hiệu chỉnh không bao giờ chứa calibrated score
     → thay đổi tham số calibration KHÔNG làm drift μ/σ các quý sau
     (không feedback loop, rebuild idempotent).
  3. TUẦN TỰ TĂNG DẦN: input phải sort theo quarter tăng dần, không trùng.
     Batch rebuild song song hoặc giảm dần bị reject rõ ràng.
  4. MONOTONIC: với cùng lịch sử, raw cao hơn ⇒ calibrated không thấp hơn
     (được kiểm trên toàn lịch sử với lưới quét).

Module này THUẦN HÀM (pure): không đọc/ghi file. IO nằm ở script gọi nó.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from src.scoring.quarterly_scorer import calibrate_total_score
from src.utils.config import get_score_label


def _as_quarter_series(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, float]]:
    """Chuẩn hoá input thành [{quarter, total_score}] và kiểm bất biến thứ tự."""
    series: List[Dict[str, Any]] = []
    seen = set()
    prev = None
    for row in rows:
        q = str(row["quarter"])
        s = row.get("total_score")
        if q in seen:
            raise ValueError(f"Duplicate quarter {q!r} in history — rebuild từ chối.")
        if prev is not None and q <= prev:
            raise ValueError(
                f"History không tăng dần: {prev!r} -> {q!r}. "
                "Batch rebuild PHẢI chạy tuần tự TĂNG DẦN theo quarter "
                "(expanding window, point-in-time)."
            )
        seen.add(q)
        prev = q
        series.append({"quarter": q, "total_score": None if s is None else float(s)})
    return series


def calibrate_history_sequentially(
    rows: Sequence[Mapping[str, Any]],
    max_quarters: int | None = None,
) -> List[Dict[str, Any]]:
    """
    Tính Calibrated Action Signal cho chuỗi quý TĂNG DẦN.

    Parameters
    ----------
    rows         : iterable các mapping có 'quarter' (vd '2022-Q2') và 'total_score'
                   (raw composite). PHẢI sort tăng dần theo quarter, không trùng.
    max_quarters : tuỳ chọn — nếu chuỗi dài hơn giới hạn này thì raise (chống
                   rebuild tràn vô hạn nếu input lỗi; mặc định không giới hạn).

    Returns
    -------
    list[dict] — mỗi phần tử: quarter, total_score, calibrated_score,
        calibrated_label/emoji/description/allocation, calibration_applied,
        calibration_z, calibration_z_raw, calibration_hist_mean/std,
        calibration_std_effective, calibration_std_floored, calibration_n_history,
        calibration_method.
    """
    series = _as_quarter_series(rows)
    if max_quarters is not None and len(series) > max_quarters:
        raise ValueError(f"Quá {max_quarters} quý ({len(series)}) — kiểm tra lại input.")

    results: List[Dict[str, Any]] = []
    hist_raw: List[float] = []           # CHỈ điểm thô các quý TRƯỚC — không calibrated

    for item in series:
        q = item["quarter"]
        total = item["total_score"]

        # POINT-IN-TIME: lịch sử = raw của các quý đã xử lý TRƯỚC đó (strictly prior)
        res = calibrate_total_score(total, list(hist_raw))

        if res["applied"]:
            cal_label, cal_emoji, cal_desc, cal_alloc = get_score_label(res["calibrated_score"])
        else:
            # Fallback (thiếu lịch sử / disabled): giữ nguyên tầng raw
            cal_label, cal_emoji, cal_desc, cal_alloc = get_score_label(total)

        results.append({
            "quarter": q,
            "total_score": total,
            "calibrated_score": round(float(res["calibrated_score"]), 2) if res["calibrated_score"] is not None else None,
            "calibrated_label": cal_label,
            "calibrated_emoji": cal_emoji,
            "calibrated_description": cal_desc,
            "calibrated_allocation": cal_alloc,
            "calibration_applied": bool(res["applied"]),
            "calibration_z": res["calibration_z"],
            "calibration_z_raw": res.get("calibration_z_raw"),
            "calibration_hist_mean": res["calibration_hist_mean"],
            "calibration_hist_std": res["calibration_hist_std"],
            "calibration_std_effective": res.get("calibration_std_effective"),
            "calibration_std_floored": res.get("calibration_std_floored"),
            "calibration_n_history": res["calibration_n_history"],
            "calibration_method": res.get("calibration_method"),
        })

        # Stack raw vào lịch sử cho quý SAU (không stack calibrated — tránh feedback)
        if total is not None and total == total:  # bỏ qua NaN
            hist_raw.append(float(total))

    return results


def assert_monotonic_calibration(grid_step: float = 1.0) -> None:
    """
    Kiểm chứng bất biến MONOTONIC của calibrate_total_score trên lưới quét:
      với MỌI lịch sử hợp lệ (n ≥ min_history), raw tăng ⇒ calibrated không giảm.
    Dùng trong tests; raise AssertionError nếu vi phạm.
    """
    import numpy as np

    histories = [
        [50.0, 52.0, 48.0, 54.0],                          # window nhỏ điển hình
        [66.86, 62.75, 63.44, 60.22, 59.69],               # window thực 2022-Q2 (σ nhỏ)
        [50.0, 50.05, 49.95, 50.0],                        # σ gần 0 tuyệt đối
        [45.0, 65.0, 50.0, 70.0, 40.0, 60.0],              # σ lớn
    ]
    grid = np.arange(0.0, 100.0 + grid_step, grid_step)
    for hist in histories:
        prev_cal = None
        for raw in grid:
            cal = calibrate_total_score(float(raw), hist)["calibrated_score"]
            if prev_cal is not None:
                assert cal >= prev_cal - 1e-9, (
                    f"MONOTONIC VIOLATION: hist={hist}, raw={raw:.1f} -> {cal:.2f} "
                    f"< previous {prev_cal:.2f}"
                )
            prev_cal = cal
