import pandas as pd
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier
import numpy as np

df_ml = pd.read_parquet("debug_df_ml.parquet")
print(df_ml.columns.tolist())
print(df_ml.shape)

exclude = {"date", "open", "high", "low", "close", "volume",
           "index", "target", "target_binary", "forward_return",
           "log_return", "weekly_return", "monthly_return"}
feature_cols = [c for c in df_ml.columns
                if c not in exclude
                and df_ml[c].dtype in ["float64", "float32", "int64", "int32"]
                and float(pd.to_numeric(df_ml[c], errors="coerce").std(skipna=True) or 0) > 1e-10]

df_clean = df_ml[feature_cols + ["target"]].dropna()
print("df_clean shape:", df_clean.shape)

X = df_clean[feature_cols].values
y = df_clean["target"].values.astype(int)

y_unique = np.unique(y)
label_map = {v: i for i, v in enumerate(y_unique)}
y_mapped = np.array([label_map[v] for v in y])

clf = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, eval_metric="mlogloss", verbosity=0)

clf.fit(X, y_mapped)
y_pred = clf.predict(X)
print("Accuracy:", accuracy_score(y_mapped, y_pred))

importances = clf.feature_importances_
df_fi = pd.DataFrame({
    "feature": feature_cols,
    "importance": importances
}).sort_values("importance", ascending=False).head(5)
print(df_fi)
