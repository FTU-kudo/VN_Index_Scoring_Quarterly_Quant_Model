"""
report_builder.py — Cấu hình Báo cáo HTML/JSON Định lượng
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.utils.config import REPORTS_DIR, EXPORTS_DIR

logger = logging.getLogger(__name__)

def _score_bar(score: float, width: int = 30) -> str:
    filled = int(round(score / 100 * width))
    empty  = width - filled
    bar    = "█" * filled + "░" * empty
    return f"[{bar}] {score:.1f}/100"

def _color_for_score(score: float) -> str:
    if score >= 80: return "var(--color-green)"
    if score >= 60: return "var(--color-blue)"
    if score >= 40: return "var(--color-amber)"
    if score >= 20: return "var(--color-orange)"
    return "var(--color-red)"

def export_score_json(
    score_record: Dict[str, Any],
    quarter: str,
    mlr_summary: Optional[pd.DataFrame] = None,
    granger_df:  Optional[pd.DataFrame] = None,
    wfv_summary: Optional[Dict] = None,
    fi_df:       Optional[pd.DataFrame] = None,
) -> Path:
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
        "ml_walk_forward_validation": (
            {k: v for k, v in wfv_summary.items() if not isinstance(v, pd.DataFrame)}
            if isinstance(wfv_summary, dict) else wfv_summary
        ),
        "feature_importance": (
            fi_df.head(15).to_dict(orient="records")
            if fi_df is not None else None
        ),
    }

    def _convert(obj):
        if isinstance(obj, (np.integer,)):  return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)):    return bool(obj)
        if isinstance(obj, pd.Timestamp):   return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    out_path = EXPORTS_DIR / f"score_{quarter.replace('-','_')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_convert)
    logger.info(f"[REPORT] JSON exported → {out_path}")
    return out_path


_HTML_STYLE = """
<style>
  :root {
    --bg-primary: #f8fafc;
    --bg-card: #ffffff;
    --text-main: #0f172a;
    --text-muted: #64748b;
    --border-color: #e2e8f0;
    --hero-bg: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
    --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    
    --color-green: #16a34a;
    --color-blue: #2563eb;
    --color-amber: #d97706;
    --color-orange: #ea580c;
    --color-red: #dc2626;
    --badge-ok-bg: #dcfce7;
    --badge-ok-text: #16a34a;
    --badge-fail-bg: #fee2e2;
    --badge-fail-text: #dc2626;
  }
  body.dark-mode {
    --bg-primary: #0f172a;
    --bg-card: #1e293b;
    --text-main: #e2e8f0;
    --text-muted: #94a3b8;
    --border-color: #334155;
    --hero-bg: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5);
    
    --color-green: #22c55e;
    --color-blue: #3b82f6;
    --color-amber: #f59e0b;
    --color-orange: #f97316;
    --color-red: #ef4444;
    --badge-ok-bg: #052e16;
    --badge-ok-text: #4ade80;
    --badge-fail-bg: #2d0a0a;
    --badge-fail-text: #f87171;
  }
  
  * { box-sizing: border-box; transition: background-color 0.3s, color 0.3s; }
  body { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; background: var(--bg-primary);
         color: var(--text-main); margin: 0; padding: 0; }
  
  /* Navbar */
  .navbar { background: var(--bg-card); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); position: sticky; top: 0; z-index: 100; box-shadow: var(--card-shadow); }
  .nav-left { display: flex; align-items: center; gap: 20px; }
  .clock { font-size: 16px; font-weight: 600; font-family: monospace; color: var(--color-blue); background: var(--bg-primary); padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-color); }
  .nav-right { display: flex; gap: 10px; }
  .btn { cursor: pointer; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-primary); color: var(--text-main); font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .btn:hover { background: var(--border-color); }

  .page-wrapper { max-width: 1300px; margin: 30px auto; padding: 0 20px; display: flex; gap: 30px; align-items: flex-start; }
  .sidebar { width: 250px; flex-shrink: 0; position: sticky; top: 80px; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 15px 0; box-shadow: var(--card-shadow); }
  .sidebar ul { list-style: none; padding: 0; margin: 0; }
  .sidebar li { padding: 12px 20px; cursor: pointer; font-size: 15px; font-weight: 600; border-left: 3px solid transparent; color: var(--text-muted); transition: all 0.2s; display: flex; align-items: center; gap: 10px; }
  .sidebar li:hover { background: var(--bg-primary); color: var(--text-main); }
  .sidebar li.active { border-left-color: var(--color-blue); color: var(--color-blue); background: var(--bg-primary); }
  .main-content { flex-grow: 1; min-width: 0; }
  .tab-content { display: none; animation: fadeIn 0.3s; }
  .tab-content.active { display: block; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

  h1 { color: var(--text-main); border-bottom: 2px solid var(--border-color); padding-bottom: 12px; margin-top: 0; }
  h2 { color: var(--text-muted); margin-top: 0; margin-bottom: 20px; }
  h3 { color: var(--text-main); }
  
  .hero { background: var(--hero-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 32px; margin-bottom: 28px; text-align: center; box-shadow: var(--card-shadow); }
  .score-big { font-size: 72px; font-weight: 900; line-height: 1; text-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
  .score-label { font-size: 28px; font-weight: 700; margin-top: 8px; }
  .score-desc  { color: var(--text-muted); margin-top: 6px; font-size: 16px; }
  .progress-bar { background: var(--bg-primary); border-radius: 8px; height: 12px; margin: 6px 0; overflow: hidden; border: 1px solid var(--border-color); }
  .progress-fill { height: 100%; border-radius: 8px; transition: width 1s ease-out; }
  
  .grid-6 { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 20px 0; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
  
  .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 20px; box-shadow: var(--card-shadow); transition: transform 0.2s; }
  .card:hover { transform: translateY(-3px); }
  .card-title { font-size: 14px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }
  .card-value { font-size: 24px; font-weight: 700; }
  .card-detail { font-size: 13px; color: var(--text-muted); margin-top: 6px; }
  
  .section { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 10px; padding: 24px; margin-bottom: 24px; box-shadow: var(--card-shadow); }
  
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  th { background: var(--bg-primary); color: var(--text-muted); padding: 12px 14px; text-align: left; font-size: 14px; border-bottom: 1px solid var(--border-color); }
  td { padding: 12px 14px; font-size: 14px; border-bottom: 1px solid var(--border-color); }
  tr:hover td { background: var(--bg-primary); }
  
  .badge { display: inline-block; padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
  .badge-ok     { background: var(--badge-ok-bg); color: var(--badge-ok-text); }
  .badge-fail   { background: var(--badge-fail-bg); color: var(--badge-fail-text); }
  .leading-badge { background: var(--color-blue); color: #fff; padding: 3px 10px; border-radius: 6px; font-size: 12px; margin-left: 8px; }
  .report-badge { display: inline-block; white-space: nowrap; }
  
  .rationale { color: var(--text-muted); font-style: italic; font-size: 14px; border-left: 3px solid var(--border-color); padding-left: 14px; margin-top: 12px; }
  .disclaimer { color: var(--text-muted); font-size: 13px; margin-top: 40px; border-top: 1px solid var(--border-color); padding-top: 20px; text-align: center; padding-bottom: 40px; }
  
  /* Lang toggle */
  .lang-vi { display: none; }
  body.lang-vi-active .lang-vi { display: inline; }
  body.lang-vi-active .lang-en { display: none; }
  
  .chart-container { position: sticky; top: 1.5rem; align-self: flex-start; height: 350px; width: 100%; display: flex; justify-content: center; }
</style>
"""

_JS_SCRIPT = """
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
  // Real-time Clock
  function updateClock() {
    const now = new Date();
    const options = { timeZone: 'Asia/Ho_Chi_Minh', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const formatter = new Intl.DateTimeFormat('sv-SE', options); // sv-SE gives ISO-like format YYYY-MM-DD HH:mm:ss
    document.getElementById('clock').innerText = formatter.format(now) + ' ICT';
  }
  setInterval(updateClock, 1000);
  updateClock();

  // Tab switching logic
  function openTab(evt, tabName) {
    const tabContents = document.getElementsByClassName("tab-content");
    for (let i = 0; i < tabContents.length; i++) {
      tabContents[i].classList.remove("active");
    }
    const tabLinks = document.getElementsByClassName("tab-link");
    for (let i = 0; i < tabLinks.length; i++) {
      tabLinks[i].classList.remove("active");
    }
    document.getElementById(tabName).classList.add("active");
    if (evt) {
      evt.currentTarget.classList.add("active");
    }
    // Re-render charts so canvas picks up new dimensions when unhidden
    if (typeof renderCharts === 'function') {
      setTimeout(renderCharts, 50);
    }
  }

  // Theme Toggle
  const themeBtn = document.getElementById('theme-btn');
  themeBtn.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    themeBtn.innerHTML = isDark ? '☀️ Light' : '🌙 Dark';
    renderCharts(); // Re-render charts for theme colors
  });
  if (localStorage.getItem('theme') === 'dark') {
    document.body.classList.add('dark-mode');
    themeBtn.innerHTML = '☀️ Light';
  }

  // Dynamic Keyword Translation
  function translateDynamicContent(isVi) {
    const dict = {
      "score": "điểm",
      "Forecast": "Dự báo",
      "stable": "ổn định",
      "strong": "mạnh",
      "weak": "yếu",
      "normal": "bình thường",
      "pressure": "áp lực",
      "high_risk": "rủi ro cao",
      "neutral": "trung tính",
      "hikes": "tăng",
      "cuts": "cắt giảm",
      "growth": "tăng trưởng",
      "Incomplete": "Không đầy đủ",
      "data": "dữ liệu",
      "need": "cần",
      "weekly": "tuần",
      "bil": "tỷ",
      "Status": "Trạng thái",
      "confirmed": "đã xác nhận",
      "pending": "đang chờ",
      "completed": "hoàn thành",
      "months to rebalancing": "tháng tới kỳ cơ cấu",
      "bonus": "điểm thưởng",
      "unavailable": "không có",
      "neutral": "trung lập",
      "Vn1Y Yield": "Lợi suất TPCP VN1Y",
      "Vn10Y Yield": "Lợi suất TPCP VN10Y",
      "Vn Yield Spread": "Độ dốc (Spread) 10Y-2Y/1Y"
    };
    
    const els = document.querySelectorAll('td:nth-child(1), td:nth-child(2), .rationale');
    els.forEach(el => {
      if (!el.dataset.orig) el.dataset.orig = el.innerHTML;
      let text = el.dataset.orig;
      if (isVi) {
        for (const [en, vi] of Object.entries(dict)) {
          const regex = new RegExp(`\\\\b${en}\\\\b`, 'g');
          text = text.replace(regex, vi);
        }
        // Also case-insensitive replacements for some
        text = text.replace(/\\\\bscore\\\\b/gi, "điểm");
      }
      el.innerHTML = text;
    });
  }

  // Language Toggle
  const langBtn = document.getElementById('lang-btn');
  langBtn.addEventListener('click', () => {
    document.body.classList.toggle('lang-vi-active');
    const isVi = document.body.classList.contains('lang-vi-active');
    localStorage.setItem('lang', isVi ? 'vi' : 'en');
    langBtn.innerHTML = isVi ? '🇬🇧 EN' : '🇻🇳 VI';
    
    // Radar Chart Labels Translation
    if (window.chartDataRadar && radarChartInstance) {
      const radarVi = {
        "Macro & Monetary": "Vĩ mô & Tiền tệ",
        "Global & Intermarket": "Biến số Toàn cầu",
        "Valuation & Leverage": "Định giá & Đòn bẩy",
        "Quant Model": "Mô hình Định lượng",
        "ML Forecast": "Dự báo Máy học",
        "Market Structure": "Cấu trúc Thị trường"
      };
      const baseLabels = ["Macro & Monetary", "Global & Intermarket", "Valuation & Leverage", "Quant Model", "ML Forecast", "Market Structure"];
      window.chartDataRadar.labels = baseLabels.map(l => isVi ? radarVi[l] : l);
      radarChartInstance.update();
    }
    
    translateDynamicContent(isVi);
  });
  
  if (localStorage.getItem('lang') === 'vi') {
    document.body.classList.add('lang-vi-active');
    langBtn.innerHTML = '🇬🇧 EN';
    // Let charts and dynamic content translate on next tick
    setTimeout(() => translateDynamicContent(true), 100);
  }
  
  // Charts setup
  let radarChartInstance = null;
  let lineChartInstance = null;

  function renderCharts() {
    const isDark = document.body.classList.contains('dark-mode');
    const textColor = isDark ? '#e2e8f0' : '#0f172a';
    const gridColor = isDark ? '#64748b' : '#e2e8f0';
    
    // Radar Chart
    const radarCtx = document.getElementById('radarChart');
    if (radarCtx && window.chartDataRadar) {
      if (radarChartInstance) radarChartInstance.destroy();
      radarChartInstance = new Chart(radarCtx, {
        type: 'radar',
        data: window.chartDataRadar,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            r: {
              angleLines: { color: gridColor, lineWidth: 1 },
              grid: { color: gridColor, lineWidth: 1 },
              pointLabels: { color: textColor, font: { size: 12 } },
              ticks: { display: false, min: 0, max: 100 }
            }
          },
          plugins: { legend: { display: false } }
        }
      });
    }

    // Line Chart
    const lineCtx = document.getElementById('lineChart');
    if (lineCtx && window.chartDataLine) {
      if (lineChartInstance) lineChartInstance.destroy();
      lineChartInstance = new Chart(lineCtx, {
        type: 'line',
        data: window.chartDataLine,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { grid: { color: gridColor }, ticks: { color: textColor } },
            y: { grid: { color: gridColor }, ticks: { color: textColor }, min: 0, max: 100 }
          },
          plugins: { legend: { display: false } }
        }
      });
    }
  }
  
  // Initial render is handled at end of body
</script>
"""

# Translation dictionary mapping EN -> VI for specific terms
VI_TRANS = {
    "Macro & Monetary": "Macro & Tiền tệ",
    "Global & Intermarket": "Global & Ngoại lực",
    "Valuation & Leverage": "Định giá & Đòn bẩy",
    "Quant Model": "Mô hình Định lượng",
    "ML Forecast": "Dự báo Machine Learning",
    "Market Structure": "Cấu trúc & FTSE",
    "Variable / Indicator": "Biến số / Chỉ số",
    "Value & Analysis": "Giá trị & Phân tích",
    "Leading Indicator": "Biến dẫn dắt",
    "Variable": "Biến độc lập",
    "Sign Expected": "Dấu kỳ vọng",
    "Sign Actual": "Dấu thực tế",
    "Sign OK": "Đúng kỳ vọng?",
    "Causing Variable": "Biến gây nhân quả",
    "Rank": "Xếp hạng",
    "Feature": "Đặc trưng",
    "Importance": "Mức quan trọng",
    "Highly favorable environment — Increase exposure aggressively": "Môi trường rất thuận lợi — Tăng tỷ trọng mạnh",
    "Gradually accumulate — Controllable risks": "Tích lũy dần — Rủi ro kiểm soát được",
    "Neutral — Await confirming signals": "Trung lập — Chờ tín hiệu xác nhận",
    "Reduce exposure — Increasing pressure": "Giảm tỷ trọng — Áp lực tăng",
    "Defensive — Unfavorable environment": "Phòng thủ — Môi trường bất lợi",
    "FTSE Secondary EM upgrade is creating a structural tailwind for VN-Index": "FTSE Secondary EM upgrade đang tạo structural tailwind cho VN-Index"
}

def t(en_text: str, custom_vi: str = None) -> str:
    """Helper to generate bilingual HTML span."""
    vi_text = custom_vi or VI_TRANS.get(en_text, en_text)
    return f'<span class="lang-en">{en_text}</span><span class="lang-vi">{vi_text}</span>'


def build_html_report(
    score_record: Dict[str, Any],
    quarter:      str,
    mlr_summary:  Optional[pd.DataFrame] = None,
    granger_df:   Optional[pd.DataFrame] = None,
    wfv_summary:  Optional[Dict] = None,
    fi_df:        Optional[pd.DataFrame] = None,
    score_history: Optional[pd.DataFrame] = None,
) -> Path:
    
    total = score_record.get("total_score", 50)
    label = score_record.get("label", "HOLD")
    emoji = score_record.get("emoji", "🟡")
    desc  = score_record.get("label_description", "")
    leading = score_record.get("most_divergent_pillar", score_record.get("leading_indicator", ""))
    date_computed = score_record.get("date_computed", "")

    score_color = _color_for_score(total)
    group_scores = score_record.get("group_scores", {})
    group_details = score_record.get("group_details", {})
    group_rationale = score_record.get("group_rationale", {})

    # Navbar
    navbar = f"""
    <div class="navbar">
      <div class="nav-left">
        <div style="font-weight: 700; font-size: 18px; color: var(--color-blue);">
          VNI Quant
        </div>
        <div class="clock" id="clock">Loading time...</div>
      </div>
      <div class="nav-right">
        <button class="btn" id="lang-btn">🇻🇳 VI</button>
        <button class="btn" id="theme-btn">🌙 Dark</button>
      </div>
    </div>
    """

    # Hero Section
    hero_html = f"""
    <div class="hero">
      <div style="color: var(--text-muted); font-size: 14px; margin-bottom: 12px; font-weight: 500;">
        {t("VN-INDEX QUARTERLY QUANTITATIVE SCORE", "ĐIỂM ĐỊNH LƯỢNG VN-INDEX HÀNG QUÝ")} — {quarter}
        &nbsp;|&nbsp; {t("Last Updated", "Cập nhật lần cuối")}: {date_computed}
      </div>
      <div class="score-big" style="color: {score_color};">{total:.1f}</div>
      <div class="score-label" style="color: {score_color};">{emoji} {label}</div>
      <div class="score-desc">{t(desc)}</div>
      <div style="margin-top: 24px; max-width: 500px; margin-left: auto; margin-right: auto;">
        <div class="progress-bar">
          <div class="progress-fill" style="width:{total}%; background:{score_color};"></div>
        </div>
      </div>
      <div style="margin-top: 14px; color: var(--text-muted); font-size: 14px;">
        {t("Leading Indicator", "Nhóm dẫn dắt")}:
        <span class="leading-badge">{t(leading.replace('_', ' ').title())}</span>
      </div>
    </div>
    """

    # 6 Group Score Cards + Chart Data
    group_labels = {
        "macro_monetary":     ("💰", "Macro & Monetary"),
        "global_intermarket": ("🌐", "Global & Intermarket"),
        "valuation_leverage": ("📐", "Valuation & Leverage"),
        "quant_model":        ("📊", "Quant Model"),
        "ml_forecast":        ("🤖", "ML Forecast"),
        "market_structure":   ("🏗️", "Market Structure"),
    }
    
    radar_labels = []
    radar_data = []

    cards_html = '<div class="grid-6">'
    for grp, (ico, name) in group_labels.items():
        g_data = group_scores.get(grp, {})
        raw    = g_data.get("raw_score", 50)
        wtd    = g_data.get("weighted_score", 0)
        color  = _color_for_score(raw)
        
        radar_labels.append(name)
        radar_data.append(raw)
        
        cards_html += f"""
        <div class="card">
          <div class="card-title">{ico} {t(name)}</div>
          <div class="card-value" style="color:{color};">{raw:.1f}</div>
          <div class="progress-bar" style="margin-top:10px;">
            <div class="progress-fill" style="width:{raw}%;background:{color};"></div>
          </div>
          <div class="card-detail">{t('Weighted', 'Tỷ trọng')}: {wtd:.2f} pts</div>
        </div>"""
    cards_html += "</div>"
    
    # Inject Radar Chart config
    chart_js_data = f"""
    <script>
      window.chartDataRadar = {{
        labels: {json.dumps(radar_labels)},
        datasets: [{{
          label: 'Score',
          data: {json.dumps(radar_data)},
          fill: true,
          backgroundColor: 'rgba(59, 130, 246, 0.2)',
          borderColor: 'rgba(59, 130, 246, 1)',
          pointBackgroundColor: 'rgba(59, 130, 246, 1)',
          pointBorderColor: '#fff',
          pointHoverBackgroundColor: '#fff',
          pointHoverBorderColor: 'rgba(59, 130, 246, 1)'
        }}]
      }};
    </script>
    """

    # Layout for Radar + Details
    layout_html = f"""
    <div>
      <div class="card" style="display:flex; flex-direction:column; margin-bottom: 24px;">
        <h3 style="margin-top:0; color: var(--text-muted); font-size:15px; border-bottom:1px solid var(--border-color); padding-bottom:10px;">{t("Pillars Overview", "Tổng quan 6 trụ cột")}</h3>
        <div class="chart-container" style="flex:1; min-height: 400px;">
          <canvas id="radarChart"></canvas>
        </div>
      </div>
      <div class="grid-2">
    """
    
    details_html = ""
    for grp, (ico, name) in group_labels.items():
        details = group_details.get(grp, {})
        rationale = group_rationale.get(grp, "")
        g_data = group_scores.get(grp, {})
        raw = g_data.get("raw_score", 50)
        color = _color_for_score(raw)

        rows_html = ""
        for k, v in details.items():
            rows_html += f"<tr><td class=\"var-col\">{t(k.replace('_', ' ').title())}</td><td>{str(v)}</td></tr>"

        details_html += f"""
        <div class="section" style="padding:16px;">
          <h3 style="color:{color}; margin-top:0; font-size: 16px;">{ico} {t(name)} — {raw:.1f}/100</h3>
          <table style="margin: 8px 0;">
            <thead><tr><th>{t('Variable / Indicator')}</th><th>{t('Value & Analysis')}</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
          <div class="rationale">{rationale}</div>
        </div>"""
        
    layout_html += details_html + "</div></div>"

    # MLR
    mlr_html = ""
    if mlr_summary is not None and not mlr_summary.empty:
        mlr_rows = ""
        for _, row in mlr_summary.iterrows():
            sign_cls = "badge-ok" if row.get("Sign OK") == "✅" else "badge-fail"
            sig_color = "var(--color-green)" if "***" in str(row.get("Significance","")) else (
                        "var(--color-blue)" if "**" in str(row.get("Significance","")) else (
                        "var(--color-amber)" if "*" in str(row.get("Significance","")) else "var(--text-muted)"))
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
          <h2>📐 {t('Multiple Linear Regression (MLR) Results', 'Kết quả Hồi quy Đa biến (MLR)')}</h2>
          <p style="color:var(--text-muted); font-size:13px; font-family:monospace; background:var(--bg-primary); padding:10px; border-radius:6px;">
            R_VNI = α + β₁·ΔVN1Y + β₂·ΔDXY + β₃·NFF + β₄·Z(PE) + β₅·ΔMrg + β₆·ΔUS10Y + β₇·ΔUSD/JPY + ε
          </p>
          <table>
            <thead><tr>
              <th>{t('Variable')}</th><th>Beta (β)</th><th>P-value</th>
              <th>{t('Sign Expected')}</th><th>{t('Sign Actual')}</th><th>{t('Sign OK')}</th>
            </tr></thead>
            <tbody>{mlr_rows}</tbody>
          </table>
        </div>"""

    # Score History Chart.js Data
    history_html = ""
    if score_history is not None and len(score_history) > 1:
        score_history = score_history.sort_values("quarter").reset_index(drop=True)
        qtrs = score_history["quarter"].tolist()
        scores_list = score_history["total_score"].tolist()
        
        chart_js_data += f"""
        <script>
          window.chartDataLine = {{
            labels: {json.dumps(qtrs)},
            datasets: [{{
              label: 'Total Score',
              data: {json.dumps(scores_list)},
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              borderWidth: 3,
              pointBackgroundColor: '#3b82f6',
              pointBorderColor: '#fff',
              pointRadius: 5,
              pointHoverRadius: 7,
              fill: true,
              tension: 0.3
            }}]
          }};
        </script>
        """
        
        history_html = f"""
        <div class="section">
          <h2>📈 {t('Historical Score Trend', 'Lịch sử Điểm số Theo Quý')}</h2>
          <div class="chart-container" style="height: 300px;">
            <canvas id="lineChart"></canvas>
          </div>
        </div>"""

    # Recommendation
    rec_html = f"""
    <div class="section" style="border-color:{score_color};">
      <h2>{emoji} {t('Investment Recommendation', 'Khuyến nghị Đầu tư')} — {quarter}</h2>
      <h3 style="color:{score_color};">{label}: {desc}</h3>
      <div class="rationale">
        {t('This is a quantitative analysis report. Please combine with fundamental analysis and your risk tolerance before making investment decisions.', 'Đây là báo cáo phân tích định lượng. Vui lòng kết hợp với phân tích cơ bản và mức độ chịu đựng rủi ro cá nhân trước khi ra quyết định đầu tư.')}
      </div>
    </div>"""

    # Interpretation of Results
    interpretation_html = f"""
    <div class="section">
      <h2>🧠 {t('Interpretation of Results & Methodology', 'Diễn giải Kết quả & Phương pháp luận')}</h2>
      
      <h3 style="margin-top: 16px; color: var(--color-blue);">{t('1. Composite Scoring System (0-100)', '1. Hệ thống Chấm điểm Tổng hợp (0-100)')}</h3>
      <p style="font-size: 14px; line-height: 1.6; color: var(--text-muted);">
        {t('The model evaluates the VN-Index across 6 fundamental and quantitative pillars. Each pillar is assigned a specific weight based on empirical backtesting: <strong>Macro & Monetary (25%)</strong>, <strong>Valuation & Leverage (20%)</strong>, <strong>Global Intermarket (20%)</strong>, <strong>Quant Model (15%)</strong>, <strong>Machine Learning (10%)</strong>, and <strong>Market Structure (10%)</strong>. A score closer to 100 indicates a highly favorable environment for equities, while a score near 0 suggests extreme risk.', 'Mô hình đánh giá VN-Index qua 6 trụ cột cơ bản và định lượng. Mỗi trụ cột được gán trọng số dựa trên kiểm định lịch sử: <strong>Vĩ mô & Tiền tệ (25%)</strong>, <strong>Định giá & Đòn bẩy (20%)</strong>, <strong>Liên thị trường (20%)</strong>, <strong>Mô hình Định lượng (15%)</strong>, <strong>Machine Learning (10%)</strong>, và <strong>Cấu trúc Thị trường (10%)</strong>. Điểm gần 100 cho thấy môi trường rất thuận lợi cho cổ phiếu, trong khi điểm gần 0 cảnh báo rủi ro cực đại.')}
      </p>

      <h3 style="margin-top: 16px; color: var(--color-blue);">{t('2. Econometric Models', '2. Mô hình Kinh tế lượng')}</h3>
      <ul style="font-size: 14px; line-height: 1.6; color: var(--text-muted); padding-left: 20px;">
        <li><strong>{t('Multiple Linear Regression (MLR)', 'Hồi quy Đa biến (MLR)')}:</strong> {t('Predicts the next quarter return by regressing it against macro variables (DXY, US10Y, VN1Y Yield, etc.). We use Newey-West HAC robust standard errors to correct for heteroskedasticity and autocorrelation, ensuring reliable Beta coefficients.', 'Dự báo lợi suất quý tiếp theo dựa trên các biến vĩ mô (DXY, US10Y, Lợi suất VN1Y...). Mô hình sử dụng sai số chuẩn mạnh Newey-West HAC để khắc phục hiện tượng phương sai thay đổi và tự tương quan, đảm bảo hệ số Beta đáng tin cậy.')}</li>
        <li><strong>{t('Vector Autoregression (VAR)', 'Tự hồi quy Vectơ (VAR)')}:</strong> {t("Analyzes the dynamic impact of macro shocks over time. It utilizes Granger Causality Tests to determine if variables like DXY lead the VN-Index, and Impulse Response Functions (IRF) to simulate the market reaction to external shocks.", "Phân tích tác động động lượng của các cú sốc vĩ mô qua thời gian. Mô hình dùng Kiểm định Nhân quả Granger để xác định xem các biến như DXY có dẫn dắt VN-Index hay không, và Hàm phản ứng xung (IRF) để mô phỏng phản ứng của thị trường trước cú sốc bên ngoài.")}</li>
      </ul>

      <h3 style="margin-top: 16px; color: var(--color-blue);">{t('3. Machine Learning & Reliability', '3. Học máy & Độ tin cậy')}</h3>
      <p style="font-size: 14px; line-height: 1.6; color: var(--text-muted);">
        {t('The system incorporates an <strong>XGBoost / Random Forest Classifier</strong> to predict market trends (UP, DOWN, SIDEWAY). To eliminate <em>look-ahead bias</em> (peeking into the future), we strictly employ <strong>Walk-Forward Validation (WFV)</strong> with an expanding window. This means the model is only trained on historical data up to a specific point and tested on unseen future data, mirroring real-world trading conditions.', 'Hệ thống sử dụng bộ phân loại <strong>XGBoost / Random Forest</strong> để dự báo xu hướng (UP, DOWN, SIDEWAY). Để loại bỏ hoàn toàn <em>thành kiến nhìn trước (look-ahead bias)</em>, chúng tôi áp dụng nghiêm ngặt <strong>Kiểm định Trượt (Walk-Forward Validation)</strong> với cửa sổ mở rộng. Điều này đảm bảo mô hình chỉ học từ dữ liệu quá khứ và dự báo trên dữ liệu tương lai chưa từng thấy, phản ánh đúng điều kiện giao dịch thực tế.')}
      </p>

      <h3 style="margin-top: 16px; color: var(--color-blue);">{t('4. Asset Allocation Recommendations', '4. Khuyến nghị Phân bổ Tài sản')}</h3>
      <p style="font-size: 14px; line-height: 1.6; color: var(--text-muted);">
        {t('Based on the composite score, the model outputs 5 strategic recommendations:', 'Dựa trên điểm số tổng hợp, mô hình đưa ra 5 mức khuyến nghị chiến lược:')}
        <br>• <strong>80-100:</strong> {t('Strong Buy (85-100% Equities)', 'Rất hấp dẫn (85-100% Cổ phiếu)')}
        <br>• <strong>65-79:</strong> {t('Accumulate (70-85% Equities)', 'Hấp dẫn / Tích lũy (70-85% Cổ phiếu)')}
        <br>• <strong>50-64:</strong> {t('Neutral (40-60% Equities)', 'Trung lập (40-60% Cổ phiếu)')}
        <br>• <strong>35-49:</strong> {t('Reduce (20-40% Equities)', 'Kém hấp dẫn / Giảm tỷ trọng (20-40% Cổ phiếu)')}
        <br>• <strong>0-34:</strong> {t('Defensive (0-20% Equities)', 'Phòng thủ / Tiền mặt (0-20% Cổ phiếu)')}
      </p>
    </div>
    """

    # Full HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VN-Index Quant Score {quarter}</title>
  {_HTML_STYLE}
</head>
<body>
  {navbar}
  <div class="page-wrapper">
    <div class="sidebar">
      <ul>
        <li class="tab-link active" onclick="openTab(event, 'tab-overview')">
           🏠 {t('Overview', 'Tổng Quan')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-pillars')">
           🧩 {t('Pillars Analysis', 'Phân Rã Điểm Số')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-models')">
           📐 {t('Econometric Models', 'Mô hình Kinh tế lượng')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-history')">
           📈 {t('Score History', 'Lịch sử Điểm số')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-methodology')">
           🧠 {t('Methodology', 'Phương pháp luận')}
        </li>
      </ul>
    </div>
    
    <div class="main-content">
      <h1>📊 {t('VN-Index Quantitative Scoring Model', 'Hệ thống Chấm điểm Định lượng VN-Index')}
        <span class="report-badge" style="font-size:18px; color:var(--text-muted); font-weight:400; margin-left: 10px;">{quarter} Report</span>
      </h1>
      {chart_js_data}
      
      <div id="tab-overview" class="tab-content active">
        {hero_html}
        {cards_html}
        {rec_html}
      </div>
      
      <div id="tab-pillars" class="tab-content">
        {layout_html}
      </div>
      
      <div id="tab-models" class="tab-content">
        {mlr_html}
      </div>
      
      <div id="tab-history" class="tab-content">
        {history_html}
      </div>
      
      <div id="tab-methodology" class="tab-content">
        {interpretation_html}
      </div>

      <div class="disclaimer">
        <strong>Disclaimer:</strong> {t('Generated by VN_Index_Scoring_Quarterly_Quant_Model v1.0.0. For research purposes only. Not financial advice.', 'Báo cáo được tạo tự động bởi hệ thống định lượng. Phục vụ mục đích nghiên cứu và tham khảo. Không phải khuyến nghị đầu tư.')}<br>
        Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
      </div>
    </div>
  </div>
  {_JS_SCRIPT}
  <script>
    // Trigger charts on load
    document.addEventListener("DOMContentLoaded", () => {{
      if (typeof renderCharts === 'function') renderCharts();
    }});
  </script>
</body>
</html>"""

    qtr_dir = REPORTS_DIR / quarter.replace("-", "_")
    qtr_dir.mkdir(parents=True, exist_ok=True)
    out_path = qtr_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"[REPORT] HTML report → {out_path}")
    
    build_root_index_html()
    
    return out_path


def build_root_index_html():
    reports = []
    for d in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "index.html").exists():
            reports.append(d.name)
            
    links_html = ""
    for r in reports:
        links_html += f'      <li><a href="{r}/index.html">📄 {t("Report", "Báo cáo")} {r.replace("_", "/")}</a></li>\n'
        
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VN-Index Quantitative Reports</title>
  <style>
    body {{ font-family: 'Inter', 'Segoe UI', Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 0; transition: background 0.3s, color 0.3s; }}
    body.dark-mode {{ background: #0f172a; color: #e2e8f0; }}
    
    .navbar {{ background: #ffffff; padding: 15px 30px; display: flex; justify-content: flex-end; border-bottom: 1px solid #e2e8f0; }}
    body.dark-mode .navbar {{ background: #1e293b; border-color: #334155; }}
    
    .btn {{ cursor: pointer; padding: 6px 12px; border-radius: 6px; border: 1px solid #e2e8f0; background: #f8fafc; color: #0f172a; font-size: 14px; font-weight: 600; margin-left:10px; }}
    body.dark-mode .btn {{ border-color: #334155; background: #0f172a; color: #e2e8f0; }}
    
    .container {{ max-width: 800px; margin: 40px auto; background: #ffffff; padding: 40px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
    body.dark-mode .container {{ background: #1e293b; border-color: #334155; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5); }}
    
    h1 {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; margin-top:0; }}
    body.dark-mode h1 {{ border-color: #334155; }}
    
    ul {{ list-style-type: none; padding: 0; }}
    li {{ margin: 15px 0; padding: 15px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; transition: transform 0.2s, border-color 0.2s; }}
    body.dark-mode li {{ background: #0f172a; border-color: #334155; }}
    
    li:hover {{ transform: translateX(5px); border-color: #3b82f6; }}
    a {{ color: #2563eb; text-decoration: none; font-size: 18px; font-weight: 600; display:block; }}
    body.dark-mode a {{ color: #60a5fa; }}
    
    .lang-vi {{ display: none; }}
    body.lang-vi-active .lang-vi {{ display: inline; }}
    body.lang-vi-active .lang-en {{ display: none; }}
  </style>
</head>
<body>
  <div class="navbar">
    <button class="btn" id="lang-btn">🇻🇳 VI</button>
    <button class="btn" id="theme-btn">🌙 Dark</button>
  </div>
  <div class="container">
    <h1>📊 {t("VN-Index Quantitative Reports", "Hệ thống Báo cáo Định lượng VN-Index")}</h1>
    <p style="color: #64748b; font-size: 15px;">{t("List of automatically generated quantitative reports:", "Danh sách các báo cáo định lượng được tạo tự động:")}</p>
    <ul>
{links_html}    </ul>
  </div>
  <script>
    const themeBtn = document.getElementById('theme-btn');
    themeBtn.addEventListener('click', () => {{
      document.body.classList.toggle('dark-mode');
      const isDark = document.body.classList.contains('dark-mode');
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
      themeBtn.innerHTML = isDark ? '☀️ Light' : '🌙 Dark';
    }});
    if (localStorage.getItem('theme') === 'dark') {{
      document.body.classList.add('dark-mode');
      themeBtn.innerHTML = '☀️ Light';
    }}

    const langBtn = document.getElementById('lang-btn');
    langBtn.addEventListener('click', () => {{
      document.body.classList.toggle('lang-vi-active');
      const isVi = document.body.classList.contains('lang-vi-active');
      localStorage.setItem('lang', isVi ? 'vi' : 'en');
      langBtn.innerHTML = isVi ? '🇬🇧 EN' : '🇻🇳 VI';
    }});
    if (localStorage.getItem('lang') === 'vi') {{
      document.body.classList.add('lang-vi-active');
      langBtn.innerHTML = '🇬🇧 EN';
    }}
  </script>
</body>
</html>"""
    
    out_path = REPORTS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"[REPORT] Root Index updated → {out_path}")
