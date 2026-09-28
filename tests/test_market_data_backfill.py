"""
test_market_data_backfill.py — Tests cho backfill dữ liệu thị trường 09/2026
=============================================================================
Phạm vi:
  1. Z-score min_periods (config 252): mở khoá NaN sớm, giá trị ≥2.5y KHÔNG đổi.
  2. M2 point-in-time: merge_asof backward trong build_macro_features —
     giá trị năm gần nhất ĐÃ CÔNG BỐ, kể cả khi ngày công bố rơi cuối tuần.
  3. fetch_m2_credit_auto: manual override > ADB live > fallback committed.
  4. fetch_vietnam_bonds: URL full-history ưu tiên, fallback bản cắt, lỗi → empty.
  5. Scorer với giá trị thật từ backfill (m2/vn1y).
  6. backfill_all: end-to-end trên workspace tổng hợp (tmp_path) — parquet +
     JSON export + audit; pre-check dữ liệu lệch → SystemExit (không ghi sai).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import ZSCORE_MIN_PERIODS_DAYS, ZSCORE_WINDOW_YEARS
from src.features.valuation_features import compute_zscore_rolling
from src.features.macro_features import build_macro_features
from src.scoring.quarterly_scorer import score_macro_monetary
import src.data.fetcher as fetcher_mod
from src.data.fetcher import fetch_m2_credit_auto, fetch_vietnam_bonds


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Z-score min_periods
# ═══════════════════════════════════════════════════════════════════════════════

def test_zscore_min_periods_config():
    assert ZSCORE_MIN_PERIODS_DAYS == 252
    assert ZSCORE_MIN_PERIODS_DAYS < ZSCORE_WINDOW_YEARS * 252 // 2  # nhỏ hơn mức cũ 630


def test_zscore_first_valid_at_252():
    """NaN cho 251 phiên đầu, có giá trị từ phiên thứ 252."""
    s = pd.Series(np.random.default_rng(42).normal(10, 1, 800))
    z = compute_zscore_rolling(s)
    assert z.iloc[:251].isna().all()
    assert z.iloc[251:].notna().all()


def test_zscore_values_unchanged_beyond_old_min_periods():
    """Với ≥630 phiên dữ liệu, Z mới PHẢI bằng Z theo công thức cũ (min=630)."""
    rng = np.random.default_rng(7)
    s = pd.Series(rng.normal(20, 3, 1000))
    window = ZSCORE_WINDOW_YEARS * 252
    z_new = compute_zscore_rolling(s)
    roll = s.rolling(window, min_periods=630)
    z_old = (s - roll.mean()) / roll.std()
    both = pd.concat([z_new, z_old], axis=1).dropna()
    assert len(both) > 0
    assert np.allclose(both.iloc[:, 0], both.iloc[:, 1])


# ═══════════════════════════════════════════════════════════════════════════════
# 2. M2 point-in-time (merge_asof backward)
# ═══════════════════════════════════════════════════════════════════════════════

def _m2_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-29"]),
        "m2_yoy_pct": [14.53, 10.66, 6.15, 12.46],
        "credit_growth_yoy_pct": [np.nan, np.nan, np.nan, np.nan],
        "m2_b_vnd": [np.nan] * 4,
    })


def test_m2_asof_backward_mapping():
    """Quyết định Q nhận M2 của năm gần nhất ĐÃ CÔNG BỐ (≤ as-of)."""
    vni_dates = pd.DataFrame({"date": pd.bdate_range("2021-01-04", "2024-03-29")})
    out = build_macro_features(vni_dates, pd.DataFrame(), pd.DataFrame(), _m2_frame())
    out = out.set_index("date")

    # 2021 các quý (as-of 2020-12-31/2021-03-31/2021-06-30/2021-09-30) → 2020 value
    for d in ["2021-01-04", "2021-03-31", "2021-06-30", "2021-09-30", "2021-12-30"]:
        assert out.loc[pd.Timestamp(d), "m2_yoy_pct"] == pytest.approx(14.53), d
    # 2022 → 2021 value; 2023 → 2022 value (tăng trưởng thấp 2022)
    assert out.loc[pd.Timestamp("2022-03-31"), "m2_yoy_pct"] == pytest.approx(10.66)
    assert out.loc[pd.Timestamp("2023-06-30"), "m2_yoy_pct"] == pytest.approx(6.15)
    # 2024 → 2023 value
    assert out.loc[pd.Timestamp("2024-01-02"), "m2_yoy_pct"] == pytest.approx(12.46)


def test_m2_non_trading_day_observation_is_kept():
    """Ngày công bố rơi CUỐI TUẦN không bị mất (bug cũ: exact-merge làm mất dòng)."""
    m2 = pd.DataFrame({
        "date": [pd.Timestamp("2021-01-03")],  # Chủ nhật — không phải ngày giao dịch
        "m2_yoy_pct": [9.0],
        "credit_growth_yoy_pct": [np.nan],
        "m2_b_vnd": [np.nan],
    })
    vni = pd.DataFrame({"date": pd.bdate_range("2021-01-04", "2021-01-15")})
    out = build_macro_features(vni, pd.DataFrame(), pd.DataFrame(), m2)
    assert out["m2_yoy_pct"].notna().all()
    assert out["m2_yoy_pct"].iloc[0] == pytest.approx(9.0)


def test_m2_no_lookahead():
    """Trước khi có bất kỳ quan sát nào → NaN (không kéo tương lai về trước)."""
    m2 = pd.DataFrame({
        "date": [pd.Timestamp("2021-06-30")],
        "m2_yoy_pct": [9.0],
        "credit_growth_yoy_pct": [np.nan],
        "m2_b_vnd": [np.nan],
    })
    vni = pd.DataFrame({"date": pd.bdate_range("2021-01-04", "2021-12-31")})
    out = build_macro_features(vni, pd.DataFrame(), pd.DataFrame(), m2).set_index("date")
    assert pd.isna(out.loc[pd.Timestamp("2021-06-29"), "m2_yoy_pct"])
    assert out.loc[pd.Timestamp("2021-06-30"), "m2_yoy_pct"] == pytest.approx(9.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. fetch_m2_credit_auto — chuỗi ưu tiên manual > ADB > fallback
# ═══════════════════════════════════════════════════════════════════════════════

def test_m2_manual_override_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_mod, "RAW_DIR", tmp_path)
    manual = tmp_path / "m2_credit_monthly.csv"
    manual.write_text("date,m2_yoy_pct,credit_growth_yoy_pct,m2_b_vnd\n2020-12-31,99.9,,\n")
    df = fetch_m2_credit_auto()
    assert len(df) == 1 and df["m2_yoy_pct"].iloc[0] == pytest.approx(99.9)


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_m2_adb_live_parse(tmp_path, monkeypatch):
    """ADB SDMX payload giả lập → parse đúng năm/giá trị, cache xuống manual path."""
    monkeypatch.setattr(fetcher_mod, "RAW_DIR", tmp_path)
    payload = {
        "data": {
            "datasets": [{"series": {"0": {"observations": {
                "0": [14.53], "1": [10.66], "2": [6.15]}}}}],
            "structures": [{"dimensions": {"observation": [
                {"values": [{"value": "2020"}, {"value": "2021"}, {"value": "2022"}]}
            ]}}],
        }
    }
    import requests as _r
    monkeypatch.setattr(_r, "get", lambda *a, **kw: _FakeResp(payload))
    df = fetch_m2_credit_auto()
    assert list(df["m2_yoy_pct"]) == [14.53, 10.66, 6.15]
    assert list(df["date"].dt.year) == [2020, 2021, 2022]
    # Cache đã ghi để lần sau offline
    assert (tmp_path / "m2_credit_monthly.csv").exists()


def test_m2_fallback_committed(tmp_path, monkeypatch):
    """ADB lỗi & không có manual → fallback committed trong repo."""
    monkeypatch.setattr(fetcher_mod, "RAW_DIR", tmp_path)  # không có manual
    fallback = tmp_path / "fallback.csv"
    fallback.write_text("date,m2_yoy_pct,credit_growth_yoy_pct,m2_b_vnd\n2024-12-31,11.97,15.08,\n")
    monkeypatch.setattr(fetcher_mod, "M2_FALLBACK_CSV", fallback)
    import requests as _r
    def _boom(*a, **kw):
        raise ConnectionError("no network in sandbox")
    monkeypatch.setattr(_r, "get", _boom)
    df = fetch_m2_credit_auto()
    assert len(df) == 1 and df["m2_yoy_pct"].iloc[0] == pytest.approx(11.97)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. fetch_vietnam_bonds — URL full-history ưu tiên
# ═══════════════════════════════════════════════════════════════════════════════

_BOND_RECORDS = [
    {"date": "2020-12-31", "tenor_yr": 1.0, "yield_pct": 0.43, "method": "NS"},
    {"date": "2020-12-31", "tenor_yr": 2.0, "yield_pct": 0.64, "method": "NS"},
    {"date": "2020-12-31", "tenor_yr": 10.0, "yield_pct": 2.02, "method": "NS"},
    {"date": "2026-09-25", "tenor_yr": 1.0, "yield_pct": 3.86, "method": "NS"},
    {"date": "2026-09-25", "tenor_yr": 2.0, "yield_pct": 3.95, "method": "NS"},
    {"date": "2026-09-25", "tenor_yr": 10.0, "yield_pct": 4.48, "method": "NS"},
]


def test_bonds_prefers_full_history_url(monkeypatch):
    calls = []
    import requests as _r
    def fake_get(url, *a, **kw):
        calls.append(url)
        return _FakeResp(_BOND_RECORDS if "fitted_curve_ns_full.json" in url else [])
    monkeypatch.setattr(_r, "get", fake_get)
    df = fetch_vietnam_bonds()
    assert any("fitted_curve_ns_full.json" in u for u in calls), "phải thử bản full trước"
    assert len(df) == 2
    row = df[df["date"] == "2026-09-25"].iloc[0]
    assert row["vn1y_yield"] == pytest.approx(3.86)
    assert row["vn10y_yield"] == pytest.approx(4.48)


def test_bonds_fallback_to_trimmed(monkeypatch):
    import requests as _r
    def fake_get(url, *a, **kw):
        if "fitted_curve_ns_full.json" in url:
            raise ConnectionError("full down")
        return _FakeResp(_BOND_RECORDS)
    monkeypatch.setattr(_r, "get", fake_get)
    df = fetch_vietnam_bonds()
    assert len(df) == 2 and df["vn2y_yield"].notna().all()


def test_bonds_all_sources_fail_returns_empty(monkeypatch):
    import requests as _r
    def _boom(*a, **kw):
        raise ConnectionError("offline")
    monkeypatch.setattr(_r, "get", _boom)
    df = fetch_vietnam_bonds()
    assert df.empty
    assert list(df.columns) == ["date", "vn1y_yield", "vn2y_yield", "vn10y_yield"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Scorer với giá trị thật của backfill
# ═══════════════════════════════════════════════════════════════════════════════

def test_macro_scorer_with_backfill_values():
    """Giá trị 2021-Q1 sau backfill: VN1Y 0.43%, M2 +14.53% → không còn default 50."""
    df_latest = pd.Series({
        "vn1y_yield": 0.4326, "delta_vn1y_yield": -0.0642,
        "usd_vnd_zscore": -2.68, "m2_yoy_pct": 14.53,
        "vn10y_yield": 2.0246, "vn_yield_spread": 2.0246 - 0.6374,
    }, dtype=float)
    out = score_macro_monetary(df_latest)
    assert "<MISSING>" not in str(out["details"])
    # m2_score = 80 - |14.53-12|*4 = 69.88
    assert out["sub_scores"]["m2_score"] == pytest.approx(69.88, abs=0.5)
    # vn1y cực thấp → clamp 100
    assert out["sub_scores"]["vn1y_rate_score"] == pytest.approx(100.0, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. backfill_all — end-to-end trên workspace tổng hợp
# ═══════════════════════════════════════════════════════════════════════════════

def _synthetic_workspace(tmp_path: Path):
    """2 quý: quý 1 macro MISSING bonds/m2; quý 2 có bonds cũ + pe z mới."""
    from src.utils.config import SCORING_WEIGHTS

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    hist_rows = []
    specs = [
        # quarter, as_of, old_macro_raw, old_val_raw, old_total, pe_z_old, pe_z_new
        ("2021-Q1", "2020-12-31", 60.0, 62.5, 50.0, None, None),
        ("2022-Q1", "2021-12-31", 60.0, 62.3, 50.0, None, 1.37),
    ]
    for q, as_of, macro_raw, val_raw, total, pe_old, pe_new in specs:
        gs = {
            "macro_monetary": {"raw_score": macro_raw,
                               "weighted_score": round(macro_raw * SCORING_WEIGHTS["macro_monetary"], 2)},
            "valuation_leverage": {"raw_score": val_raw,
                                   "weighted_score": round(val_raw * SCORING_WEIGHTS["valuation_leverage"], 2)},
        }
        det_macro = {
            "vn1y_yield": "0.49% → score 100" if q == "2022-Q1" else "<MISSING> N/A → default 50",
            "ir_trend": "Δ VN1Y = 0.0100 (↑ Hike) → score 49" if q == "2022-Q1" else "<MISSING> N/A → default 50",
            "usd_vnd": "Z-score = -1.30 → score 70",
            "m2_yoy_growth": "<MISSING> N/A → default 50",
            "vn_bonds": "VN10Y 2.11% | Spread 1.40% → score 85" if q == "2022-Q1" else "<MISSING> N/A → default 50",
        }
        det_val = {
            "margin_risk": "Risk = 40/100 (WARNING) → score 60",
        }
        if pe_old is not None:
            det_val["pe_zscore"] = f"Z = {pe_old:.2f} (FAIR VALUE) → score 47"
        else:
            det_val["pe_zscore"] = "<MISSING> N/A → default 50"
        payload = {
            "quarterly_score": {
                "quarter": q, "data_as_of": as_of,
                "date_computed": "2026-09-01 00:00",
                "total_score": total, "label": "HOLD", "emoji": "🟡",
                "label_description": "d", "label_allocation": "a",
                "most_divergent_pillar": "macro_monetary",
                "percentile_label": "HOLD", "percentile_p15": None, "percentile_p85": None,
                "pillar_std": 5.0, "pillar_range": 10.0, "dispersion_level": "MEDIUM",
                "group_scores": gs,
                "group_details": {"macro_monetary": det_macro, "valuation_leverage": det_val},
                "group_rationale": {"macro_monetary": "r", "valuation_leverage": "r"},
            }
        }
        with open(exports_dir / f"score_{q.replace('-', '_')}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        hist_rows.append({
            "quarter": q, "date_computed": "2026-09-01", "total_score": total,
            "label": "HOLD", "score_macro_monetary": gs["macro_monetary"]["weighted_score"],
            "score_global_intermarket": 10.0, "score_valuation_leverage": gs["valuation_leverage"]["weighted_score"],
            "score_quant_model": 10.0, "score_ml_forecast": 10.0, "score_market_structure": 10.0,
            "percentile_label": "HOLD", "pillar_std": 5.0, "pillar_range": 10.0,
            "dispersion_level": "MEDIUM", "calibrated_score": total, "calibrated_label": "HOLD",
        })
    hist_path = tmp_path / "hist.parquet"
    pd.DataFrame(hist_rows).to_parquet(hist_path, index=False)

    # Bonds synthetic (as-of Q1 = 2020-12-31 → 0.43; as-of Q2 = 2021-12-31 → 0.49)
    bonds = pd.DataFrame({
        "date": pd.to_datetime(["2020-12-30", "2020-12-31", "2021-12-30", "2021-12-31"]),
        "vn1y_yield": [0.40, 0.43, 0.48, 0.49],
        "vn2y_yield": [0.63, 0.64, 0.70, 0.71],
        "vn10y_yield": [2.00, 2.02, 2.10, 2.11],
    })
    m2 = pd.DataFrame({
        "date": pd.to_datetime(["2020-12-31", "2021-12-31"]),
        "m2_yoy_pct": [14.53, 10.66],
        "credit_growth_yoy_pct": [np.nan, np.nan],
        "m2_b_vnd": [np.nan, np.nan],
    })
    # PEPB: pe z có từ 2021-12-20; quý 1 (as-of 2020-12-31) không có
    pepb = pd.DataFrame({
        "date": pd.to_datetime(["2020-12-31", "2021-12-20", "2021-12-31"]),
        "headline_pe": [15.0, 16.0, 16.5], "median_pe": [12.0, 13.0, 13.5],
        "ex_vingroup_pe": [np.nan, 14.0, 14.5],
        "headline_pb": [1.8, 1.9, 2.0], "median_pb": [1.5, 1.6, 1.7],
        "ex_vingroup_pb": [np.nan, 1.5, 1.6],
        "pe_zscore": [np.nan, 1.30, 1.37],
        "pb_zscore": [np.nan, 1.60, 1.72],
        "eyg_zscore": [np.nan, -0.80, -0.89],
        "valuation_composite_score": [np.nan, 60.0, 55.0],
    })
    return hist_path, exports_dir, bonds, m2, pepb


def test_backfill_all_end_to_end(tmp_path):
    from scripts.backfill_market_data import backfill_all

    hist_path, exports_dir, bonds, m2, pepb = _synthetic_workspace(tmp_path)
    audit_path = tmp_path / "audit.json"

    out = backfill_all(
        bonds, m2, pepb, dry_run=False,
        history_path=hist_path, exports_dir=exports_dir, audit_path=audit_path,
    )
    # Parquet ghi lại, 2 quý
    assert len(out) == 2

    rec1 = json.load(open(exports_dir / "score_2021_Q1.json"))["quarterly_score"]
    rec2 = json.load(open(exports_dir / "score_2022_Q1.json"))["quarterly_score"]

    # Q1: macro có bonds thật (0.49% — as-of 2021-12-31? KHÔNG: as-of Q1 = 2020-12-31 → 0.43)
    d1 = rec1["group_details"]["macro_monetary"]
    assert "0.43%" in d1["vn1y_yield"] and "<MISSING>" not in d1["vn1y_yield"]
    assert "<MISSING>" not in d1["m2_yoy_growth"] and "14.5%" in d1["m2_yoy_growth"]
    assert "<MISSING>" not in d1["vn_bonds"]
    # Valuation Q1: pe z vẫn N/A (dữ liệu thật chưa có) → giữ nguyên raw cũ
    assert rec1["group_scores"]["valuation_leverage"]["raw_score"] == pytest.approx(62.5)

    # Q2: pe z mới 1.37 → valuation re-score, eyg_zscore detail xuất hiện
    d2v = rec2["group_details"]["valuation_leverage"]
    assert "Z = 1.37" in d2v["pe_zscore"]
    assert "EYG Z-score" in d2v["eyg_zscore"]
    # Macro Q2: bonds khớp detail cũ 3.50% (pre-check đã chứng minh) + m2 2021
    d2m = rec2["group_details"]["macro_monetary"]
    assert "10.7%" in d2m["m2_yoy_growth"]

    # Tổng thay đổi đúng theo trọng số
    from src.utils.config import SCORING_WEIGHTS
    w_m = SCORING_WEIGHTS["macro_monetary"]
    w_v = SCORING_WEIGHTS["valuation_leverage"]
    expect2 = round(50.0 - 60.0 * w_m + rec2["group_scores"]["macro_monetary"]["raw_score"] * w_m
                    - 62.3 * w_v + rec2["group_scores"]["valuation_leverage"]["raw_score"] * w_v, 2)
    assert rec2["total_score"] == pytest.approx(expect2, abs=0.05)

    # Audit cache có input thật
    audit = json.load(open(audit_path))
    assert audit["quarters"]["2021-Q1"]["m2"]["m2_yoy_pct"] == pytest.approx(14.53)
    assert audit["quarters"]["2021-Q1"]["bonds"]["vn1y_yield"] == pytest.approx(0.43, abs=0.01)
    assert audit["quarters"]["2022-Q1"]["pepb_z"]["pe"] == pytest.approx(1.37)


def test_backfill_precheck_stops_on_mismatch(tmp_path):
    """Detail cũ không khớp dữ liệu nguồn → SystemExit (không ghi đè sai)."""
    from scripts.backfill_market_data import backfill_all

    hist_path, exports_dir, bonds, m2, pepb = _synthetic_workspace(tmp_path)
    # Tamper: detail vn1y cũ của 2022-Q1 sai (2.00% thay vì 3.50%)
    p = exports_dir / "score_2022_Q1.json"
    payload = json.load(open(p))
    payload["quarterly_score"]["group_details"]["macro_monetary"]["vn1y_yield"] = "2.00% → score 90"  # thật ra 0.49
    json.dump(payload, open(p, "w"), ensure_ascii=False)

    with pytest.raises(SystemExit, match="không khớp|KHÔNG khớp"):
        backfill_all(bonds, m2, pepb, dry_run=False,
                     history_path=hist_path, exports_dir=exports_dir,
                     audit_path=tmp_path / "audit.json")


def test_backfill_dry_run_writes_nothing(tmp_path):
    from scripts.backfill_market_data import backfill_all

    hist_path, exports_dir, bonds, m2, pepb = _synthetic_workspace(tmp_path)
    before = (exports_dir / "score_2021_Q1.json").read_text()
    hist_before = pd.read_parquet(hist_path)["total_score"].tolist()

    backfill_all(bonds, m2, pepb, dry_run=True,
                 history_path=hist_path, exports_dir=exports_dir,
                 audit_path=tmp_path / "audit.json")

    assert (exports_dir / "score_2021_Q1.json").read_text() == before
    assert pd.read_parquet(hist_path)["total_score"].tolist() == hist_before
    assert not (tmp_path / "audit.json").exists()
