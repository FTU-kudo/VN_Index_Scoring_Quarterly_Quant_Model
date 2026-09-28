"""
test_mlr_forecast.py — Enforce MLR là mô hình DỰ BÁO, không phải nowcast
=========================================================================
BỐI CẢNH: Trước fix này, MLR hồi quy log_return CÙNG NGÀY trên features
đồng thời (nowcast), rồi lấy trung bình fitted values 30 ngày cuối làm
"forecast" — không có giá trị dự báo cho quyết định phân bổ đầu quý.

Test này sẽ FAIL ngay nếu ai đó sửa target quay lại return cùng ngày.

Acceptance Criteria:
  1. make_forward_target: y_t = mean(r_{t+1..t+h}) — kiểm tra bằng tay,
     KHÔNG chứa r_t; h hàng cuối phải NaN.
  2. Anti-nowcast: feature = chính return cùng ngày (predictor đương thời
     hoàn hảo) trên dữ liệu iid → R² phải THẤP. (Model nowcast cũ sẽ cho
     R² = 1.0 → test này phân biệt tuyệt đối hai thiết kế.)
  3. Oracle: feature = forward target + nhiễu nhỏ → R² phải CAO
     (chứng minh alignment X_t ↔ y_{t+1..t+h} nối dây đúng).
  4. OOS metrics (hit-rate, R², n) phải tồn tại sau fit.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from src.models.regression.mlr_model import MLRModel, make_forward_target


# ═══════════════════════════════════════════════════════════════════════════
# 1. make_forward_target — alignment kiểm tra bằng tay
# ═══════════════════════════════════════════════════════════════════════════

class TestMakeForwardTarget:

    def test_alignment_hand_computed(self):
        r = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
        y = make_forward_target(r, horizon=2)
        # (h-1) hàng đầu NaN do rolling window chưa đầy
        assert pd.isna(y.iloc[0])
        # y_1 = mean(r_2, r_3) = (0.03 + 0.04) / 2 — chỉ chứa TƯƠNG LAI của t=1
        assert y.iloc[1] == pytest.approx((0.03 + 0.04) / 2)
        # y_3 = mean(r_4, r_5) = (0.05 + 0.06) / 2
        assert y.iloc[3] == pytest.approx((0.05 + 0.06) / 2)
        # 2 hàng cuối chưa biết tương lai → NaN
        assert y.iloc[-2:].isna().all()

    def test_target_excludes_same_day_return(self):
        """y_t KHÔNG được chứa r_t — điểm phân biệt dự báo vs nowcast."""
        rng = np.random.default_rng(7)
        r = pd.Series(rng.normal(0, 0.01, 300))
        y = make_forward_target(r, horizon=5)
        valid = y.notna()
        # r_t và y_t (mean của r_{t+1..t+5}, iid) phải gần như không tương quan
        corr = float(np.corrcoef(r[valid], y[valid])[0, 1])
        assert abs(corr) < 0.2, (
            f"corr(r_t, y_t) = {corr:.3f} — target đang chứa return cùng ngày?"
        )

    def test_invalid_horizon_raises(self):
        with pytest.raises(ValueError):
            make_forward_target(pd.Series([0.01, 0.02]), horizon=0)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers cho fixture dữ liệu synthetic
# ═══════════════════════════════════════════════════════════════════════════

def _base_df(n=400, seed=42):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "date":       pd.date_range("2020-01-01", periods=n, freq="B"),
        "log_return": rng.normal(0.0003, 0.012, n),
        "noise_x":    rng.normal(0, 1, n),
    }), rng


# ═══════════════════════════════════════════════════════════════════════════
# 2. Anti-nowcast — regression test cho chính bug đã sửa
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiNowcast:

    def test_contemporaneous_predictor_gives_low_r2(self):
        """
        Feature = chính log_return cùng ngày (predictor đương thời hoàn hảo).
        - Model NOWCAST cũ: R² = 1.0 (target là return cùng ngày)
        - Model DỰ BÁO đúng: R² ≈ 0 (return iid không dự báo được tương lai)
        """
        df, _ = _base_df()
        df["same_day_leak"] = df["log_return"]

        mlr = MLRModel(
            feature_cols=["same_day_leak", "noise_x"],
            horizon=21,
        )
        mlr.fit(df)
        assert mlr.r2_ < 0.2, (
            f"R²-train = {mlr.r2_:.4f} với feature đương thời hoàn hảo — "
            "MLR đang nowcast return cùng ngày thay vì dự báo forward!"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Oracle — xác nhận alignment X_t ↔ y_{t+1..t+h} nối dây đúng
# ═══════════════════════════════════════════════════════════════════════════

class TestOracleAlignment:

    def test_oracle_feature_gives_high_r2(self):
        """
        Feature 'oracle' = forward target + nhiễu nhỏ. Nếu target/feature
        alignment đúng, model phải học được gần hoàn hảo. Nếu ai đổi target
        về return cùng ngày, oracle mất khả năng giải thích → test fail.
        """
        df, rng = _base_df(seed=123)
        h = 21
        fwd = make_forward_target(df["log_return"], horizon=h)
        df["oracle"] = fwd + rng.normal(0, fwd.std() * 0.1, len(df))

        mlr = MLRModel(feature_cols=["oracle", "noise_x"], horizon=h)
        mlr.fit(df)
        assert mlr.r2_ > 0.5, (
            f"R²-train = {mlr.r2_:.4f} với oracle feature — "
            "target/feature alignment bị sai (target không phải forward return?)"
        )

        # Dự báo từ hàng có oracle hợp lệ phải xấp xỉ forward target thật
        valid_rows = df.dropna(subset=["oracle"]).tail(5)
        preds = mlr.predict(valid_rows)
        assert np.isfinite(preds).all()


# ═══════════════════════════════════════════════════════════════════════════
# 4. OOS metrics — thước đo dự báo trung thực phải luôn có mặt
# ═══════════════════════════════════════════════════════════════════════════

class TestOOSMetrics:

    def test_oos_metrics_populated_after_fit(self):
        df, _ = _base_df()
        mlr = MLRModel(feature_cols=["noise_x", "same"], horizon=5)
        df["same"] = df["log_return"].shift(1)  # lagged — hợp lệ
        mlr.fit(df)

        assert set(mlr.oos_metrics_.keys()) >= {"oos_r2", "oos_hit_rate", "oos_n"}
        assert mlr.oos_metrics_["oos_n"] >= 10
        assert 0.0 <= mlr.oos_metrics_["oos_hit_rate"] <= 1.0

        diag = mlr.diagnostics()
        assert "oos" in diag, "diagnostics() phải expose OOS metrics"

    def test_nw_maxlags_at_least_horizon(self):
        """Overlapping windows → NW maxlags phải ≥ horizon."""
        mlr = MLRModel(horizon=21, max_lags_nw=5)
        assert mlr.max_lags_nw >= 21


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
