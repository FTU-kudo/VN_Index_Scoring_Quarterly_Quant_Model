import os
import re

reports_dir = os.path.join("output", "reports")

old_nav = """<div class="nav-right">
        <button class="btn" id="lang-btn">"""
new_nav = """<div class="nav-right">
        <button class="btn" id="prev-quarter-btn" title="Previous Quarter" style="padding: 6px 10px;">◀</button>
        <select class="btn" id="quarter-select" style="max-width: 150px; cursor: pointer;"></select>
        <button class="btn" id="next-quarter-btn" title="Next Quarter" style="padding: 6px 10px;">▶</button>
        <button class="btn" id="lang-btn">"""

js_template = """  <script>
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
</body>"""

for dirname in os.listdir(reports_dir):
    dir_path = os.path.join(reports_dir, dirname)
    if os.path.isdir(dir_path) and re.match(r"20\d\d_Q\d", dirname):
        quarter = dirname.replace("_", "-")
        html_file = os.path.join(dir_path, "index.html")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "id=\"quarter-select\"" not in content:
                print(f"Injecting into {dirname}...")
                content = content.replace(old_nav, new_nav)
                
                # Replace </body> with js_template + </body>
                js_injected = js_template.format(quarter=quarter)
                content = content.replace("</body>", js_injected)
                
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                print(f"Already injected in {dirname}")
