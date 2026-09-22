import pandas as pd

df_ml = pd.read_parquet("debug_df_ml.parquet")
print(df_ml["date"].value_counts().head())
