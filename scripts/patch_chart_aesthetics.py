import os
import re
import glob

def patch_html():
    reports_dir = os.path.join("output", "reports")
    html_files = glob.glob(os.path.join(reports_dir, "**", "index.html"), recursive=True)
    
    count = 0
    for path in html_files:
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
            
        # 1. Plugin script
        if 'chartjs-plugin-annotation' not in html:
            html = html.replace('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
                                '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>\n  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.1.0/dist/chartjs-plugin-annotation.min.js"></script>')

        # 2. Container
        if 'var(--card-shadow)' not in html:
            html = re.sub(
                r'<div class="chart-container" style="height: 300px;">\s*<canvas id="lineChart"></canvas>\s*</div>',
                '<div class="chart-container" style="height: 380px; padding: 24px; border-radius: 12px; box-shadow: var(--card-shadow); background-color: var(--bg-card); margin-top: 16px;">\n            <canvas id="lineChart" aria-label="Historical Score Trend Chart" role="img"></canvas>\n          </div>',
                html
            )

        # 3. Checkbox accent color
        if 'accent-color: var(--color-blue);' not in html:
            html = html.replace('id="toggleVNIndex" style="width:16px; height:16px;"', 'id="toggleVNIndex" style="width:16px; height:16px; accent-color: var(--color-blue);"')
            html = html.replace('align-items:center; gap:6px;', 'align-items:center; justify-content: flex-end; gap:6px;')

        # 4. Chart options
        match = re.search(r'lineChartInstance = new Chart\(lineCtx, \{.*?\}\);', html, re.DOTALL)
        if match:
            old_chart = match.group(0)
            new_chart = '''// MUTATE SCORE DATASET
      if (window.chartDataLine && window.chartDataLine.datasets && window.chartDataLine.datasets.length > 0) {
          window.chartDataLine.datasets[0].borderWidth = 3;
          window.chartDataLine.datasets[0].pointRadius = 4;
          window.chartDataLine.datasets[0].tension = 0.3;
          window.chartDataLine.datasets[0].order = 1;
          window.chartDataLine.datasets[0].fill = false;
          window.chartDataLine.datasets[0].label = document.body.classList.contains('lang-vi-active') ? 'Điểm tổng hợp' : 'Composite Score';
          window.chartDataLine.datasets[0].pointBorderColor = '#fff';
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
      });'''
            html = html.replace(old_chart, new_chart)

        # 5. Injection dataset props
        # We need to make VN-Index an area chart (mountain)
        html = re.sub(r"borderColor: '#64748b',.*?hidden: true", 
                      "borderColor: '#94a3b8',\n                backgroundColor: 'rgba(148, 163, 184, 0.15)',\n                borderWidth: 2,\n                fill: true,\n                pointRadius: 0,\n                tension: 0.3,\n                order: 2,\n                pointHoverRadius: 4,\n                yAxisID: 'y1',\n                hidden: true", 
                      html, flags=re.DOTALL)
        
        # In case it hasn't been patched by the first regex due to state, let's also catch the original
        html = re.sub(r"borderColor: '#10b981',.*?hidden: true", 
                      "borderColor: '#94a3b8',\n                backgroundColor: 'rgba(148, 163, 184, 0.15)',\n                borderWidth: 2,\n                fill: true,\n                pointRadius: 0,\n                tension: 0.3,\n                order: 2,\n                pointHoverRadius: 4,\n                yAxisID: 'y1',\n                hidden: true", 
                      html, flags=re.DOTALL)
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        count += 1
            
    print(f"Patched chart aesthetics in {count} HTML files.")

if __name__ == "__main__":
    patch_html()
