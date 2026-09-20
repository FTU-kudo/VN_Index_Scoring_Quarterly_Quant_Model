"""
test_scoring_weights.py — Automated tests for scoring weight integrity
=======================================================================
Acceptance Criteria:
  1. Sum of SCORING_WEIGHTS == 1.0
  2. Every group has weight > 0 (especially valuation_leverage)
  3. compute_quarterly_score() produces effective weights > 0.9
  4. When pepb data exists, valuation weighted_score > 0
"""

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

from src.utils.config import SCORING_WEIGHTS


class TestScoringWeightsConfig:
    """Tests for the canonical weight definitions in config.py."""

    def test_weights_sum_to_one(self):
        total = sum(SCORING_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Total weights = {total}, expected 1.0"

    def test_all_groups_have_positive_weight(self):
        for group, weight in SCORING_WEIGHTS.items():
            assert weight > 0, f"Group '{group}' has weight={weight}, must be > 0"

    def test_valuation_leverage_has_meaningful_weight(self):
        """valuation_leverage must have >= 15% weight (it's a critical pillar)."""
        val_weight = SCORING_WEIGHTS.get("valuation_leverage", 0)
        assert val_weight >= 0.15, (
            f"valuation_leverage weight={val_weight}, expected >= 0.15. "
            "This pillar is critical for market attractiveness scoring."
        )

    def test_expected_groups_exist(self):
        expected = {
            "macro_monetary", "global_intermarket", "valuation_leverage",
            "quant_model", "ml_forecast", "market_structure"
        }
        actual = set(SCORING_WEIGHTS.keys())
        assert expected == actual, f"Missing groups: {expected - actual}, Extra: {actual - expected}"


class TestComputeQuarterlyScore:
    """Tests for the master scoring function."""

    @pytest.fixture
    def mock_latest_series(self):
        """Create a pd.Series with enough indicators for all 6 scorers."""
        return pd.Series({
            "omo_overnight_rate": 4.0,
            "delta_omo_rate": -0.01,
            "usd_vnd_zscore": -0.5,
            "m2_yoy_pct": 12.0,
            "vn10y_yield": 4.5,
            "vn_yield_spread": 0.5,
            "dxy_zscore_60d": 0.3,
            "us10y_yield": 4.5,
            "delta_us10y": 0.01,
            "nff_zscore_60d": 0.2,
            "nff_rolling5d": 100,
            "pe_zscore": -0.3,
            "pb_zscore": -0.2,
            "margin_risk_score": 30,
            "eyg_zscore": 0.5,
        })

    def test_effective_weights_above_threshold(self, mock_latest_series):
        from src.scoring.quarterly_scorer import compute_quarterly_score

        result = compute_quarterly_score(
            quarter="2026-Q3",
            df_latest=mock_latest_series,
            mlr_pred=0.001,
            var_forecast=0.0005,
            mlr_adj_r2=0.25,
            granger_leaders=3,
            ml_accuracy=0.55,
            ml_f1=0.54,
            ml_pred_class=1,
            ml_confidence=0.6,
            ftse_upgrade_status="confirmed",
            adtv_change_pct=0.10,
        )

        # Sum of effective weighted scores should be > 0.9 * 100 = 90%+ of theoretical max
        group_scores = result["group_scores"]
        total_effective_weight = sum(
            gs["weighted_score"] / max(gs["raw_score"], 1e-9)
            for gs in group_scores.values()
            if gs["raw_score"] > 0
        )
        # Each group contributes weight * raw_score; effective weight = weighted/raw
        # If all groups have data, total effective weight should equal sum of config weights = 1.0
        assert total_effective_weight > 0.9, (
            f"Effective weight = {total_effective_weight:.3f}, expected > 0.9. "
            "Some groups may be missing data or have zero contribution."
        )

    def test_valuation_contributes_when_data_exists(self, mock_latest_series):
        from src.scoring.quarterly_scorer import compute_quarterly_score

        result = compute_quarterly_score(
            quarter="2026-Q3",
            df_latest=mock_latest_series,
            ftse_upgrade_status="confirmed",
            adtv_change_pct=0.10,
        )

        val_score = result["group_scores"].get("valuation_leverage", {})
        assert val_score.get("weighted_score", 0) > 0, (
            f"valuation_leverage weighted_score = {val_score.get('weighted_score', 0)}. "
            "When P/E Z-score data exists, valuation MUST contribute to total score."
        )

    def test_total_score_in_valid_range(self, mock_latest_series):
        from src.scoring.quarterly_scorer import compute_quarterly_score

        result = compute_quarterly_score(
            quarter="2026-Q3",
            df_latest=mock_latest_series,
            ftse_upgrade_status="confirmed",
            adtv_change_pct=0.10,
        )

        total = result["total_score"]
        assert 0 <= total <= 100, f"Total score {total} out of range [0, 100]"

    def test_score_market_structure_requires_rebalancing_param(self):
        from src.scoring.quarterly_scorer import score_market_structure

        with pytest.raises(ValueError, match="months_to_next_rebalancing is required"):
            score_market_structure(ftse_upgrade_status="confirmed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
