"""
test_flows_backfill.py — Tests cho backfill flows full-history (09/2026)
=========================================================================
Phạm vi:
  1. _splice_published_market_cap: MC công bố thay MC ticker rác; MC hợp lệ
     giữ nguyên; không ngoại suy ngoài các mốc.
  2. build_foreign_flow_features: quý đầu tiên (bắt đầu giữa quý) bị drop;
     z khả dụng từ quý thứ 5; pct dùng MC splice (không phải MC rác).
  3. fetch_foreign_flows: chặn dưới 2018-08-01 (API có dữ liệu từ 2018-08-30).
  4. backfill_all: end-to-end trên workspace tổng hợp (tmp_path) — pre-check
     q_ytd sai → SystemExit; 24/24 phải có z; dry-run không ghi.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import src.features.global_features as gf
from src.features.global_features import (
    MC_SANITY_MIN_B_VND,
    _splice_published_market_cap,
    build_foreign_flow_features,
)
import src.data.fetcher as fetcher_mod
from src.data.fetcher import fetch_foreign_flows


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

PUB_CSV = """date,mc_b_vnd,source
2018-12-31,2875721,test
2019-12-31,3280000,test
2020-12-31,4080000,test
"""


def _pub_csv(tmp_path):
    p = tmp_path / "hose_mc.csv"
    p.write_text(PUB_CSV, encoding="utf-8")
    return p


def _make_flows(start="2019-10-01", end="2021-06-30") -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "date": dates,
        "nff_ex_etf_vnd": rng.normal(-100, 400, len(dates)),  # tỷ VND
        "etf_flow_vnd": rng.normal(30, 100, len(dates)),
    })


def _make_pepb(flows: pd.DataFrame, valid_mc_from="2021-04-15") -> pd.DataFrame:
    """total_mc rác trước valid_mc_from (26 mã ~ 11k tỷ), thật sau đó."""
    dates = flows["date"]
    mc = pd.Series(np.where(dates >= pd.Timestamp(valid_mc_from), 4_784_377.0, 11_000.0),
                   index=dates)
    return pd.DataFrame({"date": dates, "total_mc": mc * 1e9})


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Splice MC công bố
# ═══════════════════════════════════════════════════════════════════════════════

def test_splice_replaces_garbage_mc(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    df_mc = pd.DataFrame({
        "date": pd.to_datetime(["2019-06-28", "2020-06-30", "2021-04-15", "2021-06-30"]),
        "total_mc_b": [11_000.0, 15_000.0, 4_784_377.0, 5_200_000.0],  # 2 dòng rác
    })
    out = _splice_published_market_cap(df_mc)
    # 2019-06-28: nội suy giữa 2018-12-31 (2.875.721) và 2019-12-31 (3.280.000)
    frac = (pd.Timestamp("2019-06-28") - pd.Timestamp("2018-12-31")).days / \
           (pd.Timestamp("2019-12-31") - pd.Timestamp("2018-12-31")).days
    expect = 2_875_721 + frac * (3_280_000 - 2_875_721)
    assert out.iloc[0] == pytest.approx(expect, rel=1e-6)
    # 2020-06-30: nội suy giữa 2019-12-31 (3.280.000) và 2020-12-31 (4.080.000)
    frac = (pd.Timestamp("2020-06-30") - pd.Timestamp("2019-12-31")).days / \
           (pd.Timestamp("2020-12-31") - pd.Timestamp("2019-12-31")).days
    expect = 3_280_000 + frac * (4_080_000 - 3_280_000)
    assert out.iloc[1] == pytest.approx(expect, rel=1e-6)
    # MC hợp lệ giữ nguyên
    assert out.iloc[2] == pytest.approx(4_784_377.0)
    assert out.iloc[3] == pytest.approx(5_200_000.0)


def test_splice_no_extrapolation_before_first_anchor(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    df_mc = pd.DataFrame({
        "date": pd.to_datetime(["2018-06-29", "2019-06-28"]),
        "total_mc_b": [np.nan, 11_000.0],
    })
    out = _splice_published_market_cap(df_mc)
    # Trước mốc đầu (2018-12-31) → NaN (không ngoại suy) → dòng này bị drop
    assert pd.isna(out.iloc[0])
    # Nội suy chính xác giữa 2018-12-31 (2.875.721) và 2019-12-31 (3.280.000)
    frac = (pd.Timestamp("2019-06-28") - pd.Timestamp("2018-12-31")).days / \
           (pd.Timestamp("2019-12-31") - pd.Timestamp("2018-12-31")).days
    assert out.iloc[1] == pytest.approx(2_875_721 + frac * (3_280_000 - 2_875_721), rel=1e-6)


def test_splice_all_valid_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    df_mc = pd.DataFrame({
        "date": pd.to_datetime(["2022-01-04", "2022-06-30"]),
        "total_mc_b": [5_000_000.0, 5_500_000.0],
    })
    out = _splice_published_market_cap(df_mc)
    assert list(out) == [5_000_000.0, 5_500_000.0]


def test_splice_missing_csv_returns_original(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", tmp_path / "khong_co.csv")
    df_mc = pd.DataFrame({
        "date": pd.to_datetime(["2019-06-28"]),
        "total_mc_b": [11_000.0],
    })
    out = _splice_published_market_cap(df_mc)
    assert out.iloc[0] == 11_000.0  # không đổi, không crash


# ═══════════════════════════════════════════════════════════════════════════════
# 2. build_foreign_flow_features — quý partial + z + pct dùng MC splice
# ═══════════════════════════════════════════════════════════════════════════════

def test_features_partial_first_quarter_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    flows = _make_flows(start="2018-08-30", end="2021-06-30")  # bắt đầu giữa quý 2018-Q3
    pepb = _make_pepb(flows)
    feat = build_foreign_flow_features(flows, pepb)
    # 2018-Q3 (chỉ 2 phiên) phải bị drop → quý đầu của chuỗi = 2018-Q4
    # → z đầu tiên ở quý thứ 5 (2019-Q3+1... kiểm qua giá trị): z phải có từ 2019-Q4
    z_dates = feat.loc[feat["nff_ex_etf_q_zscore_live"].notna(), "date"]
    assert len(z_dates) > 0
    assert z_dates.min() >= pd.Timestamp("2019-10-01")
    # Không có z trước 2019-Q4 (cần 4 quý trước đó: 2018Q4..2019Q3)
    assert feat.loc[feat["date"] < "2019-10-01", "nff_ex_etf_q_zscore_live"].isna().all()


def test_features_pct_uses_spliced_mc_not_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    flows = _make_flows(start="2020-01-01", end="2020-03-31")
    flows["nff_ex_etf_vnd"] = -100.0  # tỷ VND mỗi ngày, 62 phiên
    pepb = _make_pepb(flows, valid_mc_from="2099-01-01")  # toàn bộ rác (11k tỷ)
    feat = build_foreign_flow_features(flows, pepb)
    # Nếu dùng MC rác 11k tỷ: pct/ngày = -100/11000 = -0.9%; quý = -56%
    # Với MC splice (~3,3-4 triệu tỷ): pct/ngày ≈ -100/3.600.000 ≈ -0.003%
    q1_ytd = feat.iloc[-1]["nff_ex_etf_q_ytd"]
    assert abs(q1_ytd) < 0.01  # 1% — chắc chắn KHÔNG phải thang MC rác
    # Mẫu số: nội suy DAILY giữa 2019-12-31 (3,28M) → 2020-12-31 (4,08M)
    idx = pd.date_range("2019-12-31", "2020-12-31", freq="D")
    mc_daily = pd.Series(np.linspace(3_280_000, 4_080_000, len(idx)), index=idx)
    mc_on_flows = mc_daily.reindex(pd.DatetimeIndex(flows["date"])).values
    expect = float(np.sum(-100.0 / mc_on_flows))
    assert q1_ytd == pytest.approx(expect, rel=1e-9)


def test_features_z_available_for_2021_q1_decision(tmp_path, monkeypatch):
    """Chuỗi 2019-Q4 trở đi → 4 quý trước 2020-Q4 → z cho quyết định 2021-Q1."""
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    flows = _make_flows(start="2019-10-01", end="2021-03-31")
    pepb = _make_pepb(flows)
    feat = build_foreign_flow_features(flows, pepb)
    row = feat[feat["date"] <= pd.Timestamp("2020-12-31")].iloc[-1]
    assert pd.notna(row["nff_ex_etf_q_zscore_live"])
    assert pd.notna(row["etf_flow_q_zscore_live"])
    assert pd.notna(row["nff_ex_etf_q_ytd"])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Fetcher — chặn dưới 2018-08-01
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_fetcher_floor_2018(monkeypatch, tmp_path):
    """start sớm hơn 2018-08-01 bị kẹp lên 2018-08-01 (API có từ 2018-08-30)."""
    monkeypatch.setattr(fetcher_mod, "RAW_DIR", tmp_path)
    import requests as _r
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["q"] = params["q"]
        return _FakeResp({"data": [
            {"code": "STOCK_HOSE", "tradingDate": "2018-08-30", "netVal": -1e11},
            {"code": "ETF_HOSE", "tradingDate": "2018-08-30", "netVal": 2e10},
        ]})

    monkeypatch.setattr(_r, "get", fake_get)
    df = fetch_foreign_flows(start="2017-01-01", end="2018-09-30", use_cache=False)
    assert "tradingDate:gte:2018-08-01" in captured["q"]
    assert len(df) == 1
    assert df["nff_ex_etf_vnd"].iloc[0] == pytest.approx((-1e11 - 2e10) / 1e9)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. backfill_all — end-to-end trên workspace tổng hợp
# ═══════════════════════════════════════════════════════════════════════════════

def _synthetic_workspace(tmp_path: Path, flows_feat: pd.DataFrame):
    """2 quý: 2021-Q1 (flows N/A cũ) + 2021-Q2 (có flows cũ) — q_ytd lưu khớp."""
    from src.utils.config import SCORING_WEIGHTS

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    hist_rows = []

    def feat_at(as_of):
        sub = flows_feat[flows_feat["date"] <= pd.Timestamp(as_of)]
        return sub.iloc[-1]

    specs = [
        ("2021-Q1", "2020-12-31", 60.0, 62.5, 50.0, True),   # flows N/A cũ
        ("2021-Q2", "2021-03-31", 60.0, 62.3, 50.0, False),  # có flows cũ
    ]
    for q, as_of, glob_raw, ms_raw, total, na_flows in specs:
        row = feat_at(as_of)
        # Format đúng như scorer: f"{fraction:.2%}" (KHÔNG nhân 100 trước)
        nff_ytd_str = f"{float(row['nff_ex_etf_q_ytd']):.2%}"
        etf_ytd_str = f"{float(row['etf_flow_q_ytd']):.2%}"
        nff_z = float(row["nff_ex_etf_q_zscore_live"])
        etf_z = float(row["etf_flow_q_zscore_live"])

        gs = {
            "global_intermarket": {"raw_score": glob_raw,
                                   "weighted_score": round(glob_raw * SCORING_WEIGHTS["global_intermarket"], 2)},
            "market_structure": {"raw_score": ms_raw,
                                 "weighted_score": round(ms_raw * SCORING_WEIGHTS["market_structure"], 2)},
        }
        det_glob = {
            "dxy": "Z = -1.57 → score 81",
            "us10y": "0.92% → score 82",
            "nff_ex_etf": ("<MISSING> Not enough data for Z-score (2021) → default 50"
                           if na_flows else f"Z = {nff_z:.2f} (Neutral) → score 50"),
            "jpy_carry": "Z = -1.76 (High_Risk) → score 24",
            "oil_shock": "Oil Shock Score = 20.7 (Max Δ5d = 9.8%) → score 59",
        }
        if not na_flows:
            det_glob["nff_ex_etf_q_ytd"] = f"{nff_ytd_str} of Market Cap (YTD in Q)"
        det_ms = {
            "ftse_upgrade": "Status: unknown → score 50",
            "rebalancing": "3 months to rebalancing → bonus +6",
            "etf_flow": ("<MISSING> Not enough data for Z-score (2021) → excluded from pillar average"
                         if na_flows else f"Z = {etf_z:.2f} (Neutral) → score 50"),
        }
        if not na_flows:
            det_ms["etf_flow_q_ytd"] = f"{etf_ytd_str} of Market Cap (YTD in Q)"
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
                "group_details": {"global_intermarket": det_glob, "market_structure": det_ms},
                "group_rationale": {"global_intermarket": "r", "market_structure": "r"},
            }
        }
        with open(exports_dir / f"score_{q.replace('-', '_')}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        hist_rows.append({
            "quarter": q, "date_computed": "2026-09-01", "total_score": total,
            "label": "HOLD", "score_macro_monetary": 15.0,
            "score_global_intermarket": gs["global_intermarket"]["weighted_score"],
            "score_valuation_leverage": 12.0, "score_quant_model": 8.0,
            "score_ml_forecast": 5.0,
            "score_market_structure": gs["market_structure"]["weighted_score"],
            "percentile_label": "HOLD", "pillar_std": 5.0, "pillar_range": 10.0,
            "dispersion_level": "MEDIUM", "calibrated_score": total, "calibrated_label": "HOLD",
        })
    hist_path = tmp_path / "hist.parquet"
    pd.DataFrame(hist_rows).to_parquet(hist_path, index=False)
    return hist_path, exports_dir


@pytest.fixture()
def flows_feat(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    flows = _make_flows(start="2019-10-01", end="2021-06-30")
    pepb = _make_pepb(flows)
    return build_foreign_flow_features(flows, pepb)


def test_backfill_all_end_to_end(tmp_path, flows_feat):
    from scripts.backfill_flows import backfill_all

    hist_path, exports_dir = _synthetic_workspace(tmp_path, flows_feat)
    audit_path = tmp_path / "audit.json"
    out = backfill_all(flows_feat, dry_run=False,
                       history_path=hist_path, exports_dir=exports_dir,
                       audit_path=audit_path)
    assert len(out) == 2

    rec1 = json.load(open(exports_dir / "score_2021_Q1.json"))["quarterly_score"]
    rec2 = json.load(open(exports_dir / "score_2022_Q1.json".replace("2022", "2021")))["quarterly_score"]

    # Q1: flows từng N/A → giờ có z thật trong details
    d1 = rec1["group_details"]["global_intermarket"]
    assert "<MISSING>" not in d1["nff_ex_etf"]
    assert re.search(r"Z = -?\d+\.\d+", d1["nff_ex_etf"])
    assert "of Market Cap (YTD in Q)" in d1["nff_ex_etf_q_ytd"]
    m1 = rec1["group_details"]["market_structure"]
    assert "<MISSING>" not in m1["etf_flow"]

    # Q2: q_ytd giữ nguyên (pre-check đảm bảo) — z cũ được thay bằng z mới
    d2 = rec2["group_details"]["global_intermarket"]
    assert "of Market Cap (YTD in Q)" in d2["nff_ex_etf_q_ytd"]

    # Tổng thay đổi đúng theo trọng số
    from src.utils.config import SCORING_WEIGHTS
    w_g = SCORING_WEIGHTS["global_intermarket"]
    w_m = SCORING_WEIGHTS["market_structure"]
    for rec, old_glob, old_ms, old_total in [(rec1, 60.0, 62.5, 50.0), (rec2, 60.0, 62.3, 50.0)]:
        expect = round(old_total - old_glob * w_g + rec["group_scores"]["global_intermarket"]["raw_score"] * w_g
                       - old_ms * w_m + rec["group_scores"]["market_structure"]["raw_score"] * w_m, 2)
        assert rec["total_score"] == pytest.approx(expect, abs=0.05)

    # Audit
    audit = json.load(open(audit_path))
    assert audit["quarters"]["2021-Q1"]["nff_z"] is not None
    assert audit["quarters"]["2021-Q1"]["etf_z"] is not None


def test_backfill_precheck_q_ytd_mismatch_stops(tmp_path, flows_feat):
    from scripts.backfill_flows import backfill_all

    hist_path, exports_dir = _synthetic_workspace(tmp_path, flows_feat)
    # Tamper: q_ytd lưu sai ở 2021-Q2
    p = exports_dir / "score_2021_Q2.json"
    payload = json.load(open(p))
    payload["quarterly_score"]["group_details"]["global_intermarket"]["nff_ex_etf_q_ytd"] = \
        "99.99% of Market Cap (YTD in Q)"
    json.dump(payload, open(p, "w"), ensure_ascii=False)

    with pytest.raises(SystemExit, match="q_ytd|KHÔNG khớp"):
        backfill_all(flows_feat, dry_run=False,
                     history_path=hist_path, exports_dir=exports_dir,
                     audit_path=tmp_path / "audit.json")


def test_backfill_gate_requires_z_all_quarters(tmp_path, monkeypatch):
    """Flows features thiếu z (chuỗi ngắn) → SystemExit, không half-backfill."""
    from scripts.backfill_flows import backfill_all

    monkeypatch.setattr(gf, "HOSE_MC_PUBLISHED_CSV", _pub_csv(tmp_path))
    # Chuỗi chỉ từ 2020-10-01 → 2021-Q1 (as-of 2020-12-31) chưa đủ 4 quý trước
    flows = _make_flows(start="2020-10-01", end="2021-06-30")
    pepb = _make_pepb(flows)
    feat_short = build_foreign_flow_features(flows, pepb)

    hist_path, exports_dir = _synthetic_workspace(tmp_path, feat_short)
    with pytest.raises(SystemExit, match="GATE|KHÔNG có flows z"):
        backfill_all(feat_short, dry_run=False,
                     history_path=hist_path, exports_dir=exports_dir,
                     audit_path=tmp_path / "audit.json")


def test_backfill_dry_run_writes_nothing(tmp_path, flows_feat):
    from scripts.backfill_flows import backfill_all

    hist_path, exports_dir = _synthetic_workspace(tmp_path, flows_feat)
    before = (exports_dir / "score_2021_Q1.json").read_text()
    hist_before = pd.read_parquet(hist_path)["total_score"].tolist()

    backfill_all(flows_feat, dry_run=True,
                 history_path=hist_path, exports_dir=exports_dir,
                 audit_path=tmp_path / "audit.json")
    assert (exports_dir / "score_2021_Q1.json").read_text() == before
    assert pd.read_parquet(hist_path)["total_score"].tolist() == hist_before
    assert not (tmp_path / "audit.json").exists()
