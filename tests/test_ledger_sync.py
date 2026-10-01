"""Regression tests for the audit-ledger synchronisation contract.

`data/scores/vnindex_quarterly_{market_data,flows,adtv}.json` used to be written
only by the manual `scripts/backfill_*.py` runs, so a live re-score of an already
published quarter left them behind (root cause of workflow runs #18/#19).
`sync_quarter_ledgers()` now refreshes the scored quarter — and only that
quarter — straight from the inputs the scorer used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.scoring.ledger_sync import (
    ADTV_LEDGER,
    FLOWS_LEDGER,
    MARKET_DATA_LEDGER,
    sync_quarter_ledgers,
)
from src.scoring.quarterly_scorer import build_pit_scorer_inputs

HISTORY_QUARTER = "2026-Q3"
LIVE_QUARTER = "2026-Q4"


def _pit():
    return build_pit_scorer_inputs(
        df_latest=pd.Series({
            "date": pd.Timestamp("2026-09-30"),
            "vn1y_yield": 3.9012345, "delta_vn1y_yield": 0.00613579,
            "vn10y_yield": 4.4910987, "vn_yield_spread": 0.5898642,
            "usd_vnd_zscore": -1.2213456, "m2_yoy_pct": 14.98,
            "pe_zscore": 0.83311111, "pb_zscore": 0.70042222, "eyg_zscore": -1.21883333,
            "margin_risk_score": 20.0,
            "nff_ex_etf_q_zscore_live": -0.01801223,
            "nff_ex_etf_q_ytd": -0.0018012223148955058,
            "etf_flow_q_zscore_live": -0.11041234,
            "etf_flow_q_ytd": 1.304077894212551e-05,
        }),
        mlr_pred=-0.00025130269673105177, var_forecast=1.3e-05, mlr_adj_r2=0.0602,
        granger_leaders=1, ftse_upgrade_status="confirmed",
        months_to_next_rebalancing=0, adtv_change_pct=-0.1226,
    )


@pytest.fixture()
def scores_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "ledgers"
    directory.mkdir(exist_ok=True)
    history = {
        "description": "backfill 09/2026",
        "updated_at": "2026-09-28 12:11",
        "quarters": {
            HISTORY_QUARTER: {"quarter": HISTORY_QUARTER, "as_of": "2026-06-30",
                              "bonds": {"vn1y_yield": 3.5}, "rescored": {"macro_monetary": True}},
            LIVE_QUARTER: {"quarter": LIVE_QUARTER, "as_of": "2026-09-25",
                           "bonds": {"vn1y_yield": 3.8615, "bond_date": "2026-09-25"},
                           "fx_zscore": -1.27,
                           "pepb_z": {"pe": 0.8055, "pb": 0.6810, "eyg": -1.2509, "composite": 48.64},
                           "rescored": {"macro_monetary": True, "valuation_leverage": False}},
        },
    }
    for name in (MARKET_DATA_LEDGER, FLOWS_LEDGER, ADTV_LEDGER):
        (directory / name).write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    return directory


def _quarters(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["quarters"]


def test_sync_refreshes_only_the_scored_quarter(scores_dir: Path):
    before_history = _quarters(scores_dir / MARKET_DATA_LEDGER)[HISTORY_QUARTER]
    sync_quarter_ledgers(LIVE_QUARTER, _pit(), scores_dir)

    market = _quarters(scores_dir / MARKET_DATA_LEDGER)
    assert market[HISTORY_QUARTER] == before_history            # history untouched
    assert market[LIVE_QUARTER]["as_of"] == "2026-09-30"
    assert market[LIVE_QUARTER]["bonds"]["vn1y_yield"] == pytest.approx(3.9012345, abs=0)
    assert market[LIVE_QUARTER]["pepb_z"]["pe"] == pytest.approx(0.83311111, abs=0)
    # merge, never clobber: keys owned by the backfill audit survive
    assert market[LIVE_QUARTER]["rescored"] == {"macro_monetary": True, "valuation_leverage": False}
    assert market[LIVE_QUARTER]["pepb_z"]["composite"] == 48.64

    flows = _quarters(scores_dir / FLOWS_LEDGER)[LIVE_QUARTER]
    assert flows["nff_z"] == pytest.approx(-0.01801223, abs=0)
    assert flows["nff_ytd_pct"] == pytest.approx(-0.18012223148955058, rel=1e-12)

    adtv = _quarters(scores_dir / ADTV_LEDGER)[LIVE_QUARTER]
    assert adtv["adtv_change_pct"] == pytest.approx(-0.1226, abs=0)


def test_sync_is_idempotent_for_a_republished_quarter(scores_dir: Path):
    sync_quarter_ledgers(LIVE_QUARTER, _pit(), scores_dir)
    snapshot = {name: (scores_dir / name).read_text(encoding="utf-8")
                for name in (MARKET_DATA_LEDGER, FLOWS_LEDGER, ADTV_LEDGER)}

    changed = sync_quarter_ledgers(LIVE_QUARTER, _pit(), scores_dir)

    assert not any(changed.values())
    for name, text in snapshot.items():
        assert (scores_dir / name).read_text(encoding="utf-8") == text


def test_sync_records_adtv_windows_when_available(scores_dir: Path):
    windows = {"2026-Q3": {"adtv": 670735870.12, "n_sessions": 63},
               "2026-Q2": {"adtv": 764471909.39, "n_sessions": 62}}
    sync_quarter_ledgers(LIVE_QUARTER, _pit(), scores_dir, adtv_windows=windows)
    assert _quarters(scores_dir / ADTV_LEDGER)[LIVE_QUARTER]["windows"] == windows


def test_sync_refuses_to_run_without_the_input_contract(scores_dir: Path):
    with pytest.raises(ValueError):
        sync_quarter_ledgers(LIVE_QUARTER, {}, scores_dir)


def test_sync_creates_a_new_quarter_entry_without_touching_others(scores_dir: Path):
    sync_quarter_ledgers("2027-Q1", _pit(), scores_dir)
    market = _quarters(scores_dir / MARKET_DATA_LEDGER)
    assert set(market) == {HISTORY_QUARTER, LIVE_QUARTER, "2027-Q1"}
    assert market[LIVE_QUARTER]["as_of"] == "2026-09-25"
