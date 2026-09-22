import pandas as pd
from src.features.technical_features import add_technical_indicators
from src.models.ml.ml_model import build_ml_features, create_target_variable
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

df_all = pd.read_parquet("data/features/valuation_leverage_features.parquet")
# Wait, this is just val features. I need the full merged df.
