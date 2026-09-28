"""
export_excel_detailed.py — Xuất Workbook Excel SIÊU CHI TIẾT toàn bộ dữ liệu mô hình.

Khác với `generate_excel_report.py` (workbook phân tích factor-impact tóm tắt),
script này xuất MỌI dữ liệu ở dạng phẳng, từng dòng một, để tra cứu / audit:

  - Điểm tổng hợp & calibrated 24 quý (2021-Q1 → 2026-Q4)
  - Điểm 6 trụ cột: raw + weighted
  - Chi tiết từng factor từng quý (text gốc + score parse được)
  - Input dữ liệu thật: trái phiếu VN (Nelson-Siegel), M2 (ADB/GSO), FX z, P/E-P/B-EYG z
  - Audit dòng tiền khối ngoại (VNDirect 2018→nay): z cũ vs z mới
  - ADTV point-in-time + 2 cửa sổ quý
  - MLR regression từng quý (beta, p-value, significance)
  - Granger causality từng quý
  - ML walk-forward validation + fold metrics từng fold
  - Feature importance từng quý
  - Rationale (giải thích) 6 trụ cột từng quý
  - Giá VN-Index theo quý + QoQ/YoY
  - Nguồn ngoài: vốn hóa HOSE công bố, M2 ADB/GSO
  - Sổ đăng ký N/A (NA register): mục nào đã fill bằng nguồn nào, mục nào còn N/A cố ý

Chạy:  python scripts/export_excel_detailed.py
"""

import json
import logging
import os
import re
import sys
from datetime import datetime

import pandas as pd

sys.path.append(os.getcwd())

from src.utils.config import SCORING_WEIGHTS, SCORE_LABELS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = os.getcwd()
EXPORTS_DIR = os.path.join(ROOT, "output", "exports")
OUT_PATH = os.path.join(EXPORTS_DIR, "VN_Index_Detailed_Data_Export.xlsx")

PILLARS = [
    "macro_monetary",
    "global_intermarket",
    "valuation_leverage",
    "quant_model",
    "ml_forecast",
    "market_structure",
]
PILLAR_VN = {
    "macro_monetary": "Vĩ mô - Tiền tệ",
    "global_intermarket": "Toàn cầu - Liên thị trường",
    "valuation_leverage": "Định giá - Đòn bẩy",
    "quant_model": "Mô hình Quant",
    "ml_forecast": "Dự báo ML",
    "market_structure": "Cấu trúc thị trường",
}
NA_STATUS_NOTE = (
    "Sau 3 đợt backfill 09/2026 (ADTV; trái phiếu + M2 + P/E-P/B-EYG z; dòng tiền "
    "khối ngoại 2018→nay), toàn bộ factor dữ liệu thị trường 24/24 quý đều có số "
    "THẬT. N/A còn lại DUY NHẤT: pe_zscore / pb_zscore / eyg_zscore 4 quý "
    "2021-Q1→Q4 — series P/E-P_B ex-Vingroup chỉ bắt đầu ~2020-12, cần 252 phiên "
    "cho z-score → z đầu tiên 2021-12-20, muộn hơn as-of mọi quyết định 2021 → "
    "cố ý giữ default trung lập 50, không nội suy, không suy đoán."
)

# Sổ đăng ký N/A — mỗi dòng truy vết được về README.md + audit JSON trong repo
NA_REGISTER = [
    # (mục, trạng thái, quý từng N/A, cách fill, nguồn)
    ("ADTV change (market_structure.adtv)", "ĐÃ FILL 24/24", "toàn bộ 24 quý (đợt 1)",
     "ADTV(Q-1)/ADTV(Q-2)-1 point-in-time từ cột volume OHLCV VN-Index; điểm = clip(50+100×%Δ, 0, 100)",
     "vnindex_ohlcv.volume (vnstock, nguồn VCI) — audit data/scores/vnindex_quarterly_adtv.json"),
    ("Trái phiếu VN1Y / ΔVN1Y / VN10Y / spread (macro_monetary)", "ĐÃ FILL 24/24", "7 quý 2021-Q1→2022-Q3",
     "Đường cong fitted Nelson-Siegel bản full-history 2012-08-06→nay (3.397 ngày), as-of point-in-time; pre-check 68/68 khớp",
     "VN_Bond_Yield_pipeline — fitted_curve_ns_full.json"),
    ("M2 YoY (macro_monetary)", "ĐÃ FILL 24/24", "quý 2026 (dùng số 2025 gần nhất đã công bố)",
     "merge_asof backward — quyết định quý Q nhận giá trị năm gần nhất ĐÃ CÔNG BỐ (2021-Q*←2020 +14.53%...)",
     "ADB KIDB FM2_PTX_PS.VIE (nguồn SBV) 2000-2024 + GSO Q4/2025 (+14.98% đến 22/12/2025) — data/external/m2_credit_adb_gso.csv"),
    ("EYG z-score (valuation_leverage)", "ĐÃ FILL 24/24", "âm thầm default 50 ở cả 24/24 quý",
     "EYG = 1/PE − VN10Y truyền đúng qua df_macro; z min_periods 252 phiên",
     "bộ PE_PB_HOSE_stocks + đường cong trái phiếu NS"),
    ("pe_zscore / pb_zscore 2022+", "ĐÃ FILL 20/24", "6 quý 2022-Q1→2023-Q2",
     "hạ min_periods z-score từ 630 → 252 phiên; giá trị Z các ngày đủ 2.5 năm GIỮ NGUYÊN (pre-check 28/28 khớp)",
     "bộ PE_PB_HOSE_stocks (series ex-Vingroup bắt đầu ~2020-12)"),
    ("nff / etf flows z (global_intermarket + market_structure)", "ĐÃ FILL 24/24", "5 quý 2021-Q1→2022-Q1",
     "bỏ giới hạn fetch 'từ 2021' (tự đặt, API có dữ liệu từ 2018-08-30) → chuỗi flows từ 2018-Q4; splice vốn hóa HOSE công bố trước 2021-04-15 thay total_mc rác ~11 nghìn tỷ",
     "VNDirect api-finfo /v4/foreigns (STOCK_HOSE − ETF_HOSE) + data/external/hose_market_cap_published.csv — audit data/scores/vnindex_quarterly_flows.json"),
    ("pe_zscore / pb_zscore / eyg_zscore 2021-Q1→Q4", "N/A CỐ Ý — giới hạn dữ liệu thật", "4 quý 2021",
     "default trung lập 50 (renormalize các factor còn lại) — KHÔNG nội suy, KHÔNG suy đoán",
     "series P/E ex-Vingroup bắt đầu ~2020-12 (thiếu số cổ phiếu lưu thông trước đó); z đầu tiên 2021-12-20 > as-of mới nhất của 2021 (2021-09-30)"),
    ("Trường thống kê: mlr.Significance / granger.significance (sao ***)", "KHÔNG PHẢI N/A DỮ LIỆU", "—",
     "ô trống = factor KHÔNG có ý nghĩa thống kê (p≥0.10) — đây là nhãn suy diễn, không phải thiếu dữ liệu",
     "src/models/regression/mlr_model.py summary_table()"),
    ("percentile_p15/p85, calibration_z/hist_mean/hist_std 2021", "KHÔNG PHẢI N/A DỮ LIỆU", "4 quý 2021",
     "tầng calibrated dùng expanding window — 2021 chưa đủ lịch sử để calibration (thiết kế)",
     "src/scoring/quarterly_scorer.py"),
]

SCORE_RE = re.compile(r"→\s*score\s+([\d.]+)")


def _quarters_from(v):
    """Chuẩn hoá block 'quarters' của audit JSON về dict key=quarter."""
    if isinstance(v, dict):
        return v
    return {row["quarter"]: row for row in v}


def load_sources():
    """Đọc toàn bộ nguồn đã commit — KHÔNG đụng cache gitignored."""
    src = {}
    src["scores"] = {}
    for q in pd.period_range("2021Q1", "2026Q4", freq="Q"):
        key = f"{q.year}_Q{q.quarter}"
        path = os.path.join(EXPORTS_DIR, f"score_{key}.json")
        src["scores"][key] = json.load(open(path, encoding="utf-8"))
    src["market_data"] = _quarters_from(
        json.load(open("data/scores/vnindex_quarterly_market_data.json", encoding="utf-8"))["quarters"])
    src["flows"] = _quarters_from(
        json.load(open("data/scores/vnindex_quarterly_flows.json", encoding="utf-8"))["quarters"])
    src["adtv"] = _quarters_from(
        json.load(open("data/scores/vnindex_quarterly_adtv.json", encoding="utf-8"))["quarters"])
    src["close"] = json.load(open("data/scores/vnindex_quarterly_close.json", encoding="utf-8"))
    src["hose_mc"] = pd.read_csv("data/external/hose_market_cap_published.csv")
    src["m2_ext"] = pd.read_csv("data/external/m2_credit_adb_gso.csv")
    src["history"] = pd.read_parquet("data/scores/quarterly_scores_history.parquet")
    return src


def parse_score(text):
    """'Z = -2.43 (NET SELL) → score 14' -> 14.0 ; không có -> None."""
    if not isinstance(text, str):
        return None
    m = SCORE_RE.search(text)
    return float(m.group(1)) if m else None


def build_sheets(src):
    """Trả về dict {tên sheet: (DataFrame, kiểu định dạng gợi ý)}."""
    qkeys = sorted(src["scores"].keys())
    sheets = {}

    # ── 01_Summary ────────────────────────────────────────────────────────────
    rows = []
    prev_close = None
    for k in qkeys:
        qs = src["scores"][k]["quarterly_score"]
        close = src["close"].get(k.replace("_", "-"))
        qoq = (close / prev_close - 1) if (close and prev_close) else None
        prev_close = close or prev_close
        rows.append({
            "Quarter": k.replace("_", "-"),
            "As-of (dữ liệu)": qs.get("data_as_of"),
            "Total Score (RAW)": qs["total_score"],
            "Label (RAW)": qs["label"],
            "Calibrated Score": qs.get("calibrated_score"),
            "Label (CAL)": qs.get("calibrated_label"),
            "Phân bổ (CAL)": qs.get("calibrated_allocation"),
            "Trụ cột lệch nhất": qs.get("most_divergent_pillar"),
            "Dispersion": qs.get("dispersion_level"),
            "Pillar Std": qs.get("pillar_std"),
            "Pillar Range": qs.get("pillar_range"),
            "Percentile": qs.get("percentile_label"),
            "ADTV change QoQ": qs.get("adtv_change_pct"),
            "VN-Index Close": close,
            "QoQ Return": qoq,
        })
    sheets["01_Summary"] = pd.DataFrame(rows)

    # ── 02_Pillars_Raw ────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        gs = src["scores"][k]["quarterly_score"]["group_scores"]
        row = {"Quarter": k.replace("_", "-")}
        for p in PILLARS:
            row[f"{PILLAR_VN[p]} (raw)"] = gs[p]["raw_score"]
        row["Total (RAW)"] = src["scores"][k]["quarterly_score"]["total_score"]
        row["Calibrated"] = src["scores"][k]["quarterly_score"].get("calibrated_score")
        rows.append(row)
    sheets["02_Pillars_Raw"] = pd.DataFrame(rows)

    # ── 03_Pillars_Weighted ───────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        gs = src["scores"][k]["quarterly_score"]["group_scores"]
        row = {"Quarter": k.replace("_", "-")}
        total_w = 0.0
        for p in PILLARS:
            row[f"{PILLAR_VN[p]} (×{SCORING_WEIGHTS[p]:.0%})"] = gs[p]["weighted_score"]
            total_w += gs[p]["weighted_score"]
        row["Tổng weighted"] = round(total_w, 2)
        rows.append(row)
    sheets["03_Pillars_Weighted"] = pd.DataFrame(rows)

    # ── 04_Factor_Details ─────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        det = src["scores"][k]["quarterly_score"]["group_details"]
        for p in PILLARS:
            for factor, text in det.get(p, {}).items():
                rows.append({
                    "Quarter": k.replace("_", "-"),
                    "Trụ cột": PILLAR_VN[p],
                    "Factor": factor,
                    "Chi tiết (text gốc)": text,
                    "Score parse được": parse_score(text),
                })
    sheets["04_Factor_Details"] = pd.DataFrame(rows)

    # ── 05_Market_Inputs ──────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        md = src["market_data"][k.replace("_", "-")]
        b = md.get("bonds") or {}
        m2 = md.get("m2") or {}
        pz = md.get("pepb_z") or {}
        rows.append({
            "Quarter": k.replace("_", "-"),
            "As-of": md.get("as_of"),
            "Bond date": b.get("bond_date"),
            "VN1Y yield (%)": b.get("vn1y_yield"),
            "ΔVN1Y (pp)": b.get("delta_vn1y_yield"),
            "VN10Y yield (%)": b.get("vn10y_yield"),
            "Spread 10Y-1Y (pp)": b.get("vn_yield_spread"),
            "M2 năm": m2.get("year"),
            "M2 YoY (%)": m2.get("m2_yoy_pct"),
            "FX z-score": md.get("fx_zscore"),
            "P/E z": pz.get("pe"),
            "P/B z": pz.get("pb"),
            "EYG z": pz.get("eyg"),
            "Composite (0-100)": pz.get("composite"),
        })
    sheets["05_Market_Inputs"] = pd.DataFrame(rows)

    # ── 06_Flows_Audit ────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        f = src["flows"][k.replace("_", "-")]
        s = f.get("scores") or {}
        rows.append({
            "Quarter": k.replace("_", "-"),
            "As-of": f.get("as_of"),
            "Flows row date": f.get("flows_row_date"),
            "NFF z (mới)": f.get("nff_z"),
            "NFF z (cũ)": f.get("nff_z_old"),
            "NFF YTD (% MC)": f.get("nff_ytd_pct"),
            "ETF z (mới)": f.get("etf_z"),
            "ETF z (cũ)": f.get("etf_z_old"),
            "ETF YTD (% MC)": f.get("etf_ytd_pct"),
            "Global raw (mới)": s.get("global_raw"),
            "Global raw (cũ)": s.get("global_raw_old"),
            "Mkt structure raw (mới)": s.get("market_structure_raw"),
            "Mkt structure raw (cũ)": s.get("market_structure_raw_old"),
        })
    sheets["06_Flows_Audit"] = pd.DataFrame(rows)

    # ── 07_ADTV ───────────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        a = src["adtv"][k.replace("_", "-")]
        w = a.get("windows") or {}
        wins = sorted(w.keys())
        q1 = w.get(wins[-1], {}) if len(wins) > 0 else {}
        q2 = w.get(wins[-2], {}) if len(wins) > 1 else {}
        rows.append({
            "Quarter": k.replace("_", "-"),
            "ADTV change QoQ": a.get("adtv_change_pct"),
            "Cửa sổ Q-1": wins[-1] if len(wins) > 0 else None,
            "ADTV Q-1 (cp/phiên)": q1.get("adtv"),
            "Số phiên Q-1": q1.get("n_sessions"),
            "Cửa sổ Q-2": wins[-2] if len(wins) > 1 else None,
            "ADTV Q-2 (cp/phiên)": q2.get("adtv"),
            "Số phiên Q-2": q2.get("n_sessions"),
        })
    sheets["07_ADTV"] = pd.DataFrame(rows)

    # ── 08_MLR_Regression ─────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        for r in src["scores"][k].get("mlr_regression", []):
            rows.append({
                "Quarter": k.replace("_", "-"),
                "Variable": r.get("Variable"),
                "Beta (β)": r.get("Beta (β)"),
                "P-value": r.get("P-value"),
                "Sign expected": r.get("Sign Expected"),
                "Sign actual": r.get("Sign Actual"),
                "Sign OK": r.get("Sign OK"),
                "Significance": r.get("Significance") or "ns",
            })
    sheets["08_MLR_Regression"] = pd.DataFrame(rows)

    # ── 09_Granger ────────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        for r in src["scores"][k].get("granger_causality", []):
            rows.append({
                "Quarter": k.replace("_", "-"),
                "Causing variable": r.get("causing_variable"),
                "Test statistic": r.get("test_statistic"),
                "P-value": r.get("p_value"),
                "Granger causes VNI?": "YES" if r.get("granger_causes_vni") else "no",
                "Significance": r.get("significance") or "ns",
            })
    sheets["09_Granger"] = pd.DataFrame(rows)

    # ── 10_ML_WalkForward ─────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        ml = src["scores"][k].get("ml_walk_forward_validation", {})
        rows.append({
            "Quarter": k.replace("_", "-"),
            "Model": ml.get("model_type"),
            "Số folds": ml.get("n_folds"),
            "Số features": ml.get("n_features"),
            "Mean accuracy": ml.get("mean_accuracy"),
            "Std accuracy": ml.get("std_accuracy"),
            "Mean F1": ml.get("mean_f1"),
            "Pred class mới nhất": ml.get("latest_pred_class"),
            "Prediction": ml.get("latest_prediction"),
            "Confidence": ml.get("latest_confidence"),
        })
    sheets["10_ML_WalkForward"] = pd.DataFrame(rows)

    # ── 11_ML_Folds ───────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        for f in src["scores"][k].get("ml_walk_forward_validation", {}).get("fold_metrics", []):
            rows.append({"Quarter": k.replace("_", "-"), **f})
    sheets["11_ML_Folds"] = pd.DataFrame(rows)

    # ── 12_Feature_Importance ─────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        for f in src["scores"][k].get("feature_importance", []):
            rows.append({
                "Quarter": k.replace("_", "-"),
                "Rank": f.get("rank"),
                "Feature": f.get("feature"),
                "Importance": f.get("importance"),
            })
    sheets["12_Feature_Importance"] = pd.DataFrame(rows)

    # ── 13_Rationale ──────────────────────────────────────────────────────────
    rows = []
    for k in qkeys:
        rat = src["scores"][k]["quarterly_score"].get("group_rationale", {})
        row = {"Quarter": k.replace("_", "-")}
        for p in PILLARS:
            row[PILLAR_VN[p]] = rat.get(p)
        rows.append(row)
    sheets["13_Rationale"] = pd.DataFrame(rows)

    # ── 14_Index_Prices ───────────────────────────────────────────────────────
    rows = []
    prev = None
    closes = [(k.replace("_", "-"), src["close"].get(k.replace("_", "-"))) for k in qkeys]
    for i, (q, c) in enumerate(closes):
        # 2026-Q4 (quý live) chưa có close — QoQ/YoY để trống, không suy đoán
        qoq = (c / prev - 1) if (c is not None and prev is not None) else None
        yoy = (c / closes[i - 4][1] - 1) if (i >= 4 and c is not None and closes[i - 4][1] is not None) else None
        rows.append({"Quarter": q, "VN-Index Close": c, "QoQ Return": qoq, "YoY Return": yoy})
        prev = c if c is not None else prev
    sheets["14_Index_Prices"] = pd.DataFrame(rows)

    # ── 15_HOSE_MCap_Published ────────────────────────────────────────────────
    df = src["hose_mc"].rename(columns={
        "date": "Ngày", "mc_b_vnd": "Vốn hóa HOSE (tỷ VND)", "source": "Nguồn công bố"})
    df = df.sort_values("Ngày").reset_index(drop=True)
    sheets["15_HOSE_MCap_Published"] = df

    # ── 16_M2_ADB_GSO ─────────────────────────────────────────────────────────
    df = src["m2_ext"].rename(columns={
        "date": "Năm (cuối kỳ)", "m2_yoy_pct": "M2 YoY (%)",
        "credit_growth_yoy_pct": "Tín dụng YoY (%)", "m2_b_vnd": "M2 (tỷ VND)"})
    sheets["16_M2_ADB_GSO"] = df

    # ── 17_NA_Register ────────────────────────────────────────────────────────
    sheets["17_NA_Register"] = pd.DataFrame(
        NA_REGISTER, columns=["Mục", "Trạng thái", "Quý từng N/A", "Cách fill", "Nguồn"])

    # ── 18_Labels_Method ──────────────────────────────────────────────────────
    rows = []
    for (lo, hi), (label, emoji, desc, alloc) in sorted(SCORE_LABELS.items(), reverse=True):
        rows.append({
            "Band điểm": f"{lo}–{hi}", "Label": label, "Emoji": emoji,
            "Ý nghĩa": desc, "Phân bổ gợi ý": alloc,
        })
    sheets["18_Labels_Method"] = pd.DataFrame(rows)

    # ── 19_ML_Features ────────────────────────────────────────────────────────
    feats = src["scores"][qkeys[-1]].get("ml_walk_forward_validation", {}).get("features_used", [])
    sheets["19_ML_Features"] = pd.DataFrame({"#": range(1, len(feats) + 1), "Feature": feats})

    return sheets


# ═════════════════════════════ GHI XLSX ══════════════════════════════════════

PCT_COLS = {"ADTV change QoQ", "QoQ Return", "YoY Return", "Mean accuracy", "Std accuracy",
            "Mean F1", "Confidence", "Importance"}
Z_COLS = {"FX z-score", "P/E z", "P/B z", "EYG z", "NFF z (mới)", "NFF z (cũ)", "ETF z (mới)",
          "ETF z (cũ)"}
BIGINT_COLS = {"ADTV Q-1 (cp/phiên)", "ADTV Q-2 (cp/phiên)"}
LABEL_COLOR = {"SELL": "#C00000", "REDUCE": "#ED7D31", "HOLD": "#BF9000",
               "ACCUMULATE": "#2E75B6", "BUY": "#375623", "no": "#808080", "YES": "#375623"}


def _write_readme(wb, src):
    ws = wb.add_worksheet("00_README")
    F = {
        "title": wb.add_format({"bold": True, "font_size": 18, "font_color": "#1F3864"}),
        "sub": wb.add_format({"font_size": 11, "italic": True, "font_color": "#404040"}),
        "h": wb.add_format({"bold": True, "font_size": 13, "font_color": "#1F3864",
                            "bottom": 1, "border_color": "#1F3864"}),
        "txt": wb.add_format({"text_wrap": True, "valign": "top"}),
        "b": wb.add_format({"bold": True, "valign": "top"}),
        "cell_b": wb.add_format({"border": 1, "text_wrap": True, "valign": "top"}),
        "cell": wb.add_format({"border": 1, "valign": "top"}),
    }
    last = src["scores"][sorted(src["scores"])[-1]]
    meta = last["metadata"]
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 95)
    ws.hide_gridlines(2)

    ws.write("A1", "VN-INDEX QUARTERLY SCORING — DỮ LIỆU SIÊU CHI TIẾT (EXCEL EXPORT)", F["title"])
    ws.write("A2", f"Xuất lúc {datetime.now().strftime('%Y-%m-%d %H:%M')} — "
                   f"model v{meta.get('model_version')} — {meta.get('analysis_type')}", F["sub"])
    r = 4
    ws.write(r, 0, "TRẠNG THÁI N/A (câu hỏi thường gặp)", F["h"]); r += 1
    ws.write(r, 0, NA_STATUS_NOTE, F["txt"])
    ws.set_row(r, 60); r += 2

    ws.write(r, 0, "NGUỒN / PROVENANCE CÁC ĐỢT BACKFILL 09/2026", F["h"]); r += 1
    for k, v in meta.items():
        if isinstance(v, dict):
            ws.write(r, 0, k, F["b"])
            ws.write(r, 1, json.dumps(v, ensure_ascii=False), F["txt"]); r += 1
    r += 1

    ws.write(r, 0, "DANH MỤC SHEET", F["h"]); r += 1
    idx = [
        ("01_Summary", "Điểm tổng hợp 24 quý: RAW + calibrated, label, phân bổ, ADTV, close, QoQ"),
        ("02_Pillars_Raw", "Điểm RAW 6 trụ cột từng quý (0-100)"),
        ("03_Pillars_Weighted", "Điểm có trọng số từng trụ cột (trọng số 25/20/20/15/10/10%)"),
        ("04_Factor_Details", "MỖI factor của MỖI quý: text chi tiết gốc + score parse được"),
        ("05_Market_Inputs", "Input dữ liệu thật: trái phiếu NS, M2 ADB/GSO, FX z, P/E-P/B-EYG z"),
        ("06_Flows_Audit", "Dòng tiền khối ngoại VNDirect 2018→nay: z mới vs z cũ, YTD % MC, điểm re-score"),
        ("07_ADTV", "ADTV point-in-time + 2 cửa sổ quý (giá trị + số phiên)"),
        ("08_MLR_Regression", "Hồi quy MLR từng quý: beta, p-value, sign, significance"),
        ("09_Granger", "Granger causality từng quý: statistic, p, kết luận"),
        ("10_ML_WalkForward", "Walk-forward validation XGBoost từng quý: accuracy/F1/prediction"),
        ("11_ML_Folds", "Kết quả TỪNG FOLD của walk-forward"),
        ("12_Feature_Importance", "Feature importance từng quý (rank + trọng số)"),
        ("13_Rationale", "Giải thích (rationale) 6 trụ cột từng quý — text gốc"),
        ("14_Index_Prices", "VN-Index close theo quý + QoQ + YoY"),
        ("15_HOSE_MCap_Published", "Vốn hóa HOSE công bố 2018-2020 (dùng splice MC) + nguồn từng mốc"),
        ("16_M2_ADB_GSO", "M2 + tín dụng ADB/GSO 2015-2025 (fallback committed)"),
        ("17_NA_Register", "Sổ đăng ký N/A: mục nào fill bằng gì, nguồn nào, mục nào cố ý giữ N/A"),
        ("18_Labels_Method", "Band điểm → label → phân bổ (single source of truth)"),
        ("19_ML_Features", f"Danh sách {len(last.get('ml_walk_forward_validation', {}).get('features_used', []))} features của mô hình ML"),
    ]
    for name, desc in idx:
        ws.write(r, 0, name, F["cell"])
        ws.write(r, 1, desc, F["cell_b"]); r += 1
    r += 1
    ws.write(r, 0, "NGUYÊN TẮC DỮ LIỆU", F["h"]); r += 1
    ws.write(r, 0, "", F["b"])
    ws.write(r, 1, "Không bịa số — không suy đoán — không nội suy N/A: thiếu dữ liệu thật → default "
                   "trung lập 50 và ghi rõ. Mọi số truy vết được về nguồn công bố (audit JSON trong "
                   "data/scores/, CSV nguồn trong data/external/).", F["txt"])
    ws.set_row(r, 45)


def _write_table(wb, name, df):
    ws = wb.add_worksheet(name)
    header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#1F3864",
                            "border": 1, "text_wrap": True, "valign": "vcenter",
                            "align": "center"})
    pct = wb.add_format({"num_format": "0.0%"})
    z = wb.add_format({"num_format": "0.00"})
    num2 = wb.add_format({"num_format": "0.00"})
    num4 = wb.add_format({"num_format": "0.0000"})
    big = wb.add_format({"num_format": "#,##0"})
    int0 = wb.add_format({"num_format": "0"})
    txt_wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    dates = wb.add_format({"num_format": "yyyy-mm-dd", "align": "left"})

    cols = list(df.columns)
    # Header
    for j, c in enumerate(cols):
        ws.write(0, j, c, header)
    ws.set_row(0, 30)

    # Widths
    for j, c in enumerate(cols):
        if c in ("Chi tiết (text gốc)",) or c in ("Cách fill", "Nguồn", "Ý nghĩa"):
            ws.set_column(j, j, 60)
        elif c.startswith("Pillar VN") or c in ("Phân bổ (CAL)",):
            ws.set_column(j, j, 45)
        elif any(t in c for t in ("Mô tả", "rationale")):
            ws.set_column(j, j, 50)
        elif c == "Quarter":
            ws.set_column(j, j, 11)
        else:
            ws.set_column(j, j, max(11, min(22, len(c) + 3)))

    # Data
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        for j, c in enumerate(cols):
            v = row[c]
            if pd.isna(v):
                ws.write(i, j, "")
            elif c in PCT_COLS:
                ws.write_number(i, j, float(v), pct)
            elif c in Z_COLS:
                ws.write_number(i, j, float(v), z)
            elif c in BIGINT_COLS:
                ws.write_number(i, j, float(v), big)
            elif c == "Importance":
                ws.write_number(i, j, float(v), num4)
            elif isinstance(v, float):
                ws.write_number(i, j, v, num2 if abs(v) < 1000 else big)
            elif isinstance(v, (int,)) and not isinstance(v, bool):
                ws.write_number(i, j, v, big if abs(v) >= 10000 else int0)
            elif isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                ws.write(i, j, v, dates)
            else:
                ws.write(i, j, v, txt_wrap if isinstance(v, str) and len(v) > 40 else None)

    n = len(df)
    ws.freeze_panes(1, 1)
    if n:
        ws.autofilter(0, 0, n, len(cols) - 1)

    # Conditional formatting theo tên cột
    for j, c in enumerate(cols):
        col = chr(65 + j) if j < 26 else None
        if col is None:
            continue
        rng = f"{col}2:{col}{n + 1}"
        if "Label" in c or c in ("Granger causes VNI?",):
            for val, color in LABEL_COLOR.items():
                ws.conditional_format(rng, {
                    "type": "cell", "criteria": "==", "value": f'"{val}"',
                    "format": wb.add_format({"font_color": color, "bold": True})})
        elif isinstance(df[c].dropna(), pd.Series) and pd.api.types.is_numeric_dtype(df[c]):
            ws.conditional_format(rng, {
                "type": "3_color_scale",
                "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B",
                "min_type": "num", "mid_type": "num", "max_type": "num",
                "min_value": 0, "mid_value": 50, "max_value": 100})
    return ws


def write_workbook(sheets, src, path=OUT_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = pd.ExcelWriter(path, engine="xlsxwriter")
    xw = wb.book
    _write_readme(xw, src)
    for name, df in sheets.items():
        if name == "13_Rationale":
            ws = _write_table(xw, name, df)
            # text dài: nới rộng cột trụ cột + cao dòng
            for j in range(1, len(df.columns)):
                ws.set_column(j, j, 48)
            for i in range(len(df)):
                ws.set_row(i + 1, 70)
        else:
            _write_table(xw, name, df)
    wb.close()
    return path


def main():
    src = load_sources()
    sheets = build_sheets(src)
    for name, df in sheets.items():
        log.info(f"  sheet {name:<26} {df.shape[0]:>4} dòng × {df.shape[1]} cột")
    path = write_workbook(sheets, src)
    size_kb = os.path.getsize(path) / 1024
    log.info(f"Workbook written -> {path} ({size_kb:.0f} KB, {len(sheets) + 1} sheets)")
    return path


if __name__ == "__main__":
    main()
