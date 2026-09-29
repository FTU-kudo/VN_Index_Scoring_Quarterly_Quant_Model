"""
excel_builder.py — Xuất Workbook Excel Phân tích Định lượng (Quant Factor Workbook)

Tạo 1 file Excel nhiều sheet theo chuẩn quant finance:
  00_Dashboard        — Executive summary + phân rã đóng góp 6 trụ cột (có chart)
  01_Score_History    — Lịch sử 24 quý: điểm, pillar, VN-Index, fwd return
  02_Factor_Impact    — MLR betas, p-value, sign check + độ ổn định beta theo quý
  03_Granger          — Kiểm định nhân quả Granger (biến nào dẫn dắt VN-Index)
  04_ML_Validation    — Walk-Forward Validation + Feature Importance
  05_Factor_Scores    — Chi tiết điểm từng chỉ số trong từng trụ cột (quý mới nhất)
  06_Signal_Efficacy  — Backtest tín hiệu: IC, hit-rate, mô phỏng chiến lược phân bổ
  07_Methodology      — Trọng số, thang nhãn, nguồn dữ liệu

Chạy:  python scripts/generate_excel_report.py
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import (
    EXPORTS_DIR,
    REPORTS_DIR,
    SCORE_LABEL_RANGES,
    SCORING_WEIGHTS,
    get_score_label,
)

logger = logging.getLogger(__name__)

PRICE_CACHE_PATH = Path("data/scores/vnindex_quarterly_close.json")
HISTORY_PATH = Path("data/scores/quarterly_scores_history.parquet")

PILLAR_NAMES = {
    "macro_monetary":     "Macro & Monetary",
    "global_intermarket": "Global & Intermarket",
    "valuation_leverage": "Valuation & Leverage",
    "quant_model":        "Quant Model (MLR/VAR)",
    "ml_forecast":        "ML Forecast",
    "market_structure":   "Market Structure",
}

# Điểm giữa của dải phân bổ cổ phiếu cho mô phỏng chiến lược
ALLOCATION_MID = {
    "BUY":        0.925,   # 85–100%
    "ACCUMULATE": 0.775,   # 70–85%
    "HOLD":       0.50,    # 40–60%
    "REDUCE":     0.30,    # 20–40%
    "SELL":       0.10,    # 0–20%
}

_SCORE_RE = re.compile(r"(?:→|->)\s*(?:score|quality|default)\s*([\d.]+)")


# ──────────────────────────────────────────────────────────────────────────────
# Data loading helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_exports() -> Dict[str, dict]:
    """Đọc toàn bộ exports/score_*.json, key = 'YYYY-QN' (asc)."""
    out: Dict[str, dict] = {}
    for p in sorted(EXPORTS_DIR.glob("score_*.json")):
        q = p.stem.replace("score_", "").replace("_", "-")
        try:
            with open(p, "r", encoding="utf-8") as f:
                out[q] = json.load(f)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[EXCEL] Cannot read {p}: {exc}")
    return out


def _load_price_cache() -> Dict[str, Optional[float]]:
    if PRICE_CACHE_PATH.exists():
        with open(PRICE_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _latest_full_export(exports: Dict[str, dict]) -> Tuple[str, dict]:
    """Quý mới nhất có đầy đủ kết quả mô hình (MLR không rỗng)."""
    for q in sorted(exports.keys(), reverse=True):
        if exports[q].get("mlr_regression"):
            return q, exports[q]
    q = sorted(exports.keys())[-1]
    return q, exports[q]


def _clean_detail_text(v: Any) -> Tuple[str, Optional[float], bool]:
    """Trả về (text sạch, điểm parse được, cờ missing) từ group_details."""
    text = str(v)
    missing = text.strip().startswith("<MISSING>")
    text = text.replace("<MISSING>", "").strip()
    m = _SCORE_RE.search(text)
    score = float(m.group(1)) if m else None
    if m:
        text = text[: m.start()].strip().rstrip("|").strip()
    text = re.sub(r"<br\s*/?>", " | ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, score, missing


def _spearman(x: pd.Series, y: pd.Series) -> float:
    return float(x.rank().corr(y.rank()))


# ──────────────────────────────────────────────────────────────────────────────
# Main builder
# ──────────────────────────────────────────────────────────────────────────────

def build_excel_report(out_path: Optional[Path] = None) -> Path:
    import xlsxwriter  # local import: chỉ cần khi xuất Excel

    exports = _load_exports()
    if not exports:
        raise FileNotFoundError(f"No score_*.json exports found in {EXPORTS_DIR}")

    history = pd.read_parquet(HISTORY_PATH) if HISTORY_PATH.exists() else pd.DataFrame()
    if not history.empty:
        history = history[history["quarter"] != "2099-Q1"].copy()
        history = history.sort_values("quarter").reset_index(drop=True)

    prices = _load_price_cache()
    latest_q, latest = _latest_full_export(exports)
    latest_score = latest.get("quarterly_score", {})

    if out_path is None:
        out_path = EXPORTS_DIR / "VN_Index_Quant_Factor_Analysis.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = xlsxwriter.Workbook(str(out_path), {"nan_inf_to_errors": True})

    # ── Formats ───────────────────────────────────────────────────────────
    F = {
        "title":    wb.add_format({"bold": True, "font_size": 16, "font_color": "#1e3a8a"}),
        "subtitle": wb.add_format({"font_size": 10, "font_color": "#64748b", "italic": True}),
        "h2":       wb.add_format({"bold": True, "font_size": 12, "font_color": "#1e3a8a",
                                   "bottom": 2, "border_color": "#3b82f6"}),
        "th":       wb.add_format({"bold": True, "font_color": "#ffffff", "bg_color": "#1e3a8a",
                                   "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True}),
        "td":       wb.add_format({"border": 1, "valign": "vcenter"}),
        "td_wrap":  wb.add_format({"border": 1, "valign": "vcenter", "text_wrap": True}),
        "td_c":     wb.add_format({"border": 1, "align": "center", "valign": "vcenter"}),
        "num2":     wb.add_format({"border": 1, "num_format": "0.00", "align": "right"}),
        "num4":     wb.add_format({"border": 1, "num_format": "0.0000", "align": "right"}),
        "num6":     wb.add_format({"border": 1, "num_format": "0.000000", "align": "right"}),
        "pct1":     wb.add_format({"border": 1, "num_format": "0.0%", "align": "right"}),
        "pct0":     wb.add_format({"border": 1, "num_format": "0%", "align": "right"}),
        "good":     wb.add_format({"border": 1, "align": "center", "bg_color": "#dcfce7", "font_color": "#166534", "bold": True}),
        "bad":      wb.add_format({"border": 1, "align": "center", "bg_color": "#fee2e2", "font_color": "#991b1b", "bold": True}),
        "warn":     wb.add_format({"border": 1, "align": "center", "bg_color": "#fef9c3", "font_color": "#854d0e", "bold": True}),
        "kpi_lbl":  wb.add_format({"bold": True, "font_color": "#475569", "border": 1, "bg_color": "#f1f5f9"}),
        "kpi_val":  wb.add_format({"bold": True, "font_size": 12, "border": 1, "align": "center"}),
        "big":      wb.add_format({"bold": True, "font_size": 28, "font_color": "#1e3a8a", "align": "center", "valign": "vcenter", "border": 1}),
        "note":     wb.add_format({"font_size": 9, "font_color": "#64748b", "italic": True, "text_wrap": True}),
    }

    def _sheet(name: str, tab_color: str):
        ws = wb.add_worksheet(name)
        ws.set_tab_color(tab_color)
        ws.hide_gridlines(2)
        return ws

    def _header(ws, row: int, col: int, headers: List[str], widths: Optional[List[int]] = None):
        for j, h in enumerate(headers):
            ws.write(row, col + j, h, F["th"])
            if widths:
                ws.set_column(col + j, col + j, widths[j])
        return row + 1

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 00 — DASHBOARD
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("00_Dashboard", "#1e3a8a")
    ws.set_column("A:A", 2)
    ws.set_column("B:B", 30)
    ws.set_column("C:H", 16)

    ws.write("B2", "VN-INDEX QUARTERLY QUANT FACTOR WORKBOOK", F["title"])
    ws.write("B3", f"Latest full-model quarter: {latest_q}  |  Generated at: {generated}  |  Source: output/exports/score_*.json", F["subtitle"])

    total = float(latest_score.get("total_score", 50))
    label = latest_score.get("label", "HOLD")
    emoji = latest_score.get("emoji", "🟡")
    alloc = latest_score.get("label_allocation") or get_score_label(total)[3]

    # ── Calibrated Action Signal (Tầng 2) ──────────────────────────────────
    cal_total = latest_score.get("calibrated_score")
    if cal_total is None:
        cal_total, cal_label, cal_emoji = total, label, emoji
        cal_alloc = alloc
        cal_applied = False
    else:
        cal_label = latest_score.get("calibrated_label", get_score_label(float(cal_total))[0])
        cal_emoji = latest_score.get("calibrated_emoji", "🟡")
        cal_alloc = latest_score.get("calibrated_allocation", get_score_label(float(cal_total))[3])
        cal_applied = bool(latest_score.get("calibration_applied"))

    # KPI block
    ws.merge_range("B5:C7", f"{total:.1f}", F["big"])
    kpis = [
        ("Raw Regime / Label",   f"{emoji} {label} (raw composite)"),
        ("CALIBRATED ACTION",    f"{cal_emoji} {cal_label} — {float(cal_total):.1f}"),
        ("Recommended Equity",   f"{cal_alloc} (calibrated)"),
        ("Percentile Signal",    str(latest_score.get("percentile_label", "N/A"))),
        ("Pillar Dispersion",    f'{latest_score.get("dispersion_level", "N/A")} (σ={latest_score.get("pillar_std", "N/A")})'),
        ("Data As-Of",           str(latest_score.get("data_as_of", "N/A"))),
        ("Point-in-Time",        "YES" if latest_score.get("point_in_time") else "NO"),
    ]
    r = 4
    for name, val in kpis:
        ws.write(r, 4, name, F["kpi_lbl"])
        ws.write(r, 5, val, F["kpi_val"])
        r += 1

    # Pillar contribution table
    ws.write("B12", "PILLAR CONTRIBUTION DECOMPOSITION", F["h2"])
    r = _header(ws, 12, 1,
                ["Pillar", "Weight", "Raw Score (0-100)", "Weighted Contribution", "% of Total Score", "Signal"],
                [30, 10, 18, 20, 16, 14])
    gs = latest_score.get("group_scores", {})
    pillar_rows_start = r
    for key, pname in PILLAR_NAMES.items():
        g = gs.get(key, {})
        raw = float(g.get("raw_score", np.nan))
        wtd = float(g.get("weighted_score", np.nan))
        w = SCORING_WEIGHTS.get(key, 0)
        ws.write(r, 1, pname, F["td"])
        ws.write_number(r, 2, w, F["pct0"])
        ws.write_number(r, 3, raw, F["num2"])
        ws.write_number(r, 4, wtd, F["num2"])
        ws.write_number(r, 5, wtd / total if total else 0, F["pct1"])
        sig = "Bullish" if raw >= 65 else ("Bearish" if raw < 45 else "Neutral")
        ws.write(r, 6, sig, F["good"] if sig == "Bullish" else (F["bad"] if sig == "Bearish" else F["warn"]))
        r += 1
    pillar_rows_end = r - 1
    ws.write(r, 1, "TOTAL COMPOSITE", F["kpi_lbl"])
    ws.write_number(r, 2, 1.0, F["pct0"])
    ws.write(r, 3, "", F["td"])
    ws.write_number(r, 4, total, F["num2"])
    ws.write_number(r, 5, 1.0, F["pct1"])
    ws.write(r, 6, label, F["kpi_val"])
    ws.conditional_format(pillar_rows_start, 3, pillar_rows_end, 3,
                          {"type": "3_color_scale", "min_color": "#ef4444",
                           "mid_color": "#fde047", "max_color": "#22c55e",
                           "min_type": "num", "min_value": 0,
                           "mid_type": "num", "mid_value": 50,
                           "max_type": "num", "max_value": 100})

    # Chart: pillar weighted contribution
    ch = wb.add_chart({"type": "column"})
    ch.add_series({
        "name": "Weighted Contribution",
        "categories": ["00_Dashboard", pillar_rows_start, 1, pillar_rows_end, 1],
        "values":     ["00_Dashboard", pillar_rows_start, 4, pillar_rows_end, 4],
        "fill": {"color": "#3b82f6"},
        "data_labels": {"value": True, "num_format": "0.0"},
    })
    ch.set_title({"name": f"Pillar Weighted Contribution — {latest_q}", "name_font": {"size": 11, "bold": True}})
    ch.set_legend({"none": True})
    ch.set_size({"width": 560, "height": 300})
    ws.insert_chart("H12", ch)

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 01 — SCORE HISTORY
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("01_Score_History", "#3b82f6")
    ws.set_column("A:A", 2)
    ws.write("B2", "COMPOSITE SCORE HISTORY vs VN-INDEX", F["title"])
    ws.write("B3", "Two-tier scores: Total Score = raw composite (reference) | Calibrated Score = relative regime/allocation signal vs PRIOR quarters only "
                   "(point-in-time, v2: σ-floor 5.0, z winsorised ±3, bounded ±25 vs raw — saturation near 5/95 by design, NOT a return forecast). "
                   "Pillar columns are weighted contributions (raw × weight). Fwd Return = VN-Index return of the NEXT quarter (signal evaluation).", F["subtitle"])

    headers = ["Quarter", "Total Score", "Label (Raw)", "Calibrated Score", "Calibrated Label",
               "Percentile Signal", "Dispersion"] + \
              [PILLAR_NAMES[k] for k in PILLAR_NAMES] + \
              ["VN-Index Close", "QoQ Return", "Fwd Return (t+1)"]
    widths = [10, 12, 13, 14, 15, 16, 12] + [19] * 6 + [14, 12, 15]
    r0 = _header(ws, 4, 1, headers, widths)

    hist_rows = []
    if not history.empty:
        qtrs = history["quarter"].tolist()
        closes = [prices.get(q) for q in qtrs]
        rets: List[Optional[float]] = [None]
        for i in range(1, len(closes)):
            a, b = closes[i - 1], closes[i]
            rets.append((b / a - 1) if (a and b) else None)
        fwd = rets[1:] + [None]

        has_cal = "calibrated_score" in history.columns
        r = r0
        for i, (_, row) in enumerate(history.iterrows()):
            cal_v = row.get("calibrated_score") if has_cal else None
            cal_l = str(row.get("calibrated_label") or row["label"]) if has_cal else str(row["label"])
            ws.write(r, 1, row["quarter"], F["td_c"])
            ws.write_number(r, 2, float(row["total_score"]), F["num2"])
            ws.write(r, 3, str(row["label"]), F["td_c"])
            if pd.notna(cal_v):
                ws.write_number(r, 4, float(cal_v), F["num2"])
            else:
                ws.write(r, 4, "N/A", F["td_c"])
            ws.write(r, 5, cal_l, F["td_c"])
            ws.write(r, 6, str(row.get("percentile_label") or "N/A"), F["td_c"])
            ws.write(r, 7, str(row.get("dispersion_level") or "N/A"), F["td_c"])
            for j, k in enumerate(PILLAR_NAMES):
                v = row.get(f"score_{k}")
                if pd.notna(v):
                    ws.write_number(r, 8 + j, float(v), F["num2"])
                else:
                    ws.write(r, 8 + j, "N/A", F["td_c"])
            if closes[i] is not None:
                ws.write_number(r, 14, float(closes[i]), F["num2"])
            else:
                ws.write(r, 14, "N/A", F["td_c"])
            for cc, val in ((15, rets[i]), (16, fwd[i])):
                if val is not None:
                    ws.write_number(r, cc, val, F["pct1"])
                else:
                    ws.write(r, cc, "N/A", F["td_c"])
            hist_rows.append({"quarter": row["quarter"], "score": float(row["total_score"]),
                              "label": str(row["label"]),
                              "cal_score": float(cal_v) if pd.notna(cal_v) else float(row["total_score"]),
                              "cal_label": cal_l,
                              "pct_label": str(row.get("percentile_label") or "N/A"),
                              "close": closes[i], "ret": rets[i], "fwd": fwd[i]})
            r += 1
        r_end = r - 1
        ws.freeze_panes(r0, 2)
        for col in (2, 4):
            ws.conditional_format(r0, col, r_end, col,
                                  {"type": "3_color_scale", "min_color": "#ef4444",
                                   "mid_color": "#fde047", "max_color": "#22c55e",
                                   "min_type": "num", "min_value": 0,
                                   "mid_type": "num", "mid_value": 50,
                                   "max_type": "num", "max_value": 100})
        ws.conditional_format(r0, 15, r_end, 16,
                              {"type": "3_color_scale", "min_color": "#ef4444",
                               "mid_color": "#ffffff", "max_color": "#22c55e",
                               "min_type": "num", "min_value": -0.2,
                               "mid_type": "num", "mid_value": 0,
                               "max_type": "num", "max_value": 0.2})

        # Dual-axis chart: calibrated score + raw score vs VN-Index
        ch = wb.add_chart({"type": "line"})
        ch.add_series({
            "name": "Calibrated Action Score",
            "categories": ["01_Score_History", r0, 1, r_end, 1],
            "values":     ["01_Score_History", r0, 4, r_end, 4],
            "line": {"color": "#8b5cf6", "width": 2.5},
        })
        ch.add_series({
            "name": "Raw Composite Score",
            "categories": ["01_Score_History", r0, 1, r_end, 1],
            "values":     ["01_Score_History", r0, 2, r_end, 2],
            "line": {"color": "#3b82f6", "width": 1.5, "dash_type": "dash"},
        })
        ch.add_series({
            "name": "VN-Index Close",
            "categories": ["01_Score_History", r0, 1, r_end, 1],
            "values":     ["01_Score_History", r0, 14, r_end, 14],
            "line": {"color": "#94a3b8", "width": 1.5, "dash_type": "dash"},
            "y2_axis": True,
        })
        ch.set_title({"name": "Calibrated Action (solid) + Raw Composite (dashed) vs VN-Index (RHS)", "name_font": {"size": 11, "bold": True}})
        ch.set_y_axis({"min": 0, "max": 100, "name": "Score (0-100)"})
        ch.set_y2_axis({"name": "VN-Index"})
        ch.set_size({"width": 900, "height": 320})
        ws.insert_chart(r_end + 3, 1, ch)

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 02 — FACTOR IMPACT (MLR)
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("02_Factor_Impact", "#8b5cf6")
    ws.set_column("A:A", 2)
    ws.write("B2", "FACTOR IMPACT — MULTIPLE LINEAR REGRESSION (Newey-West HAC)", F["title"])
    ws.write("B3", f"Dependent variable: forward VN-Index log-return. Quarter: {latest_q}. Significance: *** p<0.01, ** p<0.05, * p<0.10.", F["subtitle"])

    mlr = pd.DataFrame(latest.get("mlr_regression") or [])
    if not mlr.empty:
        r = _header(ws, 4, 1,
                    ["Factor", "Beta (β)", "P-value", "Significance", "Sign Expected", "Sign Actual",
                     "Sign OK", "|β| Rank", "Economic Reading"],
                    [22, 12, 10, 12, 13, 11, 9, 9, 58])
        mlr = mlr.copy()
        mlr["abs_beta"] = mlr["Beta (β)"].abs()
        mlr["rank"] = mlr["abs_beta"].rank(ascending=False).astype(int)
        mlr_start = r
        for _, row in mlr.iterrows():
            beta = float(row["Beta (β)"])
            pval = float(row["P-value"])
            sig = str(row.get("Significance", ""))
            ok = str(row.get("Sign OK", "")) == "✅"
            direction = "supportive of" if beta > 0 else "a headwind for"
            strength = ("statistically significant" if pval < 0.05 else
                        "weakly significant" if pval < 0.10 else "not significant")
            reading = f"A rise in {row['Variable']} is {direction} next-quarter VN-Index returns ({strength}, p={pval:.3f})."
            ws.write(r, 1, str(row["Variable"]), F["td"])
            ws.write_number(r, 2, beta, F["num6"])
            ws.write_number(r, 3, pval, F["num4"])
            ws.write(r, 4, sig or "—", F["td_c"])
            ws.write(r, 5, str(row["Sign Expected"]), F["td_c"])
            ws.write(r, 6, str(row["Sign Actual"]), F["td_c"])
            ws.write(r, 7, "PASS" if ok else "FAIL", F["good"] if ok else F["bad"])
            ws.write_number(r, 8, int(row["rank"]), F["td_c"])
            ws.write(r, 9, reading, F["td_wrap"])
            r += 1
        mlr_end = r - 1
        ws.conditional_format(mlr_start, 3, mlr_end, 3,
                              {"type": "cell", "criteria": "<", "value": 0.05,
                               "format": F["good"]})
        ws.conditional_format(mlr_start, 2, mlr_end, 2,
                              {"type": "data_bar", "bar_color": "#8b5cf6",
                               "bar_negative_color": "#ef4444", "bar_axis_position": "middle"})

        # Sign-check pass rate
        n_pass = int((mlr["Sign OK"] == "✅").sum())
        ws.write(r + 1, 1, "Sign-check pass rate:", F["kpi_lbl"])
        ws.write(r + 1, 2, f"{n_pass}/{len(mlr)} ({n_pass/len(mlr):.0%})", F["kpi_val"])

        # Beta bar chart
        ch = wb.add_chart({"type": "bar"})
        ch.add_series({
            "name": "Beta (β)",
            "categories": ["02_Factor_Impact", mlr_start, 1, mlr_end, 1],
            "values":     ["02_Factor_Impact", mlr_start, 2, mlr_end, 2],
            "fill": {"color": "#8b5cf6"},
            "data_labels": {"value": True, "num_format": "0.0000"},
        })
        ch.set_title({"name": f"Factor Betas — {latest_q}", "name_font": {"size": 11, "bold": True}})
        ch.set_legend({"none": True})
        ch.set_size({"width": 620, "height": 320})
        ws.insert_chart(r + 4, 1, ch)

        # Beta stability across quarters
        beta_hist: Dict[str, Dict[str, float]] = {}
        for q, exp in exports.items():
            for rec in exp.get("mlr_regression") or []:
                beta_hist.setdefault(rec["Variable"], {})[q] = rec["Beta (β)"]
        if beta_hist:
            qcols = sorted({q for d in beta_hist.values() for q in d})
            r2 = r + 22
            ws.write(r2 - 1, 1, "BETA STABILITY ACROSS QUARTERS (sign consistency = % quarters with same sign as latest)", F["h2"])
            hdr = ["Factor"] + qcols + ["Sign Consistency"]
            r3 = _header(ws, r2, 1, hdr, [22] + [10] * len(qcols) + [16])
            for var, d in beta_hist.items():
                ws.write(r3, 1, var, F["td"])
                latest_sign = np.sign(d.get(latest_q, list(d.values())[-1]))
                same = sum(1 for v in d.values() if np.sign(v) == latest_sign)
                for j, q in enumerate(qcols):
                    if q in d:
                        ws.write_number(r3, 2 + j, d[q], F["num4"])
                    else:
                        ws.write(r3, 2 + j, "—", F["td_c"])
                ws.write_number(r3, 2 + len(qcols), same / len(d), F["pct0"])
                r3 += 1

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 03 — GRANGER CAUSALITY
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("03_Granger", "#f59e0b")
    ws.set_column("A:A", 2)
    ws.write("B2", "VAR GRANGER CAUSALITY — WHICH FACTORS LEAD THE VN-INDEX?", F["title"])
    ws.write("B3", "H0: factor does NOT Granger-cause VNI returns. p < 0.05 → reject H0 → factor has leading power.", F["subtitle"])

    gr = pd.DataFrame(latest.get("granger_causality") or [])
    if not gr.empty:
        r = _header(ws, 4, 1,
                    ["Factor", "F-Statistic", "P-value", "Significance", "Granger-causes VNI?", "Verdict"],
                    [24, 13, 10, 12, 20, 44])
        g_start = r
        for _, row in gr.iterrows():
            causes = bool(row["granger_causes_vni"])
            ws.write(r, 1, str(row["causing_variable"]), F["td"])
            ws.write_number(r, 2, float(row["test_statistic"]), F["num4"])
            ws.write_number(r, 3, float(row["p_value"]), F["num4"])
            ws.write(r, 4, str(row.get("significance", "")) or "—", F["td_c"])
            ws.write(r, 5, "YES — LEADING" if causes else "NO", F["good"] if causes else F["bad"])
            verdict = (f"{row['causing_variable']} contains predictive information for future VN-Index returns."
                       if causes else
                       f"No statistical evidence that {row['causing_variable']} leads VN-Index returns.")
            ws.write(r, 6, verdict, F["td_wrap"])
            r += 1
        ws.conditional_format(g_start, 3, r - 1, 3,
                              {"type": "cell", "criteria": "<", "value": 0.05, "format": F["good"]})

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 04 — ML VALIDATION
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("04_ML_Validation", "#10b981")
    ws.set_column("A:A", 2)
    ws.write("B2", "MACHINE LEARNING — WALK-FORWARD VALIDATION (no look-ahead bias)", F["title"])

    wfv = latest.get("ml_walk_forward_validation") or {}
    r = 4
    for k, lbl in [("model_type", "Model"), ("n_folds", "Folds"), ("n_features", "Features"),
                   ("mean_accuracy", "Mean Accuracy"), ("std_accuracy", "Std Accuracy"),
                   ("mean_f1", "Mean F1 (weighted)"), ("latest_prediction", "Latest Prediction"),
                   ("latest_confidence", "Prediction Confidence")]:
        v = wfv.get(k, "N/A")
        ws.write(r, 1, lbl, F["kpi_lbl"])
        if isinstance(v, float):
            ws.write_number(r, 2, v, F["num4"])
        else:
            ws.write(r, 2, str(v), F["kpi_val"])
        r += 1
    ws.set_column("B:B", 22)
    ws.set_column("C:C", 14)

    folds = wfv.get("fold_metrics") or []
    if folds:
        r += 1
        ws.write(r, 1, "WALK-FORWARD FOLD METRICS (expanding window)", F["h2"])
        r = _header(ws, r + 1, 1,
                    ["Fold", "Train Size", "Test Size", "Accuracy", "F1 (weighted)", "Precision"],
                    [7, 11, 10, 11, 13, 11])
        f_start = r
        for fm in folds:
            ws.write_number(r, 1, int(fm["fold"]), F["td_c"])
            ws.write_number(r, 2, int(fm["train_size"]), F["td_c"])
            ws.write_number(r, 3, int(fm["test_size"]), F["td_c"])
            ws.write_number(r, 4, float(fm["accuracy"]), F["num4"])
            ws.write_number(r, 5, float(fm["f1_weighted"]), F["num4"])
            ws.write_number(r, 6, float(fm["precision"]), F["num4"])
            r += 1
        f_end = r - 1
        ch = wb.add_chart({"type": "column"})
        ch.add_series({
            "name": "Accuracy",
            "categories": ["04_ML_Validation", f_start, 1, f_end, 1],
            "values":     ["04_ML_Validation", f_start, 4, f_end, 4],
            "fill": {"color": "#10b981"},
        })
        ch.add_series({
            "name": "F1 (weighted)",
            "categories": ["04_ML_Validation", f_start, 1, f_end, 1],
            "values":     ["04_ML_Validation", f_start, 5, f_end, 5],
            "fill": {"color": "#3b82f6"},
        })
        ch.set_title({"name": "Out-of-Sample Metrics per Fold", "name_font": {"size": 11, "bold": True}})
        ch.set_size({"width": 560, "height": 280})
        ws.insert_chart(f_start, 8, ch)

    fi = pd.DataFrame(latest.get("feature_importance") or [])
    if not fi.empty:
        r += 2
        ws.write(r, 1, "TOP FEATURE IMPORTANCE (model-implied factor relevance)", F["h2"])
        r = _header(ws, r + 1, 1, ["Rank", "Feature", "Importance"], [7, 30, 13])
        fi_start = r
        for _, row in fi.iterrows():
            ws.write_number(r, 1, int(row["rank"]), F["td_c"])
            ws.write(r, 2, str(row["feature"]), F["td"])
            ws.write_number(r, 3, float(row["importance"]), F["num4"])
            r += 1
        fi_end = r - 1
        ws.conditional_format(fi_start, 3, fi_end, 3,
                              {"type": "data_bar", "bar_color": "#10b981"})
        ch = wb.add_chart({"type": "bar"})
        ch.add_series({
            "name": "Importance",
            "categories": ["04_ML_Validation", fi_start, 2, fi_end, 2],
            "values":     ["04_ML_Validation", fi_start, 3, fi_end, 3],
            "fill": {"color": "#10b981"},
        })
        ch.set_title({"name": "Feature Importance", "name_font": {"size": 11, "bold": True}})
        ch.set_legend({"none": True})
        ch.set_size({"width": 560, "height": 380})
        ws.insert_chart(fi_start, 8, ch)

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 05 — FACTOR SCORES (latest quarter detail)
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("05_Factor_Scores", "#f97316")
    ws.set_column("A:A", 2)
    ws.write("B2", f"FACTOR-LEVEL SCORE DECOMPOSITION — {latest_q}", F["title"])
    ws.write("B3", "Every indicator inside each pillar with its parsed 0-100 score. <MISSING> indicators fall back to neutral 50.", F["subtitle"])

    r = _header(ws, 4, 1,
                ["Pillar", "Pillar Weight", "Indicator", "Observed Value / Analysis", "Score (0-100)", "Data Status"],
                [24, 12, 24, 70, 13, 12])
    d_start = r
    details = latest_score.get("group_details", {})
    for key, pname in PILLAR_NAMES.items():
        for ind, v in (details.get(key) or {}).items():
            text, score, missing = _clean_detail_text(v)
            ws.write(r, 1, pname, F["td"])
            ws.write_number(r, 2, SCORING_WEIGHTS.get(key, 0), F["pct0"])
            ws.write(r, 3, ind, F["td"])
            ws.write(r, 4, text, F["td_wrap"])
            if score is not None:
                ws.write_number(r, 5, score, F["num2"])
            else:
                ws.write(r, 5, "—", F["td_c"])
            ws.write(r, 6, "MISSING" if missing else "OK", F["bad"] if missing else F["good"])
            r += 1
    ws.conditional_format(d_start, 5, r - 1, 5,
                          {"type": "3_color_scale", "min_color": "#ef4444",
                           "mid_color": "#fde047", "max_color": "#22c55e",
                           "min_type": "num", "min_value": 0,
                           "mid_type": "num", "mid_value": 50,
                           "max_type": "num", "max_value": 100})
    ws.freeze_panes(5, 0)
    ws.autofilter(4, 1, r - 1, 6)

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 06 — SIGNAL EFFICACY (backtest theo tín hiệu CALIBRATED)
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("06_Signal_Efficacy", "#ef4444")
    ws.set_column("A:A", 2)
    ws.write("B2", "SIGNAL EFFICACY — DOES THE CALIBRATED ACTION SIGNAL PREDICT STRICT FORWARD (t+1) RETURNS?", F["title"])
    ws.write("B3", "Primary test = CALIBRATED action signal (relative regime vs prior quarters only, point-in-time, winsorised v2). Signal at quarter t is evaluated "
                   "against the VN-Index return over quarter t+1 (strict forward return — outcome data is never an input to scoring). Raw composite shown as comparison. No look-ahead.", F["subtitle"])

    eff = pd.DataFrame([h for h in hist_rows if h["fwd"] is not None])
    if not eff.empty:
        # Strategy simulation theo tín hiệu CALIBRATED: allocation mid-point × fwd return
        eff["alloc"] = eff["cal_label"].map(ALLOCATION_MID).fillna(0.5)
        eff["strat_ret"] = eff["alloc"] * eff["fwd"]
        eff["hit"] = np.where(eff["cal_score"] >= 50, eff["fwd"] > 0, eff["fwd"] < 0)
        eff["cum_strategy"] = (1 + eff["strat_ret"]).cumprod() * 100
        eff["cum_bh"] = (1 + eff["fwd"]).cumprod() * 100

        # Raw-composite comparison strategy (cùng cơ chế, nhãn raw)
        eff["raw_alloc"] = eff["label"].map(ALLOCATION_MID).fillna(0.5)
        eff["raw_strat_ret"] = eff["raw_alloc"] * eff["fwd"]
        eff["raw_cum_strategy"] = (1 + eff["raw_strat_ret"]).cumprod() * 100

        # KPIs (calibrated) + comparison (raw)
        ic_p = float(eff["cal_score"].corr(eff["fwd"]))
        ic_s = _spearman(eff["cal_score"], eff["fwd"])
        ic_p_raw = float(eff["score"].corr(eff["fwd"]))
        ic_s_raw = _spearman(eff["score"], eff["fwd"])
        hit_rate = float(eff["hit"].mean())
        raw_hit = float(np.where(eff["score"] >= 50, eff["fwd"] > 0, eff["fwd"] < 0).mean())
        n = len(eff)
        strat_tot = eff["cum_strategy"].iloc[-1] / 100 - 1
        raw_strat_tot = eff["raw_cum_strategy"].iloc[-1] / 100 - 1
        bh_tot = eff["cum_bh"].iloc[-1] / 100 - 1
        strat_vol = float(eff["strat_ret"].std())
        bh_vol = float(eff["fwd"].std())
        sharpe_s = float(eff["strat_ret"].mean() / strat_vol * np.sqrt(4)) if strat_vol else np.nan
        sharpe_b = float(eff["fwd"].mean() / bh_vol * np.sqrt(4)) if bh_vol else np.nan

        kpi_rows = [
            ("Quarters evaluated (N)",                          n,             "td_c"),
            ("IC Calibrated (Pearson)",                         ic_p,          "num4"),
            ("IC Calibrated (Spearman)",                        ic_s,          "num4"),
            ("IC Raw composite (Pearson) — comparison",         ic_p_raw,      "num4"),
            ("IC Raw composite (Spearman) — comparison",        ic_s_raw,      "num4"),
            ("Directional Hit Rate — calibrated (≥50 → up)",    hit_rate,      "pct1"),
            ("Directional Hit Rate — raw (comparison)",         raw_hit,       "pct1"),
            ("Strategy total return — calibrated signal",       strat_tot,     "pct1"),
            ("Strategy total return — raw signal (comparison)", raw_strat_tot, "pct1"),
            ("Buy & Hold total return",                         bh_tot,        "pct1"),
            ("Strategy Sharpe (annualised, rf=0)",              sharpe_s,      "num2"),
            ("Buy & Hold Sharpe (annualised, rf=0)",            sharpe_b,      "num2"),
        ]
        r = 4
        for name, val, fmt in kpi_rows:
            ws.write(r, 1, name, F["kpi_lbl"])
            if fmt == "td_c":
                ws.write_number(r, 2, val, F["td_c"])
            else:
                ws.write_number(r, 2, float(val), F[fmt])
            r += 1
        ws.set_column("B:B", 44)
        ws.set_column("C:C", 13)

        # Bucket analysis by CALIBRATED regime
        r += 1
        ws.write(r, 1, "FORWARD RETURN BY CALIBRATED REGIME BUCKET", F["h2"])
        r = _header(ws, r + 1, 1,
                    ["Calibrated Regime", "N", "Avg Fwd Return", "Median Fwd Return", "Win Rate (fwd>0)"],
                    [18, 6, 15, 17, 16])
        order = ["BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL"]
        for lbl in order:
            sub = eff[eff["cal_label"] == lbl]
            if sub.empty:
                continue
            ws.write(r, 1, lbl, F["td_c"])
            ws.write_number(r, 2, len(sub), F["td_c"])
            ws.write_number(r, 3, float(sub["fwd"].mean()), F["pct1"])
            ws.write_number(r, 4, float(sub["fwd"].median()), F["pct1"])
            ws.write_number(r, 5, float((sub["fwd"] > 0).mean()), F["pct1"])
            r += 1

        # Detail table — calibrated ledger (raw giữ cột tham chiếu)
        r += 1
        ws.write(r, 1, "QUARTER-BY-QUARTER SIGNAL LEDGER (calibrated)", F["h2"])
        r = _header(ws, r + 1, 1,
                    ["Quarter", "Calibrated (t)", "Calibrated Label", "Equity Allocation",
                     "Raw Score (t)", "Raw Label", "Fwd Return (t+1)",
                     "Strategy Return", "Hit?", "Strategy Index", "Buy&Hold Index"],
                    [10, 14, 16, 16, 12, 11, 15, 15, 8, 14, 14])
        l_start = r
        for _, row in eff.iterrows():
            ws.write(r, 1, row["quarter"], F["td_c"])
            ws.write_number(r, 2, row["cal_score"], F["num2"])
            ws.write(r, 3, row["cal_label"], F["td_c"])
            ws.write_number(r, 4, row["alloc"], F["pct0"])
            ws.write_number(r, 5, row["score"], F["num2"])
            ws.write(r, 6, row["label"], F["td_c"])
            ws.write_number(r, 7, row["fwd"], F["pct1"])
            ws.write_number(r, 8, row["strat_ret"], F["pct1"])
            ws.write(r, 9, "✓" if row["hit"] else "✗", F["good"] if row["hit"] else F["bad"])
            ws.write_number(r, 10, row["cum_strategy"], F["num2"])
            ws.write_number(r, 11, row["cum_bh"], F["num2"])
            r += 1
        l_end = r - 1

        ch = wb.add_chart({"type": "line"})
        ch.add_series({
            "name": "Calibrated-Signal Strategy (base=100)",
            "categories": ["06_Signal_Efficacy", l_start, 1, l_end, 1],
            "values":     ["06_Signal_Efficacy", l_start, 10, l_end, 10],
            "line": {"color": "#8b5cf6", "width": 2.5},
        })
        ch.add_series({
            "name": "Buy & Hold (base=100)",
            "categories": ["06_Signal_Efficacy", l_start, 1, l_end, 1],
            "values":     ["06_Signal_Efficacy", l_start, 11, l_end, 11],
            "line": {"color": "#94a3b8", "width": 1.5, "dash_type": "dash"},
        })
        ch.set_title({"name": "Cumulative Growth: Calibrated-Signal Allocation vs Buy & Hold", "name_font": {"size": 11, "bold": True}})
        ch.set_size({"width": 760, "height": 320})
        ws.insert_chart(l_end + 3, 1, ch)

        ws.write(l_end + 21, 1,
                 "Note: strategy holds the mid-point of the CALIBRATED recommended equity band (e.g. HOLD = 50%) for the following quarter; "
                 "residual cash earns 0%. Gross of fees/slippage. Quarterly Sharpe annualised with √4. "
                 "ICs are reported as-is (no curve-fitting) — low IC means weak directional edge; the calibrated layer primarily restores "
                 "regime dispersion for allocation sizing, not alpha prediction.",
                 F["note"])

    # ══════════════════════════════════════════════════════════════════════
    # SHEET 07 — METHODOLOGY
    # ══════════════════════════════════════════════════════════════════════
    ws = _sheet("07_Methodology", "#64748b")
    ws.set_column("A:A", 2)
    ws.write("B2", "METHODOLOGY — WEIGHTS, REGIME BANDS & DATA SOURCES", F["title"])

    r = _header(ws, 4, 1, ["Pillar", "Weight"], [30, 10])
    for k, name in PILLAR_NAMES.items():
        ws.write(r, 1, name, F["td"])
        ws.write_number(r, 2, SCORING_WEIGHTS.get(k, 0), F["pct0"])
        r += 1

    r += 1
    ws.write(r, 1, "REGIME BANDS (config.py SCORE_LABELS — single source of truth)", F["h2"])
    r = _header(ws, r + 1, 1, ["Score Range", "Label", "Description", "Equity Allocation"], [12, 13, 52, 18])
    for (lo, hi), (lbl, em, desc, alloc_band) in sorted(SCORE_LABEL_RANGES, key=lambda x: x[0][0], reverse=True):
        ws.write(r, 1, f"{lo}–{hi}", F["td_c"])
        ws.write(r, 2, f"{em} {lbl}", F["td_c"])
        ws.write(r, 3, desc, F["td_wrap"])
        ws.write(r, 4, alloc_band, F["td_c"])
        r += 1

    r += 1
    ws.write(r, 1, "MODELS & DATA SOURCES", F["h2"])
    notes = [
        "MLR: forward VN-Index log-return regressed on macro factors; Newey-West HAC robust standard errors.",
        "VAR + Granger causality: tests whether factors statistically lead VN-Index returns.",
        "ML (XGBoost/RandomForest): trend classification with expanding-window Walk-Forward Validation (no look-ahead).",
        "Composite score (TIER 1 - raw): 6 pillar raw scores (0-100) × fixed weights; labels/allocations from config.py SCORE_LABELS. Kept unchanged as the reference layer.",
        "Calibrated Action Signal (TIER 2): calibrated = clip(center + z_scale × (raw − μ_hist)/σ_hist, 0, 100) where μ/σ come from PRIOR quarters only (expanding window, point-in-time, no look-ahead); parameters in config.py SCORE_CALIBRATION. First 4 quarters (or σ≈0) keep the raw score. Raw composite is never overwritten.",
        "Anti-compression at source: MLR signal gain 20000 (±0.10%/day → 70/30), VAR gain 5000; missing MLR/VAR/ADTV/ETF signals are excluded from pillar averages (renormalized over live signals) instead of defaulting to neutral 50.",
        "Data: vnstock (HOSE OHLCV, foreign flows, valuation), yfinance/FRED (DXY, US10Y, USD/JPY), SBV (rates, USD/VND), KBNN (VN yield curve).",
        f"Workbook generated at {generated} from output/exports/score_*.json, data/scores/quarterly_scores_history.parquet and data/scores/vnindex_quarterly_close.json.",
        "Disclaimer: for research purposes only. Not financial advice.",
    ]
    for note in notes:
        ws.write(r + 1, 1, "•", F["td_c"])
        ws.merge_range(r + 1, 2, r + 1, 8, note, F["note"])
        r += 1

    wb.close()
    logger.info(f"[EXCEL] Quant factor workbook -> {out_path}")
    return out_path
