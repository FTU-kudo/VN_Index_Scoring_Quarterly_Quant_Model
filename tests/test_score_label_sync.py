"""
test_score_label_sync.py - Kiem tra dong bo nguong SCORE_LABELS
=================================================================
Test nay se FAIL ngay neu ai hardcode lai nguong trong report_builder.py
ma quen sua config.py - dung loi da xay ra (Fix #1 enforcement).

Acceptance Criteria:
  1. SCORE_LABELS trong config.py va text HTML phai khop nhau 100%
  2. get_score_label() phai tra ve dung nhan cho tung vung diem
  3. Khong co hardcode nguong trong report_builder.py
  4. Cac truong moi (percentile_label, pillar_std, dispersion_level)
     phai co trong score_record output
"""
import sys, json, re
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import numpy as np
import pandas as pd
import pytest
from src.utils.config import SCORE_LABELS, SCORE_LABEL_RANGES, get_score_label


class TestScoreLabelConfig:
    """Tests for SCORE_LABELS structure and get_score_label() function."""

    def test_score_labels_has_5_tiers(self):
        assert len(SCORE_LABELS) == 5, (
            f"SCORE_LABELS has {len(SCORE_LABELS)} tiers, expected 5. "
            "Required: BUY, ACCUMULATE, HOLD, REDUCE, SELL."
        )

    def test_score_labels_covers_0_to_100_continuously(self):
        sorted_ranges = sorted(SCORE_LABELS.keys(), key=lambda x: x[0])
        assert sorted_ranges[0][0] == 0, f"Lowest tier starts at {sorted_ranges[0][0]}, expected 0"
        assert sorted_ranges[-1][1] == 100, f"Highest tier ends at {sorted_ranges[-1][1]}, expected 100"
        for i in range(len(sorted_ranges) - 1):
            hi_current = sorted_ranges[i][1]
            lo_next    = sorted_ranges[i + 1][0]
            assert hi_current + 1 == lo_next, (
                f"Gap/overlap at tier {i}: hi={hi_current} -> lo_next={lo_next}. "
                "Tiers MUST be continuous without gaps."
            )

    def test_score_labels_has_allocation_field(self):
        for (lo, hi), values in SCORE_LABELS.items():
            assert len(values) == 4, (
                f"Tier ({lo},{hi}) has {len(values)} fields, expected 4: "
                "(label, emoji, description, allocation)."
            )
            label, emoji, desc, alloc = values
            assert isinstance(label, str) and len(label) > 0
            assert "%" in alloc, f"allocation {alloc!r} must contain '%'"

    def test_get_score_label_boundary_values(self):
        for (lo, hi), (lbl, em, desc, alloc) in SCORE_LABELS.items():
            assert get_score_label(lo)[0] == lbl, f"get_score_label({lo}) returned wrong label"
            assert get_score_label(hi)[0] == lbl, f"get_score_label({hi}) returned wrong label"

    def test_get_score_label_typical_values(self):
        """Test labels for typical historical score values."""
        # With thresholds 35-49=REDUCE, 50-64=HOLD, 65-79=ACCUMULATE:
        cases = [
            (42.58, "REDUCE"),    # 2026-Q1: lowest in history
            (46.59, "REDUCE"),    # 2022-Q2: second lowest
            (50.0,  "HOLD"),      # lower bound of HOLD
            (52.86, "HOLD"),      # 2026-Q3
            (58.42, "HOLD"),      # 2023-Q2: highest in history
            (64.0,  "HOLD"),      # upper bound of HOLD
            (65.0,  "ACCUMULATE"),
            (79.0,  "ACCUMULATE"),
            (80.0,  "BUY"),
            (100.0, "BUY"),
            (35.0,  "REDUCE"),
            (34.0,  "SELL"),
            (0.0,   "SELL"),
        ]
        config_str = {f"{lo}-{hi}": v[0] for (lo, hi), v in SCORE_LABELS.items()}
        for score, expected in cases:
            result = get_score_label(score)
            assert result[0] == expected, (
                f"get_score_label({score}) = {result[0]!r}, expected {expected!r}. "
                f"Current SCORE_LABELS: {config_str}"
            )


class TestHtmlThresholdSync:
    """
    CRITICAL: This test verifies HTML report thresholds match config.py.
    This is exactly the bug that was fixed (40-59 in code, 50-64 in report).
    This test FAILS if that bug recurs.
    """

    @pytest.fixture
    def sample_html_path(self):
        reports_dir = PROJECT_ROOT / "output" / "reports"
        candidate = reports_dir / "2026_Q3" / "index.html"
        if candidate.exists():
            return candidate
        html_files = list(reports_dir.glob("*/index.html"))
        return sorted(html_files)[-1] if html_files else None

    def test_html_allocation_uses_config_thresholds(self, sample_html_path):
        """HTML Asset Allocation thresholds must match config.py SCORE_LABELS exactly."""
        if sample_html_path is None or not sample_html_path.exists():
            pytest.skip("No HTML report found. Run run_quarterly.py first.")
        html = sample_html_path.read_text(encoding="utf-8", errors="replace")
        # Find all "NN-NN:" patterns (both hyphen and en-dash)
        threshold_pattern = re.compile(r"(\d{1,3})[–\-](\d{1,3}):", re.UNICODE)
        found = set()
        for m in threshold_pattern.finditer(html):
            lo, hi = int(m.group(1)), int(m.group(2))
            if 0 <= lo <= 100 and 0 <= hi <= 100 and lo < hi:
                found.add((lo, hi))
        config_t = set(SCORE_LABELS.keys())
        extra   = found - config_t
        missing = config_t - found
        assert not extra, (
            f"HTML has thresholds {sorted(extra)} NOT in config.py SCORE_LABELS. "
            f"This means hardcoded thresholds exist in report_builder.py. "
            f"Config thresholds: {sorted(config_t)}"
        )
        assert not missing, (
            f"HTML is MISSING thresholds {sorted(missing)} vs config.py SCORE_LABELS. "
            f"HTML thresholds found: {sorted(found)}"
        )

    def test_no_hardcoded_old_thresholds_in_report_builder(self):
        """report_builder.py must NOT contain hardcoded old thresholds."""
        rb_path = PROJECT_ROOT / "src" / "reporting" / "report_builder.py"
        rb_src  = rb_path.read_text(encoding="utf-8")
        # Old hardcoded patterns that should no longer exist
        forbidden = ["50-64:", "65-79:", "35-49:", "0-34:", "80-100:"]
        for pat in forbidden:
            matches = [
                line for line in rb_src.splitlines()
                if re.search(re.escape(pat), line) and not line.strip().startswith("#")
            ]
            assert not matches, (
                f"report_builder.py still has hardcoded threshold {pat!r} "
                f"at {len(matches)} lines: {matches[:2]}. "
                "Remove hardcode and use SCORE_LABELS from config.py."
            )


class TestNewScoreFields:
    """Tests that score_record has the new Fix #2 and Fix #3 fields."""

    @pytest.fixture
    def mock_series(self):
        return pd.Series({
            "omo_overnight_rate": 4.0, "delta_omo_rate": -0.01,
            "usd_vnd_zscore": -0.5, "m2_yoy_pct": 12.0,
            "vn10y_yield": 4.5, "vn_yield_spread": 0.5,
            "dxy_zscore_60d": 0.3, "us10y_yield": 4.5, "delta_us10y": 0.01,
            "nff_ex_etf_q_zscore_live": 0.2,
            "pe_zscore": -0.3, "pb_zscore": -0.2,
            "margin_risk_score": 30, "eyg_zscore": 0.5,
        })

    def _run_scorer(self, mock_series):
        from src.scoring.quarterly_scorer import compute_quarterly_score
        return compute_quarterly_score(
            quarter="2099-Q1",
            df_latest=mock_series,
            ftse_upgrade_status="pending",
            adtv_change_pct=0.0,
        )

    def test_has_percentile_label(self, mock_series):
        result = self._run_scorer(mock_series)
        assert "percentile_label" in result, f"Missing percentile_label. Keys: {list(result.keys())}"
        assert result["percentile_label"] in ("BUY/ACCUMULATE", "REDUCE/SELL", "HOLD")

    def test_has_dispersion_fields(self, mock_series):
        result = self._run_scorer(mock_series)
        for field in ("pillar_std", "pillar_range", "dispersion_level"):
            assert field in result, f"Missing {field!r}. Keys: {list(result.keys())}"
        assert result["dispersion_level"] in ("LOW", "MEDIUM", "HIGH")
        assert result["pillar_std"] >= 0
        assert result["pillar_range"] >= 0

    def test_has_label_allocation(self, mock_series):
        result = self._run_scorer(mock_series)
        assert "label_allocation" in result
        assert "%" in result["label_allocation"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
