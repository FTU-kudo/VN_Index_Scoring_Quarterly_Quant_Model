import pandas as pd
df = pd.read_parquet("https://raw.githubusercontent.com/FTU-kudo/PE_PB_HOSE_stocks/main/data/ticker_history.parquet")
print(df.columns.tolist())
print(df.head())
