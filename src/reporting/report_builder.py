"""
report_builder.py — Tạo Báo cáo Phân tích Định lượng HTML / JSON / Markdown
=============================================================================
Báo cáo bao gồm:
  1. Executive Summary (điểm tổng hợp, phân loại, khuyến nghị)
  2. Bảng biến số định lượng (6 nhóm × chi tiết từng biến)
  3. Kết quả MLR (bảng beta, p-value, sign check)
  4. Granger Causality Rankings
  5. ML Forecast Summary
  6. FTSE Upgrade Analysis
  7. Lịch sử điểm số theo quý (trend chart)
  8. Khuyến nghị đầu tư (data-driven)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.utils.config import REPORTS_DIR, CHARTS_DIR, EXPORTS_DIR

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ══════════════════════════════════════════════════════════════════════════════

def _score_bar(score: float, width: int = 30) -> str:
    """Tạo thanh tiến trình ASCII: [████████░░░░░░░░] 70/100"""
    filled = int(round(score / 100 * width))
    empty  = width - filled
    bar    = "█" * filled + "░" * empty
    return f"[{bar}] {score:.1f}/100"


def _color_for_score(score: float) -> str:
    """Trả về CSS color class cho score."""
    if score >= 80: return "#22c55e"   # green
    if score >= 60: return "#3b82f6"   # blue
    if score >= 40: return "#f59e0b"   # amber
    if score >= 20: return "#f97316"   # orange
    return "#ef4444"                   # red


def _format_pct(v: Optional[float], decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v*100:+.{decimals}f}%"


def _format_num(v: Optional[float], decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v:.{decimals}f}"


# ══════════════════════════════════════════════════════════════════════════════
# 1. JSON Export
# ══════════════════════════════════════════════════════════════════════════════

def export_score_json(
    score_record: Dict[str, Any],
    quarter: str,
    mlr_summary: Optional[pd.DataFrame] = None,
    granger_df:  Optional[pd.DataFrame] = None,
    wfv_summary: Optional[Dict] = None,
    fi_df:       Optional[pd.DataFrame] = None,
) -> Path:
    """
    Xuất toàn bộ kết quả phân tích sang JSON.

    Returns
    -------
    Path tới file JSON đã lưu
    """
    payload = {
        "metadata": {
            "quarter":        quarter,
            "generated_at":   datetime.now().isoformat(),
            "model_version":  "1.0.0",
            "analysis_type":  "VN-Index Comprehensive Quantitative Scoring",
        },
        "quarterly_score": score_record,
        "mlr_regression": (
            mlr_summary.to_dict(orient="records")
            if mlr_summary is not None else None
        ),
        "granger_causality": (
            granger_df.to_dict(orient="records")
            if granger_df is not None else None
        ),
        "ml_walk_forward_validation": wfv_summary,
        "feature_importance": (
            fi_df.head(15).to_dict(orient="records")
            if fi_df is not None else None
        ),
    }

    # Xử lý numpy types
    def _convert(obj):
        if isinstance(obj, (np.integer,)):  return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)):    return bool(obj)
        if isinstance(obj, pd.Timestamp):   return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    out_path = EXPORTS_DIR / f"score_{quarter.replace('-','_')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_convert)
    logger.info(f"[REPORT] Đã xuất JSON → {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# 2. HTML Report Builder
# ══════════════════════════════════════════════════════════════════════════════

_HTML_STYLE = """
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a;
         color: #e2e8f0; margin: 0; padding: 20px; }
  .container { max-width: 1100px; margin: 0 auto; }
  h1 { color: #f1f5f9; border-bottom: 2px solid #334155; padding-bottom: 12px; }
  h2 { color: #94a3b8; margin-top: 36px; }
  h3 { color: #cbd5e1; }
  .hero { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
          border: 1px solid #334155; border-radius: 12px; padding: 28px;
          margin-bottom: 28px; text-align: center; }
  .score-big { font-size: 72px; font-weight: 900; line-height: 1; }
  .score-label { font-size: 28px; font-weight: 700; margin-top: 8px; }
  .score-desc  { color: #94a3b8; margin-top: 6px; }
  .progress-bar { background: #1e293b; border-radius: 8px; height: 12px;
                  margin: 6px 0; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 8px; }
  .grid-6 { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
             gap: 14px; margin: 20px 0; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
          padding: 16px; }
  .card-title { font-size: 13px; color: #64748b; margin-bottom: 8px; }
  .card-value { font-size: 22px; font-weight: 700; }
  .card-detail { font-size: 12px; color: #475569; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  th { background: #1e293b; color: #94a3b8; padding: 10px 12px;
       text-align: left; font-size: 13px; border-bottom: 1px solid #334155; }
  td { padding: 9px 12px; font-size: 13px; border-bottom: 1px solid #1e293b; }
  tr:hover td { background: #1e293b; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: 11px; font-weight: 700; }
  .badge-green  { background: #052e16; color: #4ade80; }
  .badge-blue   { background: #0c1a4e; color: #60a5fa; }
  .badge-yellow { background: #1c1400; color: #fbbf24; }
  .badge-red    { background: #2d0a0a; color: #f87171; }
  .badge-ok     { background: #052e16; color: #4ade80; }
  .badge-fail   { background: #2d0a0a; color: #f87171; }
  .section { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
             padding: 20px; margin-bottom: 20px; }
  .rationale { color: #94a3b8; font-style: italic; font-size: 13px;
               border-left: 3px solid #334155; padding-left: 12px; margin-top: 8px; }
  .disclaimer { color: #475569; font-size: 12px; margin-top: 28px;
                border-top: 1px solid #334155; padding-top: 12px; }
  .leading-badge { background: #1e40af; color: #bfdbfe; padding: 3px 10px;
                   border-radius: 6px; font-size: 12px; margin-left: 8px; }
</style>
"""


def build_html_report(
    score_record: Dict[str, Any],
    quarter:      str,
    mlr_summary:  Optional[pd.DataFrame] = None,
    granger_df:   Optional[pd.DataFrame] = None,
    wfv_summary:  Optional[Dict] = None,
    fi_df:        Optional[pd.DataFrame] = None,
    score_history: Optional[pd.DataFrame] = None,
) -> Path:
    """
    Tạo báo cáo HTML đầy đủ.

    Returns
    -------
    Path tới file HTML đã lưu
    """
    total = score_record.get("total_score", 50)
    label = score_record.get("label", "HOLD")
    emoji = score_record.get("emoji", "🟡")
    desc  = score_record.get("label_description", "")
    leading = score_record.get("leading_indicator", "")
    date_computed = score_record.get("date_computed", "")

    score_color = _color_for_score(total)
    group_scores = score_record.get("group_scores", {})
    group_details = score_record.get("group_details", {})
    group_rationale = score_record.get("group_rationale", {})

    # ── Hero Section ──────────────────────────────────────────────────────────
    hero_html = f"""
    <div class="hero">
      <div style="color: #64748b; font-size: 14px; margin-bottom: 12px;">
        VN-INDEX QUARTERLY QUANTITATIVE SCORE — {quarter}
        &nbsp;|&nbsp; Cập nhật: {date_computed}
      </div>
      <div class="score-big" style="color: {score_color};">{total:.1f}</div>
      <div class="score-label" style="color: {score_color};">{emoji} {label}</div>
      <div class="score-desc">{desc}</div>
      <div style="margin-top: 16px; max-width: 400px; margin-left: auto; margin-right: auto;">
        <div class="progress-bar">
          <div class="progress-fill"
               style="width:{total}%; background:{score_color}; opacity:0.8;"></div>
        </div>
      </div>
      <div style="margin-top: 10px; color: #64748b; font-size: 13px;">
        Leading Indicator:
        <span class="leading-badge">{leading.replace('_', ' ').title()}</span>
      </div>
    </div>
    """

    # ── 6 Group Score Cards ────────────────────────────────────────────────────
    group_labels = {
        "macro_monetary":     ("💰", "Macro & Tiền tệ"),
        "global_intermarket": ("🌐", "Global & Ngoại lực"),
        "valuation_leverage": ("📐", "Định giá & Đòn bẩy"),
        "quant_model":        ("📊", "Mô hình Định lượng"),
        "ml_forecast":        ("🤖", "ML Forecast"),
        "market_structure":   ("🏗️", "Cấu trúc & FTSE"),
    }
    cards_html = '<div class="grid-6">'
    for grp, (ico, name) in group_labels.items():
        g_data = group_scores.get(grp, {})
        raw    = g_data.get("raw_score", 50)
        wtd    = g_data.get("weighted_score", 0)
        color  = _color_for_score(raw)
        cards_html += f"""
        <div class="card">
          <div class="card-title">{ico} {name}</div>
          <div class="card-value" style="color:{color};">{raw:.1f}</div>
          <div class="progress-bar" style="margin-top:8px;">
            <div class="progress-fill"
                 style="width:{raw}%;background:{color};opacity:0.7;"></div>
          </div>
          <div class="card-detail">Weighted: {wtd:.2f} pts</div>
        </div>"""
    cards_html += "</div>"

    # ── Group Details Table ────────────────────────────────────────────────────
    details_html = ""
    for grp, (ico, name) in group_labels.items():
        details = group_details.get(grp, {})
        rationale = group_rationale.get(grp, "")
        g_data = group_scores.get(grp, {})
        raw = g_data.get("raw_score", 50)
        color = _color_for_score(raw)

        rows_html = ""
        for k, v in details.items():
            rows_html += f"<tr><td>{k.replace('_',' ').title()}</td><td>{str(v)}</td></tr>"

        details_html += f"""
        <div class="section">
          <h3 style="color:{color};">{ico} {name} — Score: {raw:.1f}/100</h3>
          <table>
            <thead><tr><th>Biến số / Chỉ số</th><th>Giá trị & Phân tích</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
          <div class="rationale">{rationale}</div>
        </div>"""

    # ── MLR Regression Table ──────────────────────────────────────────────────
    mlr_html = ""
    if mlr_summary is not None and not mlr_summary.empty:
        mlr_rows = ""
        for _, row in mlr_summary.iterrows():
            sign_cls = "badge-ok" if row.get("Sign OK") == "✅" else "badge-fail"
            sig_color = "#4ade80" if "***" in str(row.get("Significance","")) else (
                        "#60a5fa" if "**" in str(row.get("Significance","")) else (
                        "#fbbf24" if "*" in str(row.get("Significance","")) else "#64748b"))
            mlr_rows += f"""<tr>
              <td>{row['Variable']}</td>
              <td style="font-weight:700;">{row['Beta (β)']:.6f}</td>
              <td style="color:{sig_color};">{row['P-value']} {row.get('Significance','')}</td>
              <td>{row['Sign Expected']}</td>
              <td>{row['Sign Actual']}</td>
              <td><span class="badge {sign_cls}">{row['Sign OK']}</span></td>
            </tr>"""
        mlr_html = f"""
        <div class="section">
          <h2>📐 Kết quả Hồi quy Đa biến (MLR) — OLS với Newey-West HAC</h2>
          <p style="color:#64748b; font-size:13px;">
            R_VNI = α + β₁·ΔIR + β₂·ΔDXY + β₃·NFF + β₄·Z(PE) + β₅·ΔMrg + β₆·ΔUS10Y + ε
          </p>
          <table>
            <thead><tr>
              <th>Biến độc lập</th><th>Beta (β)</th><th>P-value</th>
              <th>Dấu kỳ vọng</th><th>Dấu thực tế</th><th>Đúng kỳ vọng?</th>
            </tr></thead>
            <tbody>{mlr_rows}</tbody>
          </table>
          <div class="rationale">
            *** p&lt;1% &nbsp; ** p&lt;5% &nbsp; * p&lt;10% — Sai số chuẩn Newey-West (HAC)
          </div>
        </div>"""

    # ── Granger Causality Table ───────────────────────────────────────────────
    granger_html = ""
    if granger_df is not None and not granger_df.empty:
        gc_rows = ""
        for _, row in granger_df.iterrows():
            causes = row.get("granger_causes_vni", False)
            badge = '<span class="badge badge-ok">✅ Dẫn dắt</span>' if causes else \
                    '<span class="badge badge-fail">❌ Không</span>'
            gc_rows += f"""<tr>
              <td>{row['causing_variable'].replace('_',' ')}</td>
              <td>{row.get('test_statistic', 'N/A')}</td>
              <td style="{'color:#4ade80' if causes else 'color:#64748b'};">
                {row['p_value']} {row.get('significance','')}</td>
              <td>{badge}</td>
            </tr>"""
        granger_html = f"""
        <div class="section">
          <h2>🔗 Granger Causality Test — Biến nào dẫn dắt VN-Index?</h2>
          <table>
            <thead><tr>
              <th>Biến gây nhân quả</th>
              <th>Test Statistic (F)</th>
              <th>P-value</th>
              <th>Granger-cause VNI?</th>
            </tr></thead>
            <tbody>{gc_rows}</tbody>
          </table>
          <div class="rationale">
            H₀: Biến X không Granger-cause VNI. Reject H₀ khi p &lt; 0.05 → X có thể dự báo VNI.
          </div>
        </div>"""

    # ── ML WFV Summary ────────────────────────────────────────────────────────
    ml_html = ""
    if wfv_summary:
        acc  = wfv_summary.get("mean_accuracy", 0)
        f1   = wfv_summary.get("mean_f1", 0)
        nf   = wfv_summary.get("n_folds", 0)
        mtyp = wfv_summary.get("model_type", "").upper()
        acc_color = _color_for_score(acc * 100)

        fi_rows = ""
        if fi_df is not None and not fi_df.empty:
            for _, row in fi_df.head(10).iterrows():
                pct = row["importance"] / fi_df["importance"].sum() * 100
                fi_rows += f"""<tr>
                  <td>#{int(row['rank'])}</td>
                  <td>{row['feature']}</td>
                  <td>
                    <div class="progress-bar">
                      <div class="progress-fill"
                           style="width:{pct:.0f}%;background:#3b82f6;"></div>
                    </div>
                  </td>
                  <td>{pct:.1f}%</td>
                </tr>"""

        ml_html = f"""
        <div class="section">
          <h2>🤖 Machine Learning — Walk-Forward Validation ({mtyp})</h2>
          <div class="grid-6" style="grid-template-columns: repeat(3,1fr); max-width:500px;">
            <div class="card">
              <div class="card-title">Mean Accuracy</div>
              <div class="card-value" style="color:{acc_color};">{acc:.1%}</div>
            </div>
            <div class="card">
              <div class="card-title">Mean F1-Score</div>
              <div class="card-value">{f1:.3f}</div>
            </div>
            <div class="card">
              <div class="card-title">N Folds (WFV)</div>
              <div class="card-value">{nf}</div>
            </div>
          </div>
          {f'''<h3 style="margin-top:20px;">Top-10 Feature Importance</h3>
          <table>
            <thead><tr><th>Rank</th><th>Feature</th><th>Importance</th><th>%</th></tr></thead>
            <tbody>{fi_rows}</tbody>
          </table>''' if fi_rows else ''}
          <div class="rationale">
            Walk-Forward Validation: Expanding window — Train [t₀:tᵢ] → Test [tᵢ:tᵢ₊ₖ].
            Không dùng random split để tránh data leakage trong time-series.
          </div>
        </div>"""

    # ── Score History Chart ───────────────────────────────────────────────────
    history_html = ""
    if score_history is not None and len(score_history) > 1:
        qtrs = score_history["quarter"].tolist()
        scores_list = score_history["total_score"].tolist()

        points = []
        n = len(scores_list)
        for i, (q, s) in enumerate(zip(qtrs, scores_list)):
            x = i / max(n - 1, 1) * 560 + 20
            y = (1 - s / 100) * 200 + 20
            color = _color_for_score(s)
            points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')
            points.append(f'<text x="{x:.1f}" y="{y-10:.1f}" text-anchor="middle"'
                          f' font-size="10" fill="#94a3b8">{s:.0f}</text>')

        polyline_pts = " ".join([
            f"{i/(max(n-1,1))*560+20:.1f},{(1-s/100)*200+20:.1f}"
            for i, s in enumerate(scores_list)
        ])
        history_html = f"""
        <div class="section">
          <h2>📈 Lịch sử Điểm số Theo Quý</h2>
          <svg width="600" height="260" style="background:#0f172a; border-radius:8px;">
            <!-- Đường baseline -->
            <line x1="20" y1="120" x2="580" y2="120" stroke="#334155" stroke-dasharray="4"/>
            <text x="585" y="124" fill="#64748b" font-size="10">50</text>
            <!-- Đường điểm số -->
            <polyline points="{polyline_pts}" fill="none" stroke="#3b82f6" stroke-width="2"/>
            {''.join(points)}
            <!-- Labels quý -->
            {''.join([f'<text x="{i/(max(n-1,1))*560+20:.1f}" y="250" text-anchor="middle" font-size="9" fill="#64748b">{q}</text>' for i, q in enumerate(qtrs)])}
          </svg>
        </div>"""

    # ── Investment Recommendation ─────────────────────────────────────────────
    rec_text = {
        "BUY": """
          <ul>
            <li><strong>Tăng tỷ trọng VN30:</strong> Ưu tiên các cổ phiếu vốn hóa lớn
              hưởng lợi từ dòng vốn ETF ngoại (FTSE upgrade).</li>
            <li><strong>Sector rotation:</strong> Ngân hàng (VCB, BID, TCB), Thực phẩm (VNM),
              Bất động sản khu công nghiệp (KBC, BCM) hưởng lợi môi trường lãi suất thấp.</li>
            <li><strong>Position sizing:</strong> Có thể nâng leverage moderate; kiểm soát
              margin ở mức &lt;30% NAV.</li>
            <li><strong>Stop-loss:</strong> Đặt stop tại -8% từ entry để tránh margin call cascade.</li>
          </ul>""",
        "ACCUMULATE": """
          <ul>
            <li><strong>Mua từng đợt (DCA):</strong> Không all-in; phân bổ 60-70% vốn dự kiến.</li>
            <li><strong>Focus on quality:</strong> Lọc cổ phiếu có ROE &gt;15%, debt/equity &lt;1.</li>
            <li><strong>Monitor NFF:</strong> Theo dõi khối ngoại — bán ròng 5 phiên liên tiếp
              là tín hiệu pause.</li>
          </ul>""",
        "HOLD": """
          <ul>
            <li><strong>Duy trì danh mục hiện tại:</strong> Không mở mới vị thế lớn.</li>
            <li><strong>Chờ tín hiệu xác nhận:</strong> VNI cần vượt MA20 với volume &gt;average.</li>
            <li><strong>Giảm exposure ngành nhạy cảm:</strong> BDS, chứng khoán — rủi ro margin cao.</li>
          </ul>""",
        "REDUCE": """
          <ul>
            <li><strong>Cắt giảm 30-40% tỷ trọng:</strong> Chốt lời các vị thế có lợi nhuận.</li>
            <li><strong>Tăng cash buffer:</strong> Duy trì &gt;40% tiền mặt.</li>
            <li><strong>Hedge:</strong> Xem xét short CW hoặc bán VN30F nếu có.</li>
          </ul>""",
        "SELL": """
          <ul>
            <li><strong>Thoát vị thế:</strong> Giảm về mức phòng thủ (90%+ tiền mặt).</li>
            <li><strong>Risk-off assets:</strong> Chuyển sang TPCP, gửi tiết kiệm.</li>
            <li><strong>Alert margin call:</strong> Kiểm tra ngưỡng giải chấp — VNI tiếp tục
              giảm có thể kích hoạt chuỗi margin call.</li>
          </ul>""",
    }
    rec_html = f"""
    <div class="section" style="border-color:{_color_for_score(total)};">
      <h2>{emoji} Khuyến nghị Đầu tư — {quarter}</h2>
      <h3 style="color:{_color_for_score(total)};">{label}: {desc}</h3>
      {rec_text.get(label, "")}
      <div class="rationale">
        ⚠️ Khuyến nghị dựa trên dữ liệu định lượng. Kết hợp với phân tích
        định tính và điều chỉnh theo rủi ro chịu đựng cá nhân trước khi quyết định.
      </div>
    </div>"""

    # ── Full HTML ─────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VN-Index Quant Score {quarter}</title>
  {_HTML_STYLE}
</head>
<body>
<div class="container">
  <h1>📊 VN-Index Comprehensive Quantitative Scoring Model
    <span style="font-size:18px; color:#64748b; font-weight:400;">Q3/2026 Report</span>
  </h1>

  {hero_html}
  {cards_html}
  {details_html}
  {mlr_html}
  {granger_html}
  {ml_html}
  {history_html}
  {rec_html}

  <div class="disclaimer">
    <strong>Disclaimer:</strong> Báo cáo này được tạo tự động bởi hệ thống phân tích định lượng
    VN_Index_Scoring_Quarterly_Quant_Model v1.0.0. Kết quả phục vụ mục đích nghiên cứu và tham khảo.
    Không phải khuyến nghị đầu tư chính thức. Nhà đầu tư tự chịu trách nhiệm quyết định cuối cùng.
    Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} ICT
  </div>
</div>
</body>
</html>"""

    # Lưu file
    qtr_dir = REPORTS_DIR / quarter.replace("-", "_")
    qtr_dir.mkdir(parents=True, exist_ok=True)
    out_path = qtr_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"[REPORT] HTML report → {out_path}")
    return out_path
