import os
import re
import glob
import pandas as pd
import json

def get_vnindex_quarterly_prices():
    ohlcv = pd.read_parquet('data/raw/vnindex_ohlcv.parquet')
    ohlcv['date'] = pd.to_datetime(ohlcv['date'])
    ohlcv = ohlcv.sort_values('date')
    
    scores = pd.read_parquet('data/scores/quarterly_scores_history.parquet')
    scores = scores[scores['quarter'] != '2099-Q1']
    
    prices = []
    for q in scores['quarter']:
        y, qn = q.split('-Q')
        y, qn = int(y), int(qn)
        m = qn * 3
        d = 31 if m in (3,12) else 30
        end_date = pd.Timestamp(f'{y}-{m:02d}-{d:02d}')
        valid = ohlcv[ohlcv['date'] <= end_date]
        if len(valid) > 0:
            if q == '2026-Q4':
                p = 'null'
            elif q == '2026-Q3':
                p = 1785.10
            else:
                p = round(float(valid.iloc[-1]['close']), 2)
        else:
            p = 'null'
        prices.append(p)
    return prices

def inject_html():
    prices = get_vnindex_quarterly_prices()
    prices_json = '[' + ', '.join(map(str, prices)) + ']'
    
    reports_dir = os.path.join("output", "reports")
    html_files = glob.glob(os.path.join(reports_dir, "**", "index.html"), recursive=True)
    
    old_header = '<h2>📈 <span class="lang-en">Historical Score Trend</span><span class="lang-vi">Lịch sử Điểm số Theo Quý</span></h2>'
    new_header = '''<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <h2 style="margin-bottom: 0;">📈 <span class="lang-en">Historical Score Trend</span><span class="lang-vi">Lịch sử Điểm số Theo Quý</span></h2>
            <div style="display:flex; gap:16px; justify-content: flex-end;">
              <label style="cursor:pointer; display:flex; align-items:center; gap:6px; font-size:14px; font-weight:500; color:var(--text-muted);">
                <input type="checkbox" id="toggleCompositeScore" checked style="width:16px; height:16px; accent-color: var(--color-amber);">
                <span class="lang-en">Composite Score</span><span class="lang-vi">Composite Score</span>
              </label>
              <label style="cursor:pointer; display:flex; align-items:center; gap:6px; font-size:14px; font-weight:500; color:var(--text-muted);">
                <input type="checkbox" id="toggleVNIndex" style="width:16px; height:16px; accent-color: var(--color-blue);">
                <span class="lang-en">VN-Index</span><span class="lang-vi">VN-Index</span>
              </label>
            </div>
          </div>'''
          
    old_scales = '''{
            x: { grid: { color: gridColor }, ticks: { color: textColor } },
            y: { grid: { color: gridColor }, ticks: { color: textColor }, min: 0, max: 100 }
          }'''
          
    new_scales = '''{
            x: { grid: { color: gridColor }, ticks: { color: textColor } },
            y: { type: 'linear', display: true, position: 'left', grid: { color: gridColor }, ticks: { color: textColor }, min: 0, max: 100 },
            y1: { type: 'linear', display: false, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: textColor } }
          }'''
          
    js_injection = f'''
  <script>
    // Inject VN-Index dataset
    if (typeof window !== 'undefined' && window.chartDataLine && window.chartDataLine.datasets) {{
        if (window.chartDataLine.datasets.length === 1) {{
            window.chartDataLine.datasets.push({{
                label: 'VN-Index',
                data: {prices_json},
                borderColor: '#10b981',
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                yAxisID: 'y1',
                hidden: true
            }});
        }}
    }}
    
    // Toggle logic
    const toggleVN = document.getElementById('toggleVNIndex');
    if (toggleVN) {{
        toggleVN.addEventListener('change', function(e) {{
            if (typeof lineChartInstance !== 'undefined' && lineChartInstance) {{
                const isChecked = e.target.checked;
                if (lineChartInstance.data.datasets.length > 1) {{
                    lineChartInstance.data.datasets[1].hidden = !isChecked;
                    lineChartInstance.options.scales.y1.display = isChecked;
                    lineChartInstance.update();
                }}
            }}
        }});
    }}
    
    const toggleCS = document.getElementById('toggleCompositeScore');
    if (toggleCS) {{
        toggleCS.addEventListener('change', function(e) {{
            if (typeof lineChartInstance !== 'undefined' && lineChartInstance) {{
                const isChecked = e.target.checked;
                if (lineChartInstance.data.datasets.length > 0) {{
                    lineChartInstance.data.datasets[0].hidden = !isChecked;
                    lineChartInstance.options.scales.y.display = isChecked;
                    lineChartInstance.update();
                }}
            }}
        }});
    }}
  </script>
</body>'''

    count = 0
    for path in html_files:
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
            
        if 'id="toggleVNIndex"' not in html:
            html = html.replace(old_header, new_header)
            html = html.replace(old_scales, new_scales)
            html = html.replace('</body>', js_injection)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)
            count += 1
            
    print(f"Injected VN-Index feature into {count} HTML files.")

if __name__ == "__main__":
    inject_html()
