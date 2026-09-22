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
    logger.info(f"[REPORT] JSON exported -> {out_path}")
    return out_path


_HTML_STYLE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    --bg-primary: #f8fafc;
    --bg-card: rgba(255, 255, 255, 0.85);
    --text-main: #0f172a;
    --text-muted: #475569;
    --border-color: rgba(226, 232, 240, 0.8);
    --hero-bg: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(241,245,249,0.9) 100%);
    --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
    
    --color-green: #10b981;
    --color-blue: #3b82f6;
    --color-amber: #f59e0b;
    --color-orange: #f97316;
    --color-red: #ef4444;
    --badge-ok-bg: rgba(16, 185, 129, 0.15);
    --badge-ok-text: #059669;
    --badge-fail-bg: rgba(239, 68, 68, 0.15);
    --badge-fail-text: #b91c1c;
    
    --blur-effect: blur(12px);
  }
  body.dark-mode {
    --bg-primary: #0f172a;
    --bg-card: rgba(30, 41, 59, 0.75);
    --text-main: #f1f5f9;
    --text-muted: #94a3b8;
    --border-color: rgba(51, 65, 85, 0.8);
    --hero-bg: linear-gradient(135deg, rgba(30,41,59,0.9) 0%, rgba(15,23,42,0.9) 100%);
    --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    
    --color-green: #34d399;
    --color-blue: #60a5fa;
    --color-amber: #fbbf24;
    --color-orange: #fb923c;
    --color-red: #f87171;
    --badge-ok-bg: rgba(16, 185, 129, 0.2);
    --badge-ok-text: #6ee7b7;
    --badge-fail-bg: rgba(239, 68, 68, 0.2);
    --badge-fail-text: #fca5a5;
  }
  
  * { box-sizing: border-box; transition: background-color 0.4s ease, color 0.4s ease; }
  body { font-family: 'Outfit', sans-serif; background: var(--bg-primary); color: var(--text-main); margin: 0; padding: 0; line-height: 1.6; }
  
  /* Navbar */
  .navbar { background: var(--bg-card); backdrop-filter: var(--blur-effect); -webkit-backdrop-filter: var(--blur-effect); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
  .nav-left { display: flex; align-items: center; gap: 20px; }
  .clock { font-size: 14px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: var(--color-blue); background: var(--bg-primary); padding: 6px 14px; border-radius: 8px; border: 1px solid var(--border-color); letter-spacing: 0.5px; }
  .nav-right { display: flex; gap: 12px; }
  .btn { cursor: pointer; padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-main); font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.02); transition: all 0.2s ease; }
  .btn:hover { background: var(--bg-primary); transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.05); }

  .page-wrapper { max-width: 1350px; margin: 40px auto; padding: 0 24px; display: flex; gap: 35px; align-items: flex-start; }
  .sidebar { width: 260px; flex-shrink: 0; position: sticky; top: 90px; background: var(--bg-card); backdrop-filter: var(--blur-effect); -webkit-backdrop-filter: var(--blur-effect); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px 0; box-shadow: var(--card-shadow); }
  .sidebar ul { list-style: none; padding: 0; margin: 0; }
  .sidebar li { padding: 14px 24px; cursor: pointer; font-size: 15px; font-weight: 500; border-left: 4px solid transparent; color: var(--text-muted); transition: all 0.25s ease; display: flex; align-items: center; gap: 12px; margin: 4px 12px; border-radius: 8px; }
  .sidebar li:hover { background: var(--bg-primary); color: var(--text-main); transform: translateX(4px); }
  .sidebar li.active { background: rgba(59, 130, 246, 0.1); color: var(--color-blue); border-left: 4px solid transparent; }
  .main-content { flex-grow: 1; min-width: 0; }
  
  .tab-content { display: none; animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
  .tab-content.active { display: block; }
  @keyframes slideUp { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }

  h1 { color: var(--text-main); border-bottom: 2px solid var(--border-color); padding-bottom: 16px; margin-top: 0; font-weight: 700; font-size: 28px; }
  h2 { color: var(--text-main); margin-top: 0; margin-bottom: 24px; font-weight: 600; font-size: 22px; }
  
  .hero { background: var(--hero-bg); backdrop-filter: var(--blur-effect); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 40px; margin-bottom: 30px; text-align: center; box-shadow: var(--card-shadow); position: relative; overflow: hidden; }
  .hero::before { content: ""; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(59,130,246,0.05) 0%, transparent 60%); z-index: -1; pointer-events: none; }
  .score-big { font-size: 84px; font-weight: 800; line-height: 1; text-shadow: 0 4px 15px rgba(0,0,0,0.08); background: linear-gradient(90deg, var(--color-blue), #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .score-label { font-size: 24px; font-weight: 600; margin-top: 12px; }
  .score-desc  { color: var(--text-muted); margin-top: 8px; font-size: 16px; max-width: 600px; margin-left: auto; margin-right: auto; }
  
  .progress-bar { background: rgba(0,0,0,0.05); border-radius: 8px; height: 10px; margin: 12px 0 6px 0; overflow: hidden; box-shadow: inset 0 1px 3px rgba(0,0,0,0.1); }
  body.dark-mode .progress-bar { background: rgba(255,255,255,0.05); }
  .progress-fill { height: 100%; border-radius: 8px; transition: width 1s ease-out; position: relative; overflow: hidden; }
  .progress-fill::after { content: ''; position: absolute; top: 0; left: 0; bottom: 0; right: 0; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent); transform: translateX(-100%); animation: shimmer 2s infinite; }
  @keyframes shimmer { 100% { transform: translateX(100%); } }
  
  .grid-6 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin: 24px 0; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
  
  .card { background: var(--bg-card); backdrop-filter: var(--blur-effect); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px; box-shadow: var(--card-shadow); transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
  .card:hover { transform: translateY(-4px); box-shadow: 0 12px 30px -8px rgba(0,0,0,0.15); border-color: rgba(59,130,246,0.3); }
  .card-title { font-size: 14px; color: var(--text-muted); margin-bottom: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .card-value { font-size: 28px; font-weight: 700; }
  .card-detail { font-size: 14px; color: var(--text-muted); margin-top: 8px; }
  
  .section { background: var(--bg-card); backdrop-filter: var(--blur-effect); border: 1px solid var(--border-color); border-radius: 16px; padding: 30px; margin-bottom: 30px; box-shadow: var(--card-shadow); overflow: hidden; }
  
  .table-responsive { width: 100%; overflow-x: auto; border-radius: 12px; border: 1px solid var(--border-color); }
  table { width: 100%; border-collapse: collapse; margin: 0; background: var(--bg-card); }
  th { background: rgba(59,130,246,0.05); color: var(--text-main); padding: 16px; text-align: left; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid var(--border-color); position: sticky; top: 0; backdrop-filter: blur(4px); }
  td { padding: 16px; font-size: 15px; border-bottom: 1px solid var(--border-color); font-weight: 400; }
  tr { transition: background-color 0.2s; }
  tr:nth-child(even) { background-color: rgba(0,0,0,0.015); }
  body.dark-mode tr:nth-child(even) { background-color: rgba(255,255,255,0.02); }
  tr:hover { background-color: rgba(59,130,246,0.05) !important; }
  
  .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; letter-spacing: 0.3px; }
  .badge-ok     { background: var(--badge-ok-bg); color: var(--badge-ok-text); }
  .badge-fail   { background: var(--badge-fail-bg); color: var(--badge-fail-text); }
  .leading-badge { background: linear-gradient(135deg, var(--color-blue), #8b5cf6); color: #fff; padding: 4px 12px; border-radius: 8px; font-size: 12px; margin-left: 8px; font-weight: 600; box-shadow: 0 2px 4px rgba(59,130,246,0.2); }
  .report-badge { display: inline-block; white-space: nowrap; }
  
  .math-formula { font-size: 15px; font-weight: 600; font-family: 'JetBrains Mono', monospace; background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(139,92,246,0.08)); padding: 16px 18px; border-radius: 12px; border: 1px solid rgba(59,130,246,0.15); border-left: 6px solid var(--color-blue); margin-bottom: 24px; overflow-x: auto; box-shadow: 0 8px 20px -6px rgba(59,130,246,0.15); color: #1e3a8a; letter-spacing: -0.2px; white-space: nowrap; }
  body.dark-mode .math-formula { color: #93c5fd; border-color: rgba(59,130,246,0.25); background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(139,92,246,0.15)); }
  
  .rationale { color: var(--text-muted); font-style: normal; font-size: 14px; border-left: 3px solid var(--color-amber); padding-left: 16px; margin-top: 16px; background: rgba(245,158,11,0.05); padding: 12px 16px; border-radius: 0 8px 8px 0; }
  .disclaimer { color: var(--text-muted); font-size: 13px; margin-top: 50px; border-top: 1px solid var(--border-color); padding-top: 30px; text-align: center; padding-bottom: 40px; opacity: 0.8; }
  
  .lang-vi { display: none; }
  body.lang-vi-active .lang-vi { display: inline; }
  body.lang-vi-active .lang-en { display: none; }
  
  .chart-container { position: sticky; top: 1.5rem; align-self: flex-start; height: 380px; width: 100%; display: flex; justify-content: center; }
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
        <button class="btn" id="prev-quarter-btn" title="Previous Quarter" style="padding: 6px 10px;">◀</button>
        <select class="btn" id="quarter-select" style="max-width: 150px; cursor: pointer;"></select>
        <button class="btn" id="next-quarter-btn" title="Next Quarter" style="padding: 6px 10px;">▶</button>
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
            k_display = k.replace('_', ' ').title()
            acronyms = [
                ("Vn1Y", "VN1Y"), ("Usd", "USD"), ("Vnd", "VND"), ("Dxy", "DXY"), 
                ("Us10Y", "US10Y"), ("Jpy", "JPY"), ("Pe", "P/E"), ("Pb", "P/B"), 
                ("Mlr", "MLR"), ("Var", "VAR"), ("R2", "R²"), ("Fdi", "FDI"), 
                ("Ftse", "FTSE"), ("Adtv", "ADTV"), ("Eyg", "EYG"), ("Omo", "OMO"), 
                ("Vni", "VNI"), ("Zscore", "Z-Score"),
                ("Ir Trend", "IR Trend"), ("Vn Bonds", "VN Bonds"), ("USD VND", "USD/VND")
            ]
            for old, new in acronyms:
                k_display = k_display.replace(old, new)
                
            import re
            val_text = str(v)
            is_missing = False
            
            if val_text.startswith("<MISSING>"):
                is_missing = True
                val_text = val_text.replace("<MISSING>", "").strip()
                val_text = re.sub(r"^(?:N/A\s*)+", "", val_text).strip()
                val_text = re.sub(r"^(?:→|->)\s*", "", val_text).strip()
                if val_text.startswith("default"):
                    val_text = val_text.replace("default", t("Default neutral", "Mặc định trung lập")).strip()

            score_match = re.search(r"(?:→|->)\s*(?:score|default)\s*([\d\.]+)", val_text)
            score_val = None
            if score_match:
                score_val = float(score_match.group(1))
                val_text = val_text[:score_match.start()].strip()
                if val_text.endswith("|"): val_text = val_text[:-1].strip()

            if is_missing and not val_text:
                val_text = t("Default neutral", "Mặc định trung lập")
            elif is_missing and "50" in val_text:
                val_text = val_text.replace(" 50", "").strip()

            if "|" in val_text:
                parts = [p.strip() for p in val_text.split("|") if p.strip()]
                val_text_html = "<ul style='margin:0; padding-left:20px; color:var(--text-muted); font-size: 14px;'>"
                for p in parts:
                    if ":" in p:
                        lbl, val = p.split(":", 1)
                        val_text_html += f"<li style='margin-bottom:4px;'><span style='color:var(--text-main); font-weight:600;'>{lbl}:</span> {val}</li>"
                    else:
                        val_text_html += f"<li style='margin-bottom:4px;'>{p}</li>"
                val_text_html += "</ul>"
            else:
                val_text_html = val_text

            # Create score badge
            def get_score_badge(s):
                if s is None:
                    return '<span class="badge" style="background:#94a3b8; color:#fff; display:inline-block; width:100%; text-align:center;">N/A</span>'
                if s <= 34: bg = "#ef4444"       # Red
                elif s <= 49: bg = "#f59e0b"     # Orange
                elif s <= 64: bg = "#eab308"     # Yellow
                elif s <= 79: bg = "#84cc16"     # Light Green
                else: bg = "#16a34a"             # Dark Green
                return f'<span class="badge" style="background:{bg}; color:#fff; display:inline-block; width:100%; text-align:center;">{s:.0f}</span>'

            score_badge_html = get_score_badge(score_val)

            if is_missing:
                val_text_html = f"<span class=\"badge badge-fail\" style=\"background:#94a3b8; color:#fff; margin-bottom: 4px;\">N/A</span> {val_text_html}"

            rows_html += f"<tr><td class=\"var-col\">{t(k_display)}</td><td>{val_text_html}</td><td style='width: 70px; vertical-align: middle;'>{score_badge_html}</td></tr>"

        details_html += f"""
        <div class="section" style="padding:16px;">
          <h3 style="color:{color}; margin-top:0; font-size: 16px;">{ico} {t(name)} — {raw:.1f}/100</h3>
          <table style="margin: 8px 0;">
            <thead><tr><th>{t('Variable / Indicator')}</th><th>{t('Value & Analysis')}</th><th style="width: 70px; text-align: center;">{t('Score')}</th></tr></thead>
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
          <div class="math-formula">
            R_VNI = α + β₁·ΔVN1Y + β₂·ΔDXY + β₃·NFF + β₄·Z(PE) + β₅·ΔMrg + β₆·ΔUS10Y + β₇·ΔUSD/JPY + ε
          </div>
          <div class="table-responsive">
          <table>
            <thead><tr>
              <th>{t('Variable')}</th><th>Beta (β)</th><th>P-value</th>
              <th>{t('Sign Expected')}</th><th>{t('Sign Actual')}</th><th>{t('Sign OK')}</th>
            </tr></thead>
            <tbody>{mlr_rows}</tbody>
          </table>
          </div>
        </div>"""

    # VAR Granger Causality
    var_granger_html = ""
    if granger_df is not None and not granger_df.empty:
        var_rows = ""
        for _, row in granger_df.iterrows():
            var_rows += f"""<tr>
              <td>{row['causing_variable']}</td>
              <td style="font-weight:700;">{row['test_statistic']}</td>
              <td style="color:{'var(--color-green)' if row['granger_causes_vni'] else 'var(--text-muted)'};">{row['p_value']} {row.get('significance', '')}</td>
              <td><span class="badge {'badge-ok' if row['granger_causes_vni'] else 'badge-fail'}">{"✅ Yes" if row['granger_causes_vni'] else "❌ No"}</span></td>
            </tr>"""
            
        var_granger_html = f"""
        <div class="section">
          <h2>🔮 {t('VAR Granger Causality Tests', 'Kiểm định VAR Granger Causality')}</h2>
          <p style="color:var(--text-muted); font-size:14px; margin-bottom:15px; opacity:0.9;">
            {t('H₀: Variable does not Granger-cause VNI_Return. If p-value < 0.05, we reject H₀ (i.e. the variable leads the VN-Index).', 'H₀: Biến số không tác động nhân quả (Granger) lên lợi suất VNI. Nếu p-value < 0.05, bác bỏ H₀ (tức là biến có tính dẫn dắt VN-Index).')}
          </p>
          <div class="table-responsive">
          <table>
            <thead><tr>
              <th>{t('Variable', 'Biến số')}</th><th>{t('F-Statistic', 'Thống kê F')}</th><th>P-value</th>
              <th>{t('Causes VNI?', 'Dẫn dắt VNI?')}</th>
            </tr></thead>
            <tbody>{var_rows}</tbody>
          </table>
          </div>
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

    glossary_rows = f"""
    <tr><td><code>delta_vn1y_yield</code></td><td style="font-weight:bold;">Δ VN1Y Yield</td><td>-</td><td>{t('Change in VN1Y Yield. Higher yields increase borrowing costs, pressure equity valuations.', 'Thay đổi lợi suất trái phiếu chính phủ VN 1 năm. Lợi suất tăng làm tăng chi phí đi vay, gây áp lực lên định giá.')}</td></tr>
    <tr><td><code>delta_dxy</code></td><td style="font-weight:bold;">Δ DXY</td><td>-</td><td>{t('Change in US Dollar Index. A strong USD puts pressure on emerging market currencies and foreign flows.', 'Thay đổi chỉ số sức mạnh đồng USD. USD mạnh gây áp lực lên tỷ giá và dòng vốn ngoại.')}</td></tr>
    <tr><td><code>delta_us10y</code></td><td style="font-weight:bold;">Δ US10Y</td><td>-</td><td>{t('Change in US 10-Year Treasury Yield. Global risk-free rate proxy; higher rates reduce global liquidity.', 'Thay đổi lợi suất TPCP Mỹ 10 năm. Đại diện lãi suất phi rủi ro toàn cầu, tăng sẽ hút thanh khoản.')}</td></tr>
    <tr><td><code>delta_usdjpy</code></td><td style="font-weight:bold;">Δ USD/JPY</td><td>+</td><td>{t('Change in USD/JPY. Proxy for Yen carry trade. Higher pair implies risk-on global environment.', 'Thay đổi tỷ giá USD/JPY. Đại diện cho Yen carry trade. Cặp này tăng thường thể hiện khẩu vị rủi ro cao.')}</td></tr>
    <tr><td><code>usd_vnd_pct_change</code></td><td style="font-weight:bold;">USD/VND %</td><td>-</td><td>{t('Change in USD/VND exchange rate. FX pressure negatively impacts foreign capital and central bank policy.', 'Biến động tỷ giá USD/VND. Áp lực tỷ giá tác động tiêu cực đến dòng vốn ngoại và chính sách tiền tệ.')}</td></tr>
    <tr><td><code>pe_zscore</code></td><td style="font-weight:bold;">P/E Z-Score</td><td>-</td><td>{t('P/E Valuation Z-Score. High valuation implies lower forward returns (mean reversion).', 'Z-Score định giá P/E. Định giá quá cao (Z-score dương lớn) thường dẫn đến lợi suất tương lai thấp do mean reversion.')}</td></tr>
    <tr><td><code>rsi_14</code>, <code>macd_hist</code>, <code>bb_pct</code></td><td style="font-weight:bold;">RSI, MACD, BB</td><td>?</td><td>{t('Technical Indicators (Momentum). Captures short-term market momentum and overbought/oversold conditions.', 'Các chỉ báo kỹ thuật. Bắt nhịp đà tăng trưởng ngắn hạn và tình trạng quá mua/quá bán.')}</td></tr>
    <tr><td><code>rvol_20d</code></td><td style="font-weight:bold;">RVOL (20D)</td><td>?</td><td>{t('Relative Volatility (20-day). High volatility often precedes or accompanies market corrections.', 'Độ biến động tương đối 20 ngày. Biến động cao thường đi kèm với các nhịp điều chỉnh của thị trường.')}</td></tr>
    <tr><td><code>drawdown_from_peak</code></td><td style="font-weight:bold;">Drawdown</td><td>?</td><td>{t('Drawdown from recent high. Measures the depth of current correction.', 'Mức sụt giảm từ đỉnh gần nhất. Đo lường mức độ sâu của nhịp điều chỉnh hiện tại.')}</td></tr>
    <tr><td><code>price_vs_ma200</code></td><td style="font-weight:bold;">Price vs MA200</td><td>+</td><td>{t('Distance from 200-day Moving Average. Indicates long-term trend strength.', 'Khoảng cách giá so với đường MA200. Thể hiện sức mạnh xu hướng dài hạn.')}</td></tr>
    <tr><td><code>log_return_lag1</code>, <code>lag5</code></td><td style="font-weight:bold;">Lag Returns</td><td>?</td><td>{t('Historical lag returns. Captures autocorrelation and short-term mean reversion/momentum.', 'Lợi suất trễ trong quá khứ. Nắm bắt tính tự tương quan và quán tính/đảo chiều ngắn hạn.')}</td></tr>
    """

    glossary_html = f"""
    <div id="tab-glossary" class="tab-content">
      <div class="section">
        <h2>📖 {t('Variables Glossary & Rationale', 'Từ điển Biến số & Rationale')}</h2>
        <p style="color:var(--text-muted); font-size:14px; margin-bottom: 20px;">
          {t('Detailed explanation of all variables used in econometric models and scoring engine.', 'Giải thích chi tiết tất cả các biến số được sử dụng trong mô hình kinh tế lượng và hệ thống chấm điểm.')}
        </p>
        <table style="font-size:13px;">
          <thead><tr>
            <th style="width: 15%;">{t('Code', 'Mã biến')}</th>
            <th style="width: 15%;">{t('Variable Name', 'Tên biến')}</th>
            <th style="width: 12%;">{t('Expected Sign', 'Kỳ vọng Dấu')}</th>
            <th>{t('Rationale / Meaning', 'Ý nghĩa & Nguyên nhân')}</th>
          </tr></thead>
          <tbody>{glossary_rows}</tbody>
        </table>
      </div>
    </div>
    """

    investment_rec_html = f"""
    <div id="tab-recommendation" class="tab-content">
      <div class="section">
        <h2>🎯 {{t('Investment Recommendation & Project Evaluation', 'Khuyến nghị Đầu tư & Đánh giá Dự án')}}</h2>
        
        <div class="card" style="margin-bottom: 24px;">
            <h3 style="margin-top: 0; color: var(--color-blue); border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                {{t('Quarterly Investment Recommendation', 'Khuyến nghị Đầu tư theo Quý')}}
            </h3>
            <p><strong>{{t('Current Score', 'Điểm số hiện tại')}}:</strong> <span style="color: {score_color}; font-weight: bold;">{total:.1f} / 100 ({label})</span></p>
            <p style="line-height: 1.6;"><strong>{{t('Recommendation', 'Khuyến nghị')}}:</strong> {{t(
                "Based on the aggregate quantitative score, the current market environment is classified as " + label + ". Investors are advised to align their equity exposure with this regime, utilizing the 'Pillars Analysis' to identify the specific macro or valuation drivers behind this score.",
                f"Dựa trên tổng điểm định lượng, môi trường thị trường hiện tại được phân loại là {label}. Nhà đầu tư được khuyến nghị điều chỉnh tỷ trọng cổ phiếu theo trạng thái này, đồng thời sử dụng 'Phân rã Điểm số' để nhận diện các động lực vĩ mô hoặc định giá cụ thể đứng sau mức điểm này."
            )}}</p>
        </div>

        <div class="card">
            <h3 style="margin-top: 0; color: var(--color-blue); border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                {{t('Project Requirements Evaluation', 'Đánh giá các Yêu cầu của Dự án')}}
            </h3>
            
            <h4 style="color: var(--text-main); margin-bottom: 4px;">1. {{t('Ability to identify the relevant factors', 'Khả năng xác định các yếu tố trọng yếu')}}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{{t(
                "The model successfully identifies and integrates 6 distinct pillars: Macro & Monetary, Global & Intermarket, Valuation & Leverage, Quant Model (VAR/MLR), ML Forecast, and Market Structure. These encompass a holistic view of the forces driving the VN-Index.",
                "Mô hình đã xác định và tích hợp thành công 6 trụ cột khác biệt: Vĩ mô & Tiền tệ, Toàn cầu & Liên thị trường, Định giá & Đòn bẩy, Mô hình Định lượng (VAR/MLR), Dự báo ML và Cấu trúc Thị trường. Các yếu tố này bao quát toàn diện các động lực dẫn dắt VN-Index."
            )}}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">2. {{t('Ability to quantify the impact of each factor', 'Khả năng định lượng tác động của từng yếu tố')}}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{{t(
                "Impact is rigorously quantified using Multiple Linear Regression (MLR) to extract beta coefficients, VAR Granger Causality to prove leading relationships, and a robust Z-scoring mechanism to normalize disparate datasets into a unified 0-100 scale.",
                "Tác động được định lượng chặt chẽ thông qua Hồi quy đa biến (MLR) để trích xuất hệ số Beta, Kiểm định VAR Granger để chứng minh mối quan hệ dẫn dắt, và cơ chế Z-score chuẩn hóa các tập dữ liệu khác biệt về thang điểm 0-100 thống nhất."
            )}}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">3. {{t('Ability to obtain data from any of the sources available to you', 'Khả năng thu thập dữ liệu từ các nguồn khả dụng')}}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{{t(
                "Data acquisition is highly automated and robust, fetching directly from the 'vnstock' API for market data, domestic macro variables, and foreign flows, coupled with standard APIs for global yields and DXY.",
                "Quá trình thu thập dữ liệu được tự động hóa cao và ổn định, lấy trực tiếp từ thư viện 'vnstock' đối với dữ liệu thị trường, vĩ mô trong nước, dòng tiền khối ngoại, kết hợp với các API tiêu chuẩn để lấy lợi suất trái phiếu Mỹ và chỉ số DXY."
            )}}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">4. {{t('Ability to automate the model\\'s scoring in future', 'Khả năng tự động hóa việc chấm điểm của mô hình trong tương lai')}}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{{t(
                "The pipeline is fully automated via 'run_quarterly.py', dynamically computing the current quarter using the datetime module. This ensures the entire process from data fetching to HTML report generation is turnkey and ready for crontab scheduling.",
                "Toàn bộ luồng (pipeline) được tự động hóa hoàn toàn thông qua 'run_quarterly.py', với khả năng tự động tính toán quý hiện hành qua module datetime. Điều này đảm bảo quá trình từ tải dữ liệu đến xuất báo cáo HTML diễn ra liền mạch và sẵn sàng để lập lịch tự động (crontab)."
            )}}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">5. {{t('Back-testing and evaluation of the model\\'s validity', 'Kiểm định (Back-test) và đánh giá tính hợp lệ của mô hình')}}</h4>
            <p class="rationale" style="margin-top: 0;">{{t(
                "Validity is enforced through a Walk-Forward Validation (WFV) approach for the XGBoost ML component, preventing data leakage, alongside rigorous statistical diagnostics (p-values) in the MLR and VAR models to ensure relationships are not spurious.",
                "Tính hợp lệ được đảm bảo thông qua phương pháp Kiểm chứng Tiến bước (Walk-Forward Validation) cho mô hình XGBoost nhằm ngăn ngừa rò rỉ dữ liệu (data leakage), kết hợp với các chẩn đoán thống kê nghiêm ngặt (p-values) trong MLR và VAR để đảm bảo các mối quan hệ không phải là giả mạo."
            )}}</p>
        </div>
      </div>
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
        <li class="tab-link" onclick="openTab(event, 'tab-glossary')">
           📖 {t('Variables Glossary', 'Từ điển Biến số')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-methodology')">
           🧠 {t('Methodology', 'Phương pháp luận')}
        </li>
        <li class="tab-link" onclick="openTab(event, 'tab-recommendation')">
           🎯 {t('Investment Rec', 'Khuyến nghị Đầu tư')}
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
        {var_granger_html}
      </div>
      
      <div id="tab-history" class="tab-content">
        {history_html}
      </div>
      
      {glossary_html}
      
      <div id="tab-methodology" class="tab-content">
        {interpretation_html}
      </div>
      
      {investment_rec_html}

      <div class="disclaimer">
        <strong>Disclaimer:</strong> {t('Generated by VN_Index_Scoring_Quarterly_Quant_Model v1.0.0. For research purposes only. Not financial advice.', 'Báo cáo được tạo tự động bởi hệ thống định lượng. Phục vụ mục đích nghiên cứu và tham khảo. Không phải khuyến nghị đầu tư.')}<br>
        Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
      </div>
    </div>
  </div>
  {_JS_SCRIPT}
  <script>
    // Quarter Navigation Logic
    (async function() {{
      const currentQuarter = "{quarter}";
      const select = document.getElementById("quarter-select");
      const prevBtn = document.getElementById("prev-quarter-btn");
      const nextBtn = document.getElementById("next-quarter-btn");
      
      try {{
        const response = await fetch("../quarters.json");
        if (!response.ok) throw new Error("Failed to fetch quarters.json");
        const quarters = await response.json();
        
        if (!quarters || quarters.length === 0) return;
        
        quarters.forEach(q => {{
          const option = document.createElement("option");
          option.value = q;
          option.textContent = q.replace("_", "/");
          if (q.replace("_", "-") === currentQuarter) {{
            option.selected = true;
          }}
          select.appendChild(option);
        }});
        
        const currentIndex = quarters.findIndex(q => q.replace("_", "-") === currentQuarter);
        
        if (currentIndex === 0) {{
          nextBtn.disabled = true;
          nextBtn.style.opacity = "0.5";
          nextBtn.style.cursor = "not-allowed";
        }}
        if (currentIndex === quarters.length - 1) {{
          prevBtn.disabled = true;
          prevBtn.style.opacity = "0.5";
          prevBtn.style.cursor = "not-allowed";
        }}
        
        const navigateTo = (index) => {{
          if (index >= 0 && index < quarters.length) {{
            window.location.href = "../" + quarters[index] + "/index.html";
          }}
        }};
        
        select.addEventListener("change", (e) => {{
          const target = e.target.value;
          window.location.href = "../" + target + "/index.html";
        }});
        
        prevBtn.addEventListener("click", () => navigateTo(currentIndex + 1));
        nextBtn.addEventListener("click", () => navigateTo(currentIndex - 1));
        
      }} catch (err) {{
        console.error("Quarter navigation error:", err);
      }}
    }})();
  </script>
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
    logger.info(f"[REPORT] HTML report -> {out_path}")
    
    build_root_index_html()
    
    return out_path


def build_root_index_html():
    reports = []
    for d in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "index.html").exists():
            reports.append(d.name)
            
    # Export list of quarters to quarters.json for dynamic navigation
    import json
    quarters_json_path = REPORTS_DIR / "quarters.json"
    with open(quarters_json_path, "w", encoding="utf-8") as f:
        json.dump(reports, f)

    if not reports:
        logger.warning("[REPORT] No quarter reports found to build root index.")
        return

    latest_quarter = reports[0]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="0; url={latest_quarter}/index.html" />
  <title>Redirecting to Latest Quarter...</title>
  <script>
    window.location.replace("{latest_quarter}/index.html");
  </script>
</head>
<body style="font-family: Arial, sans-serif; padding: 40px; text-align: center;">
  <p>Redirecting to the latest report ({latest_quarter.replace("_", "/")})...</p>
  <p>If you are not redirected automatically, please <a href="{latest_quarter}/index.html">click here</a>.</p>
</body>
</html>"""
    
    out_path = REPORTS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"[REPORT] Root Index updated -> {out_path}")
