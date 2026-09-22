import pandas as pd
import numpy as np

df = pd.DataFrame({"close": [100, 101, 102, 101, 99, 100, 102, 105, 104, 103]})
df["log_return"] = np.log(df["close"] / df["close"].shift(1))

horizon = 3
df["forward_return"] = df["log_return"].shift(-horizon).rolling(horizon).sum()
print(df[["close", "log_return", "forward_return"]])
