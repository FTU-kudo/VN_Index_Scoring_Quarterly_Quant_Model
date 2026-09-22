import pandas as pd
import numpy as np
from src.data.fetcher import fetch_vnindex_ohlcv, compute_vni_returns
from src.features.technical_features import add_technical_indicators
from src.models.ml.ml_model import build_ml_features, create_target_variable

df_vni = fetch_vnindex_ohlcv()
df_vni = compute_vni_returns(df_vni)
df_all = add_technical_indicators(df_vni)
df_ml = build_ml_features(df_all)
df_ml = create_target_variable(df_ml)

df_clean = df_ml[["log_return_lag1", "forward_return", "target"]].dropna()
print(df_clean.head(10))

from sklearn.metrics import confusion_matrix
from xgboost import XGBClassifier

X = df_clean[["log_return_lag1"]].values
y = df_clean["target"].values
clf = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, eval_metric="mlogloss", verbosity=0)
# Map y
y_unique = np.unique(y)
label_map = {v: i for i, v in enumerate(y_unique)}
y_mapped = np.array([label_map[v] for v in y])
clf.fit(X, y_mapped)
y_pred = clf.predict(X)
print("Accuracy:", np.mean(y_pred == y_mapped))
print(confusion_matrix(y_mapped, y_pred))
