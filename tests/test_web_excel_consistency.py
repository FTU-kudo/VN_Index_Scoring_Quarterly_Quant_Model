"""Cross-artifact contract: web reports must be projections of score JSON."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = (
    "macro_monetary", "global_intermarket", "valuation_leverage",
    "quant_model", "ml_forecast", "market_structure",
)


def test_all_quarterly_html_scores_match_json_source():
    mismatches = []
    for path in sorted((ROOT / "output/exports").glob("score_*.json")):
        quarter = path.stem.removeprefix("score_")
        record = json.loads(path.read_text(encoding="utf-8"))["quarterly_score"]
        html = (ROOT / "output/reports" / quarter / "index.html").read_text(encoding="utf-8")
        score_big = re.search(r'class="score-big"[^>]*>([\d.]+)</div>', html)
        raw = re.search(r"Raw Composite: ([\d.]+)", html)
        cards = re.findall(r'class="card-value"[^>]*>([\d.]+)</div>', html)
        expected = [record["calibrated_score"], record["total_score"]]
        expected += [record["group_scores"][group]["raw_score"] for group in GROUPS]
        actual = ([float(score_big.group(1)), float(raw.group(1))] +
                  [float(value) for value in cards[:6]]) if score_big and raw else []
        if len(actual) != len(expected) or any(abs(a - e) > 0.11 for a, e in zip(actual, expected)):
            mismatches.append((quarter, actual, expected))
    assert not mismatches, mismatches
