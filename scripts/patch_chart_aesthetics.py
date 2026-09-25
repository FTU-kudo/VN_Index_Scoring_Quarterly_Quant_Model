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
        if match and 'drawTime: \'beforeDraw\'' not in html:
            old_chart = match.group(0)
            new_chart = '''// MUTATE SCORE DATASET
      if (window.chartDataLine && window.chartDataLine.datasets && window.chartDataLine.datasets.length > 0) {
          window.chartDataLine.datasets[0].borderColor = '#2563eb';
          window.chartDataLine.datasets[0].pointBackgroundColor = '#2563eb';
          window.chartDataLine.datasets[0].borderWidth = 3;
          window.chartDataLine.datasets[0].pointRadius = 4;
          window.chartDataLine.datasets[0].tension = 0.25;
          window.chartDataLine.datasets[0].order = 1;
          window.chartDataLine.datasets[0].label = document.body.classList.contains('lang-vi-active') ? 'Điểm tổng hợp' : 'Composite Score';
      }
      
      lineChartInstance = new Chart(lineCtx, {
        type: 'line',
        data: window.chartDataLine,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 800, easing: 'easeOutQuart' },
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: { 
              grid: { color: gridColor }, 
              ticks: { color: 'var(--text-muted)', font: { size: 11 } } 
            },
            y: { 
              type: 'linear', display: true, position: 'left', 
              grid: { color: 'var(--border-color)' }, 
              ticks: { color: textColor }, min: 0, max: 100,
              title: { display: true, text: 'Composite Score (0–100)', color: textColor, font: { weight: 'bold' } }
            },
            y1: { 
              type: 'linear', display: false, position: 'right', 
              grid: { drawOnChartArea: false }, 
              ticks: { color: textColor },
              title: { display: true, text: 'VN-Index', color: textColor, font: { weight: 'bold' } }
            }
          },
          plugins: { 
            legend: { 
              display: true, 
              position: 'top', 
              align: 'end',
              labels: { usePointStyle: true, pointStyle: 'line', font: { size: 12, weight: '600' }, color: textColor }
            },
            tooltip: {
              backgroundColor: 'var(--bg-card)',
              titleColor: 'var(--text-main)',
              bodyColor: 'var(--text-main)',
              borderColor: 'var(--border-color)',
              borderWidth: 1,
              callbacks: {
                 label: function(context) {
                    let label = context.dataset.label || '';
                    if (label) { label += ': '; }
                    if (context.parsed.y !== null) { label += context.parsed.y; }
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
                box1: { type: 'box', yMin: 80, yMax: 100, backgroundColor: 'rgba(34, 197, 94, 0.05)', borderWidth: 0, drawTime: 'beforeDraw' },
                box2: { type: 'box', yMin: 65, yMax: 80, backgroundColor: 'rgba(59, 130, 246, 0.05)', borderWidth: 0, drawTime: 'beforeDraw' },
                box3: { type: 'box', yMin: 50, yMax: 65, backgroundColor: 'rgba(234, 179, 8, 0.05)', borderWidth: 0, drawTime: 'beforeDraw' },
                box4: { type: 'box', yMin: 35, yMax: 50, backgroundColor: 'rgba(249, 115, 22, 0.05)', borderWidth: 0, drawTime: 'beforeDraw' },
                box5: { type: 'box', yMin: 0, yMax: 35, backgroundColor: 'rgba(239, 68, 68, 0.05)', borderWidth: 0, drawTime: 'beforeDraw' }
              }
            }
          }
        }
      });'''
            html = html.replace(old_chart, new_chart)

        # 5. Injection dataset props
        html = html.replace("borderColor: '#10b981',", "borderColor: '#64748b',")
        if 'borderDash: [5, 3]' not in html:
            html = html.replace("pointRadius: 0,", "pointRadius: 3,\n                borderDash: [5, 3],\n                tension: 0.25,\n                order: 2,")
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        count += 1
            
    print(f"Patched chart aesthetics in {count} HTML files.")

if __name__ == "__main__":
    patch_html()
