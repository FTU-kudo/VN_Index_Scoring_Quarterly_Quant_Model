"""
test_score_calibration.py — Enforce Calibrated Action Signal (Tầng 2)
======================================================================
BỐI CẢNH: Điểm thô (raw composite) bị nén quanh 45–61 → 22/24 quý HOLD
("HOLD mãn tính") → model vô dụng cho phân bổ tài sản. Giải pháp 2 tầng:
  - Tầng 1 (raw composite): giữ nguyên để tham chiếu.
  - Tầng 2 (calibrated action signal): z-score so với lịch sử expanding,
    CHỈ dùng các quý TRƯỚC (point-in-time, không look-ahead),
    calibrated = clip(center + z_scale × (total − μ_hist)/σ_hist, 0, 100).

Acceptance Criteria:
  1. Công thức đúng theo SCORE_CALIBRATION trong config.py.
  2. Clip tại [clip_low, clip_high].
  3. σ_hist ≈ 0 → fallback giữ điểm thô, applied=False.
  4. < min_history quý lịch sử → fallback giữ điểm thô.
  5. total_score NaN → fallback NaN, applied=False (không bịa số).
  6. Point-in-time: compute_quarterly_score chỉ đọc các quý TRƯỚC từ parquet
     (expanding window) — z-diagnostics phải khớp đúng lịch sử đó.
  7. Nhãn calibrated lấy từ get_score_label() (single source of truth).
  8. score_record + parquet có đủ field/cột calibrated mới.
  9. Tier-2 gains: MLR ±0.10%/ngày → 70/30; VAR gain 5000.
 10. MISSING signal không tham gia trung bình (renormalize) — quant_model
     và market_structure.
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
# 1–5. calibrate_total_score — pure function
# ═══════════════════════════════════════════════════════════════════════════

class TestCalibrateTotalScore:

    def test_formula_exact(self):
        """calibrated = clip(center + z_scale × (total − μ)/σ, 0, 100) — kiểm bằng tay."""
        hist = [50.0, 52.0, 48.0, 54.0]     # μ = 51, σ(sample, ddof=1) = 2.5820
        total = 55.0
        res = calibrate_total_score(total, hist)
        mu, sigma = 51.0, np.std(hist, ddof=1)
        expected = SCORE_CALIBRATION["center"] + SCORE_CALIBRATION["z_scale"] * (total - mu) / sigma
        assert res["applied"] is True
        assert res["calibrated_score"] == pytest.approx(expected, abs=0.01)
        assert res["calibration_z"] == pytest.approx((total - mu) / sigma, abs=1e-3)
        assert res["calibration_hist_mean"] == pytest.approx(mu, abs=1e-3)
        assert res["calibration_hist_std"] == pytest.approx(sigma, abs=1e-3)
        assert res["calibration_n_history"] == 4

    def test_clip_bounds(self):
        """σ rất nhỏ + outlier xa → calibrated bị clip trong [clip_low, clip_high]."""
        hist = [50.0, 50.1, 49.9, 50.0]     # σ ≈ 0.0817
        hi = calibrate_total_score(60.0, hist)   # z ≈ +122 → clip 100
        lo = calibrate_total_score(40.0, hist)   # z ≈ −122 → clip 0
        assert hi["calibrated_score"] == SCORE_CALIBRATION["clip_high"]
        assert lo["calibrated_score"] == SCORE_CALIBRATION["clip_low"]
        assert hi["applied"] and lo["applied"]

    def test_sigma_zero_fallback(self):
        """σ_hist = 0 (lịch sử không phân tán) → giữ điểm thô, applied=False."""
        res = calibrate_total_score(55.0, [50.0, 50.0, 50.0, 50.0])
        assert res["applied"] is False
        assert res["calibrated_score"] == 55.0
        assert res["calibration_z"] is None

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


# ═══════════════════════════════════════════════════════════════════════════
# 6–8. compute_quarterly_score — tích hợp point-in-time
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeQuarterlyScoreCalibration:
    """Dùng SCORES_DIR cách ly (conftest.autouse) — không chạm data/ production."""

    def _seed_history(self, scores_dir, quarters_scores):
        """Ghi sẵn lịch sử parquet như các quý đã chạy trước đó."""
        rows = []
        for q, s in quarters_scores:
            rec = compute_quarterly_score(quarter=q, df_latest=MOCK_LATEST.copy(),
                                          ftse_upgrade_status="pending",
                                          months_to_next_rebalancing=2,
                                          adtv_change_pct=0.0)
            # Ép total_score về giá trị mong muốn để test deterministic
            rows.append(q)
        return rows

    def test_point_in_time_expanding_window(self, isolate_scores_dir):
        """Quý hiện tại CHỈ dùng các quý TRƯỚC làm lịch sử — z-diagnostic phải
        khớp μ/σ của đúng 4 quý đã có, không chứa chính nó hay quý tương lai."""
        hist_scores = [60.0, 52.0, 54.0, 50.0]
        quarters = ["2021-Q1", "2021-Q2", "2021-Q3", "2021-Q4"]
        # Seed 4 quý lịch sử vào SCORES_DIR cách ly
        seed = pd.DataFrame({
            "quarter": quarters,
            "date_computed": ["2026-01-01 00:00"] * 4,
            "total_score": hist_scores,
            "label": ["HOLD"] * 4,
            "percentile_label": ["HOLD"] * 4,
            "pillar_std": [5.0] * 4, "pillar_range": [10.0] * 4,
            "dispersion_level": ["MEDIUM"] * 4,
            "calibrated_score": hist_scores, "calibrated_label": ["HOLD"] * 4,
            "score_macro_monetary": [12.0] * 4,
            "score_global_intermarket": [10.0] * 4,
            "score_valuation_leverage": [10.0] * 4,
            "score_quant_model": [8.0] * 4,
            "score_ml_forecast": [5.0] * 4,
            "score_market_structure": [5.0] * 4,
        })
        seed.to_parquet(isolate_scores_dir / "quarterly_scores_history.parquet", index=False)

        rec = compute_quarterly_score(
            quarter="2022-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )

        # Point-in-time: lịch sử = đúng 4 quý 2021, không hơn
        assert rec["calibration_applied"] is True
        assert rec["calibration_n_history"] == 4
        assert rec["calibration_hist_mean"] == pytest.approx(np.mean(hist_scores), abs=1e-3)
        assert rec["calibration_hist_std"] == pytest.approx(np.std(hist_scores, ddof=1), abs=1e-3)
        # z dùng total_score của chính quý hiện tại (nguyên tắc không look-ahead:
        # z chỉ được tính từ thông tin của quý trước + điểm hiện tại)
        z_expected = (rec["total_score"] - np.mean(hist_scores)) / np.std(hist_scores, ddof=1)
        assert rec["calibration_z"] == pytest.approx(z_expected, abs=1e-3)

    def test_no_history_keeps_raw_label(self, isolate_scores_dir):
        """Quý đầu tiên (chưa có lịch sử) → calibrated = raw, applied=False."""
        rec = compute_quarterly_score(
            quarter="2021-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        assert rec["calibration_applied"] is False
        assert rec["calibrated_score"] == rec["total_score"]
        assert rec["calibrated_label"] == rec["label"]

    def test_record_has_all_calibrated_fields(self, isolate_scores_dir):
        """score_record xuất đủ field calibrated_* + calibration_* theo spec."""
        rec = compute_quarterly_score(
            quarter="2021-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        for field in ("calibrated_score", "calibrated_label", "calibrated_emoji",
                      "calibrated_description", "calibrated_allocation",
                      "calibration_z", "calibration_hist_mean", "calibration_hist_std",
                      "calibration_n_history", "calibration_applied"):
            assert field in rec, f"Missing field {field!r}"
        # Nhãn phải nhất quán với get_score_label() của calibrated score (SSOT)
        lbl, em, desc, alloc = get_score_label(rec["calibrated_score"])
        assert rec["calibrated_label"] == lbl
        assert rec["calibrated_emoji"] == em
        assert rec["calibrated_allocation"] == alloc

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
        seed = pd.DataFrame({
            "quarter": [f"2021-Q{i}" for i in (1, 2, 3, 4)],
            "date_computed": ["2026-01-01 00:00"] * 4,
            "total_score": [60.0, 52.0, 54.0, 50.0],
            "label": ["HOLD"] * 4, "percentile_label": ["HOLD"] * 4,
            "pillar_std": [5.0] * 4, "pillar_range": [10.0] * 4,
            "dispersion_level": ["MEDIUM"] * 4,
            "calibrated_score": [60.0, 52.0, 54.0, 50.0], "calibrated_label": ["HOLD"] * 4,
            "score_macro_monetary": [12.0] * 4, "score_global_intermarket": [10.0] * 4,
            "score_valuation_leverage": [10.0] * 4, "score_quant_model": [8.0] * 4,
            "score_ml_forecast": [5.0] * 4, "score_market_structure": [5.0] * 4,
        })
        seed.to_parquet(isolate_scores_dir / "quarterly_scores_history.parquet", index=False)

        before = seed["total_score"].tolist()
        compute_quarterly_score(
            quarter="2022-Q1", df_latest=MOCK_LATEST.copy(),
            ftse_upgrade_status="pending", months_to_next_rebalancing=2,
            adtv_change_pct=0.0,
        )
        after = pd.read_parquet(isolate_scores_dir / "quarterly_scores_history.parquet")
        # 4 quý cũ giữ nguyên điểm thô
        for q, s in zip(before, after[after["quarter"] != "2022-Q1"]["total_score"]):
            assert s == q


# ═══════════════════════════════════════════════════════════════════════════
# 9–10. Tier-2 — chống nén tín hiệu tại nguồn
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiCompression:

    def test_quant_model_gains_and_renormalization(self):
        """MLR ±0.10%/ngày → 70/30 (gain 20000); VAR gain 5000;
        tín hiệu MISSING không tham gia trung bình."""
        # MLR +0.10%/ngày → score 70
        r = score_quant_model(mlr_pred=0.001, var_forecast=None)
        assert r["sub_scores"]["mlr_signal_score"] == pytest.approx(70.0, abs=0.5)
        # Chỉ MLR sống → pillar = MLR score (renormalize), KHÔNG bị kéo về (70+50)/2 = 60
        assert r["raw_score"] == pytest.approx(70.0, abs=0.5)
        # MLR -0.10%/ngày → score 30
        r2 = score_quant_model(mlr_pred=-0.001, var_forecast=None)
        assert r2["sub_scores"]["mlr_signal_score"] == pytest.approx(30.0, abs=0.5)
        assert r2["raw_score"] == pytest.approx(30.0, abs=0.5)
        # VAR T+5 +1% → 50 + 0.01*5000 = 100 (clip),VAR duy nhất → pillar = 100
        r3 = score_quant_model(mlr_pred=None, var_forecast=0.01)
        assert r3["sub_scores"]["var_signal_score"] == pytest.approx(100.0, abs=0.5)
        assert r3["raw_score"] == pytest.approx(100.0, abs=0.5)
        # Cả hai MISSING → pillar trung lập thật sự = 50 (không phải "trung bình giả")
        r4 = score_quant_model(mlr_pred=None, var_forecast=None)
        assert r4["raw_score"] == 50.0

    def test_market_structure_renormalizes_missing_components(self):
        """ADTV/ETF thiếu → KHÔNG kéo pillar về 50; trung bình chỉ trên cấu phần có dữ liệu."""
        empty = pd.Series(dtype=float)   # không có ETF z-score
        # FTSE unknown (50) + 2 tháng tới rebalancing (bonus 12) = 62; ADTV/ETF missing
        r = score_market_structure(df_latest=empty, ftse_upgrade_status="unknown",
                                   months_to_next_rebalancing=2, adtv_change_pct=None)
        assert r["raw_score"] == pytest.approx(62.0, abs=0.1), \
            "Pillar phải = FTSE component một mình (renormalize), không bị kéo về 50"
        # Có thêm ADTV +20% (score 70) → mean(62, 70) = 66
        r2 = score_market_structure(df_latest=empty, ftse_upgrade_status="unknown",
                                    months_to_next_rebalancing=2, adtv_change_pct=0.20)
        assert r2["raw_score"] == pytest.approx(66.0, abs=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
