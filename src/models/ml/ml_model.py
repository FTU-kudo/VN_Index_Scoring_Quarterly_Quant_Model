"""
ml_model.py — Machine Learning cho Dự báo Hướng đi VN-Index
============================================================
Kiến trúc ML đề xuất:

  Tier 1 (Nhanh, giải thích được):
    - XGBoost Classifier : Dự báo UP/DOWN/NEUTRAL (T+5)
    - LightGBM Classifier: Tốc độ huấn luyện nhanh, ít memory hơn XGBoost

  Tier 2 (Phức tạp, sequence-aware):
    - LSTM (PyTorch/Keras): Dự báo chuỗi thời gian với memory dài hạn

Phương pháp đánh giá chống Overfitting:
  - Walk-Forward Validation (WFV): Không dùng train_test_split ngẫu nhiên
  - Mỗi fold: train trên [t-n, t], test trên [t, t+k]
  - Metrics: Accuracy, Precision, Recall, F1-Score (weighted)
  - Sharpe Ratio của tín hiệu (backtested signal quality)

Feature Engineering đặc thù:
  - Lag features: X_{t-1}, X_{t-2}, ..., X_{t-20}
  - Rolling statistics: rolling_mean_5, rolling_std_20
  - Technical indicators: RSI_14, MACD, Bollinger Band position
  - Cross-asset features: DXY_zscore, US10Y_delta
  - Fundamental features: PE_zscore, foreign_flow_momentum
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import (
    ML_LOOKBACK_DAYS, ML_FORECAST_DAYS, ML_TARGET_THRESHOLD,
    ML_N_SPLITS_WFV, FEATURES_DIR
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Feature Engineering cho ML
# ═══════════════════════════════════════════════════════════════════════════════

def build_ml_features(
    df: pd.DataFrame,
    lookback: int = ML_LOOKBACK_DAYS,
    price_col: str = "close",
    return_col: str = "log_return"
) -> pd.DataFrame:
    """
    Tạo feature matrix cho ML từ dữ liệu tổng hợp.

    Feature groups:
      A. Price momentum & volatility (từ VNI OHLCV)
      B. Technical indicators (RSI, MACD, BB)
      C. Cross-asset (từ global_features)
      D. Macro (từ macro_features)
      E. Valuation (từ valuation_features)

    Parameters
    ----------
    df      : DataFrame tổng hợp (đã merge tất cả feature groups)
    lookback: Cửa sổ rolling (ngày giao dịch)
    price_col  : Cột giá đóng cửa
    return_col : Cột log-return

    Returns
    -------
    DataFrame với tất cả ML features
    """
    df = df.copy().sort_values("date").reset_index(drop=True)

    # ── A. Price Momentum & Volatility ────────────────────────────────────────
    if return_col in df.columns:
        df[f"return_lag1"]   = df[return_col].shift(1)
        df[f"return_lag2"]   = df[return_col].shift(2)
        df[f"return_lag5"]   = df[return_col].shift(5)
        df[f"return_lag10"]  = df[return_col].shift(10)
        df[f"return_lag20"]  = df[return_col].shift(20)

        # Realized volatility rolling
        for w in [5, 10, 20, 60]:
            df[f"rvol_{w}d"] = df[return_col].rolling(w, min_periods=w//2).std() * np.sqrt(252)

        # Return momentum
        for w in [5, 10, 20]:
            df[f"ret_mom_{w}d"] = df[return_col].rolling(w, min_periods=w//2).sum()

    # ── B. Technical Indicators (Pure Pandas/Numpy) ──────────────────────────
    if price_col in df.columns:
        ta_df = df[[price_col]].copy()
        ta_df.columns = ["close"]

        # RSI 14
        delta = ta_df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD (12, 26, 9)
        ema12 = ta_df["close"].ewm(span=12, adjust=False).mean()
        ema26 = ta_df["close"].ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema12 - ema26
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # Bollinger Bands (20, 2σ)
        sma20 = ta_df["close"].rolling(window=20).mean()
        std20 = ta_df["close"].rolling(window=20).std()
        df["bb_upper"] = sma20 + (std20 * 2)
        df["bb_lower"] = sma20 - (std20 * 2)
        df["bb_mid"] = sma20
        df["bb_pct"] = (ta_df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

        # EMA 20/50
        df["ema_20"] = ta_df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = ta_df["close"].ewm(span=50, adjust=False).mean()
        df["ema_cross"] = (df["ema_20"] > df["ema_50"]).astype(int)

    # ── C. Cross-asset features (từ global_features) ─────────────────────────
    cross_asset_cols = [
        "delta_dxy", "dxy_zscore_60d", "delta_us10y",
        "us10y_zscore_1y", "nff_zscore_60d", "nff_momentum",
        "nff_consecutive_sell_days"
    ]
    # Các cột này đã được merge vào df từ trước — chỉ tạo lag
    for col in cross_asset_cols:
        if col in df.columns:
            df[f"{col}_lag1"] = df[col].shift(1)
            df[f"{col}_lag5"] = df[col].shift(5)

    # ── D. Macro features ─────────────────────────────────────────────────────
    macro_cols = ["delta_omo_rate", "usd_vnd_pct_change", "ir_policy_shift"]
    for col in macro_cols:
        if col in df.columns:
            df[f"{col}_lag1"] = df[col].shift(1)

    # ── E. Valuation features ─────────────────────────────────────────────────
    val_cols = ["pe_zscore", "pb_zscore", "margin_risk_score"]
    for col in val_cols:
        if col in df.columns:
            df[f"{col}_lag1"] = df[col].shift(1)

    return df


def create_target_variable(
    df: pd.DataFrame,
    horizon: int = ML_FORECAST_DAYS,
    threshold: float = ML_TARGET_THRESHOLD,
    return_col: str = "log_return"
) -> pd.DataFrame:
    """
    Tạo biến mục tiêu cho phân loại (UP / DOWN / NEUTRAL).

    Target: Forward return T+horizon
      - UP      (+1): forward_return > +threshold
      - DOWN    (-1): forward_return < -threshold
      - NEUTRAL ( 0): |forward_return| <= threshold

    Parameters
    ----------
    horizon   : Số phiên dự báo (T+5 = 1 tuần)
    threshold : Ngưỡng phân loại (mặc định ±0.5%)
    """
    df = df.copy()
    df["forward_return"] = df[return_col].shift(-horizon).rolling(horizon).sum()

    def _classify(r):
        if pd.isna(r):
            return np.nan
        if r > threshold:
            return 1    # UP
        elif r < -threshold:
            return -1   # DOWN
        else:
            return 0    # NEUTRAL

    df["target"] = df["forward_return"].apply(_classify)
    df["target_binary"] = (df["target"] == 1).astype(int)  # Binary: UP vs not-UP
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Walk-Forward Validation (Time-Series Cross-Validation)
# ═══════════════════════════════════════════════════════════════════════════════

def walk_forward_splits(
    n: int,
    n_splits: int = ML_N_SPLITS_WFV,
    train_min_frac: float = 0.5
) -> List[Tuple[int, int, int, int]]:
    """
    Tạo các fold cho Walk-Forward Validation.

    Mỗi fold có dạng:
      [train_start, train_end] → [test_start, test_end]

    Không có data leakage: test luôn sau train.
    Expanding window: train window ngày càng lớn.

    Parameters
    ----------
    n            : Tổng số quan sát
    n_splits     : Số fold validation
    train_min_frac : Tỷ lệ tối thiểu để train (0.5 = 50%)

    Returns
    -------
    List of (train_start, train_end, test_start, test_end) tuples
    """
    train_min = int(n * train_min_frac)
    step = (n - train_min) // (n_splits + 1)

    splits = []
    for i in range(n_splits):
        train_end   = train_min + (i + 1) * step
        test_start  = train_end
        test_end    = min(test_start + step, n)
        splits.append((0, train_end, test_start, test_end))
        if test_end >= n:
            break

    logger.info(f"[WFV] Tạo {len(splits)} fold với expanding window")
    return splits


def evaluate_wfv(
    df_ml: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "target",
    model_type: str = "xgboost",
    n_splits: int = ML_N_SPLITS_WFV
) -> Dict:
    """
    Walk-Forward Validation: train và evaluate model qua nhiều fold.

    Parameters
    ----------
    df_ml       : DataFrame với features và target
    feature_cols: Danh sách feature columns
    target_col  : Cột mục tiêu phân loại
    model_type  : 'xgboost' | 'lightgbm'
    n_splits    : Số fold

    Returns
    -------
    dict: fold_metrics, mean_accuracy, mean_f1, overall_summary
    """
    # Lọc dữ liệu
    available_features = [f for f in feature_cols if f in df_ml.columns]
    df_clean = df_ml[available_features + [target_col]].dropna()
    X = df_clean[available_features].values
    y = df_clean[target_col].values.astype(int)
    n = len(X)

    splits = walk_forward_splits(n, n_splits=n_splits)

    fold_metrics = []
    all_preds, all_true = [], []

    for fold_idx, (tr_s, tr_e, te_s, te_e) in enumerate(splits, 1):
        X_train, y_train = X[tr_s:tr_e], y[tr_s:tr_e]
        X_test,  y_test  = X[te_s:te_e], y[te_s:te_e]

        if len(X_test) == 0:
            continue

        # Khởi tạo model
        try:
            if model_type == "xgboost":
                from xgboost import XGBClassifier
                clf = XGBClassifier(
                    n_estimators=200, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, eval_metric="mlogloss",
                    verbosity=0, use_label_encoder=False
                )
            elif model_type == "lightgbm":
                from lightgbm import LGBMClassifier
                clf = LGBMClassifier(
                    n_estimators=200, max_depth=4, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, verbose=-1
                )
            else:
                raise ValueError(f"model_type không hỗ trợ: {model_type}")
        except ImportError as e:
            logger.error(f"[ML-WFV] {e} — pip install {model_type}")
            raise

        # LGBMClassifier cần labels từ 0
        y_unique = np.unique(y_train)
        label_map = {v: i for i, v in enumerate(y_unique)}
        y_train_mapped = np.array([label_map[v] for v in y_train])
        y_test_mapped  = np.array([label_map.get(v, -1) for v in y_test])

        clf.fit(X_train, y_train_mapped)
        y_pred = clf.predict(X_test)

        # Metrics
        try:
            from sklearn.metrics import accuracy_score, f1_score, precision_score
            valid_mask = (y_test_mapped != -1)
            if valid_mask.sum() == 0:
                continue

            acc  = accuracy_score(y_test_mapped[valid_mask], y_pred[valid_mask])
            f1   = f1_score(y_test_mapped[valid_mask], y_pred[valid_mask],
                            average="weighted", zero_division=0)
            prec = precision_score(y_test_mapped[valid_mask], y_pred[valid_mask],
                                   average="weighted", zero_division=0)

            fold_metrics.append({
                "fold": fold_idx,
                "train_size":  tr_e - tr_s,
                "test_size":   te_e - te_s,
                "accuracy":    round(acc,  4),
                "f1_weighted": round(f1,   4),
                "precision":   round(prec, 4),
            })
            all_preds.extend(y_pred[valid_mask].tolist())
            all_true.extend(y_test_mapped[valid_mask].tolist())

        except ImportError:
            logger.warning("[ML-WFV] sklearn chưa cài — pip install scikit-learn")

    # Tổng hợp kết quả
    if fold_metrics:
        df_metrics = pd.DataFrame(fold_metrics)
        summary = {
            "model_type":      model_type,
            "n_folds":         len(fold_metrics),
            "mean_accuracy":   round(df_metrics["accuracy"].mean(), 4),
            "std_accuracy":    round(df_metrics["accuracy"].std(), 4),
            "mean_f1":         round(df_metrics["f1_weighted"].mean(), 4),
            "fold_metrics_df": df_metrics,
        }
        logger.info(
            f"[ML-WFV] {model_type.upper()} | {len(fold_metrics)} folds\n"
            f"  Mean Accuracy = {summary['mean_accuracy']:.1%} ± {summary['std_accuracy']:.1%}\n"
            f"  Mean F1       = {summary['mean_f1']:.4f}"
        )
        return summary
    else:
        logger.warning("[ML-WFV] Không có fold nào hoàn thành")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Feature Importance
# ═══════════════════════════════════════════════════════════════════════════════

def get_feature_importance(
    df_ml: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "target",
    model_type: str = "xgboost",
    top_n: int = 20
) -> pd.DataFrame:
    """
    Huấn luyện trên toàn bộ data và lấy feature importance.

    Returns
    -------
    DataFrame: feature, importance, rank (top_n features)
    """
    available = [f for f in feature_cols if f in df_ml.columns]
    df_clean = df_ml[available + [target_col]].dropna()
    X = df_clean[available].values
    y = df_clean[target_col].values.astype(int)

    # Normalize labels
    y_unique = np.unique(y)
    label_map = {v: i for i, v in enumerate(y_unique)}
    y_mapped = np.array([label_map[v] for v in y])

    try:
        if model_type == "xgboost":
            from xgboost import XGBClassifier
            clf = XGBClassifier(n_estimators=300, max_depth=4, random_state=42,
                                verbosity=0, eval_metric="mlogloss",
                                use_label_encoder=False)
        else:
            from lightgbm import LGBMClassifier
            clf = LGBMClassifier(n_estimators=300, max_depth=4, random_state=42,
                                 verbose=-1)
    except ImportError as e:
        logger.error(f"[FI] {e}")
        return pd.DataFrame()

    clf.fit(X, y_mapped)
    importances = clf.feature_importances_

    df_fi = pd.DataFrame({
        "feature":    available,
        "importance": importances
    }).sort_values("importance", ascending=False).head(top_n)
    df_fi["rank"] = range(1, len(df_fi) + 1)

    logger.info(f"[FI] Top-5 features:\n{df_fi.head(5).to_string(index=False)}")
    return df_fi.reset_index(drop=True)
