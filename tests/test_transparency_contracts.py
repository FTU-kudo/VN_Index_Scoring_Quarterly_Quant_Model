import re
import pandas as pd
from src.scoring.quarterly_scorer import score_ml_forecast, compute_data_coverage


def test_ml_direction_and_confidence_are_monotone():
    up_low = score_ml_forecast(0.5, 0.5, 1, 0.34)
    up_high = score_ml_forecast(0.5, 0.5, 1, 0.90)
    down_low = score_ml_forecast(0.5, 0.5, -1, 0.34)
    down_high = score_ml_forecast(0.5, 0.5, -1, 0.90)
    assert up_high["sub_scores"]["ml_signal_score"] >= up_low["sub_scores"]["ml_signal_score"]
    assert down_high["sub_scores"]["ml_signal_score"] <= down_low["sub_scores"]["ml_signal_score"]
    assert down_high["sub_scores"]["ml_signal_score"] < 50 < up_high["sub_scores"]["ml_signal_score"]


def test_coverage_uses_only_24_required_fields():
    details = {
        "macro_monetary": {k: "value" for k in ("vn1y_yield", "ir_trend", "usd_vnd", "m2_yoy_growth", "vn_bonds")},
        "global_intermarket": {k: "value" for k in ("dxy", "us10y", "nff_ex_etf", "jpy_carry", "oil_shock")},
        "valuation_leverage": {"pe_zscore": "<MISSING> N/A", "pb_zscore": "<MISSING> N/A", "margin_risk": "Risk = 10/100 → score 90", "eyg_zscore": "<MISSING> N/A"},
        "quant_model": {k: "value" for k in ("mlr_forecast", "var_forecast", "mlr_adj_r2", "granger_leaders")},
        "ml_forecast": {k: "value" for k in ("model_quality", "ml_signal")},
        "market_structure": {k: "value" for k in ("ftse_upgrade", "rebalancing", "adtv", "etf_flow")},
    }
    result = compute_data_coverage(details)
    assert result["required"] == 24
    assert result["available"] == 21
    assert result["by_group"]["valuation_leverage"]["missing"] == ["pe_zscore", "pb_zscore", "eyg_zscore"]


def test_model_quality_parser_accepts_quality_and_score_formats():
    from src.reporting.excel_builder import _clean_detail_text
    for text in ("Accuracy=50% → quality 50", "Accuracy=50% → score 50"):
        assert _clean_detail_text(text)[1] == 50
