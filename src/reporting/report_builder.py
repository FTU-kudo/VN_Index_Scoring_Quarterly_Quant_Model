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
from src.utils.config import SCORE_LABELS, SCORE_LABEL_RANGES, get_score_label, MODEL_VERSION

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
    import hashlib
    import subprocess
    config_snapshot = score_record.get("model_config", {})
    config_hash = hashlib.sha256(json.dumps(config_snapshot, sort_keys=True, default=str).encode()).hexdigest()
    scorer_path = Path(__file__).resolve().parents[1] / "scoring" / "quarterly_scorer.py"
    model_hash = hashlib.sha256(scorer_path.read_bytes()).hexdigest()
    payload = {
        "metadata": {
            "quarter":        quarter,
            "generated_at":   datetime.now().isoformat(),
            "model_version":  MODEL_VERSION,
            "git_commit":      __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "status":           "PROVISIONAL" if (score_record.get("quarter") == "2026-Q4" and str(score_record.get("data_as_of", "")) < "2026-09-30") else "FINAL",
            "config_hash":      config_hash,
            "model_hash":       model_hash,
            "data_as_of":       score_record.get("data_as_of"),
            "point_in_time":    score_record.get("point_in_time"),
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

  /* ── Action Panel (Allocation) ─────────────────────────────────────── */
  .action-panel { margin: 20px auto 0 auto; max-width: 640px; padding: 18px 22px; border-radius: 14px; text-align: left; background: rgba(59,130,246,0.06); border: 1px solid rgba(59,130,246,0.22); }
  body.dark-mode .action-panel { background: rgba(59,130,246,0.10); }
  .action-panel-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); margin-bottom: 8px; }
  .alloc-value { font-size: 24px; font-weight: 800; line-height: 1.2; }
  .alloc-sub { font-size: 13px; color: var(--text-muted); margin-top: 2px; }
  .alloc-track { position: relative; margin-top: 16px; padding-top: 8px; }
  .alloc-bands { display: flex; height: 14px; border-radius: 7px; overflow: hidden; }
  .alloc-band { height: 100%; }
  .alloc-marker { position: absolute; top: 0; transform: translateX(-50%); width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-top: 8px solid var(--text-main); }
  .alloc-legend { display: flex; justify-content: space-between; font-size: 10px; color: var(--text-muted); margin-top: 6px; letter-spacing: 0.3px; }

  /* ── Calibrated Action chip (hero) ─────────────────────────────────── */
  .action-chip { display: inline-block; padding: 10px 22px; border-radius: 999px; color: #fff; font-size: 18px; font-weight: 800; letter-spacing: 0.3px; box-shadow: 0 6px 18px -4px rgba(0,0,0,0.35); border: 2px solid rgba(255,255,255,0.35); }

  /* ── Chart series toggle chips (Historical Score Trend) ────────────── */
  .chart-toggle { cursor: pointer; display: inline-flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 600; color: var(--text-muted); padding: 6px 12px; border: 1px solid var(--border-color); border-radius: 999px; background: var(--bg-primary); user-select: none; transition: border-color .15s ease, color .15s ease, background .15s ease; }
  .chart-toggle:hover { border-color: var(--color-blue); }
  .chart-toggle input { width: 15px; height: 15px; cursor: pointer; accent-color: var(--color-blue); margin: 0; }
  .chart-toggle input:checked ~ .chart-name { color: var(--text-main); }
  .chart-toggle input:not(:checked) ~ .chart-swatch { opacity: .35; }
  .chart-swatch { display: inline-block; width: 18px; height: 4px; border-radius: 2px; flex: none; transition: opacity .15s ease; }
  .chart-swatch.dashed { background-image: repeating-linear-gradient(90deg, currentColor 0 5px, transparent 5px 9px); background-color: transparent !important; height: 3px; }

  /* ── Data Coverage Panel ───────────────────────────────────────────── */
  .coverage-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 16px; }
  .coverage-item { padding: 12px 14px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--bg-primary); }
  .coverage-name { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between; gap: 8px; }
  .coverage-count { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-main); white-space: nowrap; }

  /* ── Responsive layout ─────────────────────────────────────────────── */
  @media (max-width: 1100px) {
    .page-wrapper { flex-direction: column; gap: 20px; }
    .sidebar { position: static; width: 100%; padding: 8px; overflow-x: auto; }
    .sidebar ul { display: flex; flex-wrap: nowrap; gap: 4px; }
    .sidebar li { margin: 0; padding: 10px 14px; white-space: nowrap; flex-shrink: 0; border-left: none; }
    .sidebar li:hover { transform: none; }
    .grid-6 { grid-template-columns: repeat(2, 1fr); }
    .grid-2 { grid-template-columns: 1fr; }
  }
  @media (max-width: 720px) {
    .navbar { flex-wrap: wrap; gap: 10px; padding: 12px 16px; }
    .nav-left, .nav-right { flex-wrap: wrap; }
    .clock { display: none; }
    .page-wrapper { margin: 20px auto; padding: 0 12px; }
    .grid-6, .coverage-grid { grid-template-columns: 1fr; }
    .hero { padding: 24px 16px; }
    .score-big { font-size: 56px; }
    .score-label { font-size: 20px; }
    h1 { font-size: 22px; }
    .section { padding: 18px; }
    th, td { padding: 10px; font-size: 13px; }
  }

  /* ── Print styles ──────────────────────────────────────────────────── */
  @media print {
    body { background: #fff !important; color: #000 !important; }
    .navbar, .sidebar, .btn, #quarter-select { display: none !important; }
    .page-wrapper { display: block; margin: 0; padding: 0; max-width: 100%; }
    .main-content { width: 100%; }
    .tab-content { display: block !important; page-break-before: always; }
    #tab-overview { page-break-before: avoid; }
    .card, .section { box-shadow: none !important; break-inside: avoid; border: 1px solid #d1d5db; backdrop-filter: none; -webkit-backdrop-filter: none; }
    .card:hover { transform: none; }
    .hero { box-shadow: none !important; border: 1px solid #d1d5db; backdrop-filter: none; -webkit-backdrop-filter: none; }
    .progress-fill::after { animation: none; display: none; }
    .chart-container { position: static; }
    .score-big { -webkit-text-fill-color: initial; }
    a { text-decoration: none; color: inherit; }
  }
.score-legend { font-size: 12px; color: var(--text-muted); margin: 8px 0 16px; }
  .lang-vi { display:none; } body.vi-mode .lang-en { display:none; } body.vi-mode .lang-vi { display:inline; }
  </style>
"""

_JS_SCRIPT = """
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.1.0/dist/chartjs-plugin-annotation.min.js"></script>
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]
  }
};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<script>
  // Real-time Clock (UTC+7 = Vietnam time, no DST) — clock-face emoji tracks the current hour
  const CLOCK_EMOJIS = ['🕛','🕐','🕑','🕒','🕓','🕔','🕕','🕖','🕗','🕘','🕙','🕚'];
  function vnTimeParts(now) {
    const options = { timeZone: 'Asia/Ho_Chi_Minh', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const text = new Intl.DateTimeFormat('sv-SE', options).format(now); // sv-SE gives ISO-like format YYYY-MM-DD HH:mm:ss
    const hour = parseInt(text.substring(11, 13), 10); // hour of day in Vietnam (0-23)
    return { text: text, emoji: CLOCK_EMOJIS[hour % 12] };
  }
  function updateClock() {
    const p = vnTimeParts(new Date());
    const clockEl = document.getElementById('clock');
    if (clockEl) clockEl.innerText = p.emoji + ' ' + p.text + ' UTC+7';
  }
  setInterval(updateClock, 1000);
  updateClock();

  // "Generated at" — rendered at actual runtime (not hardcoded at build time)
  (function() {
    const p = vnTimeParts(new Date());
    const stamp = p.emoji + ' ' + p.text + ' UTC+7';
    document.querySelectorAll('.js-generated-at').forEach(el => { el.textContent = stamp; });
  })();

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

      // MUTATE SCORE DATASET (raw composite — dashed reference)
      if (window.chartDataLine && window.chartDataLine.datasets && window.chartDataLine.datasets.length > 0) {
          window.chartDataLine.datasets[0].borderWidth = 2;
          window.chartDataLine.datasets[0].pointRadius = 4;
          window.chartDataLine.datasets[0].tension = 0.3;
          window.chartDataLine.datasets[0].order = 2;
          window.chartDataLine.datasets[0].fill = false;
          window.chartDataLine.datasets[0].borderDash = [6, 4];
          window.chartDataLine.datasets[0].label = document.body.classList.contains('lang-vi-active') ? 'Điểm thô (tham chiếu)' : 'Raw Composite (ref)';
          window.chartDataLine.datasets[0].pointBorderColor = '#fff';
      }

      // MUTATE VN-INDEX DATASET (tìm theo label — không phụ thuộc vị trí)
      if (window.chartDataLine && window.chartDataLine.datasets) {
          const vniDs = window.chartDataLine.datasets.find(d => d.label === 'VN-Index');
          if (vniDs) {
              vniDs.borderColor = '#94a3b8';
              vniDs.backgroundColor = 'rgba(148, 163, 184, 0.15)';
              vniDs.borderWidth = 2;
              vniDs.fill = true;
              vniDs.pointRadius = 0;
              vniDs.tension = 0.3;
              vniDs.order = 3;
              vniDs.pointHoverRadius = 4;
              vniDs.yAxisID = 'y1';
          }
      }

      lineChartInstance = new Chart(lineCtx, {
        type: 'line',
        data: window.chartDataLine,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 1000, easing: 'easeOutQuart' },
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: { 
              grid: { display: false }, 
              ticks: { color: 'var(--text-muted)', font: { size: 11 } } 
            },
            y: { 
              type: 'linear', display: true, position: 'left', 
              grid: { display: false }, 
              ticks: { color: textColor }, min: 0, max: 100,
              title: { display: true, text: 'Composite Score (0–100)', color: textColor, font: { weight: 'bold' } }
            },
            y1: { 
              type: 'linear', display: false, position: 'right', 
              grid: { display: false }, 
              ticks: { color: textColor },
              title: { display: true, text: 'VN-Index', color: textColor, font: { weight: 'bold' } }
            }
          },
          plugins: { 
            legend: { 
              display: true, 
              position: 'top', 
              align: 'end',
              onClick: function() { return; },
              labels: { usePointStyle: true, pointStyle: 'circle', font: { size: 12, weight: '600' }, color: textColor, filter: function(item, data) { return !data.datasets[item.datasetIndex].hidden; } }
            },
            tooltip: {
              backgroundColor: document.body.classList.contains('dark-mode') ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)',
              titleColor: document.body.classList.contains('dark-mode') ? '#f1f5f9' : '#0f172a',
              bodyColor: document.body.classList.contains('dark-mode') ? '#f1f5f9' : '#0f172a',
              borderColor: document.body.classList.contains('dark-mode') ? '#334155' : '#e2e8f0',
              borderWidth: 1,
              callbacks: {
                 label: function(context) {
                    const isVi = document.body.classList.contains('lang-vi-active');
                    let label = context.dataset.label || '';
                    if (label) { label += ': '; }
                    if (context.parsed.y !== null) { label += context.parsed.y.toFixed(1); }
                    if (context.datasetIndex === 0 && context.dataset.percentile_label) {
                      const pct = context.dataset.percentile_label[context.dataIndex];
                      const disp = context.dataset.dispersion_level ? context.dataset.dispersion_level[context.dataIndex] : 'N/A';
                      if (pct && pct !== 'N/A') {
                        let pctTrans = pct;
                        if (isVi) {
                           if (pct === 'BUY/ACCUMULATE') pctTrans = 'MUA / TÍCH LŨY';
                           else if (pct === 'REDUCE/SELL') pctTrans = 'GIẢM / BÁN';
                           else if (pct === 'HOLD') pctTrans = 'GIỮ';
                        }
                        let dispTrans = disp;
                        if (isVi) {
                           if (disp === 'HIGH') dispTrans = 'CAO';
                           else if (disp === 'MEDIUM') dispTrans = 'TRUNG BÌNH';
                           else if (disp === 'LOW') dispTrans = 'THẤP';
                        }
                        const pctText = isVi ? 'Phân vị' : 'Percentile';
                        const dispText = isVi ? 'Phân tán' : 'Dispersion';
                        label += ' | ' + pctText + ': ' + pctTrans + ' | ' + dispText + ': ' + dispTrans;
                      }
                    }
                    return label;
                 }
              }
            },
            annotation: {
              annotations: (function() {
                 let annotations = {};
                 if (window.chartDataLine.datasets[0].percentile_label) {
                    let labels = window.chartDataLine.datasets[0].percentile_label;
                    for (let i = 0; i < labels.length; i++) {
                       if (labels[i] === 'REDUCE/SELL') {
                          annotations['box' + i] = {
                             type: 'box',
                             xMin: i - 0.5,
                             xMax: i + 0.5,
                             backgroundColor: 'rgba(239, 68, 68, 0.1)',
                             borderWidth: 0,
                             drawTime: 'beforeDraw'
                          };
                       }
                    }
                 }
                 return annotations;
              })()
            }
          }
        }
      });
    }
  }

  // ── Dataset toggles (checkbox-controlled, read-only chart legend) ─────
  function syncScoreAxis() {
      if (!lineChartInstance) return;
      const raw = lineChartInstance.data.datasets[0];
      const cal = lineChartInstance.data.datasets.find(d => d.label === 'Calibrated Action');
      const anyVisible = (raw && !raw.hidden) || (cal && !cal.hidden);
      lineChartInstance.options.scales.y.display = anyVisible;
  }
  const toggleCal = document.getElementById('toggleCalibrated');
  if (toggleCal) {
      toggleCal.addEventListener('change', function(e) {
          if (lineChartInstance) {
              const calDs = lineChartInstance.data.datasets.find(d => d.label === 'Calibrated Action');
              if (calDs) { calDs.hidden = !e.target.checked; syncScoreAxis(); lineChartInstance.update(); }
          }
      });
  }
  const toggleVN = document.getElementById('toggleVNIndex');
  if (toggleVN) {
      toggleVN.addEventListener('change', function(e) {
          if (lineChartInstance) {
              const vniDs = lineChartInstance.data.datasets.find(d => d.label === 'VN-Index');
              if (vniDs) { vniDs.hidden = !e.target.checked; lineChartInstance.options.scales.y1.display = e.target.checked; lineChartInstance.update(); }
          }
      });
  }
  const toggleCS = document.getElementById('toggleCompositeScore');
  if (toggleCS) {
      toggleCS.addEventListener('change', function(e) {
          if (lineChartInstance) {
              if (lineChartInstance.data.datasets.length > 0) {
                  lineChartInstance.data.datasets[0].hidden = !e.target.checked; syncScoreAxis(); lineChartInstance.update();
              }
          }
      });
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


def _build_percentile_dispersion_html(score_record: dict, t) -> str:
    """
    Tạo HTML hiển thị:
    - Fix #2: Nhãn percentile động (song song với nhãn cố định)
    - Fix #3: Chỉ số độ phân tán giữa 6 pillar
    """
    pct_label     = score_record.get("percentile_label", None)
    pct_p15       = score_record.get("percentile_p15", None)
    pct_p85       = score_record.get("percentile_p85", None)
    disp_level    = score_record.get("dispersion_level", "MEDIUM")
    pillar_std    = score_record.get("pillar_std", None)
    pillar_range  = score_record.get("pillar_range", None)

    # ── Percentile label block ──────────────────────────────────────────────
    if pct_label and pct_p15 is not None:
        pct_color = {
            "BUY/ACCUMULATE": "var(--color-green, #22c55e)",
            "REDUCE/SELL":    "var(--color-red,   #ef4444)",
            "HOLD":           "var(--color-yellow, #eab308)",
        }.get(pct_label, "var(--text-muted)")
        pct_icon = {
            "BUY/ACCUMULATE": "📈",
            "REDUCE/SELL":    "📉",
            "HOLD":           "➡️",
        }.get(pct_label, "➡️")
        pct_vi = {
            "BUY/ACCUMULATE": "MUA / TÍCH LŨY",
            "REDUCE/SELL":    "GIẢM / BÁN",
            "HOLD":           "GIỮ",
        }.get(pct_label, "GIỮ")
        pct_html = f"""
      <div style="margin-top:12px; padding:10px 16px; border-radius:8px;
                  background:color-mix(in srgb, {pct_color} 12%, transparent);
                  border:1px solid color-mix(in srgb, {pct_color} 35%, transparent);">
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">
          {pct_icon} {t('Percentile Signal (Expanding Window)', 'Tín hiệu Phân vị Động')}
          <span style="font-size:11px; opacity:.7;">
            — {t('Top/Bot 15% vs history', 'Top/Đáy 15% so với lịch sử')}
          </span>
        </div>
        <div style="font-size:15px; font-weight:700; color:{pct_color};">
          {pct_icon} {t(pct_label, pct_vi)}
        </div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">
          {t(f'Historical thresholds: BUY ≥ {pct_p85:.1f} | REDUCE ≤ {pct_p15:.1f}',
             f'Ngưỡng lịch sử: MUA ≥ {pct_p85:.1f} | GIẢM ≤ {pct_p15:.1f}')}
        </div>
      </div>"""
    else:
        pct_html = f"""
      <div style="margin-top:12px; padding:8px 16px; border-radius:8px;
                  background:rgba(128,128,128,.1); border:1px solid rgba(128,128,128,.2);
                  font-size:12px; color:var(--text-muted);">
        {t('Percentile Signal: Insufficient history (< 4 quarters)', 
           'Tín hiệu Phân vị: Chưa đủ lịch sử (< 4 quý)')}
      </div>"""

    # ── Dispersion block ────────────────────────────────────────────────────
    if pillar_std is not None:
        disp_color = {
            "HIGH":   "var(--color-orange, #f97316)",
            "MEDIUM": "var(--color-blue,   #3b82f6)",
            "LOW":    "var(--color-green,  #22c55e)",
        }.get(disp_level, "var(--text-muted)")
        disp_icon = {"HIGH": "⚠️", "MEDIUM": "📊", "LOW": "✅"}.get(disp_level, "📊")
        disp_vi   = {"HIGH": "CAO", "MEDIUM": "TRUNG BÌNH", "LOW": "THẤP"}.get(disp_level, "TRUNG BÌNH")
        disp_msg_en = {
            "HIGH":   "Pillars disagree strongly — study Pillars Analysis before acting",
            "MEDIUM": "Moderate disagreement between pillars",
            "LOW":    "Pillars show broad consensus — signal more reliable",
        }.get(disp_level, "")
        disp_msg_vi = {
            "HIGH":   "Các trụ cột đang bất đồng mạnh — xem kỹ Pillars Analysis trước khi hành động",
            "MEDIUM": "Các trụ cột có sự khác biệt ở mức trung bình",
            "LOW":    "Các trụ cột đồng thuận rộng rãi — tín hiệu đáng tin cậy hơn",
        }.get(disp_level, "")
        std_str   = f"{pillar_std:.1f}" if pillar_std is not None else "N/A"
        range_str = f"{pillar_range:.1f}" if pillar_range is not None else "N/A"
        disp_html = f"""
      <div style="margin-top:8px; padding:10px 16px; border-radius:8px;
                  background:color-mix(in srgb, {disp_color} 10%, transparent);
                  border:1px solid color-mix(in srgb, {disp_color} 30%, transparent);">
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">
          {disp_icon} {t('Pillar Dispersion', 'Độ Phân Tán Giữa Các Trụ Cột')}
          <span style="font-size:11px; opacity:.7;">
            (σ={std_str} | range={range_str})
          </span>
        </div>
        <div style="font-size:14px; font-weight:700; color:{disp_color};">
          {disp_icon} {t(disp_level, disp_vi)}
          <span style="font-weight:400; font-size:12px;">
            — {t(disp_msg_en, disp_msg_vi)}
          </span>
        </div>
      </div>"""
    else:
        disp_html = ""

    return pct_html + disp_html


_LABEL_COLORS = {
    "BUY":        "#10b981",
    "ACCUMULATE": "#3b82f6",
    "HOLD":       "#eab308",
    "REDUCE":     "#f97316",
    "SELL":       "#ef4444",
}

_LABEL_VI = {
    "BUY":        "MUA",
    "ACCUMULATE": "TÍCH LŨY",
    "HOLD":       "GIỮ",
    "REDUCE":     "GIẢM",
    "SELL":       "BÁN",
}

_GROUP_LABELS = {
    "macro_monetary":     ("💰", "Macro & Monetary"),
    "global_intermarket": ("🌐", "Global & Intermarket"),
    "valuation_leverage": ("📐", "Valuation & Leverage"),
    "quant_model":        ("📊", "Quant Model"),
    "ml_forecast":        ("🤖", "ML Forecast"),
    "market_structure":   ("🏗️", "Market Structure"),
}


def _build_action_panel_html(score_record: dict, t) -> str:
    """
    Action Panel trong hero: khuyến nghị phân bổ cổ phiếu (equity allocation)
    theo tầng CALIBRATED ACTION SIGNAL (z-score expanding, point-in-time).
    Dải regime 0-100 + marker tại vị trí điểm calibrated; dòng z-diagnostic
    (z, μ_hist, σ_hist, n) minh bạch cách hiệu chỉnh; điểm raw giữ làm tham chiếu.
    """
    # ── Tầng hành động: calibrated (fallback về raw nếu chưa đủ lịch sử) ──────
    cal_total = score_record.get("calibrated_score")
    cal_label = score_record.get("calibrated_label")
    cal_alloc = score_record.get("calibrated_allocation")
    if cal_total is None:
        cal_total = score_record.get("total_score", 50)
        cal_label = score_record.get("label", "HOLD")
        cal_alloc = score_record.get("label_allocation")
    if not cal_alloc:
        _, _, _, cal_alloc = get_score_label(float(cal_total))
    total = float(cal_total)

    raw_total = score_record.get("total_score", 50)
    raw_label = score_record.get("label", "HOLD")

    alloc_vi = cal_alloc.replace("Equities", "Cổ phiếu")

    # Dải 5 regime, xếp từ thấp (SELL) đến cao (BUY)
    bands_html = ""
    legend_html = ""
    for (lo, hi), (lbl, em, desc, alloc) in sorted(SCORE_LABEL_RANGES, key=lambda x: x[0][0]):
        width = hi - lo + 1
        color = _LABEL_COLORS.get(lbl, "#94a3b8")
        active = lo <= total <= hi
        opacity = "1" if active else "0.30"
        bands_html += (
            f'<div class="alloc-band" title="{lbl} ({lo}–{hi}): {alloc}" '
            f'style="width:{width}%; background:{color}; opacity:{opacity};"></div>'
        )
        legend_html += f'<span>{t(lbl, _LABEL_VI.get(lbl, lbl))}</span>'

    marker_pos = max(0.0, min(100.0, float(total)))
    active_color = _LABEL_COLORS.get(cal_label, "#94a3b8")

    # ── Z-diagnostic: minh bạch phép hiệu chỉnh expanding window ─────────────
    applied = bool(score_record.get("calibration_applied"))
    if applied:
        z = score_record.get("calibration_z")
        mu = score_record.get("calibration_hist_mean")
        sd = score_record.get("calibration_hist_std")
        n_hist = score_record.get("calibration_n_history")
        diag_en = (f"z = {z:+.2f} vs {n_hist} prior quarters "
                   f"(μ = {mu:.1f}, σ = {sd:.1f}) — expanding window, point-in-time")
        diag_vi = (f"z = {z:+.2f} so với {n_hist} quý trước "
                   f"(μ = {mu:.1f}, σ = {sd:.1f}) — cửa sổ expanding, point-in-time")
    else:
        diag_en = "Insufficient history (< 4 prior quarters) — calibrated = raw composite"
        diag_vi = "Chưa đủ lịch sử (< 4 quý trước) — calibrated = điểm thô"

    return f"""
      <div class="action-panel">
        <div class="action-panel-title">⚡ {t('Action Panel — Calibrated Allocation', 'Action Panel — Khuyến nghị Phân bổ (Calibrated)')}</div>
        <div class="alloc-value" style="color:{active_color};">{t(cal_alloc, alloc_vi)}</div>
        <div class="alloc-sub">
          {t(f'Action regime: {cal_label} @ calibrated {total:.1f}/100 (raw {raw_total:.1f} → {raw_label}) — thresholds from config.py SCORE_LABELS',
             f'Trạng thái hành động: {cal_label} @ calibrated {total:.1f}/100 (điểm thô {raw_total:.1f} → {raw_label}) — ngưỡng lấy từ config.py SCORE_LABELS')}
        </div>
        <div class="alloc-track">
          <div class="alloc-marker" style="left:{marker_pos}%;" title="{total:.1f}"></div>
          <div class="alloc-bands">{bands_html}</div>
          <div class="alloc-legend">{legend_html}</div>
        </div>
        <div class="alloc-sub" style="margin-top:10px; font-size:11.5px; opacity:.85;">📐 {t(diag_en, diag_vi)}</div>
      </div>"""


def _load_vnindex_quarterly_prices(quarters: List[str]):
    """
    Giá đóng cửa VN-Index theo quý (alignment với danh sách quarters truyền vào).

    Ưu tiên tính từ data/raw/vnindex_ohlcv.parquet (nếu có) và ghi cache
    data/scores/vnindex_quarterly_close.json; fallback đọc cache khi thiếu
    OHLCV gốc (rebuild HTML offline). Trả về list giá float hoặc None.

    Logic này ĐÃ ĐƯỢC TÍCH HỢP thẳng vào report_builder (trước đây nằm ở
    scripts/inject_vnindex_chart.py — post-processing string-replacement
    dễ gãy âm thầm khi template đổi).
    """
    import json as _json
    price_cache_path = Path("data/scores/vnindex_quarterly_close.json")
    ohlcv_path = Path("data/raw/vnindex_ohlcv.parquet")

    if not ohlcv_path.exists():
        if price_cache_path.exists():
            try:
                with open(price_cache_path, "r", encoding="utf-8") as f:
                    cache = _json.load(f)
                return [cache.get(q) for q in quarters]
            except Exception as exc:
                logger.warning(f"[REPORT] Cannot read VN-Index price cache: {exc}")
        logger.warning("[REPORT] No VN-Index OHLCV / price cache — chart overlay skipped")
        return None

    try:
        ohlcv = pd.read_parquet(ohlcv_path)
        ohlcv["date"] = pd.to_datetime(ohlcv["date"])
        ohlcv = ohlcv.sort_values("date")
        max_date = ohlcv["date"].max()

        prices = []
        for q in quarters:
            y, qn = q.split("-Q")
            y, qn = int(y), int(qn)
            m = qn * 3
            d = 31 if m in (3, 12) else 30
            start_date = pd.Timestamp(f"{y}-{m-2:02d}-01")
            end_date = pd.Timestamp(f"{y}-{m:02d}-{d:02d}")
            if max_date < start_date:
                p = None      # quý tương lai
            else:
                valid = ohlcv[(ohlcv["date"] >= start_date) & (ohlcv["date"] <= end_date)]
                if len(valid) > 0:
                    p = round(float(valid.iloc[-1]["close"]), 2)
                else:
                    valid_before = ohlcv[ohlcv["date"] <= end_date]
                    p = round(float(valid_before.iloc[-1]["close"]), 2) if len(valid_before) else None
            prices.append(p)

        # Ghi cache để rebuild offline không mất overlay
        try:
            with open(price_cache_path, "w", encoding="utf-8") as f:
                _json.dump({q: p for q, p in zip(quarters, prices)}, f, indent=1)
        except Exception as exc:
            logger.warning(f"[REPORT] Could not write VN-Index price cache: {exc}")
        return prices
    except Exception as exc:
        logger.warning(f"[REPORT] VN-Index overlay failed: {exc}")
        return None


def _build_data_coverage_html(score_record: dict, t) -> str:
    """Display the 24 required scoring fields, excluding supplemental rows."""
    coverage = score_record.get("data_coverage")
    if not coverage:
        from src.scoring.quarterly_scorer import compute_data_coverage
        coverage = compute_data_coverage(score_record.get("group_details", {}))
    names = {"macro_monetary": ("💰", "Macro & Monetary"), "global_intermarket": ("🌐", "Global & Intermarket"), "valuation_leverage": ("📐", "Valuation & Leverage"), "quant_model": ("📊", "Quant Model"), "ml_forecast": ("🤖", "ML Forecast"), "market_structure": ("🏗️", "Market Structure")}
    items = ""
    for group, info in coverage["by_group"].items():
        ico, name = names[group]
        pct = info["available"] / info["required"] * 100
        missing = ", ".join(info["missing"]) if info["missing"] else "none"
        items += f'<div class="coverage-item"><div class="coverage-name"><span>{ico} {t(name)}</span><span class="coverage-count">{info["available"]}/{info["required"]}</span></div><div class="progress-bar" style="margin:0;height:8px"><div class="progress-fill" style="width:{pct:.0f}%"></div></div><small>{t("Missing", "Thiếu")}: {missing}</small></div>'
    note = t("Required scoring fields only; supplemental ratios, bonuses, counts and audit metadata are excluded.", "Chỉ tính trường chấm điểm bắt buộc; tỷ lệ tham chiếu, bonus, số đếm và metadata audit không nằm trong mẫu số.")
    return f'<div class="section" id="data-coverage"><div style="display:flex;justify-content:space-between;align-items:baseline"><h2>🛰️ {t("Data Coverage", "Độ phủ dữ liệu")}</h2><strong>{coverage["available"]}/{coverage["required"]} ({coverage["percentage"]:.0f}%)</strong></div><div class="progress-bar"><div class="progress-fill"><div class="progress-fill" style="width:{coverage["percentage"]}%"></div></div></div><p style="font-size:13px;color:var(--text-muted)">{note}</p><div class="coverage-grid">{items}</div></div>'


def build_html_report(
    score_record: Dict[str, Any],
    quarter:      str,
    mlr_summary:  Optional[pd.DataFrame] = None,
    granger_df:   Optional[pd.DataFrame] = None,
    wfv_summary:  Optional[Dict] = None,
    fi_df:        Optional[pd.DataFrame] = None,
    score_history: Optional[pd.DataFrame] = None,
) -> Path:
    
    raw_total = float(score_record.get("total_score", 50))
    raw_label = score_record.get("label", "HOLD")
    raw_emoji = score_record.get("emoji", "🟡")
    leading = score_record.get("most_divergent_pillar", score_record.get("leading_indicator", ""))
    date_computed = score_record.get("date_computed", "")
    data_as_of = score_record.get("data_as_of", "")
    publication_status = "PROVISIONAL" if (quarter == "2026-Q4" and str(data_as_of) < "2026-09-30") else "FINAL"

    # ── Tầng 2: Calibrated Action Signal ────────────────────────────────────
    # Điểm thô giữ nguyên làm tầng tham chiếu (hero ghi chú "raw composite");
    # chip nổi bật "HÀNH ĐỘNG" hiển thị nhãn hành động calibrated.
    cal_total = score_record.get("calibrated_score")
    cal_label = score_record.get("calibrated_label")
    cal_emoji = score_record.get("calibrated_emoji", "🟡")
    cal_alloc = score_record.get("calibrated_allocation", "")
    if cal_total is None:
        cal_total, cal_label = raw_total, raw_label
        _, _, _, cal_alloc = get_score_label(float(raw_total))
    cal_total = float(cal_total)
    cal_color = _LABEL_COLORS.get(cal_label, "#94a3b8")
    cal_emoji = score_record.get("calibrated_emoji", get_score_label(cal_total)[1])
    _, _, cal_desc, _ = get_score_label(cal_total)
    total = cal_total
    label = cal_label
    emoji = cal_emoji
    desc = cal_desc
    score_color = cal_color
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
        <a class="btn" id="home-btn" href="../index.html" title="Dashboard Home" style="text-decoration: none;">🏠 <span class="lang-en">Home</span><span class="lang-vi">Trang chủ</span></a>
        <button class="btn" id="prev-quarter-btn" title="Previous Quarter (←)" style="padding: 6px 10px;">◀</button>
        <select class="btn" id="quarter-select" style="max-width: 150px; cursor: pointer;"></select>
        <button class="btn" id="next-quarter-btn" title="Next Quarter (→)" style="padding: 6px 10px;">▶</button>
        <button class="btn" id="print-btn" title="Print / Save as PDF">🖨️</button>
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
        &nbsp;|&nbsp; {t("Data as-of", "Dữ liệu đến")}: {data_as_of} &nbsp;|&nbsp; <strong>{publication_status}</strong>
      </div>
      <div class="score-big" style="color: {score_color};">{total:.1f}</div>
      <div class="score-label" style="color: {score_color};">{emoji} {label}
        <span style="font-size:13px; font-weight:500; opacity:.65;">({t('calibrated action signal', 'tín hiệu hành động hiệu chỉnh')})</span>
      </div>
      <div style="font-size:13px; color:var(--text-muted); margin-top:4px;">
        {t(f'Raw Composite: {raw_total:.1f} — {raw_label}', f'Điểm thô tổng hợp: {raw_total:.1f} — {raw_label}')}
      </div>
      <div class="score-desc">{t(desc)}</div>
      <div style="margin-top: 16px;">
        <span class="action-chip" style="background:{cal_color};"
              title="Calibrated Action Signal — z-score vs prior quarters (expanding, point-in-time) · Tín hiệu hành động hiệu chỉnh — z-score so với các quý trước (point-in-time)">
          <span class="lang-en">⚡ ACTION: {cal_emoji} {cal_label} — {cal_total:.1f}</span><span class="lang-vi">⚡ HÀNH ĐỘNG: {cal_emoji} {cal_label} — {cal_total:.1f}</span><span class="action-chip" style="display:none">⚡ HÀNH ĐỘNG: {cal_emoji} {cal_label} — {cal_total:.1f}</span>
        </span>
        <div style="font-size:12px; color:var(--text-muted); margin-top:6px;">
          {t(f'Calibrated action signal (allocation: {cal_alloc}) — raw composite shown below for reference.',
             f'Tín hiệu hành động hiệu chỉnh (phân bổ: {cal_alloc}) — điểm thô hiển thị bên dưới để tham chiếu.')}
        </div>
      </div>
      <div style="margin-top: 24px; max-width: 500px; margin-left: auto; margin-right: auto;">
        <div class="progress-bar">
          <div class="progress-fill" style="width:{total}%; background:{score_color};"></div>
        </div>
      </div>
      <div style="margin-top: 14px; color: var(--text-muted); font-size: 14px;">
        {t("Leading Indicator", "Nhóm dẫn dắt")}:
        <span class="leading-badge">{t(leading.replace('_', ' ').title())}</span>
      </div>

      {_build_percentile_dispersion_html(score_record, t)}

      {_build_action_panel_html(score_record, t)}
    </div>
    """

    coverage_html = _build_data_coverage_html(score_record, t)

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
        <h3 style="margin-top:0; color: var(--text-muted); font-size:15px; border-bottom:1px solid var(--border-color); padding-bottom:10px;">{t("Pillars Analysis", "Phân rã điểm số")}<p class="score-legend">{t("Legend: colored badge = standalone 0–100 score; — = contextual, bonus, count or audit row; N/A = required source field missing.", "Chú giải: huy hiệu màu = điểm độc lập 0–100; — = dòng tham chiếu, bonus, số đếm hoặc audit; N/A = thiếu trường dữ liệu bắt buộc.")}</p></h3>
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
                ("Vni", "VNI"), ("Zscore", "Z-Score"), ("Nff", "NFF"), ("Etf", "ETF"),
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

            if score_match is None and not is_missing:
                val_text = "—"
            if is_missing and not val_text:
                val_text = t("N/A — required source missing", "N/A — thiếu trường dữ liệu bắt buộc")
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
        score_history = score_history[score_history["quarter"] != "2099-Q1"]  # bỏ row test
        qtrs = score_history["quarter"].tolist()
        scores_list = [None if pd.isna(v) else float(v) for v in score_history["total_score"].tolist()]
        
        pct_labels = score_history["percentile_label"].fillna("N/A").tolist() if "percentile_label" in score_history.columns else ["N/A"] * len(qtrs)
        disp_levels = score_history["dispersion_level"].fillna("N/A").tolist() if "dispersion_level" in score_history.columns else ["N/A"] * len(qtrs)
        
        point_colors = []
        for pct in pct_labels:
            if pct == "BUY/ACCUMULATE":
                point_colors.append("#22c55e")
            elif pct == "REDUCE/SELL":
                point_colors.append("#ef4444")
            elif pct == "HOLD":
                point_colors.append("#eab308")
            else:
                point_colors.append("#3b82f6")

        # ── Calibrated Action dataset (tầng hành động, tô màu regime) ──────
        has_cal = "calibrated_score" in score_history.columns
        cal_dataset_js = ""
        if has_cal:
            cal_scores = [None if pd.isna(v) else float(v) for v in score_history["calibrated_score"].tolist()]
            cal_labels_hist = (score_history["calibrated_label"].fillna("HOLD").tolist()
                               if "calibrated_label" in score_history.columns else ["HOLD"] * len(qtrs))
            cal_point_colors = [_LABEL_COLORS.get(c, "#3b82f6") for c in cal_labels_hist]
            cal_dataset_js = f""",
            {{
              label: 'Calibrated Action',
              data: {json.dumps(cal_scores)},
              borderColor: '#8b5cf6',
              backgroundColor: 'transparent',
              borderWidth: 3,
              pointBackgroundColor: {json.dumps(cal_point_colors)},
              pointBorderColor: '#fff',
              pointRadius: 5,
              pointHoverRadius: 7,
              fill: false,
              tension: 0.3
            }}"""

        # ── VN-Index overlay (dataset ẩn, bật bằng toggle) ─────────────────
        vnindex_prices = _load_vnindex_quarterly_prices(qtrs)
        vnindex_dataset_js = ""
        if vnindex_prices is not None:
            vnindex_dataset_js = f""",
            {{
              label: 'VN-Index',
              data: {json.dumps(vnindex_prices)},
              borderColor: '#10b981',
              backgroundColor: 'transparent',
              borderWidth: 2,
              pointRadius: 0,
              pointHoverRadius: 4,
              yAxisID: 'y1',
              hidden: true
            }}"""
                
        chart_js_data += f"""
        <script>
          window.chartDataLine = {{
            labels: {json.dumps(qtrs)},
            datasets: [{{
              label: 'Total Score',
              data: {json.dumps(scores_list)},
              percentile_label: {json.dumps(pct_labels)},
              dispersion_level: {json.dumps(disp_levels)},
              borderColor: '#3b82f6',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              borderWidth: 3,
              borderDash: [6, 4],
              pointBackgroundColor: {json.dumps(point_colors)},
              pointBorderColor: '#fff',
              pointRadius: 5,
              pointHoverRadius: 7,
              fill: true,
              tension: 0.3
            }}{cal_dataset_js}{vnindex_dataset_js}]
          }};
        </script>
        """
        
        calibrated_toggle_html = ""
        if has_cal:
            calibrated_toggle_html = f"""
              <label class="chart-toggle">
                <input type="checkbox" id="toggleCalibrated" checked>
                <span class="chart-swatch" style="background:#8b5cf6;"></span>
                <span class="chart-name lang-en">Calibrated Action</span><span class="chart-name lang-vi">Hành động (calibrated)</span>
              </label>"""
        vnindex_toggle_html = ""
        if vnindex_prices is not None:
            vnindex_toggle_html = f"""
              <label class="chart-toggle">
                <input type="checkbox" id="toggleVNIndex">
                <span class="chart-swatch" style="background:#94a3b8;"></span>
                <span class="chart-name lang-en">VN-Index</span><span class="chart-name lang-vi">VN-Index</span>
              </label>"""

        history_html = f"""
        <div class="section">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px;">
            <h2 style="margin-bottom: 0;">📈 {t('Historical Score Trend', 'Lịch sử Điểm số Theo Quý')}</h2>
            <div style="display:flex; gap:10px; justify-content: flex-end; flex-wrap: wrap;">
              {calibrated_toggle_html}
              <label class="chart-toggle">
                <input type="checkbox" id="toggleCompositeScore" checked>
                <span class="chart-swatch dashed" style="color:#3b82f6;"></span>
                <span class="chart-name lang-en">Raw Composite</span><span class="chart-name lang-vi">Điểm thô</span>
              </label>
              {vnindex_toggle_html}
            </div>
          </div>
          <div class="chart-container" style="height: 380px; padding: 24px; border-radius: 12px; box-shadow: var(--card-shadow); background-color: var(--bg-card); margin-top: 16px;">
            <canvas id="lineChart" aria-label="Historical Score Trend Chart" role="img"></canvas>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">
            💡 {t('Solid line = Calibrated Action Signal (points colored by regime); dashed = raw composite reference.',
                  'Đường liền = Tín hiệu hành động Calibrated (điểm tô màu theo regime); nét đứt = điểm thô tham chiếu.')}
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
        {t('Based on the composite score, the model outputs 5 strategic recommendations (sourced from config.py SCORE_LABELS — single source of truth):', 'Dựa trên điểm số tổng hợp, mô hình đưa ra 5 mức khuyến nghị chiến lược (từ config.py SCORE_LABELS — nguồn sự thật duy nhất):')}
        {"".join(
            f"<br>• <strong>{lo}–{hi}:</strong> {lbl} {em} — {alloc}"
            for (lo, hi), (lbl, em, desc, alloc) in sorted(SCORE_LABEL_RANGES, key=lambda x: x[0][0], reverse=True)
        )}
      </p>

      <h3 style="margin-top: 24px; color: var(--color-blue); border-top: 1px solid var(--border-color); padding-top: 16px;">{t('5. Academic References & Citations', '5. Tài liệu tham khảo & Nền tảng học thuật')}</h3>
      <ul style="font-size: 14px; line-height: 1.6; color: var(--text-muted); padding-left: 20px;">
        <li style="margin-bottom: 8px;"><strong>{t('Multiple Linear Regression (MLR) & HAC Standard Errors', 'Hồi quy đa biến (MLR) & Sai số chuẩn HAC')}:</strong> Newey, W. K., & West, K. D. (1987). <em>A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix</em>. Econometrica, 55(3), 703-708.</li>
        <li style="margin-bottom: 8px;"><strong>{t('Vector Autoregression (VAR)', 'Tự hồi quy Vectơ (VAR)')}:</strong> Sims, C. A. (1980). <em>Macroeconomics and Reality</em>. Econometrica, 48(1), 1-48.</li>
        <li style="margin-bottom: 8px;"><strong>{t('Granger Causality', 'Kiểm định Nhân quả Granger')}:</strong> Granger, C. W. J. (1969). <em>Investigating Causal Relations by Econometric Models and Cross-spectral Methods</em>. Econometrica, 37(3), 424-438.</li>
        <li style="margin-bottom: 8px;"><strong>{t('Random Forest Classifier', 'Mô hình Rừng ngẫu nhiên (Random Forest)')}:</strong> Breiman, L. (2001). <em>Random Forests</em>. Machine Learning, 45(1), 5-32.</li>
        <li style="margin-bottom: 8px;"><strong>{t('XGBoost (Extreme Gradient Boosting)', 'Mô hình Tăng cường độ dốc (XGBoost)')}:</strong> Chen, T., & Guestrin, C. (2016). <em>XGBoost: A Scalable Tree Boosting System</em>. Proceedings of the 22nd ACM SIGKDD International Conference.</li>
      </ul>

      <h3 style="margin-top: 24px; color: var(--color-blue); border-top: 1px solid var(--border-color); padding-top: 16px;">{t('6. Data Sources & Integrity', '6. Nguồn Dữ liệu & Tính Toàn vẹn')}</h3>
      <ul style="font-size: 14px; line-height: 1.6; color: var(--text-muted); padding-left: 20px;">
        <li style="margin-bottom: 8px;"><strong>{t('Vietnam Equity & Market Data', 'Dữ liệu Thị trường Cổ phiếu Việt Nam')}:</strong> {t('Directly sourced from the highly reliable <code>vnstock</code> ecosystem, integrating real-time and historical OHLCV, foreign net flows, and valuation metrics from top-tier domestic securities firms (SSI, TCBS, VNDIRECT).', 'Được trích xuất trực tiếp từ hệ sinh thái <code>vnstock</code> uy tín, tích hợp dữ liệu giá (OHLCV), giao dịch khối ngoại và định giá từ các công ty chứng khoán hàng đầu (SSI, TCBS, VNDIRECT).')}</li>
        <li style="margin-bottom: 8px;"><strong>{t('Global Macro & Intermarket Data', 'Dữ liệu Vĩ mô Toàn cầu & Liên thị trường')}:</strong> {t('Fetched via <code>yfinance</code> and <code>pandas_datareader</code> APIs for authoritative global indicators including the US Dollar Index (DXY), US 10-Year Treasury Yields (US10Y), and global exchange rates (USD/JPY, USD/VND).', 'Truy xuất qua API của <code>yfinance</code> và <code>pandas_datareader</code> để lấy các chỉ số toàn cầu chuẩn xác như Chỉ số Dolar Mỹ (DXY), Lợi suất Trái phiếu Mỹ 10 năm (US10Y) và tỷ giá (USD/JPY, USD/VND).')}</li>
        <li style="margin-bottom: 8px;"><strong>{t('Data Integrity & Preprocessing', 'Tính Toàn vẹn & Tiền xử lý dữ liệu')}:</strong> {t('Missing data is rigorously imputed using forward-filling methods. The pipeline executes automated daily validation scripts (via GitHub Actions) to ensure zero data gaps before calculating the final quarterly composite score.', 'Dữ liệu khuyết thiếu được xử lý nghiêm ngặt bằng phương pháp nội suy tịnh tiến (forward-fill). Luồng thực thi chạy các kịch bản kiểm tra dữ liệu tự động hàng ngày (qua GitHub Actions) nhằm đảm bảo không có lỗ hổng dữ liệu trước khi chấm điểm.')}</li>
      </ul>
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
        <h2>🎯 {t('Investment Recommendation & Project Evaluation', 'Khuyến nghị Đầu tư & Đánh giá Dự án')}</h2>
        
        <div class="card" style="margin-bottom: 24px;">
            <h3 style="margin-top: 0; color: var(--color-blue); border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                {t('Quarterly Investment Recommendation', 'Khuyến nghị Đầu tư theo Quý')}
            </h3>
            <p><strong>{t('Current Score', 'Điểm số hiện tại')}:</strong> <span style="color: {score_color}; font-weight: bold;">{total:.1f} / 100 ({label})</span></p>
            <p style="line-height: 1.6;"><strong>{t('Recommendation', 'Khuyến nghị')}:</strong> {t(
                "Based on the aggregate quantitative score, the current market environment is classified as " + label + ". Investors are advised to align their equity exposure with this regime, utilizing the 'Pillars Analysis' to identify the specific macro or valuation drivers behind this score.",
                f"Dựa trên tổng điểm định lượng, môi trường thị trường hiện tại được phân loại là {label}. Nhà đầu tư được khuyến nghị điều chỉnh tỷ trọng cổ phiếu theo trạng thái này, đồng thời sử dụng 'Phân rã Điểm số' để nhận diện các động lực vĩ mô hoặc định giá cụ thể đứng sau mức điểm này."
            )}</p>
        </div>

        <div class="card">
            <h3 style="margin-top: 0; color: var(--color-blue); border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                {t('Project Requirements Evaluation', 'Đánh giá các Yêu cầu của Dự án')}
            </h3>
            
            <h4 style="color: var(--text-main); margin-bottom: 4px;">1. {t('Ability to identify the relevant factors', 'Khả năng xác định các yếu tố trọng yếu')}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{t(
                "The model successfully identifies and integrates 6 distinct pillars: Macro & Monetary, Global & Intermarket, Valuation & Leverage, Quant Model (VAR/MLR), ML Forecast, and Market Structure. These encompass a holistic view of the forces driving the VN-Index.",
                "Mô hình đã xác định và tích hợp thành công 6 trụ cột khác biệt: Vĩ mô & Tiền tệ, Toàn cầu & Liên thị trường, Định giá & Đòn bẩy, Mô hình Định lượng (VAR/MLR), Dự báo ML và Cấu trúc Thị trường. Các yếu tố này bao quát toàn diện các động lực dẫn dắt VN-Index."
            )}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">2. {t('Ability to quantify the impact of each factor', 'Khả năng định lượng tác động của từng yếu tố')}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{t(
                "Impact is rigorously quantified using Multiple Linear Regression (MLR) to extract beta coefficients, VAR Granger Causality to prove leading relationships, and a robust Z-scoring mechanism to normalize disparate datasets into a unified 0-100 scale.",
                "Tác động được định lượng chặt chẽ thông qua Hồi quy đa biến (MLR) để trích xuất hệ số Beta, Kiểm định VAR Granger để chứng minh mối quan hệ dẫn dắt, và cơ chế Z-score chuẩn hóa các tập dữ liệu khác biệt về thang điểm 0-100 thống nhất."
            )}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">3. {t('Ability to obtain data from any of the sources available to you', 'Khả năng thu thập dữ liệu từ các nguồn khả dụng')}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{t(
                "Data acquisition is highly automated and robust, fetching directly from the 'vnstock' API for market data, domestic macro variables, and foreign flows, coupled with standard APIs for global yields and DXY.",
                "Quá trình thu thập dữ liệu được tự động hóa cao và ổn định, lấy trực tiếp từ thư viện 'vnstock' đối với dữ liệu thị trường, vĩ mô trong nước, dòng tiền khối ngoại, kết hợp với các API tiêu chuẩn để lấy lợi suất trái phiếu Mỹ và chỉ số DXY."
            )}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">4. {t("Ability to automate the model's scoring in future", "Khả năng tự động hóa việc chấm điểm của mô hình trong tương lai")}</h4>
            <p class="rationale" style="margin-top: 0; margin-bottom: 16px;">{t(
                "The pipeline is fully automated via 'run_quarterly.py', dynamically computing the current quarter using the datetime module. This ensures the entire process from data fetching to HTML report generation is turnkey and ready for crontab scheduling.",
                "Toàn bộ luồng (pipeline) được tự động hóa hoàn toàn thông qua 'run_quarterly.py', với khả năng tự động tính toán quý hiện hành qua module datetime. Điều này đảm bảo quá trình từ tải dữ liệu đến xuất báo cáo HTML diễn ra liền mạch và sẵn sàng để lập lịch tự động (crontab)."
            )}</p>

            <h4 style="color: var(--text-main); margin-bottom: 4px;">5. {t("Back-testing and evaluation of the model's validity", "Kiểm định (Back-test) và đánh giá tính hợp lệ của mô hình")}</h4>
            <p class="rationale" style="margin-top: 0;">{t(
                "Validity is enforced through a Walk-Forward Validation (WFV) approach for the XGBoost ML component, preventing data leakage, alongside rigorous statistical diagnostics (p-values) in the MLR and VAR models to ensure relationships are not spurious.",
                "Tính hợp lệ được đảm bảo thông qua phương pháp Kiểm chứng Tiến bước (Walk-Forward Validation) cho mô hình XGBoost nhằm ngăn ngừa rò rỉ dữ liệu (data leakage), kết hợp với các chẩn đoán thống kê nghiêm ngặt (p-values) trong MLR và VAR để đảm bảo các mối quan hệ không phải là giả mạo."
            )}</p>
        </div>
      </div>
    </div>
    """

    references_html = f"""
    <div class="card">
      <div class="card-header">
        <h2 style="margin: 0; font-size: 18px;">{t('Academic Citations & Theories', 'Trích dẫn Học thuật & Lý thuyết')}</h2>
      </div>
      <div class="card-body">
        <div class="references-list" style="line-height: 1.6; color: var(--text-main);">
          <h4 style="color: var(--primary-color); margin-bottom: 8px;">1. {t('Mathematical Formulas', 'Các Công thức Toán học Định lượng')}</h4>
          <ul style="margin-top: 0; margin-bottom: 20px; padding-left: 20px;">
            <li style="margin-bottom: 8px;">
              <strong>{t('Logarithmic Returns (VN-Index):', 'Lợi suất Logarit (VN-Index):')}</strong> 
              <div class="math-formula">$$ R_t = \\ln(P_t / P_{{t-1}}) $$</div>
              <br><em>{t('Used to calculate continuous returns, ensuring symmetric scaling for financial time series.', 'Sử dụng để tính lợi suất liên tục, đảm bảo tính đối xứng cho chuỗi thời gian tài chính.')}</em>
            </li>
            <li style="margin-bottom: 8px;">
              <strong>{t('Multiple Linear Regression (MLR):', 'Hồi quy Tuyến tính Đa biến (MLR):')}</strong> 
              <div class="math-formula">$$ \\hat{{Y}} = \\beta_0 + \\sum_{{i=1}}^{{n}} \\beta_i X_i + \\epsilon $$</div>
              <br><em>{t('Estimates the beta coefficients (impact weights) of macroeconomic variables on VN-Index returns.', 'Ước lượng hệ số Beta (trọng số tác động) của các biến số vĩ mô lên lợi suất VN-Index.')}</em>
            </li>
            <li style="margin-bottom: 8px;">
              <strong>{t('Vector Autoregression (VAR):', 'Tự Hồi quy Vector (VAR):')}</strong> 
              <div class="math-formula">$$ Y_t = \\alpha + \\sum_{{i=1}}^{{p}} \\Phi_i Y_{{t-i}} + \\epsilon_t $$</div>
              <br><em>{t('Analyzes the dynamic impact of random disturbances on the system of variables (Granger Causality).', 'Phân tích tác động động của các cú sốc ngẫu nhiên lên hệ thống biến số (Kiểm định Granger Causality).')}</em>
            </li>
            <li style="margin-bottom: 8px;">
              <strong>{t('Z-Score Normalization:', 'Chuẩn hóa Z-Score:')}</strong> 
              <div class="math-formula">$$ Z = (X - \\mu) / \\sigma $$</div>
              <br><em>{t('Normalizes disparate fundamental data into a unified 0-100 scoring scale.', 'Chuẩn hóa dữ liệu cơ bản khác biệt về thang điểm 0-100 thống nhất.')}</em>
            </li>
          </ul>

          <h4 style="color: var(--primary-color); margin-bottom: 8px;">2. {t('Economic Theories & Authors', 'Lý thuyết Kinh tế & Tác giả')}</h4>
          <ul style="margin-top: 0; padding-left: 20px;">
            <li style="margin-bottom: 8px;">
              <strong>Arbitrage Pricing Theory (APT)</strong> — <em>Stephen Ross (1976)</em>:
              <br>{t('Forms the foundation for using multiple macroeconomic factors (interest rates, exchange rates) to price assets and forecast index returns.', 'Tạo nền tảng cho việc sử dụng đa yếu tố vĩ mô (lãi suất, tỷ giá) để định giá tài sản và dự báo lợi suất chỉ số.')}
            </li>
            <li style="margin-bottom: 8px;">
              <strong>Liquidity Preference Theory</strong> — <em>John Maynard Keynes (1936)</em>:
              <br>{t('Explains why money supply (M2) and credit growth affect interest rates and, subsequently, asset prices (the "liquidity pillar").', 'Giải thích lý do cung tiền (M2) và tăng trưởng tín dụng ảnh hưởng đến lãi suất và giá tài sản (trụ cột "Thanh khoản").')}
            </li>
            <li style="margin-bottom: 8px;">
              <strong>Efficient Market Hypothesis (EMH) & Anomalies</strong> — <em>Eugene Fama (1970) & Fama-French (1993)</em>:
              <br>{t('While EMH assumes prices reflect all information, our model exploits structural anomalies (e.g., foreign flow momentum) to identify excess returns.', 'Mặc dù EMH cho rằng giá phản ánh mọi thông tin, mô hình khai thác các dị biệt cấu trúc (như quán tính dòng tiền khối ngoại) để tìm kiếm lợi nhuận vượt trội.')}
            </li>
            <li style="margin-bottom: 8px;">
              <strong>Granger Causality</strong> — <em>Clive Granger (1969)</em>:
              <br>{t('The theoretical basis for our VAR model to empirically test whether leading indicators (e.g., global yields) actually "cause" movements in VN-Index.', 'Cơ sở lý thuyết cho mô hình VAR của chúng tôi nhằm kiểm định thực nghiệm xem các chỉ báo dẫn dắt (ví dụ: lợi suất trái phiếu Mỹ) có thực sự "gây ra" biến động của VN-Index hay không.')}
            </li>
          </ul>
        </div>
      </div>
    </div>
    
    <div class="card" style="margin-top: 20px;">
      <div class="card-header">
        <h2 style="margin: 0; font-size: 18px;">{t('Data Sources & Integrity', 'Nguồn Dữ liệu & Tính Toàn vẹn')}</h2>
      </div>
      <div class="card-body">
        <div style="line-height: 1.6; color: var(--text-main);">
          <p style="margin-top: 0; margin-bottom: 16px;">{t(
              'This quantitative project pulls data from verified, institutional-grade sources to ensure the highest level of integrity and accuracy:', 
              'Dự án định lượng này trích xuất dữ liệu từ các nguồn đã được xác minh, đạt chuẩn tổ chức để đảm bảo mức độ toàn vẹn và chính xác cao nhất:')}</p>
          <ul style="margin-top: 0; padding-left: 20px;">
            <li style="margin-bottom: 8px;"><strong>State Bank of Vietnam (SBV)</strong>: {t('OMO rates, 12M Deposit Rates, USD/VND Exchange Rates, M2 and Credit Growth.', 'Lãi suất OMO, Lãi suất huy động 12T, Tỷ giá trung tâm USD/VND, Cung tiền M2 và Tăng trưởng tín dụng.')}</li>
            <li style="margin-bottom: 8px;"><strong>Ho Chi Minh City Stock Exchange (HOSE) &amp; HNX</strong>: {t('VN-Index OHLCV and market breadth data (accessed via the vnstock API).', 'Du lieu OHLCV VN-Index va do rong thi truong (truy cap qua API vnstock).')}</li>
            <li style="margin-bottom: 8px;"><strong>VNDirect Financial Information API</strong>: {t('Net Foreign Flows (NFF ex-ETF) and ETF Flows on HOSE, fetched from the institutional endpoint api-finfo.vndirect.com.vn/v4/foreigns. Covers STOCK_HOSE and ETF_HOSE segments, aggregated daily and normalised against market capitalisation.', 'Dong tien khoi ngoai thuan (NFF ex-ETF) va dong tien ETF tren HOSE, lay tu endpoint to chuc api-finfo.vndirect.com.vn/v4/foreigns. Bao gom STOCK_HOSE va ETF_HOSE, tong hop ngay va chuan hoa theo von hoa thi truong.')}</li>
            <li style="margin-bottom: 8px;"><strong>Federal Reserve Economic Data (FRED) / Yahoo Finance</strong>: {t('US 10Y/2Y Treasury Yields, US Dollar Index (DXY).', 'Lợi suất trái phiếu chính phủ Mỹ 10Y/2Y, Chỉ số sức mạnh đồng USD (DXY).')}</li>
            <li style="margin-bottom: 8px;"><strong>Vietnam State Treasury (KBNN)</strong>: {t('Vietnam Government Bond Yield Curve (VN1Y, VN10Y) computed via Nelson-Siegel model from the FTU-kudo Bond Yield pipeline.', 'Đường cong lợi suất trái phiếu chính phủ Việt Nam (VN1Y, VN10Y) được tính toán qua mô hình Nelson-Siegel từ dự án VN_Bond_Yield_pipeline.')}</li>
          </ul>
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
        <li class="tab-link" onclick="openTab(event, 'tab-references')">
           📚 {t('References & Data', 'Trích dẫn & Nguồn dữ liệu')}
        </li>
      </ul>
    </div>
    
    <div class="main-content">
      <h1>📊 {t('VN-Index Quantitative Scoring Model', 'Hệ thống Chấm điểm Định lượng VN-Index')}
        <span class="report-badge" style="font-size:18px; color:var(--text-muted); font-weight:400; margin-left: 10px;">{t(f'{quarter} Report', f'Báo cáo {quarter}')}</span>
      </h1>
      {chart_js_data}
      
      <div id="tab-overview" class="tab-content active">
        {hero_html}
        {cards_html}
        {coverage_html}
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
      
      <div id="tab-references" class="tab-content">
        {references_html}
      </div>
      
      {investment_rec_html}

      <div class="disclaimer">
        <strong>⚠️ Disclaimer:</strong> {t('Generated by VN_Index_Scoring_Quarterly_Quant_Model v1.0.0. For research purposes only. Not financial advice.', 'Báo cáo được tạo tự động bởi hệ thống định lượng. Phục vụ mục đích nghiên cứu và tham khảo. Không phải khuyến nghị đầu tư.')}<br>
        Generated at: <span class="js-generated-at">…</span>
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

        // Keyboard shortcuts: ← previous (older) quarter | → next (newer) quarter
        document.addEventListener("keydown", (e) => {{
          const tag = e.target && e.target.tagName;
          if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
          if (e.altKey || e.ctrlKey || e.metaKey) return;
          if (e.key === "ArrowLeft")  {{ e.preventDefault(); navigateTo(currentIndex + 1); }}
          if (e.key === "ArrowRight") {{ e.preventDefault(); navigateTo(currentIndex - 1); }}
        }});

      }} catch (err) {{
        console.error("Quarter navigation error:", err);
      }}

      // Print / Save-as-PDF button
      const printBtn = document.getElementById("print-btn");
      if (printBtn) {{
        printBtn.addEventListener("click", () => window.print());
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


def _load_quarter_summaries(reports: List[str]) -> List[Dict[str, Any]]:
    """Đọc exports/score_*.json để lấy tóm tắt điểm cho từng quý (asc order).

    Ưu tiên tầng CALIBRATED ACTION SIGNAL (calibrated_score/calibrated_label)
    cho màu thẻ & timeline; điểm thô (total_score) giữ lại làm đường tham chiếu.
    """
    summaries = []
    for q in sorted(reports):  # ascending: 2021_Q1 ... 2026_Q4
        export_path = EXPORTS_DIR / f"score_{q}.json"
        item = {"dir": q, "quarter": q.replace("_", "-"), "score": None,
                "label": "N/A", "emoji": "⚪", "allocation": "",
                "raw_score": None, "raw_label": "N/A"}
        if export_path.exists():
            try:
                with open(export_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                qs = payload.get("quarterly_score", {}) or {}
                score = qs.get("total_score")
                if score is not None:
                    lbl, em, desc, alloc = get_score_label(float(score))
                    item.update({
                        "score": float(score),
                        "label": qs.get("label", lbl),
                        "emoji": qs.get("emoji", em),
                        "allocation": qs.get("label_allocation", alloc),
                    })
                    # Tầng calibrated (fallback về raw nếu JSON chưa backfill)
                    cal = qs.get("calibrated_score")
                    if cal is not None:
                        cal_lbl, cal_em, _, cal_alloc = get_score_label(float(cal))
                        item.update({
                            "score": float(cal),
                            "label": qs.get("calibrated_label", cal_lbl),
                            "emoji": qs.get("calibrated_emoji", cal_em),
                            "allocation": qs.get("calibrated_allocation", cal_alloc),
                        })
                    item["raw_score"] = float(score)
                    item["raw_label"] = qs.get("label", lbl)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"[REPORT] Cannot read export for {q}: {exc}")
        summaries.append(item)
    return summaries


def build_root_index_html():
    """Trang chủ dashboard: timeline 24 quý + lưới thẻ quý, thay cho redirect."""
    reports = []
    for d in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "index.html").exists():
            reports.append(d.name)

    # Export list of quarters to quarters.json for dynamic navigation
    quarters_json_path = REPORTS_DIR / "quarters.json"
    with open(quarters_json_path, "w", encoding="utf-8") as f:
        json.dump(reports, f)

    if not reports:
        logger.warning("[REPORT] No quarter reports found to build root index.")
        return

    latest_quarter = reports[0]
    summaries = _load_quarter_summaries(reports)  # ascending
    latest = next((s for s in summaries if s["dir"] == latest_quarter), summaries[-1])

    # ── Chart.js data (ascending timeline) ─────────────────────────────
    # Line chính = CALIBRATED ACTION SIGNAL (tô màu theo regime calibrated);
    # đường RAW COMPOSITE giữ nét đứt làm tham chiếu.
    tl_labels = [s["quarter"] for s in summaries]
    tl_scores = [round(s["score"], 2) if s["score"] is not None else None for s in summaries]
    tl_raws   = [round(s["raw_score"], 2) if s["raw_score"] is not None else None for s in summaries]
    tl_colors = [_LABEL_COLORS.get(s["label"], "#94a3b8") for s in summaries]
    tl_hrefs  = [f'{s["dir"]}/index.html' for s in summaries]

    # ── Quarter cards (newest first) — màu theo calibrated regime ────────
    cards_html = ""
    for s in reversed(summaries):
        color = _LABEL_COLORS.get(s["label"], "#94a3b8")
        score_txt = f'{s["score"]:.1f}' if s["score"] is not None else "—"
        width = s["score"] if s["score"] is not None else 0
        latest_badge = (
            '<span class="latest-badge">LATEST</span>' if s["dir"] == latest_quarter else ""
        )
        raw_txt = (f'raw {s["raw_score"]:.1f} · {s["raw_label"]}'
                   if s["raw_score"] is not None else "")
        cards_html += f"""
        <a class="q-card" href="{s['dir']}/index.html" style="--q-color:{color};">
          <div class="q-card-top">
            <span class="q-name">{s['quarter']}</span>{latest_badge}
          </div>
          <div class="q-score" style="color:{color};">{score_txt}</div>
          <div class="q-label" style="color:{color};">{s['emoji']} {s['label']}</div>
          <div class="q-bar"><div class="q-bar-fill" style="width:{width}%; background:{color};"></div></div>
          <div class="q-alloc">{s['allocation']}</div>
          <div class="q-raw-ref">{raw_txt}</div>
        </a>"""

    latest_color = _LABEL_COLORS.get(latest["label"], "#94a3b8")
    latest_score_txt = f'{latest["score"]:.1f}' if latest["score"] is not None else "—"
    n_quarters = len(summaries)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VN-Index Quant Dashboard — {n_quarters} Quarters</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
    :root {{
      --bg-primary: #f8fafc; --bg-card: rgba(255,255,255,0.85); --text-main: #0f172a;
      --text-muted: #475569; --border-color: rgba(226,232,240,0.8);
      --card-shadow: 0 10px 25px -5px rgba(0,0,0,0.05), 0 8px 10px -6px rgba(0,0,0,0.01);
      --color-blue: #3b82f6;
    }}
    body.dark-mode {{
      --bg-primary: #0f172a; --bg-card: rgba(30,41,59,0.75); --text-main: #f1f5f9;
      --text-muted: #94a3b8; --border-color: rgba(51,65,85,0.8);
      --card-shadow: 0 10px 25px -5px rgba(0,0,0,0.4); --color-blue: #60a5fa;
    }}
    * {{ box-sizing: border-box; transition: background-color 0.4s ease, color 0.4s ease; }}
    body {{ font-family: 'Outfit', sans-serif; background: var(--bg-primary); color: var(--text-main); margin: 0; line-height: 1.6; }}
    .navbar {{ background: var(--bg-card); backdrop-filter: blur(12px); padding: 15px 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); position: sticky; top: 0; z-index: 100; }}
    .brand {{ font-weight: 700; font-size: 18px; color: var(--color-blue); }}
    .clock {{ font-size: 14px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: var(--color-blue); background: var(--bg-primary); padding: 6px 14px; border-radius: 8px; border: 1px solid var(--border-color); letter-spacing: 0.5px; }}
    .nav-right {{ display: flex; gap: 12px; }}
    .btn {{ cursor: pointer; padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-card); color: var(--text-main); font-size: 14px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }}
    .btn:hover {{ background: var(--bg-primary); transform: translateY(-1px); }}
    .btn-primary {{ background: linear-gradient(90deg, #3b82f6, #8b5cf6); color: #fff; border: none; }}
    .wrap {{ max-width: 1350px; margin: 40px auto; padding: 0 24px; }}
    .hero {{ background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 20px; padding: 36px; text-align: center; box-shadow: var(--card-shadow); margin-bottom: 30px; }}
    .hero-sub {{ color: var(--text-muted); font-size: 14px; font-weight: 500; margin-bottom: 10px; letter-spacing: 0.5px; }}
    .hero-score {{ font-size: 72px; font-weight: 800; line-height: 1; }}
    .hero-label {{ font-size: 22px; font-weight: 700; margin-top: 8px; }}
    .hero-alloc {{ color: var(--text-muted); font-size: 15px; margin-top: 6px; }}
    .section {{ background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 28px; margin-bottom: 30px; box-shadow: var(--card-shadow); }}
    .section h2 {{ margin: 0 0 18px 0; font-size: 20px; font-weight: 600; }}
    .chart-box {{ position: relative; height: 360px; }}
    .q-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}
    .q-card {{ display: block; text-decoration: none; color: var(--text-main); background: var(--bg-card); border: 1px solid var(--border-color); border-left: 5px solid var(--q-color, #94a3b8); border-radius: 14px; padding: 16px 18px; box-shadow: var(--card-shadow); transition: transform 0.2s ease, box-shadow 0.2s ease; }}
    .q-card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 30px -8px rgba(0,0,0,0.18); }}
    .q-card-top {{ display: flex; justify-content: space-between; align-items: center; }}
    .q-name {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; color: var(--text-muted); }}
    .latest-badge {{ background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; letter-spacing: 0.5px; }}
    .q-score {{ font-size: 30px; font-weight: 800; margin-top: 6px; line-height: 1.1; }}
    .q-label {{ font-size: 13px; font-weight: 700; margin-top: 2px; }}
    .q-bar {{ background: rgba(0,0,0,0.06); border-radius: 6px; height: 6px; margin-top: 10px; overflow: hidden; }}
    body.dark-mode .q-bar {{ background: rgba(255,255,255,0.08); }}
    .q-bar-fill {{ height: 100%; border-radius: 6px; }}
    .q-alloc {{ font-size: 12px; color: var(--text-muted); margin-top: 8px; }}
    .q-raw-ref {{ font-size: 10.5px; color: var(--text-muted); margin-top: 4px; opacity: 0.75; font-family: 'JetBrains Mono', monospace; }}
    .legend-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin: 0 3px -1px 10px; }}
    .disclaimer {{ color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px 0 40px 0; opacity: 0.8; }}
    .lang-vi {{ display: none; }}
    body.lang-vi-active .lang-vi {{ display: inline; }}
    body.lang-vi-active .lang-en {{ display: none; }}
    @media (max-width: 1100px) {{ .q-grid {{ grid-template-columns: repeat(3, 1fr); }} }}
    @media (max-width: 860px)  {{ .q-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (max-width: 720px) {{
      .navbar {{ flex-wrap: wrap; gap: 10px; padding: 12px 16px; }}
      .wrap {{ margin: 20px auto; padding: 0 12px; }}
      .hero {{ padding: 24px 16px; }}
      .hero-score {{ font-size: 54px; }}
      .chart-box {{ height: 260px; }}
    }}
    @media (max-width: 520px) {{ .q-grid {{ grid-template-columns: 1fr; }} .clock {{ display: none; }} }}
    @media print {{
      body {{ background: #fff !important; }}
      .navbar, .btn {{ display: none !important; }}
      .section, .hero, .q-card {{ box-shadow: none !important; border: 1px solid #d1d5db; break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="navbar">
    <div class="brand">📊 VNI Quant Dashboard</div>
    <div class="clock" id="clock">Loading time...</div>
    <div class="nav-right">
      <a class="btn btn-primary" href="{latest_quarter}/index.html">🚀 <span class="lang-en">Latest Report</span><span class="lang-vi">Báo cáo mới nhất</span></a>
      <button class="btn" id="print-btn" title="Print / Save as PDF">🖨️</button>
      <button class="btn" id="lang-btn">🇻🇳 VI</button>
      <button class="btn" id="theme-btn">🌙 Dark</button>
    </div>
  </div>

    <div class="wrap">
    <div class="hero">
      <div class="hero-sub">
        {t('VN-INDEX QUARTERLY QUANTITATIVE SCORING MODEL', 'HỆ THỐNG CHẤM ĐIỂM ĐỊNH LƯỢNG VN-INDEX THEO QUÝ')}
        — {t(f'{n_quarters} quarters tracked', f'theo dõi {n_quarters} quý')}
      </div>
      <div class="hero-score" style="color:{latest_color};">{latest_score_txt}</div>
      <div class="hero-label" style="color:{latest_color};">{latest['emoji']} {latest['label']} — {latest['quarter']}</div>
      <div class="hero-alloc">⚡ {t('Calibrated action — recommended allocation', 'HÀNH ĐỘNG (calibrated) — khuyến nghị phân bổ')}: <strong>{latest['allocation']}</strong></div>
      <div class="hero-alloc" style="font-size: 12.5px; opacity: .85;">
        📐 {t(f"Raw composite reference: {(latest.get('raw_score') or 0):.1f} → {latest.get('raw_label', 'N/A')} — action signal is z-calibrated vs prior quarters (point-in-time).",
              f"Tham chiếu điểm thô: {(latest.get('raw_score') or 0):.1f} → {latest.get('raw_label', 'N/A')} — tín hiệu hành động được hiệu chỉnh z-score so với các quý trước (point-in-time).")}
      </div>
      <div style="margin-top: 18px;">
        <a class="btn btn-primary" href="{latest_quarter}/index.html" style="font-size: 15px;">
          📈 <span class="lang-en">Open {latest['quarter']} Report</span><span class="lang-vi">Mở Báo cáo {latest['quarter']}</span>
        </a>
      </div>
    </div>

    <div class="section">
      <h2>📈 {t(f'Calibrated Action Timeline ({n_quarters} Quarters)', f'Timeline Hành động Calibrated ({n_quarters} Quý)')}</h2>
      <div style="font-size: 12.5px; color: var(--text-muted); margin-bottom: 10px;">
        <strong>{t('Calibrated action signal', 'Tín hiệu hành động calibrated')}</strong>
        {t('— solid line, points colored by regime', '— đường liền, điểm tô màu theo regime')}
        <span class="legend-dot" style="background:#10b981;"></span>BUY
        <span class="legend-dot" style="background:#3b82f6;"></span>ACCUMULATE
        <span class="legend-dot" style="background:#eab308;"></span>HOLD
        <span class="legend-dot" style="background:#f97316;"></span>REDUCE
        <span class="legend-dot" style="background:#ef4444;"></span>SELL
        &nbsp;|&nbsp; <strong>{t('raw composite', 'điểm thô')}</strong> {t('— dashed reference', '— nét đứt tham chiếu')}
      </div>
      <div class="chart-box"><canvas id="timelineChart" aria-label="Calibrated Action Timeline" role="img"></canvas></div>
      <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">
        💡 {t("Click any point to open that quarter's report.", 'Nhấp vào bất kỳ điểm nào để mở báo cáo của quý đó.')}
      </div>
    </div>

    <div class="section">
      <h2>🗂️ {t('All Quarterly Reports', 'Tất cả Báo cáo theo Quý')}</h2>
      <div class="q-grid">{cards_html}
      </div>
    </div>

    <div class="disclaimer">
      <strong>⚠️ Disclaimer:</strong> {t('Generated by VN_Index_Scoring_Quarterly_Quant_Model. For research purposes only. Not financial advice.', 'Báo cáo được tạo tự động bởi hệ thống định lượng. Phục vụ mục đích nghiên cứu. Không phải khuyến nghị đầu tư.')}<br>
      Generated at: <span class="js-generated-at">…</span>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    const TL_LABELS = {json.dumps(tl_labels)};
    const TL_SCORES = {json.dumps(tl_scores)};
    const TL_RAW    = {json.dumps(tl_raws)};
    const TL_COLORS = {json.dumps(tl_colors)};
    const TL_HREFS  = {json.dumps(tl_hrefs)};

    // Theme toggle (shared localStorage key with quarterly reports)
    const themeBtn = document.getElementById('theme-btn');
    function applyTheme() {{
      const isDark = document.body.classList.contains('dark-mode');
      themeBtn.innerHTML = isDark ? '☀️ Light' : '🌙 Dark';
    }}
    if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');
    applyTheme();
    themeBtn.addEventListener('click', () => {{
      document.body.classList.toggle('dark-mode');
      localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
      applyTheme();
      renderTimeline();
    }});

    // Language toggle (shared localStorage key with quarterly reports)
    const langBtn = document.getElementById('lang-btn');
    function applyLang() {{
      langBtn.innerHTML = document.body.classList.contains('lang-vi-active') ? '🇬🇧 EN' : '🇻🇳 VI';
    }}
    if (localStorage.getItem('lang') === 'vi') document.body.classList.add('lang-vi-active');
    applyLang();
    langBtn.addEventListener('click', () => {{
      document.body.classList.toggle('lang-vi-active');
      localStorage.setItem('lang', document.body.classList.contains('lang-vi-active') ? 'vi' : 'en');
      applyLang();
    }});

    // Print
    document.getElementById('print-btn').addEventListener('click', () => window.print());

    // Real-time Clock (UTC+7 = Vietnam time) — clock-face emoji tracks the current hour
    const CLOCK_EMOJIS = ['🕛','🕐','🕑','🕒','🕓','🕔','🕕','🕖','🕗','🕘','🕙','🕚'];
    function updateClock() {{
      const opts = {{ timeZone: 'Asia/Ho_Chi_Minh', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }};
      const text = new Intl.DateTimeFormat('sv-SE', opts).format(new Date()); // ISO-like YYYY-MM-DD HH:mm:ss
      const hour = parseInt(text.substring(11, 13), 10); // hour of day in Vietnam (0-23)
      const emoji = CLOCK_EMOJIS[hour % 12];
      const clockEl = document.getElementById('clock');
      if (clockEl) clockEl.innerText = emoji + ' ' + text + ' UTC+7';
    }}
    setInterval(updateClock, 1000);
    updateClock();

    // "Generated at" — rendered at actual runtime (not hardcoded at build time)
    (function() {{
      const opts = {{ timeZone: 'Asia/Ho_Chi_Minh', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }};
      const text = new Intl.DateTimeFormat('sv-SE', opts).format(new Date());
      const hour = parseInt(text.substring(11, 13), 10);
      const stamp = CLOCK_EMOJIS[hour % 12] + ' ' + text + ' UTC+7';
      document.querySelectorAll('.js-generated-at').forEach(el => {{ el.textContent = stamp; }});
    }})();

    // Timeline chart
    let timelineInstance = null;
    function renderTimeline() {{
      const ctx = document.getElementById('timelineChart');
      if (!ctx) return;
      const isDark = document.body.classList.contains('dark-mode');
      const textColor = isDark ? '#e2e8f0' : '#0f172a';
      const gridColor = isDark ? 'rgba(100,116,139,0.35)' : 'rgba(226,232,240,0.9)';
      if (timelineInstance) timelineInstance.destroy();
      timelineInstance = new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: TL_LABELS,
          datasets: [{{
            label: 'Calibrated Action',
            data: TL_SCORES,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.10)',
            borderWidth: 3,
            fill: true,
            tension: 0.3,
            pointRadius: 5,
            pointHoverRadius: 8,
            pointBackgroundColor: TL_COLORS,
            pointBorderColor: '#fff',
            spanGaps: true
          }},
          {{
            label: 'Raw Composite (ref)',
            data: TL_RAW,
            borderColor: '#94a3b8',
            borderWidth: 2,
            borderDash: [6, 4],
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointBackgroundColor: '#94a3b8',
            spanGaps: true
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          onClick: (evt, elements) => {{
            if (elements.length > 0) window.location.href = TL_HREFS[elements[0].index];
          }},
          onHover: (evt, elements) => {{
            evt.native.target.style.cursor = elements.length ? 'pointer' : 'default';
          }},
          scales: {{
            x: {{ grid: {{ display: false }}, ticks: {{ color: textColor, font: {{ size: 11 }}, maxRotation: 60 }} }},
            y: {{ min: 0, max: 100, grid: {{ color: gridColor }}, ticks: {{ color: textColor }},
                 title: {{ display: true, text: 'Score (0-100)', color: textColor, font: {{ weight: 'bold' }} }} }}
          }},
          plugins: {{
            legend: {{ display: true, position: 'top', align: 'end',
                       labels: {{ usePointStyle: true, pointStyle: 'circle', font: {{ size: 12, weight: '600' }}, color: textColor }} }},
            tooltip: {{
              callbacks: {{
                afterLabel: (c) => c.datasetIndex === 0 ? 'Click to open report' : ''
              }}
            }}
          }}
        }}
      }});
    }}
    document.addEventListener('DOMContentLoaded', renderTimeline);
    if (document.readyState !== 'loading') renderTimeline();
  </script>
</body>
</html>"""

    out_path = REPORTS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info(f"[REPORT] Root Dashboard updated -> {out_path} ({n_quarters} quarters)")
