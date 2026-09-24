import yfinance as yf
import pandas as pd
import numpy as np

def main():
    print("Fetching BZ=F...")
    bz_raw = yf.download("BZ=F", start="2019-12-01", end="2026-10-01", interval="1d", progress=False, auto_adjust=True)
    
    bz = bz_raw[["Close"]].copy()
    if isinstance(bz.columns, pd.MultiIndex):
        bz.columns = bz.columns.droplevel(1)
    bz.columns = ["close"]
    bz.index = pd.to_datetime(bz.index).tz_localize(None)
    
    bz["pct_change_5d"] = bz["close"].pct_change(5)
    bz = bz[bz.index >= "2020-01-01"].copy()
    bz["year_quarter"] = bz.index.to_period("Q")
    
    def calc_shock(group):
        if len(group) < 5:
            return pd.Series({"max_weekly_change": 0, "n_shock_days": 0, "oil_shock_score": 0, "q_return": 0})
        
        max_weekly_change = group["pct_change_5d"].max()
        
        # Threshold 8% as proposed
        threshold = 0.08
        n_shock_days = (group["pct_change_5d"] > threshold).sum()
        q_return = group["close"].iloc[-1] / group["close"].iloc[0] - 1
        
        if max_weekly_change > threshold:
            # We scale the score out of 100 roughly. 
            # 24% max change -> 24 * 1.5 + 12 * 0.5 = 36 + 6 = 42
            score = (max_weekly_change * 100) * 1.5 + (n_shock_days * 0.5)
        else:
            score = 0
            
        return pd.Series({
            "max_weekly_change": max_weekly_change,
            "n_shock_days": n_shock_days,
            "oil_shock_score": score,
            "q_return": q_return
        })

    results = bz.groupby("year_quarter").apply(calc_shock, include_groups=False).reset_index()
    
    results["max_weekly_change"] = (results["max_weekly_change"] * 100).round(2).astype(str) + "%"
    results["q_return"] = (results["q_return"] * 100).round(2).astype(str) + "%"
    results["oil_shock_score"] = results["oil_shock_score"].round(2)
    
    print(results.to_markdown(index=False))

if __name__ == "__main__":
    main()
