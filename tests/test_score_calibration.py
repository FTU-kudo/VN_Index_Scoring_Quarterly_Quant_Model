"""
test_score_calibration.py — Enforce Calibrated Action Signal v2 (Tầng 2)
=========================================================================
BỐI CẢNH: điểm thô bị nén quanh 45–61 → 22/24 quý HOLD → thêm tầng calibrated
z-score expanding. NGƯỜC LẠI, calibration v1 (PR #8) sinh lỗi thái quá:
quý 2022-Q2 raw = 51.25/100 (≈ trung lập) bị ghim về calibrated = 0.00 (SELL)
vì σ của cửa sổ 5 quý 2021 chỉ 2.87 điểm → z = −3.95 → 50 + 15z < 0.

CALIBRATION V2 (method: winsorized_expanding_zscore_v2) — 3 tầng bảo vệ:
  1. min_std  : σ_eff = max(σ_hist_sample(ddof=1), min_std=5.0) — σ tiny-sample
                không thể thổi z (sàn ≈ dispersion dài hạn của composite ≈ 6đ).
  2. z_cap    : z winsorize tại ±3.0 — với z_scale=15, pre ∈ [5,95]:
                0/100 không thể xảy ra tự động (bão hoà 5/95 ở |z|≥3σ).
  3. max_dist : tín hiệu hành động không lệch raw composite quá ±25 điểm —
                raw gần trung lập không thể thành phân bổ cực đoan.

Acceptance Criteria (phản ánh đúng task review 2026-09):
  1. Công thức v2 đúng theo SCORE_CALIBRATION trong config.py (single source).
  2. 2022-Q2 REGRESSION: raw 51.25, history 5 điểm ~62.6/σ2.87 → calibrated
     = 26.25 (KHÔNG còn 0.00), σ floored, z = −2.27 — không bịa cực trị.
  3. Raw gần neutral không bao giờ tự động thành 0/100 dù σ lịch sử ≈ 0.
  4. Monotonic: cùng lịch sử, raw ↑ ⇒ calibrated không giảm.
  5. < min_history quý → calibrated = raw, applied=False; NaN → fallback.
  6. z luôn bị winsorize trong ±z_cap; |calibrated − raw| ≤ max_dist_from_raw.
  7. Sequential rebuild: chỉ stack RAW (không calibrated), không look-ahead,
     không drift khi thêm quý tương lai (mở rộng 2027-Q1).
  8. score_record + parquet có đủ field calibrated_* v1+v2 (schema tương thích).
  9. Nhãn calibrated lấy từ get_score_label() (SSOT) — có thể SELL nhưng
     KHÔNG BAO GIỜ vì ghim số 0 giả; khi hiển thị phải là regime tương đối.
 10. Tier-2 gains: MLR ±0.10%/ngày → 70/30; VAR gain 5000; MISSING renormalized.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import SCORE_CALIBRATION, get_score_label
from src.scoring.quarterly_scorer import (
    calibrate_total_score,
    compute_quarterly_score,
    score_quant_model,
    score_market_structure,
)
from src.scoring.calibration_rebuild import (
    calibrate_history_sequentially,
    assert_monotonic_calibration,
)

# Lịch sử thô THẬT của 24 quý (2021-Q1 → 2026-Q4) — nguồn: production parquet/
# JSON. Dùng làm regression fixture cho sequential rebuild ở cuối file.
PRODUCTION_RAW_SERIES = [
    ("2021-Q1", 66.86), ("2021-Q2", 62.75), ("2021-Q3", 63.44), ("2021-Q4", 60.22),
    ("2022-Q1", 59.69), ("2022-Q2", 51.25), ("2022-Q3", 57.52), ("2022-Q4", 45.88),
    ("2023-Q1", 58.49), ("2023-Q2", 57.35), ("2023-Q3", 56.64), ("2023-Q4", 50.28),
    ("2024-Q1", 47.02), ("2024-Q2", 53.70), ("2024-Q3", 49.74), ("2024-Q4", 53.13),
    ("2025-Q1", 49.61), ("2025-Q2", 51.03), ("2025-Q3", 55.20), ("2025-Q4", 51.98),
    ("2026-Q1", 51.47), ("2026-Q2", 44.38), ("2026-Q3", 46.59), ("2026-Q4", 47.67),
]

MOCK_LATEST = pd.Series({
    "omo_overnight_rate": 4.0, "delta_omo_rate": -0.01,
    "usd_vnd_zscore": -0.5, "m2_yoy_pct": 12.0,
    "vn10y_yield": 4.5, "vn_yield_spread": 0.5,
    "dxy_zscore_60d": 0.3, "us10y_yield": 4.5, "delta_us10y": 0.01,
    "nff_ex_etf_q_zscore_live": 0.2,
    "pe_zscore": -0.3, "pb_zscore": -0.2,
    "margin_risk_score": 30, "eyg_zscore": 0.5,
    "etf_flow_q_zscore_live": 0.1,
})


# ═══════════════════════════════════════════════════════════════════════════
# 1–5. calibrate_total_score v2 — pure function
# ═══════════════════════════════════════════════════════════════════════════

class TestCalibrateTotalScoreV2:

    def test_formula_exact_with_default_guards(self):
        """Công thức v2 đúng bằng tay: σ_eff=max(σ,5), z cap ±3, band raw±25."""
        hist = [50.0, 52.0, 48.0, 54.0]     # μ = 51, σ_sample = 2.582 < 5 → floored
        total = 55.0
        res = calibrate_total_score(total, hist)
        mu = 51.0
        sigma_obs = float(np.std(hist, ddof=1))
        sigma_eff = max(sigma_obs, SCORE_CALIBRATION["min_std"])
        z = (total - mu) / sigma_eff                     # 0.8 — trong cap
        expected = SCORE_CALIBRATION["center"] + SCORE_CALIBRATION["z_scale"] * z  # 62
        assert res["applied"] is True
        assert res["calibrated_score"] == pytest.approx(expected, abs=0.01)
        assert res["calibration_z"] == pytest.approx(z, abs=1e-3)
        assert res["calibration_hist_mean"] == pytest.approx(mu, abs=1e-3)
        assert res["calibration_hist_std"] == pytest.approx(sigma_obs, abs=1e-3)
        assert res["calibration_std_effective"] == pytest.approx(sigma_eff, abs=1e-3)
        assert res["calibration_std_floored"] is True
        assert res["calibration_n_history"] == 4
        assert res["calibration_method"] == SCORE_CALIBRATION["method"]

    def test_tiny_sigma_history_no_longer_rails(self):
        """V1: σ≈0.08 + raw 40/60 → 0/100 (bug). V2: σ floored → z=±2 → 20/80."""
        hist = [50.0, 50.1, 49.9, 50.0]     # σ_obs ≈ 0.0817 — đúng kịch bản bug cũ
        hi = calibrate_total_score(60.0, hist)
        lo = calibrate_total_score(40.0, hist)
        # z = ±10/5 = ±2 (flooored ở 5.0) → pre = 80/20; band ±25 không chạm
        assert hi["calibrated_score"] == pytest.approx(80.0, abs=0.01)
        assert lo["calibrated_score"] == pytest.approx(20.0, abs=0.01)
        assert hi["calibration_std_floored"] and lo["calibration_std_floored"]
        # Quan trọng: KHÔNG còn ghim 0/100 như v1
        assert hi["calibrated_score"] < SCORE_CALIBRATION["clip_high"]
        assert lo["calibrated_score"] > SCORE_CALIBRATION["clip_low"]

    def test_score_zero_or_hundred_unreachable_by_construction(self):
        """0/100 không thể xuất hiện với guardrail mặc định — kể cả raw cực trị.
        Bằng chứng mạnh nhất (raw=0, lịch sử ở 60) vẫn bão hoà 5 chứ không ghim 0."""
        hist = [58.0, 60.0, 62.0, 59.0, 61.0]
        extreme_lo = calibrate_total_score(0.0, hist)
        extreme_hi = calibrate_total_score(100.0, hist)
        # z_raw = (0−60)/5 = −12 → capped −3 → pre = 5 đúng bằng rails thiết kế
        assert extreme_lo["calibration_z_raw"] == pytest.approx(-12.0, abs=0.5)
        assert extreme_lo["calibration_z"] == pytest.approx(-SCORE_CALIBRATION["z_cap"], abs=1e-6)
        assert extreme_lo["calibrated_score"] == pytest.approx(
            SCORE_CALIBRATION["center"] - SCORE_CALIBRATION["z_scale"] * SCORE_CALIBRATION["z_cap"], abs=0.01)
        assert extreme_hi["calibrated_score"] == pytest.approx(
            SCORE_CALIBRATION["center"] + SCORE_CALIBRATION["z_scale"] * SCORE_CALIBRATION["z_cap"], abs=0.01)
        assert 0.0 < extreme_lo["calibrated_score"] and extreme_hi["calibrated_score"] < 100.0
        # Quét toàn lưới raw với nhiều history — không ô nào chạm 0/100
        for h in ([50.0, 52.0, 48.0, 54.0], [60.0] * 4 + [61.0],
                  [66.86, 62.75, 63.44, 60.22, 59.69]):
            for raw in np.arange(0.0, 100.01, 2.5):
                c = calibrate_total_score(float(raw), h)["calibrated_score"]
                assert 0.0 < c < 100.0, (h, raw, c)

    def test_near_neutral_raw_never_becomes_extreme(self):
        """Raw ~50 (gần trung lập) không bao giờ thành SELL-cực-trị chỉ vì σ nhỏ:
        |calibrated − raw| ≤ max_dist_from_raw (guardrail tầng 3)."""
        hist = [60.0, 61.0, 59.0, 60.5, 60.2]     # σ_obs ≈ 0.85 → floored
        for raw in (48.0, 49.0, 50.0, 51.0, 51.25, 52.0):
            res = calibrate_total_score(raw, hist)
            assert abs(res["calibrated_score"] - raw) <= SCORE_CALIBRATION["max_dist_from_raw"] + 1e-9
            floor_lo = SCORE_CALIBRATION["center"] - SCORE_CALIBRATION["z_scale"] * SCORE_CALIBRATION["z_cap"]
            assert res["calibrated_score"] >= floor_lo - 1e-9, \
                "raw gần neutral bị kéo xuống dưới cả thanh z-layer (không được)"

    def test_sigma_zero_history_now_calibrates_via_floor_default(self):
        """σ_hist = 0 tuyệt đối (4 điểm giống nhau): v1 fallback; v2 dùng sàn σ=5
        → vẫn calibrate an toàn (z=(55−50)/5=+1 → 65, band không chạm)."""
        res = calibrate_total_score(55.0, [50.0, 50.0, 50.0, 50.0])
        assert res["applied"] is True
        assert res["calibrated_score"] == pytest.approx(65.0, abs=0.01)
        assert res["calibration_std_floored"] is True
        # Với min_std=0 (tắt sàn, hành vi legacy) → fallback như v1
        import src.scoring.quarterly_scorer as scm
        legacy = {**SCORE_CALIBRATION, "min_std": 0.0}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(scm, "SCORE_CALIBRATION", legacy)
            res_off = calibrate_total_score(55.0, [50.0, 50.0, 50.0, 50.0])
        assert res_off["applied"] is False
        assert res_off["calibrated_score"] == 55.0

    def test_insufficient_history_fallback(self):
        """< min_history quý → giữ điểm thô (0..3 quý đều phải fallback)."""
        for hist in ([], [50.0], [50.0, 52.0], [50.0, 52.0, 48.0]):
            res = calibrate_total_score(55.0, hist)
            assert res["applied"] is False, f"n={len(hist)} must not calibrate"
            assert res["calibrated_score"] == 55.0
        # Đủ min_history thì PHẢI áp dụng
        assert calibrate_total_score(55.0, [50.0, 52.0, 48.0, 54.0])["applied"] is True

    def test_nan_inputs(self):
        """total_score NaN → NaN propagate, applied=False (không bịa 50).
        NaN trong hist_scores bị loại khỏi lịch sử (không làm hỏng μ/σ)."""
        res = calibrate_total_score(float("nan"), [50.0, 52.0, 48.0, 54.0])
        assert res["applied"] is False
        assert np.isnan(res["calibrated_score"])
        # NaN trong hist bị lọc: 3 số thật + 1 NaN → n = 3 < 4 → fallback
        res2 = calibrate_total_score(55.0, [50.0, 52.0, 48.0, float("nan")])
        assert res2["applied"] is False
        # 4 số thật + NaN → n = 4 → vẫn calibrate được
        res3 = calibrate_total_score(55.0, [50.0, 52.0, 48.0, 54.0, None])
        assert res3["applied"] is True and res3["calibration_n_history"] == 4

    def test_disabled_calibration_keeps_raw(self, monkeypatch):
        """SCORE_CALIBRATION['enabled'] = False → luôn giữ điểm thô."""
        import src.scoring.quarterly_scorer as scm
        monkeypatch.setattr(scm, "SCORE_CALIBRATION", {**SCORE_CALIBRATION, "enabled": False})
        res = calibrate_total_score(55.0, [50.0, 52.0, 48.0, 54.0])
        assert res["applied"] is False
        assert res["calibrated_score"] == 55.0

    def test_monotonic_in_raw_for_same_history(self):
        """Bất biến: raw cao hơn với cùng history ⇒ calibrated KHÔNG thấp hơn."""
        assert_monotonic_calibration(grid_step=0.5)

    def test_result_schema_v1_compat_plus_v2_fields(self):
        """Schema giữ nguyên field v1 + bổ sung diagnostic v2 (provenance)."""
        res = calibrate_total_score(55.0, [50.0, 52.0, 48.0, 54.0])
        for k in ("calibrated_score", "applied", "calibration_z",
                  "calibration_hist_mean", "calibration_hist_std", "calibration_n_history",
                  # ── v2 ──
                  "calibration_z_raw", "calibration_std_effective",
                  "calibration_std_floored", "calibration_method"):
            assert k in res, f"missing {k}"


class TestCalibration2022Q2Regression:
    """REGRESSION chính của task: 2022-Q2 không còn bị ghim về 0.00."""

    HIST = [66.86, 62.75, 63.44, 60.22, 59.69]   # 2021-Q1..2022-Q1 (đúng production)
    RAW = 51.25                                    # 2022-Q2 raw composite

    def test_2022_Q2_no_longer_zero(self):
        res = calibrate_total_score(self.RAW, self.HIST)
        # μ=62.592, σ_obs≈2.87 → floored σ_eff=5.0 → z=(51.25−62.592)/5=−2.2684
        # → pre=50−34.03=15.97 → band [26.25,76.25] → calibrated = 26.25
        # (σ quan sát tính lại từ raw đã round-2dp lệch ~0.002 so với full precision)
        assert res["applied"] is True
        assert res["calibration_hist_std"] == pytest.approx(2.874, abs=0.005)
        assert res["calibration_std_effective"] == pytest.approx(5.0, abs=1e-6)
        assert res["calibration_std_floored"] is True
        assert res["calibration_z"] == pytest.approx(-2.2684, abs=1e-3)
        assert res["calibrated_score"] == pytest.approx(26.25, abs=0.01)
        assert res["calibrated_score"] != 0.0
        assert abs(res["calibrated_score"] - self.RAW) <= SCORE_CALIBRATION["max_dist_from_raw"] + 1e-9

    def test_2022_Q2_label_derived_from_bounded_signal(self):
        """Nhãn vẫn từ get_score_label (SSOT); điểm 26.25 phản ánh regime yếu
        tương đối thật (raw thấp hơn nhiều so với nền 2021) nhưng KHÔNG phải
        cực trị 0 giả và allocation không còn là đọc-từ-rail."""
        res = calibrate_total_score(self.RAW, self.HIST)
        label, emoji, desc, alloc = get_score_label(res["calibrated_score"])
        assert label == "SELL"  # band 0–34: regime yếu tương đối thật — NHƯNG score ≠ 0
        assert get_score_label(26.25)[0] == "SELL"
        # Đối chứng v1: với guardrail tắt hoàn toàn thì sẽ ra 0 — chứng minh
        # guardrail mới chính là thứ chặn bệnh, không phải "sửa tay cho đẹp"
        import src.scoring.quarterly_scorer as scm
        legacy = {**SCORE_CALIBRATION, "min_std": 0.0, "z_cap": float("inf"),
                  "max_dist_from_raw": float("inf")}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(scm, "SCORE_CALIBRATION", legacy)
            v1 = calibrate_total_score(self.RAW, self.HIST)
        assert v1["calibrated_score"] == 0.0, "legacy v1 phải tái hiện đúng bug"

    def test_whole_2022_block_moderated_not_pinned(self):
        """Cụm 2022 (early window σ nhỏ) được điều tiết, không pinned:
        2022-Q1 30.12→39.12 (REDUCE), 2022-Q2 0.00→26.25, 2022-Q4 6.74→20.88."""
        series = dict(PRODUCTION_RAW_SERIES)
        hist = []
        out = {}
        for q, s in PRODUCTION_RAW_SERIES:
            out[q] = calibrate_total_score(s, list(hist))
            hist.append(s)
        assert out["2022-Q1"]["calibrated_score"] == pytest.approx(39.12, abs=0.02)
        assert out["2022-Q2"]["calibrated_score"] == pytest.approx(26.25, abs=0.02)
        assert out["2022-Q4"]["calibrated_score"] == pytest.approx(20.88, abs=0.02)
        # Không quý nào trong toàn lịch sử chạm 0/100
        for q, res in out.items():
            assert 0.0 < res["calibrated_score"] < 100.0, q


# ═══════════════════════════════════════════════════════════════════════════
# 6–8. compute_quarterly_score — tích hợp point-in-time
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeQuarterlyScoreCalibration:
    """Dùng SCORES_DIR cách ly (conftest.autouse) — không chạm data/ production."""

    SEED_COLS = {
        "date_computed": ["2026-01-01 00:00"] * 4,
        "label": ["HOLD"] * 4,
        "percentile_label": ["HOLD"] * 4,
        "pillar_std": [5.0] * 4, "pillar_range": [10.0] * 4,
        "dispersion_level": ["MEDIUM"] * 4,
        "calibrated_label": ["HOLD"] * 4,
        "score_macro_monetary": [12.0] * 4,
        "score_global_intermarket": [10.0] * 4,
        "score_valuation_leverage": [10.0] * 4,
        "score_quant_model": [8.0] * 4,
        "score_ml_forecast": [5.0] * 4,
        "score_market_structure": [5.0] * 4,
    }

    def _seed(self, isolate_scores_dir, hist_scores):
        quarters = ["2021-Q1", "2021-Q2", "2021-Q3", "2021-Q4"]
        seed = pd.DataFrame({
            "quarter": quarters, "total_score": hist_scores,
            "calibrated_score": hist_scores, **self.SEED_COLS,
        })
        seed.to_parquet(isolate_scores_dir / "quarterly_scores_history.parquet", index=False)

    def test_point_in_time_expanding_window(self, isolate_scores_dir):
        """Quý hiện tại CHỈ dùng các quý TRƯỚC — z-diagnostic khớp đúng μ/σ_eff
        của 4 quý lịch sử đó (σ floored), không chứa chính nó hay quý tương lai."""
        hist_scores = [60.0, 52.0, 54.0, 50.0]
        self._seed(isolate_scores_dir, hist_scores)

        rec = compute_quarterly_score(
            quarter="2022-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )

        assert rec["calibration_applied"] is True
        assert rec["calibration_n_history"] == 4
        mu = float(np.mean(hist_scores))
        sigma_obs = float(np.std(hist_scores, ddof=1))
        sigma_eff = max(sigma_obs, SCORE_CALIBRATION["min_std"])
        assert rec["calibration_hist_mean"] == pytest.approx(mu, abs=1e-3)
        assert rec["calibration_hist_std"] == pytest.approx(sigma_obs, abs=1e-3)
        assert rec["calibration_std_effective"] == pytest.approx(sigma_eff, abs=1e-3)
        z_expected = np.clip(
            (rec["total_score"] - mu) / sigma_eff,
            -SCORE_CALIBRATION["z_cap"], SCORE_CALIBRATION["z_cap"],
        )
        assert rec["calibration_z"] == pytest.approx(z_expected, abs=1e-3)
        # Point-in-time tuyệt đối: lịch sử KHÔNG chứa chính quý 2022-Q1
        pq = pd.read_parquet(isolate_scores_dir / "quarterly_scores_history.parquet")
        n_row = int((pq["quarter"] == "2022-Q1").sum())
        assert n_row == 1
        # μ/σ chỉ tính trên 4 quý seed (không phải 5 điểm gồm quý hiện tại)
        assert rec["calibration_hist_mean"] != pytest.approx(
            float(np.mean(hist_scores + [rec["total_score"]])), abs=0.3)

    def test_no_history_keeps_raw_label(self, isolate_scores_dir):
        """Quý đầu tiên (2021-Q1, chưa có lịch sử) → calibrated = raw, applied=False."""
        rec = compute_quarterly_score(
            quarter="2021-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        assert rec["calibration_applied"] is False
        assert rec["calibrated_score"] == rec["total_score"]
        assert rec["calibrated_label"] == rec["label"]

    def test_record_has_all_calibrated_fields(self, isolate_scores_dir):
        """score_record xuất đủ field calibrated_* + calibration_* (v1+v2)."""
        rec = compute_quarterly_score(
            quarter="2021-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        for field in ("calibrated_score", "calibrated_label", "calibrated_emoji",
                      "calibrated_description", "calibrated_allocation",
                      "calibration_z", "calibration_z_raw", "calibration_hist_mean",
                      "calibration_hist_std", "calibration_std_effective",
                      "calibration_std_floored", "calibration_n_history",
                      "calibration_applied", "calibration_method"):
            assert field in rec, f"Missing field {field!r}"
        lbl, em, desc, alloc = get_score_label(rec["calibrated_score"])
        assert rec["calibrated_label"] == lbl
        assert rec["calibrated_emoji"] == em
        assert rec["calibrated_allocation"] == alloc
        assert rec["calibration_method"] == SCORE_CALIBRATION["method"]

    def test_parquet_row_has_calibrated_columns(self, isolate_scores_dir):
        """Parquet sau khi chấm điểm phải có cột calibrated_score/calibrated_label."""
        compute_quarterly_score(
            quarter="2021-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        pq = pd.read_parquet(isolate_scores_dir / "quarterly_scores_history.parquet")
        assert "calibrated_score" in pq.columns
        assert "calibrated_label" in pq.columns
        assert len(pq) == 1

    def test_raw_score_not_replaced_by_calibrated(self, isolate_scores_dir):
        """Điểm thô (total_score) phải GIỮ NGUYÊN — calibrated là tầng riêng."""
        hist_scores = [60.0, 52.0, 54.0, 50.0]
        self._seed(isolate_scores_dir, hist_scores)
        before = hist_scores[:]
        compute_quarterly_score(
            quarter="2022-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        after = pd.read_parquet(isolate_scores_dir / "quarterly_scores_history.parquet")
        for s_expect, s_actual in zip(before, after[after["quarter"] != "2022-Q1"]["total_score"]):
            assert s_actual == s_expect

    def test_small_history_small_std_not_extreme_in_pipeline(self, isolate_scores_dir):
        """End-to-end qua compute_quarterly_score: window nhỏ σ nhỏ KHÔNG được
        đẩy score hiện tại về rail 0/100 (bài test chống tái phát bug 2022-Q2)."""
        # Seed 4 quý 2021 nén chặt quanh 63 — đúng môi trường lỗi cũ
        self._seed(isolate_scores_dir, [63.0, 63.5, 62.5, 63.2])
        rec = compute_quarterly_score(
            quarter="2022-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        assert 0.0 < rec["calibrated_score"] < 100.0
        assert abs(rec["calibrated_score"] - rec["total_score"]) <= \
            SCORE_CALIBRATION["max_dist_from_raw"] + 1e-9


# ═══════════════════════════════════════════════════════════════════════════
# 9. Sequential rebuild — point-in-time, no look-ahead, no drift
# ═══════════════════════════════════════════════════════════════════════════

class TestSequentialRebuild:

    def test_rebuild_matches_hand_computed_production_sequence(self):
        """Sequential rebuild trên chuỗi raw production phải khớp giá trị tính tay
        (khóa regression cho toàn bộ 24 quý — thay config là test này đổ)."""
        out = calibrate_history_sequentially(
            [{"quarter": q, "total_score": s} for q, s in PRODUCTION_RAW_SERIES]
        )
        expected_cal = {
            "2021-Q1": 66.86, "2021-Q2": 62.75, "2021-Q3": 63.44, "2021-Q4": 60.22,
            "2022-Q1": 39.12, "2022-Q2": 26.25, "2022-Q3": 40.99, "2022-Q4": 20.88,
            "2023-Q1": 50.08, "2023-Q2": 47.42, "2023-Q3": 45.78, "2023-Q4": 29.45,
            "2024-Q1": 23.54, "2024-Q2": 42.92, "2024-Q3": 33.65, "2024-Q4": 42.96,
            "2025-Q1": 34.51, "2025-Q2": 38.94, "2025-Q3": 49.86, "2025-Q4": 41.55,
            "2026-Q1": 40.48, "2026-Q2": 21.85, "2026-Q3": 30.12, "2026-Q4": 33.97,
        }
        for rec in out:
            assert rec["calibrated_score"] == pytest.approx(
                expected_cal[rec["quarter"]], abs=0.02), rec["quarter"]
        # 4 quý đầu chưa đủ lịch sử → applied=False, giữ raw
        for rec in out[:4]:
            assert rec["calibration_applied"] is False
            assert rec["calibrated_score"] == rec["total_score"]
        # n_history tuyệt đối = số quý TRƯỚC (không look-ahead)
        for i, rec in enumerate(out):
            assert rec["calibration_n_history"] == i

    def test_no_lookahead_future_change_does_not_alter_past(self):
        """Thay đổi raw của quý SAU không được phép thay đổi calibrated các quý TRƯỚC —
        chứng minh không look-ahead & không feedback (chỉ stack raw)."""
        base = [("2021-Q1", 60.0), ("2021-Q2", 55.0), ("2021-Q3", 58.0),
                ("2021-Q4", 52.0), ("2022-Q1", 61.0)]
        variant = base + [("2022-Q2", 10.0)]
        variant2 = base + [("2022-Q2", 95.0)]
        a = calibrate_history_sequentially([{"quarter": q, "total_score": s} for q, s in variant])
        b = calibrate_history_sequentially([{"quarter": q, "total_score": s} for q, s in variant2])
        for ra, rb in zip(a[:-1], b[:-1]):
            assert ra == rb, "quá khứ bị ảnh hưởng bởi quý tương lai — LOOK-AHEAD!"
        # Quý cuối dùng đúng 5 quý trước (không gồm chính nó)
        assert a[-1]["calibration_n_history"] == 5
        manual = calibrate_total_score(10.0, [60.0, 55.0, 58.0, 52.0, 61.0])
        assert a[-1]["calibrated_score"] == manual["calibrated_score"]

    def test_hist_stats_use_raw_only_expanding(self):
        """μ/σ của quý t bằng μ/σ của các RAW quý trước (không phải calibrated)."""
        out = calibrate_history_sequentially(
            [{"quarter": q, "total_score": s} for q, s in PRODUCTION_RAW_SERIES[:6]]
        )
        raws = [s for _, s in PRODUCTION_RAW_SERIES[:5]]
        q6 = out[5]  # 2022-Q2
        assert q6["calibration_hist_mean"] == pytest.approx(float(np.mean(raws)), abs=1e-3)
        assert q6["calibration_hist_std"] == pytest.approx(float(np.std(raws, ddof=1)), abs=1e-3)
        # Nếu stack calibrated bằng nhầm, mean sẽ khác — kiểm chứng trực tiếp:
        cals = [66.86, 62.75, 63.44, 60.22, 39.12]
        assert q6["calibration_hist_mean"] != pytest.approx(float(np.mean(cals)), abs=0.5)

    def test_rejects_unsorted_or_duplicate(self):
        with pytest.raises(ValueError):
            calibrate_history_sequentially([
                {"quarter": "2021-Q2", "total_score": 50.0},
                {"quarter": "2021-Q1", "total_score": 51.0},
            ])
        with pytest.raises(ValueError):
            calibrate_history_sequentially([
                {"quarter": "2021-Q1", "total_score": 50.0},
                {"quarter": "2021-Q1", "total_score": 51.0},
            ])

    def test_extension_to_future_quarters_2027_q1(self):
        """Mở rộng lịch sử tới 2027-Q1 (và xa hơn) không đổi 24 quý cũ,
        quý mới dùng đúng expanding window; không hardcode 24 dòng."""
        base = [{"quarter": q, "total_score": s} for q, s in PRODUCTION_RAW_SERIES]
        extended = base + [{"quarter": "2027-Q1", "total_score": 58.0}]
        out24 = calibrate_history_sequentially(base)
        out25 = calibrate_history_sequentially(extended)
        # Toàn bộ 24 quý cũ giữ nguyên (no drift — config mới không làm trôi quá khứ)
        assert [r["calibrated_score"] for r in out24] == [r["calibrated_score"] for r in out25[:24]]
        q_new = out25[24]
        assert q_new["quarter"] == "2027-Q1"
        assert q_new["calibration_n_history"] == 24
        hist = [s for _, s in PRODUCTION_RAW_SERIES]
        assert q_new["calibration_hist_mean"] == pytest.approx(float(np.mean(hist)), abs=1e-3)
        manual = calibrate_total_score(58.0, hist)
        assert q_new["calibrated_score"] == pytest.approx(manual["calibrated_score"], abs=0.01)

    def test_first_quarter_of_history_keeps_raw(self):
        out = calibrate_history_sequentially([{"quarter": "2021-Q1", "total_score": 66.86}])
        assert out[0]["calibration_applied"] is False
        assert out[0]["calibrated_score"] == 66.86


# ═══════════════════════════════════════════════════════════════════════════
# 10. Tier-2 — chống nén tín hiệu tại nguồn (giữ nguyên v1)
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiCompression:

    def test_quant_model_gains_and_renormalization(self):
        """MLR ±0.10%/ngày → 70/30 (gain 20000); VAR gain 5000;
        tín hiệu MISSING không tham gia trung bình."""
        r = score_quant_model(mlr_pred=0.001, var_forecast=None)
        assert r["sub_scores"]["mlr_signal_score"] == pytest.approx(70.0, abs=0.5)
        assert r["raw_score"] == pytest.approx(70.0, abs=0.5)
        r2 = score_quant_model(mlr_pred=-0.001, var_forecast=None)
        assert r2["sub_scores"]["mlr_signal_score"] == pytest.approx(30.0, abs=0.5)
        assert r2["raw_score"] == pytest.approx(30.0, abs=0.5)
        r3 = score_quant_model(mlr_pred=None, var_forecast=0.01)
        assert r3["sub_scores"]["var_signal_score"] == pytest.approx(100.0, abs=0.5)
        assert r3["raw_score"] == pytest.approx(100.0, abs=0.5)
        r4 = score_quant_model(mlr_pred=None, var_forecast=None)
        assert r4["raw_score"] == 50.0

    def test_market_structure_renormalizes_missing_components(self):
        """ADTV/ETF thiếu → KHÔNG kéo pillar về 50; trung bình chỉ trên cấu phần có dữ liệu."""
        empty = pd.Series(dtype=float)
        r = score_market_structure(df_latest=empty, ftse_upgrade_status="unknown",
                                   months_to_next_rebalancing=2, adtv_change_pct=None)
        assert r["raw_score"] == pytest.approx(62.0, abs=0.1), \
            "Pillar phải = FTSE component một mình (renormalize), không bị kéo về 50"
        r2 = score_market_structure(df_latest=empty, ftse_upgrade_status="unknown",
                                    months_to_next_rebalancing=2, adtv_change_pct=0.20)
        assert r2["raw_score"] == pytest.approx(66.0, abs=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
