"""Regression tests for the point-in-time scorer-input contract.

Root cause of the failed quarterly workflow runs #18/#19 (2026-Q4):
`run_quarterly.py` re-scored the quarter from live data while
`generate_english_master_workbook.py` rebuilt the formula workbook from

  * the manually backfilled ledgers `data/scores/vnindex_quarterly_*.json`, and
  * the 4-decimal **display strings** inside `group_details`.

Both are lossy/stale snapshots, so the workbook no longer reproduced the
published JSON and `verify_workbook_accuracy.py` exited 1.

The fix publishes the exact inputs the scorer used
(`quarterly_score.pit_scorer_inputs`) and makes the workbook prefer them.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import generate_english_master_workbook as gw
from src.scoring.quarterly_scorer import (
    PIT_INPUTS_SCHEMA_VERSION,
    build_pit_scorer_inputs,
    compute_quarterly_score,
)
from src.utils.config import SCORE_MODEL_PARAMS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _latest_series() -> pd.Series:
    return pd.Series({
        "date": pd.Timestamp("2026-09-30"),
        "vn1y_yield": 3.9012345,
        "delta_vn1y_yield": 0.00613579,
        "vn10y_yield": 4.4910987,
        "vn_yield_spread": 0.5898642,
        "usd_vnd_zscore": -1.2213456,
        "m2_yoy_pct": 14.98,
        "dxy_zscore_60d": 1.0512345,
        "us10y_yield": 5.1812345,
        "usdjpy_zscore_60d": -0.1612345,
        "oil_shock_score_ytd": 43.812345,
        "nff_ex_etf_q_zscore_live": -0.01801223,
        "nff_ex_etf_q_ytd": -0.0018012223148955058,
        "etf_flow_q_zscore_live": -0.11041234,
        "etf_flow_q_ytd": 1.304077894212551e-05,
        "pe_zscore": 0.83311111,
        "pb_zscore": 0.70042222,
        "eyg_zscore": -1.21883333,
        "margin_risk_score": 20.0,
    })


def _pit() -> dict:
    return build_pit_scorer_inputs(
        df_latest=_latest_series(),
        mlr_pred=-0.00025130269673105177,
        var_forecast=1.327466800523265e-05,
        mlr_adj_r2=0.0602,
        granger_leaders=1,
        ftse_upgrade_status="confirmed",
        months_to_next_rebalancing=0,
        adtv_change_pct=-0.1226,
    )


def _payload(pit: dict | None) -> dict:
    score = {
        "data_as_of": "2026-09-25",
        "group_details": {
            "global_intermarket": {
                "dxy": "Z = 1.05 → score 29",
                "us10y": "5.18% → score 0",
                "jpy_carry": "Z = -0.16 (Neutral) → score 48",
                "oil_shock": "Oil Shock Score = 43.8 (Max Δ5d = 19.5%) → score 56",
            },
            "valuation_leverage": {"margin_risk": "Risk = 20/100 (SAFE) → score 80"},
            "market_structure": {
                "ftse_upgrade": "Status: confirmed → score 75",
                "rebalancing": "3 months to rebalancing → bonus +6",
            },
            "quant_model": {
                # display strings are rounded to four decimals — lossy on purpose
                "mlr_forecast": "Forward log-return/day (next ~1M) = -0.0003 → score 45",
                "var_forecast": "VAR T+5 return = 0.0000 → score 50",
                "mlr_adj_r2": "Adj-R² = 0.0602 → confidence bonus 0.6",
                "granger_leaders": "1 vars Granger-cause VNI (p<5%)",
            },
        },
    }
    if pit is not None:
        score["pit_scorer_inputs"] = pit
    return {
        "quarterly_score": score,
        "granger_causality": [{"p_value": 0.0072}],
        "ml_walk_forward_validation": {"n_folds": 8, "n_features": 104},
    }


# stale ledgers: the 2026-09-25 provisional snapshot that CI still had on disk
STALE_MARKET = {"2026-Q4": {
    "bonds": {"vn1y_yield": 3.8615, "delta_vn1y_yield": 0.004357,
              "vn10y_yield": 4.4753, "vn_yield_spread": 0.5289},
    "fx_zscore": -1.27, "m2": {"m2_yoy_pct": 14.98},
    "pepb_z": {"pe": 0.8055707548717673, "pb": 0.6810894520369312, "eyg": -1.2509962353563078},
}}
STALE_FLOWS = {"2026-Q4": {"nff_z": -0.0525, "nff_ytd_pct": -0.1609,
                           "etf_z": -0.1187, "etf_ytd_pct": 0.0011}}
STALE_ADTV = {"2026-Q4": {"adtv_change_pct": -0.119329}}


def test_pit_inputs_are_full_precision_and_schema_tagged():
    pit = _pit()
    assert pit["schema_version"] == PIT_INPUTS_SCHEMA_VERSION
    assert pit["as_of"] == "2026-09-30"
    assert pit["quant"]["mlr_pred"] == pytest.approx(-0.00025130269673105177, rel=0, abs=0)
    assert pit["bonds"]["vn1y_yield"] == pytest.approx(3.9012345, abs=0)
    # flows %-of-market-cap keeps the ledger unit (percent, not fraction)
    assert pit["flows"]["nff_ytd_pct"] == pytest.approx(-0.18012223148955058, rel=1e-12)


def test_missing_inputs_are_published_as_null_not_defaults():
    pit = build_pit_scorer_inputs(
        df_latest=pd.Series({"date": pd.Timestamp("2026-09-30"), "vn1y_yield": np.nan}),
        mlr_pred=None, var_forecast=None, mlr_adj_r2=None, granger_leaders=None,
        ftse_upgrade_status="unknown", months_to_next_rebalancing=None, adtv_change_pct=None,
    )
    assert pit["bonds"]["vn1y_yield"] is None
    assert pit["macro"]["m2_yoy_pct"] is None
    assert pit["quant"]["mlr_pred"] is None
    assert pit["structure"]["adtv_change_pct"] is None
    # JSON-serialisable (no NaN leaking into the published contract)
    assert "NaN" not in json.dumps(pit)


def test_workbook_prefers_exported_inputs_over_stale_ledger_and_rounded_text():
    pit = _pit()
    item = gw.extract_inputs("2026-Q4", _payload(pit), STALE_MARKET, STALE_ADTV, STALE_FLOWS)

    assert item["as_of"] == "2026-09-30"                     # not the stale 2026-09-25
    assert item["vn1y"] == pytest.approx(3.9012345, abs=0)   # not 3.8615
    assert item["pe_z"] == pytest.approx(0.83311111, abs=0)
    assert item["nff_z"] == pytest.approx(-0.01801223, abs=0)
    assert item["adtv"] == pytest.approx(-0.1226, abs=0)
    assert item["months"] == 0                               # not the "3 months" text
    assert item["mlr_pred"] == pytest.approx(-0.00025130269673105177, abs=0)
    assert item["var_pred"] == pytest.approx(1.327466800523265e-05, abs=0)


def test_workbook_falls_back_to_legacy_sources_for_quarters_without_contract():
    """Historical quarters published before the contract must not change."""
    item = gw.extract_inputs("2026-Q4", _payload(None), STALE_MARKET, STALE_ADTV, STALE_FLOWS)
    assert item["as_of"] == "2026-09-25"
    assert item["vn1y"] == pytest.approx(3.8615)
    assert item["nff_z"] == pytest.approx(-0.0525)
    assert item["adtv"] == pytest.approx(-0.119329)
    assert item["months"] == 3
    assert item["mlr_pred"] == pytest.approx(-0.0003)


def test_rounded_display_text_cannot_carry_the_quant_pillar_within_tolerance():
    """Why the contract is required: 4-decimal text is 10× coarser than the audit.

    quant MLR signal = 50 + mlr_pred × 20000, averaged with the VAR signal, so a
    5e-5 display rounding moves the pillar by up to 0.5 — the workbook verifier
    tolerance is 0.05.
    """
    gain = SCORE_MODEL_PARAMS["quant_model"]["mlr_gain"]
    exact = -0.00025130269673105177
    displayed = float(f"{exact:.4f}")
    pillar_shift = abs(exact - displayed) * gain / 2
    assert pillar_shift > 0.05


def test_compute_quarterly_score_publishes_the_contract(tmp_path, monkeypatch):
    record = compute_quarterly_score(
        quarter="2099-Q1",
        df_latest=_latest_series(),
        mlr_pred=-0.00025130269673105177,
        var_forecast=1.327466800523265e-05,
        mlr_adj_r2=0.0602,
        granger_leaders=1,
        ml_accuracy=0.485,
        ml_f1=0.4326,
        ml_pred_class=-1,
        ml_confidence=0.6131,
        ftse_upgrade_status="confirmed",
        adtv_change_pct=-0.1226,
    )
    pit = record["pit_scorer_inputs"]
    assert pit["quant"]["mlr_pred"] == pytest.approx(-0.00025130269673105177, abs=0)
    assert pit["valuation"]["pe_zscore"] == pytest.approx(0.83311111, abs=0)
    assert pit["structure"]["ftse_upgrade_status"] == "confirmed"
