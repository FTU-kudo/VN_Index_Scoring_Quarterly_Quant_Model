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
          
          // Dynamic coloring based on score zones
          window.chartDataLine.datasets[0].segment = {
              borderColor: ctx => {
                  const val = ctx.p1.parsed.y;
                  if (val >= 80) return '#22c55e'; // BUY
                  if (val >= 65) return '#3b82f6'; // ACCUMULATE
                  if (val >= 50) return '#eab308'; // HOLD
                  if (val >= 35) return '#f97316'; // REDUCE
                  return '#ef4444'; // SELL
              }
          };
          window.chartDataLine.datasets[0].pointBackgroundColor = ctx => {
              const val = ctx.raw;
              if (val >= 80) return '#22c55e';
              if (val >= 65) return '#3b82f6';
              if (val >= 50) return '#eab308';
              if (val >= 35) return '#f97316';
              return '#ef4444';
          };
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
                    let label = context.dataset.label || '';
                    if (label) { label += ': '; }
                    if (context.parsed.y !== null) { label += context.parsed.y.toFixed(1); }
                    if (context.datasetIndex === 0) {
                       let score = context.parsed.y;
                       if (score >= 80) label += ' (BUY)';
                       else if (score >= 65) label += ' (ACCUMULATE)';
                       else if (score >= 50) label += ' (HOLD)';
                       else if (score >= 35) label += ' (REDUCE)';
                       else label += ' (SELL)';
                    }
                    return label;
                 }
              }
            },
            annotation: {
              annotations: {
                box1: { type: 'box', yMin: 80, yMax: 100, backgroundColor: 'rgba(34, 197, 94, 0.03)', borderWidth: 0, drawTime: 'beforeDraw' },
                box2: { type: 'box', yMin: 65, yMax: 80, backgroundColor: 'rgba(59, 130, 246, 0.03)', borderWidth: 0, drawTime: 'beforeDraw' },
                box3: { type: 'box', yMin: 50, yMax: 65, backgroundColor: 'rgba(234, 179, 8, 0.03)', borderWidth: 0, drawTime: 'beforeDraw' },
                box4: { type: 'box', yMin: 35, yMax: 50, backgroundColor: 'rgba(249, 115, 22, 0.03)', borderWidth: 0, drawTime: 'beforeDraw' },
                box5: { type: 'box', yMin: 0, yMax: 35, backgroundColor: 'rgba(239, 68, 68, 0.03)', borderWidth: 0, drawTime: 'beforeDraw' }
              }
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
