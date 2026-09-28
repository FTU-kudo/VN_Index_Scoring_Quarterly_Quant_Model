"""
test_excel_detailed_export.py — Test script export Excel siêu chi tiết.

Kiểm tra (chỉ đọc các nguồn ĐÃ COMMIT, không đụng cache gitignored):
  1. Đủ 24 quý 2021-Q1 → 2026-Q4 trong mọi sheet chính
  2. Sheet Summary khớp parquet lịch sử (total + label + calibrated)
  3. Flows audit: quý 2021-Q1 có z mới, z cũ None; mọi quý 2022+ đều có z
  4. N/A register ghi nhận đúng giới hạn pe_zscore 2021 (4 quý) — không bịa
  5. Điểm factor parse được từ text chi tiết khớp điểm trụ cột đã ghi
  6. Workbook ghi ra file .xlsx hợp lệ (đọc lại được bằng xlsxreader của xlsxwriter)
"""

import os
import sys

import pandas as pd
import pytest

sys.path.append(os.getcwd())
from scripts.export_excel_detailed import (  # noqa: E402
    OUT_PATH, build_sheets, load_sources, parse_score, write_workbook,
)

QUARTERS = [f"{y}-Q{q}" for y in range(2021, 2027) for q in range(1, 5)]


@pytest.fixture(scope="module")
def src():
    return load_sources()


@pytest.fixture(scope="module")
def sheets(src):
    return build_sheets(src)


# ── 1. Đủ 24 quý ─────────────────────────────────────────────────────────────
def test_all_sheets_have_24_quarters(sheets):
    for name in ["01_Summary", "02_Pillars_Raw", "03_Pillars_Weighted",
                 "05_Market_Inputs", "06_Flows_Audit", "07_ADTV",
                 "10_ML_WalkForward", "13_Rationale", "14_Index_Prices"]:
        assert sorted(sheets[name]["Quarter"]) == QUARTERS, name


def test_long_sheets_cover_all_quarters(sheets):
    for name in ["08_MLR_Regression", "09_Granger", "11_ML_Folds",
                 "12_Feature_Importance", "04_Factor_Details"]:
        got = set(sheets[name]["Quarter"])
        assert set(QUARTERS) <= got, f"{name} thiếu các quý: {set(QUARTERS) - got}"


# ── 2. Summary khớp parquet lịch sử ──────────────────────────────────────────
def test_summary_matches_history_parquet(sheets, src):
    hist = src["history"].set_index("quarter")
    df = sheets["01_Summary"].set_index("Quarter")
    for q in QUARTERS:
        assert df.loc[q, "Total Score (RAW)"] == pytest.approx(hist.loc[q, "total_score"]), q
        assert df.loc[q, "Label (RAW)"] == hist.loc[q, "label"], q
        assert df.loc[q, "Calibrated Score"] == pytest.approx(hist.loc[q, "calibrated_score"]), q
        assert df.loc[q, "Label (CAL)"] == hist.loc[q, "calibrated_label"], q


def test_pillar_raw_scores_match_history(sheets, src):
    """Parquet lưu điểm CÓ TRỌNG SỐ → so với sheet 03_Pillars_Weighted."""
    hist = src["history"].set_index("quarter")
    df = sheets["03_Pillars_Weighted"].set_index("Quarter")
    weights = [0.25, 0.20, 0.20, 0.15, 0.10, 0.10]
    hist_cols = [
        "score_macro_monetary", "score_global_intermarket", "score_valuation_leverage",
        "score_quant_model", "score_ml_forecast", "score_market_structure",
    ]
    wcols = [c for c in df.columns if c.startswith(("Vĩ mô", "Toàn cầu", "Định giá",
                                                    "Mô hình", "Dự báo", "Cấu trúc"))]
    assert len(wcols) == 6
    for q in QUARTERS:
        for wcol, hcol, w in zip(wcols, hist_cols, weights):
            assert df.loc[q, wcol] == pytest.approx(hist.loc[q, hcol]), (q, wcol)


def test_pillar_weighted_equals_raw_times_weight(sheets):
    raw = sheets["02_Pillars_Raw"].set_index("Quarter")
    wgt = sheets["03_Pillars_Weighted"].set_index("Quarter")
    weights = [0.25, 0.20, 0.20, 0.15, 0.10, 0.10]
    rcols = [c for c in raw.columns if c.endswith("(raw)")]
    wcols = [c for c in wgt.columns if not c.startswith(("Quarter", "Tổng"))]
    for q in QUARTERS:
        for rc, wc, w in zip(rcols, wcols, weights):
            assert wgt.loc[q, wc] == pytest.approx(raw.loc[q, rc] * w, abs=0.02), (q, rc)


# ── 3. Flows audit: z mới có, z cũ None ở 2021-Q1; 2022+ đủ z ────────────────
def test_flows_2021_q1_new_z_old_none(sheets):
    df = sheets["06_Flows_Audit"].set_index("Quarter")
    assert df.loc["2021-Q1", "NFF z (mới)"] == pytest.approx(-2.4315, abs=1e-3)
    assert df.loc["2021-Q1", "ETF z (mới)"] == pytest.approx(1.8116, abs=1e-3)
    assert pd.isna(df.loc["2021-Q1", "NFF z (cũ)"])


def test_flows_all_quarters_have_real_z(sheets):
    df = sheets["06_Flows_Audit"].set_index("Quarter")
    for q in QUARTERS:
        assert pd.notna(df.loc[q, "NFF z (mới)"]), f"{q} thiếu NFF z"
        assert pd.notna(df.loc[q, "ETF z (mới)"]), f"{q} thiếu ETF z"


# ── 4. N/A register trung thực ───────────────────────────────────────────────
def test_na_register_documents_remaining_limit(sheets):
    df = sheets["17_NA_Register"]
    pe_row = df[df["Mục"].str.contains("2021-Q1→Q4")]
    assert len(pe_row) == 1
    assert "N/A CỐ Ý" in pe_row.iloc[0]["Trạng thái"]
    assert "default trung lập 50" in pe_row.iloc[0]["Cách fill"]
    # các mục đã fill phải nêu nguồn
    filled = df[df["Trạng thái"].str.startswith("ĐÃ FILL")]
    assert len(filled) >= 6
    assert all(s.strip() for s in filled["Nguồn"])


def test_market_inputs_2021_pepb_null_2022_real(sheets):
    """Giới hạn dữ liệu thật: z P/E-P/B-EYG 2021 = trống (không bịa), 2022+ = số thật."""
    df = sheets["05_Market_Inputs"].set_index("Quarter")
    for q in ["2021-Q1", "2021-Q2", "2021-Q3", "2021-Q4"]:
        assert pd.isna(df.loc[q, "P/E z"]) and pd.isna(df.loc[q, "P/B z"]), q
    for q in ["2022-Q1", "2024-Q1", "2026-Q4"]:
        assert pd.notna(df.loc[q, "P/E z"]), q


# ── 5. Parse score từ text chi tiết ──────────────────────────────────────────
def test_parse_score_regex():
    assert parse_score("Z = -2.43 (NET SELL) → score 14") == 14
    assert parse_score("0.92% → score 82") == 82
    assert parse_score("Risk = 15/100 (SAFE) → score 85") == 85
    assert parse_score("-0.44% of Market Cap (YTD in Q)") is None


def test_factor_details_parse_and_complete(sheets):
    df = sheets["04_Factor_Details"]
    # mọi quý đều có chi tiết cho 6 trụ cột
    assert df.groupby("Quarter")["Trụ cột"].nunique().eq(6).all()
    # phần lớn factor có score parse được
    n_scored = df["Score parse được"].notna().sum()
    assert n_scored >= 0.5 * len(df)


# ── 6. Workbook ghi ra hợp lệ ────────────────────────────────────────────────
def test_write_workbook_valid_xlsx(src, sheets, tmp_path):
    path = os.path.join(tmp_path, "test_export.xlsx")
    write_workbook(sheets, src, path=path)
    assert os.path.getsize(path) > 10_000  # có nội dung thật
    # xlsx là zip: đọc directory để xác nhận cấu trúc hợp lệ
    import zipfile
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "xl/workbook.xml" in names
        assert any(n.startswith("xl/worksheets/sheet") for n in names)
        # 20 sheet = README + 19 sheet dữ liệu
        assert sum(1 for n in names if n.startswith("xl/worksheets/sheet")) >= 20


def test_out_path_in_exports_dir():
    assert OUT_PATH.endswith("VN_Index_Detailed_Data_Export.xlsx")
    assert "output/exports" in OUT_PATH.replace(os.sep, "/")
