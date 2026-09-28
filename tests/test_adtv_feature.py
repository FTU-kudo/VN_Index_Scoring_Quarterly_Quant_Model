"""
test_adtv_feature.py — Tests cho ADTV (Average Daily Trading Volume)
====================================================================
Phạm vi:
  1. market_structure_features: quarter_bounds, previous_quarter,
     compute_quarterly_adtv, compute_adtv_change_pct (point-in-time!),
     parse_market_structure_inputs_from_details.
  2. backfill_adtv.backfill_all: end-to-end trên workspace tổng hợp (tmp_path)
     — parquet + JSON export + audit cache; không đụng dữ liệu thật.
  3. Wiring: run_quarterly.py biên dịch + truyền adtv_change_pct (py_compile).
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.features.market_structure_features import (
    MIN_SESSIONS_PER_QUARTER,
    compute_adtv_change_pct,
    compute_quarterly_adtv,
    parse_market_structure_inputs_from_details,
    previous_quarter,
    quarter_bounds,
)
from src.scoring.quarterly_scorer import score_market_structure
from src.utils.config import get_score_label


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — OHLCV tổng hợp
# ═══════════════════════════════════════════════════════════════════════════════

def make_ohlcv(quarter_volumes: dict, sessions_per_quarter: int = 60) -> pd.DataFrame:
    """quarter_volumes: {'2025-Q3': 100e6, ...} — volume không đổi trong quý."""
    rows = []
    for q, vol in quarter_volumes.items():
        start, end = quarter_bounds(q)
        dates = pd.bdate_range(start, end)[:sessions_per_quarter]
        for d in dates:
            rows.append({"date": d, "open": 1000.0, "high": 1010.0, "low": 990.0,
                         "close": 1005.0, "volume": vol})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Quarter math
# ═══════════════════════════════════════════════════════════════════════════════

def test_quarter_bounds():
    assert quarter_bounds("2026-Q3") == (pd.Timestamp("2026-07-01"), pd.Timestamp("2026-09-30"))
    assert quarter_bounds("2026-Q1") == (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-31"))
    assert quarter_bounds("2024-Q1") == (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-31"))  # leap
    assert quarter_bounds("2025-Q4") == (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-12-31"))
    with pytest.raises(ValueError):
        quarter_bounds("2026-Q5")
    with pytest.raises(ValueError):
        quarter_bounds("bad")


def test_previous_quarter():
    assert previous_quarter("2026-Q1") == "2025-Q4"
    assert previous_quarter("2026-Q3") == "2026-Q2"
    assert previous_quarter("2025-Q4") == "2025-Q3"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ADTV computation — point-in-time là quan trọng nhất
# ═══════════════════════════════════════════════════════════════════════════════

def test_compute_quarterly_adtv_basic():
    df = make_ohlcv({"2025-Q3": 100_000_000, "2025-Q4": 120_000_000})
    rec = compute_quarterly_adtv(df, "2025-Q4")
    assert rec is not None
    assert abs(rec["adtv"] - 120_000_000) < 1e-6
    assert rec["n_sessions"] == 60


def test_compute_quarterly_adtv_ignores_zero_volume():
    df = make_ohlcv({"2025-Q3": 100_000_000})
    df.loc[df.index[:30], "volume"] = 0        # nửa quý volume = 0 → bị loại
    rec = compute_quarterly_adtv(df, "2025-Q3")
    assert rec is not None and rec["n_sessions"] == 30


def test_compute_adtv_change_pct_math():
    # Điểm quý 2026-Q1: ADTV(2025-Q4)/ADTV(2025-Q3) − 1 = 120/100 − 1 = +20%
    df = make_ohlcv({"2025-Q3": 100_000_000, "2025-Q4": 120_000_000, "2026-Q1": 999})
    change = compute_adtv_change_pct(df, "2026-Q1")
    assert change is not None
    assert abs(change - 0.20) < 1e-9


def test_compute_adtv_change_pct_is_point_in_time():
    """Dữ liệu của CHÍNH quý đang chấm KHÔNG được dùng (no look-ahead)."""
    df = make_ohlcv({"2025-Q3": 100_000_000, "2025-Q4": 120_000_000,
                     "2026-Q1": 1_000_000_000, "2026-Q2": 2_000_000_000})
    c1 = compute_adtv_change_pct(df, "2026-Q1")
    # Thay đổi dữ liệu 2026-Q1 (quý đang chấm) → kết quả KHÔNG đổi
    df2 = df.copy()
    df2.loc[(df2["date"] >= "2026-01-01") & (df2["date"] <= "2026-03-31"), "volume"] = 5_000_000_000
    c2 = compute_adtv_change_pct(df2, "2026-Q1")
    assert c1 == c2 == pytest.approx(0.20, abs=1e-9)
    # Quý 2026-Q2 dùng cặp (Q1, Q4): 1000/120 − 1
    c3 = compute_adtv_change_pct(df, "2026-Q2")
    assert c3 == pytest.approx(1_000_000_000 / 120_000_000 - 1, abs=1e-9)


def test_compute_adtv_change_pct_missing_quarter():
    df = make_ohlcv({"2025-Q4": 120_000_000})      # thiếu Q−2 (2025-Q3)
    assert compute_adtv_change_pct(df, "2026-Q1") is None


def test_compute_adtv_change_pct_insufficient_sessions():
    df = make_ohlcv({"2025-Q3": 100_000_000, "2025-Q4": 120_000_000}, sessions_per_quarter=5)
    assert compute_adtv_change_pct(df, "2026-Q1") is None  # < MIN_SESSIONS_PER_QUARTER


def test_compute_adtv_change_pct_zero_prev():
    df = make_ohlcv({"2025-Q3": 0, "2025-Q4": 120_000_000})  # Q−2 volume = 0
    assert compute_adtv_change_pct(df, "2026-Q1") is None


def test_min_sessions_constant():
    assert MIN_SESSIONS_PER_QUARTER == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Parser input từ JSON cũ
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_market_structure_inputs_full():
    details = {
        "ftse_upgrade": "Status: confirmed → score 75\n  Est passive inflow: $6.4B USD",
        "rebalancing": "0 months to rebalancing → bonus +20",
        "etf_flow": "Z = -0.21 (Neutral) → score 47",
        "etf_flow_q_ytd": "0.00% of Market Cap (YTD in Q)",
    }
    inp = parse_market_structure_inputs_from_details(details)
    assert inp["ftse_upgrade_status"] == "confirmed"
    assert inp["months_to_next_rebalancing"] == 0
    assert inp["etf_flow_q_zscore_live"] == pytest.approx(-0.21, abs=1e-9)


def test_parse_market_structure_inputs_missing_etf():
    details = {
        "ftse_upgrade": "Status: unknown → score 50\n  ...",
        "rebalancing": "3 months to rebalancing → bonus +6",
        "etf_flow": "<MISSING> Not enough data for Z-score (2021) → excluded from pillar average",
    }
    inp = parse_market_structure_inputs_from_details(details)
    assert inp["ftse_upgrade_status"] == "unknown"
    assert inp["months_to_next_rebalancing"] == 3
    assert inp["etf_flow_q_zscore_live"] is None


def test_scorer_uses_adtv():
    """Scorer: có ADTV → tham gia trung bình; thiếu → loại (renormalize)."""
    df_latest = pd.Series({"etf_flow_q_zscore_live": -0.21}, dtype=float)
    with_adtv = score_market_structure(
        df_latest=df_latest, ftse_upgrade_status="confirmed",
        months_to_next_rebalancing=0, adtv_change_pct=0.20,
    )
    assert "ADTV change +20.0% QoQ" in with_adtv["details"]["adtv"]
    assert with_adtv["sub_scores"]["adtv_score"] == 70  # 50 + 0.20*100
    # Trung bình 3 cấu phần: (75+20 + 70 + 46.85)/3
    assert with_adtv["raw_score"] == pytest.approx((95 + 70 + 50 - 0.21 * 15) / 3, abs=0.02)

    no_adtv = score_market_structure(
        df_latest=df_latest, ftse_upgrade_status="confirmed",
        months_to_next_rebalancing=0, adtv_change_pct=None,
    )
    assert no_adtv["details"]["adtv"].startswith("<MISSING>")
    assert no_adtv["raw_score"] == pytest.approx((95 + 50 - 0.21 * 15) / 2, abs=0.02)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Backfill end-to-end trên workspace tổng hợp (không đụng dữ liệu thật)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_export(quarter: str, ms_raw: float, ms_weighted: float, total: float,
                 etf_z=None, ftse="confirmed", months=3) -> dict:
    etf_detail = (f"Z = {etf_z:.2f} (Neutral) → score {50 + etf_z * 15:.0f}"
                  if etf_z is not None else
                  "<MISSING> Not enough data for Z-score (2021) → excluded from pillar average")
    return {
        "metadata": {"quarter": quarter},
        "quarterly_score": {
            "quarter": quarter,
            "date_computed": "2026-01-01 00:00",
            "total_score": total,
            "label": get_score_label(total)[0],
            "pillar_std": 10.0,
            "pillar_range": 30.0,
            "percentile_label": "HOLD",
            "percentile_p15": None,
            "percentile_p85": None,
            "dispersion_level": "MEDIUM",
            "group_scores": {
                "macro_monetary": {"raw_score": 55.0, "weighted_score": 13.75},
                "global_intermarket": {"raw_score": 45.0, "weighted_score": 6.75},
                "valuation_leverage": {"raw_score": 60.0, "weighted_score": 10.0},
                "quant_model": {"raw_score": 50.0, "weighted_score": 10.0},
                "ml_forecast": {"raw_score": 50.0, "weighted_score": 5.0},
                "market_structure": {"raw_score": ms_raw, "weighted_score": ms_weighted},
            },
            "group_details": {
                "market_structure": {
                    "ftse_upgrade": f"Status: {ftse} → score 75\n  Est passive inflow: $6.4B USD",
                    "rebalancing": f"{months} months to rebalancing → bonus +6",
                    "adtv": "<MISSING> ADTV data unavailable → neutral score 50",
                    "etf_flow": etf_detail,
                }
            },
            "group_rationale": {"market_structure": "FTSE: CONFIRMED"},
        },
    }


@pytest.fixture()
def synthetic_workspace(tmp_path):
    """6 quý history + exports + OHLCV tổng hợp (volume tăng dần đều +10%/quý)."""
    quarters = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    rows = []
    base_total, ms_raw = 50.0, 50.0
    for q in quarters:
        ms_w = round(ms_raw * 0.10, 2)
        total = round(base_total - 5.0 + ms_w, 2)  # tổng giả lập, ms đóng 10%
        payload = _make_export(q, ms_raw, ms_w, total, etf_z=-0.2, ftse="confirmed", months=3)
        with open(exports_dir / f"score_{q.replace('-', '_')}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        rows.append({
            "quarter": q, "date_computed": "2026-01-01 00:00",
            "total_score": total, "label": get_score_label(total)[0],
            "score_macro_monetary": 13.75, "score_global_intermarket": 6.75,
            "score_valuation_leverage": 10.0, "score_quant_model": 10.0,
            "score_ml_forecast": 5.0, "score_market_structure": ms_w,
            "percentile_label": "HOLD", "pillar_std": 10.0, "pillar_range": 30.0,
            "dispersion_level": "MEDIUM",
        })
    hist = pd.DataFrame(rows)
    hist_path = tmp_path / "history.parquet"
    hist.to_parquet(hist_path, index=False)

    # OHLCV: 8 quý (2024-Q3 → 2026-Q2), ADTV tăng đều +10%/quý
    vols, v = {}, 100_000_000.0
    for q in ["2024-Q3", "2024-Q4"] + quarters:
        vols[q] = v
        v *= 1.10
    ohlcv = make_ohlcv(vols)
    return tmp_path, exports_dir, hist_path, ohlcv, quarters


def test_backfill_all_end_to_end(synthetic_workspace):
    from scripts.backfill_adtv import backfill_all

    tmp_path, exports_dir, hist_path, ohlcv, quarters = synthetic_workspace
    cache_path = tmp_path / "adtv_cache.json"

    new_hist = backfill_all(
        ohlcv, dry_run=False,
        history_path=hist_path, exports_dir=exports_dir, adtv_cache_path=cache_path,
    )

    # ── Parquet: đúng số quý, cột giữ nguyên ────────────────────────────────
    assert len(new_hist) == len(quarters)
    assert "score_market_structure" in new_hist.columns

    # ── Mỗi quý: ADTV +10% QoQ → adtv_score = 60 → ms raw = (75+6+60+etf)/3 ─
    for _, row in new_hist.iterrows():
        q = row["quarter"]
        payload = json.load(open(exports_dir / f"score_{q.replace('-', '_')}.json", encoding="utf-8"))
        rec = payload["quarterly_score"]

        # ADTV detail KHÔNG còn MISSING
        assert not rec["group_details"]["market_structure"]["adtv"].startswith("<MISSING>")
        assert "ADTV change +10.0% QoQ" in rec["group_details"]["market_structure"]["adtv"]

        # ms raw: (ftse 75 + rebal 6 + adtv 60 + etf 47)/3 = 62.62 (clamp ok)
        expected_ms_raw = (75 + 6 + 60 + (50 - 0.2 * 15)) / 3
        assert rec["group_scores"]["market_structure"]["raw_score"] == pytest.approx(expected_ms_raw, abs=0.02)

        # total mới = total cũ − ms_weighted cũ + ms_weighted mới
        old_payload_total = None  # tính lại từ fixture: base_total − 5 + ms_w_old
        # ms_old = 50*0.1 = 5.0
        expected_total = round(row["total_score"], 2)  # đã là giá trị mới — kiểm tra self-consistent:
        # kiểm tra công thức trực tiếp
        import numpy as _np
        arr = _np.array([g["raw_score"] for g in rec["group_scores"].values()], dtype=float)
        assert rec["pillar_std"] == pytest.approx(float(_np.std(arr, ddof=1)), abs=0.02)

        # label nhất quán với total (single source of truth)
        assert rec["label"] == get_score_label(rec["total_score"])[0]
        assert row["label"] == rec["label"]
        old_payload_total = rec["total_score"]

    # ── Parquet total == JSON total ─────────────────────────────────────────
    for _, row in new_hist.iterrows():
        payload = json.load(open(exports_dir / f"score_{row['quarter'].replace('-', '_')}.json", encoding="utf-8"))
        assert row["total_score"] == payload["quarterly_score"]["total_score"]

    # ── Audit cache viết đầy đủ ─────────────────────────────────────────────
    cache = json.load(open(cache_path, encoding="utf-8"))
    assert set(cache["quarters"].keys()) == set(quarters)
    q0 = cache["quarters"][quarters[0]]
    assert q0["adtv_change_pct"] == pytest.approx(0.10, abs=1e-6)
    w = q0["windows"]
    assert w["2024-Q4"]["adtv"] == pytest.approx(110_000_000, abs=1)   # Q−1 của 2025-Q1
    assert w["2024-Q3"]["adtv"] == pytest.approx(100_000_000, abs=1)   # Q−2 của 2025-Q1

    # ── Percentile expanding: quý cuối đủ 5 quý trước → p15/p85 có giá trị ──
    last_payload = json.load(open(exports_dir / "score_2026_Q2.json", encoding="utf-8"))
    last_rec = last_payload["quarterly_score"]
    assert last_rec["percentile_p15"] is not None
    assert last_rec["percentile_p85"] is not None
    # quý đầu không có lịch sử → mặc định
    first_payload = json.load(open(exports_dir / "score_2025_Q1.json", encoding="utf-8"))
    assert first_payload["quarterly_score"]["percentile_p15"] is None

    # ── metadata audit ──────────────────────────────────────────────────────
    assert last_payload["metadata"]["adtv_backfill"]["source"] == "vnindex_ohlcv.volume (vnstock VCI)"


def test_backfill_all_dry_run_writes_nothing(synthetic_workspace):
    from scripts.backfill_adtv import backfill_all

    tmp_path, exports_dir, hist_path, ohlcv, quarters = synthetic_workspace
    before = (hist_path.read_bytes(), (exports_dir / "score_2025_Q1.json").read_bytes())

    backfill_all(ohlcv, dry_run=True, history_path=hist_path,
                 exports_dir=exports_dir, adtv_cache_path=tmp_path / "cache.json")

    assert hist_path.read_bytes() == before[0]
    assert (exports_dir / "score_2025_Q1.json").read_bytes() == before[1]
    assert not (tmp_path / "cache.json").exists()


def test_backfill_all_fails_loudly_without_volume(synthetic_workspace, capsys):
    from scripts.backfill_adtv import backfill_all

    tmp_path, exports_dir, hist_path, ohlcv, quarters = synthetic_workspace
    bad = ohlcv.copy()
    bad["volume"] = 0.0   # volume toàn 0 — như nguồn không có khối lượng index
    with pytest.raises(SystemExit):
        backfill_all(bad, dry_run=False, history_path=hist_path,
                     exports_dir=exports_dir, adtv_cache_path=tmp_path / "c.json")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Wiring — run_quarterly.py truyền adtv_change_pct
# ═══════════════════════════════════════════════════════════════════════════════

def test_run_quarterly_compiles_and_wires_adtv():
    """run_quarterly.py biên dịch + lời gọi compute_quarterly_score có adtv_change_pct."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(PROJECT_ROOT / "run_quarterly.py"),
         str(PROJECT_ROOT / "scripts" / "backfill_adtv.py"),
         str(PROJECT_ROOT / "src" / "features" / "market_structure_features.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    src = (PROJECT_ROOT / "run_quarterly.py").read_text(encoding="utf-8")
    assert "compute_adtv_change_pct(df_latest_full, quarter)" in src
    assert "adtv_change_pct=adtv_change_pct" in src
