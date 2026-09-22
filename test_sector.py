import pandas as pd
df = pd.read_parquet("https://raw.githubusercontent.com/FTU-kudo/PE_PB_HOSE_stocks/main/data/sector_history.parquet")
print("Columns:", df.columns.tolist())
print(df.head())
