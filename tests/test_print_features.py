import pandas as pd
df_all = pd.read_parquet("data/features/valuation_leverage_features.parquet")
print(df_all.columns.tolist())
