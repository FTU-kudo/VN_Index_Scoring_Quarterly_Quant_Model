import sys
from pathlib import Path
import pandas as pd
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.utils.config import SCORES_DIR, EXPORTS_DIR

def test_market_structure():
    history_path = SCORES_DIR / "quarterly_scores_history.parquet"
    if not history_path.exists():
        print("Scores history not found!")
        return

    df = pd.read_parquet(history_path)
    print("Checking JSON vs Parquet for all quarters...")
    
    match_count = 0
    total = len(df)
    
    for _, row in df.iterrows():
        quarter = row["quarter"]
        # extract from parquet
        parquet_raw = row.get("market_structure_raw", -1)
        
        json_file = EXPORTS_DIR / f"score_{quarter.replace('-', '_')}.json"
        if not json_file.exists():
            continue
            
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # extract from json
        json_raw = -1
        for grp in data.get("group_scores", []):
            if grp.get("group") == "market_structure":
                json_raw = grp.get("raw_score", -1)
                break
                
        if abs(parquet_raw - json_raw) > 0.01:
            print(f"[{quarter}] DISCREPANCY: Parquet={parquet_raw} vs JSON={json_raw}")
        else:
            match_count += 1
            
    print(f"Matched {match_count} out of {total} quarters.")
    if match_count == total:
        print("SUCCESS: 100% data consistency between parquet and JSON.")

if __name__ == "__main__":
    test_market_structure()
