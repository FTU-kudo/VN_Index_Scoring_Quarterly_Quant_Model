import urllib.request
import json
req = urllib.request.Request('https://api.github.com/repos/FTU-kudo/VN_Index_Scoring_Quarterly_Quant_Model/actions/runs?per_page=5', headers={'User-Agent': 'Mozilla/5.0'})
res = urllib.request.urlopen(req)
data = json.loads(res.read())
with open('actions_log.txt', 'w', encoding='utf-8') as f:
    for r in data.get('workflow_runs', []):
        f.write(f"ID: {r['id']}, Name: {r['name']}, Status: {r['status']}, Conclusion: {r['conclusion']}, Created: {r['created_at']}, Updated: {r['updated_at']}\n")
