"""
live_scoring_Q3_2026.py
=======================
Script tự chứa, chạy thực sự với dữ liệu thật.
KHÔNG bịa đặt, KHÔNG đoán mò — mọi số liệu đều từ API hoặc
được tính toán minh bạch từ dữ liệu thực tế.

Nguồn dữ liệu THỰC TẾ:
  ✅ vnstock 4.0.2   → VN-Index OHLCV (VCI source)
  ✅ yfinance 1.5.1  → DXY, US10Y Yield, SPX
  ✅ Tính từ OHLCV   → Technical indicators (RSI, MACD, BB)
  ✅ VN_PE_PB_analysis → P/E, P/B (nếu pipeline đã chạy)

Nguồn dữ liệu CẦN THỦ CÔNG (SẼ BÁO RÕ NẾU THIẾU):
  ⚠️ SBV             → Lãi suất OMO, USD/VND chính thức
  ⚠️ HOSE/HNX        → Dư nợ margin (báo cáo tháng)
  ⚠️ SBV             → M2, tín dụng (báo cáo tháng)

Chạy:
  python live_scoring_Q3_2026.py
"""

import sys
# Fix Windows console encoding (cp1252 -> utf-8)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import warnings
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Logging chuẩn ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("live_scoring")

# ── Khoảng thời gian ──────────────────────────────────────────────────────────
END_DATE   = "2026-09-19"
START_DATE = "2021-01-01"   # 5+ năm để tính Z-score hợp lệ
QUARTER    = "2026-Q3"

SEPARATOR = "=" * 70

# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 1: FETCH VN-INDEX OHLCV (vnstock)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_vnindex(start=START_DATE, end=END_DATE):
    log.info(f"[1/6] Fetch VN-Index OHLCV từ vnstock ({start} → {end})...")
    try:
        # vnstock 4.0.2: dùng API mới (Vnstock class deprecated từ 31/08/2025)
        try:
            from vnstock.api.quote import Quote
            q = Quote(symbol="VNINDEX", source="VCI")
            df = q.history(start=start, end=end, interval="1D")
        except ImportError:
            # Fallback: thử Vnstock cũ nếu phiên bản cũ hơn
            from vnstock import Vnstock
            vn = Vnstock(symbol="VNINDEX", source="VCI")
            df = vn.quote.history(start=start, end=end, interval="1D")

        df = df.reset_index() if df.index.name else df
        df.columns = [c.lower() for c in df.columns]

        # Chuẩn hóa cột — vnstock mới trả về 'time' hoặc 'date'
        if "time" in df.columns:
            df = df.rename(columns={"time": "date"})
        elif df.index.name in ["time", "date"]:
            df = df.reset_index().rename(columns={df.index.name: "date"})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Tính returns
        df["log_return"]     = np.log(df["close"] / df["close"].shift(1))
        df["ret_5d"]         = df["close"].pct_change(5)
        df["ret_20d"]        = df["close"].pct_change(20)
        df["ret_60d"]        = df["close"].pct_change(60)

        # Realized volatility
        df["rvol_20d"]       = df["log_return"].rolling(20).std() * np.sqrt(252)
        df["rvol_60d"]       = df["log_return"].rolling(60).std() * np.sqrt(252)

        # Rolling stats
        df["ma20"]           = df["close"].rolling(20).mean()
        df["ma50"]           = df["close"].rolling(50).mean()
        df["ma200"]          = df["close"].rolling(200).mean()
        df["price_vs_ma200"] = df["close"] / df["ma200"] - 1

        # Drawdown từ peak 60 ngày
        df["peak_60d"]       = df["close"].rolling(60, min_periods=20).max()
        df["drawdown_60d"]   = df["close"] / df["peak_60d"] - 1

        log.info(f"  ✅ {len(df)} phiên VNI ({df['date'].min().date()} → {df['date'].max().date()})")
        log.info(f"  VNI close cuối cùng: {df['close'].iloc[-1]:,.2f}")
        return df

    except Exception as e:
        log.error(f"  ❌ Lỗi fetch VNI: {e}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 2: FETCH GLOBAL INDICATORS (yfinance)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_global(start=START_DATE, end=END_DATE):
    log.info(f"[2/6] Fetch Global Indicators từ yfinance (DXY, US10Y, SPX)...")
    try:
        import yfinance as yf

        tickers = {
            "DX-Y.NYB": "dxy",      # US Dollar Index
            "^TNX":     "us10y",    # US Treasury 10Y Yield
            "^GSPC":    "spx",      # S&P 500
            "^VIX":     "vix",      # Volatility Index
        }

        frames = {}
        for yf_ticker, name in tickers.items():
            try:
                raw = yf.download(
                    yf_ticker, start=start, end=end,
                    interval="1d", progress=False, auto_adjust=True
                )
                if raw.empty:
                    log.warning(f"  ⚠️ {yf_ticker}: trả về trống")
                    continue

                # Xử lý MultiIndex columns từ yfinance mới
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)

                s = raw["Close"].copy()
                s.index = pd.to_datetime(s.index).tz_localize(None)
                frames[name] = s
                log.info(f"  ✅ {name.upper()}: {len(s)} ngày, last={s.iloc[-1]:.2f}")
            except Exception as e:
                log.warning(f"  ⚠️ {yf_ticker} ({name}): {e}")

        if not frames:
            raise ValueError("Không lấy được bất kỳ global indicator nào")

        df_g = pd.DataFrame(frames)
        df_g.index.name = "date"
        df_g = df_g.reset_index()

        # First differences và returns
        if "dxy" in df_g.columns:
            df_g["delta_dxy"]    = df_g["dxy"].pct_change()
            df_g["dxy_zscore"]   = (
                (df_g["dxy"] - df_g["dxy"].rolling(252, min_periods=60).mean()) /
                df_g["dxy"].rolling(252, min_periods=60).std()
            )
            df_g["dxy_5d_chg"]  = df_g["dxy"].pct_change(5)

        if "us10y" in df_g.columns:
            df_g["delta_us10y"]  = df_g["us10y"].diff()
            df_g["us10y_zscore"] = (
                (df_g["us10y"] - df_g["us10y"].rolling(252, min_periods=60).mean()) /
                df_g["us10y"].rolling(252, min_periods=60).std()
            )

        if "spx" in df_g.columns:
            df_g["spx_ret_5d"]   = df_g["spx"].pct_change(5)

        if "vix" in df_g.columns:
            df_g["vix_zscore"]   = (
                (df_g["vix"] - df_g["vix"].rolling(252, min_periods=60).mean()) /
                df_g["vix"].rolling(252, min_periods=60).std()
            )

        return df_g

    except Exception as e:
        log.error(f"  ❌ Lỗi fetch global: {e}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 3: TECHNICAL INDICATORS (tính từ OHLCV thực tế)
# ══════════════════════════════════════════════════════════════════════════════

def compute_technical_indicators(df_vni):
    """
    Tính Technical Indicators bằng thuần numpy/pandas.
    KHÔNG dùng pandas-ta (không tương thích Python 3.14).
    """
    log.info("[3/6] Tính Technical Indicators (pure pandas/numpy)...")
    df = df_vni.copy()
    close = df["close"]

    # ── RSI 14 (Wilder smoothing) ─────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta.clip(upper=0))
    # Wilder EMA = rolling EMA với com=13
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ── MACD (12, 26, 9) ──────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, min_periods=12).mean()
    ema26 = close.ewm(span=26, min_periods=26).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, min_periods=9).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────────
    df["bb_mid"]   = close.rolling(20, min_periods=10).mean()
    bb_std         = close.rolling(20, min_periods=10).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std
    denom = df["bb_upper"] - df["bb_lower"]
    df["bb_pct"]   = np.where(denom > 0, (close - df["bb_lower"]) / denom, np.nan)

    # ── EMA 20, 50, 200 ───────────────────────────────────────────────────────
    df["ema_20"]  = close.ewm(span=20,  min_periods=20).mean()
    df["ema_50"]  = close.ewm(span=50,  min_periods=50).mean()
    df["ema_200"] = close.ewm(span=200, min_periods=150).mean()

    # ── ATR 14 (Average True Range) ───────────────────────────────────────────
    if "high" in df.columns and "low" in df.columns:
        high_low   = df["high"] - df["low"]
        high_close = (df["high"] - close.shift(1)).abs()
        low_close  = (df["low"]  - close.shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.ewm(com=13, min_periods=14).mean()
        df["atr_pct"] = df["atr_14"] / close  # ATR as % of price

    # ── Stochastic %K, %D ─────────────────────────────────────────────────────
    if "high" in df.columns and "low" in df.columns:
        low14  = df["low"].rolling(14, min_periods=7).min()
        high14 = df["high"].rolling(14, min_periods=7).max()
        denom_s = high14 - low14
        df["stoch_k"] = np.where(denom_s > 0, (close - low14) / denom_s * 100, 50)
        df["stoch_d"] = pd.Series(df["stoch_k"]).rolling(3).mean().values

    log.info(f"  ✅ RSI, MACD, BB, EMA20/50/200, ATR, Stochastic — pure numpy/pandas")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 4: TÍCH HỢP DATA & FEATURE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def build_feature_matrix(df_vni, df_global):
    log.info("[4/6] Xây dựng Feature Matrix...")

    df = df_vni.copy()

    # Merge global data
    df_g = df_global.copy()
    df_g["date"] = pd.to_datetime(df_g["date"])
    df = df.merge(df_g, on="date", how="left")

    # Forward-fill global data (global market có thể thiếu ngày)
    global_cols = [c for c in df_g.columns if c != "date"]
    for col in global_cols:
        if col in df.columns:
            df[col] = df[col].ffill()

    # Lag features cho model
    lag_cols = ["log_return", "delta_dxy", "delta_us10y", "rsi_14", "macd_hist"]
    for col in lag_cols:
        if col in df.columns:
            for lag in [1, 2, 5]:
                df[f"{col}_lag{lag}"] = df[col].shift(lag)

    # Target: forward return 20 ngày (1 tháng)
    df["target_ret_20d"] = df["close"].pct_change(20).shift(-20)
    df["target_dir_20d"] = np.sign(df["target_ret_20d"].fillna(0)).astype(int)

    log.info(f"  ✅ Feature matrix: {len(df)} rows × {len(df.columns)} cols")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 5: MÔ HÌNH ĐỊNH LƯỢNG
# ══════════════════════════════════════════════════════════════════════════════

# ── 5A: Multiple Linear Regression ───────────────────────────────────────────

def run_mlr(df):
    log.info("[5A] Chạy MLR (OLS với Newey-West HAC)...")
    results = {}

    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson
        from statsmodels.tsa.stattools import adfuller

        # Feature columns khả dụng từ dữ liệu thực
        candidate_features = {
            "delta_dxy":       "Δ DXY (USD Index)",
            "delta_us10y":     "Δ US10Y Yield",
            "rsi_14":          "RSI 14",
            "macd_hist":       "MACD Histogram",
            "bb_pct":          "Bollinger Band %",
            "rvol_20d":        "Realized Volatility 20D",
            "price_vs_ma200":  "Price vs MA200 (%)",
            "drawdown_60d":    "Drawdown từ peak 60D",
            "vix_zscore":      "VIX Z-score",
            "spx_ret_5d":      "SPX 5D Return",
            "log_return_lag1": "VNI Return lag 1",
            "log_return_lag5": "VNI Return lag 5",
        }

        available = {k: v for k, v in candidate_features.items() if k in df.columns}
        feature_cols = list(available.keys())
        target_col   = "log_return"

        # Lấy dữ liệu train: từ 2021-01-01 đến 2026-09-19 bỏ 20 ngày cuối (target forward)
        df_clean = df[feature_cols + [target_col]].dropna()
        # Chỉ dùng historical data (không có forward leakage)
        df_train = df_clean.iloc[:-20] if len(df_clean) > 40 else df_clean

        X = sm.add_constant(df_train[feature_cols])
        y = df_train[target_col]

        # Fit OLS với Newey-West HAC
        ols = sm.OLS(y, X)
        res = ols.fit(cov_type="HAC", cov_kwds={"maxlags": 5})

        # Lưu kết quả
        results["n_obs"]      = len(df_train)
        results["r2"]         = res.rsquared
        results["adj_r2"]     = res.rsquared_adj
        results["aic"]        = res.aic
        results["bic"]        = res.bic
        results["dw"]         = durbin_watson(res.resid)
        results["features"]   = feature_cols
        results["feature_labels"] = available
        results["params"]     = res.params.to_dict()
        results["pvalues"]    = res.pvalues.to_dict()
        results["conf_int"]   = res.conf_int().to_dict()

        # ADF test residuals
        try:
            adf_p = adfuller(res.resid.dropna(), autolag="AIC")[1]
            results["adf_resid_pvalue"] = adf_p
            results["resid_stationary"]  = (adf_p < 0.05)
        except Exception:
            results["adf_resid_pvalue"] = None

        # Dự báo cho ngày mới nhất
        latest_row = df[feature_cols].dropna().iloc[-1]
        X_latest = pd.DataFrame([latest_row])
        X_latest = sm.add_constant(X_latest, has_constant="add")
        try:
            pred_ret = float(res.predict(X_latest).iloc[0])
            results["latest_pred_ret"] = pred_ret
        except Exception:
            results["latest_pred_ret"] = None

        log.info(f"  ✅ MLR: R²={results['r2']:.4f}, Adj-R²={results['adj_r2']:.4f}")
        log.info(f"     N obs={results['n_obs']}, DW={results['dw']:.3f}")
        log.info(f"     ADF residuals p={results.get('adf_resid_pvalue', 'N/A')}")

    except ImportError:
        log.error("  ❌ statsmodels chưa cài — pip install statsmodels")
        results["error"] = "statsmodels not installed"

    return results


# ── 5B: Walk-Forward Validation (XGBoost nếu có, else Logistic) ──────────────

def run_wfv_classification(df):
    log.info("[5B] Walk-Forward Validation — Dự báo hướng đi 20D...")
    results = {}

    candidate_features = [
        "delta_dxy", "delta_us10y", "rsi_14", "macd_hist", "bb_pct",
        "rvol_20d", "price_vs_ma200", "drawdown_60d", "vix_zscore",
        "spx_ret_5d", "log_return_lag1", "log_return_lag5",
        "delta_dxy_lag1", "delta_us10y_lag1", "ret_5d", "ret_20d"
    ]
    available_feat = [f for f in candidate_features if f in df.columns]

    # Target: direction 20D forward (không dùng NEUTRAL để đơn giản hóa)
    target = "target_dir_20d"
    if target not in df.columns:
        log.warning("  ⚠️ Không có target_dir_20d — bỏ qua WFV")
        return {}

    df_ml = df[available_feat + [target]].dropna()
    # Loại 20 ngày cuối (không có forward return thực tế)
    df_ml = df_ml.iloc[:-20]

    if len(df_ml) < 100:
        log.warning(f"  ⚠️ Chỉ có {len(df_ml)} obs sau dropna — quá ít để WFV")
        return {}

    X = df_ml[available_feat].values
    y = df_ml[target].values
    # Chuyển {-1, 0, 1} → {0, 1, 2} cho classifier
    unique_y = sorted(np.unique(y))
    class_map = {cls: idx for idx, cls in enumerate(unique_y)}
    y_mapped = np.array([class_map[v] for v in y])
    n_classes = len(unique_y)
    reverse_map = {idx: cls for cls, idx in class_map.items()}
    label_names = {idx: {-1: "DOWN", 0: "NEUTRAL", 1: "UP"}.get(cls, str(cls))
                   for idx, cls in reverse_map.items()}

    n = len(X)
    n_splits = 6
    train_min = int(n * 0.5)
    step = (n - train_min) // (n_splits + 1)

    fold_metrics = []

    # Chọn model
    try:
        from xgboost import XGBClassifier
        clf_factory = lambda: XGBClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7, random_state=42,
            eval_metric="mlogloss", verbosity=0
        )
        model_name = "XGBoost"
    except ImportError:
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
            clf_factory = lambda: Pipeline([
                ("scaler", StandardScaler()),
                ("lr", LogisticRegression(C=1.0, max_iter=500, random_state=42))
            ])
            model_name = "Logistic Regression"
        except ImportError:
            log.warning("  ⚠️ Không có XGBoost hoặc sklearn")
            return {}

    from sklearn.metrics import accuracy_score, f1_score, precision_score

    for i in range(n_splits):
        tr_end  = train_min + (i + 1) * step
        te_start = tr_end
        te_end   = min(te_start + step, n)
        if te_end <= te_start:
            break

        X_tr, y_tr = X[:tr_end], y_mapped[:tr_end]
        X_te, y_te = X[te_start:te_end], y_mapped[te_start:te_end]

        # Đảm bảo có ít nhất 2 classes trong train
        if len(np.unique(y_tr)) < 2:
            continue

        try:
            clf = clf_factory()
            clf.fit(X_tr, y_tr)
            y_pred = clf.predict(X_te)

            acc  = accuracy_score(y_te, y_pred)
            f1   = f1_score(y_te, y_pred, average="weighted", zero_division=0)
            prec = precision_score(y_te, y_pred, average="weighted", zero_division=0)

            fold_metrics.append({
                "fold": i + 1,
                "train_size": tr_end,
                "test_size": te_end - te_start,
                "accuracy": round(acc, 4),
                "f1_weighted": round(f1, 4),
                "precision": round(prec, 4),
            })
        except Exception as e:
            log.warning(f"  Fold {i+1} error: {e}")

    if fold_metrics:
        df_folds = pd.DataFrame(fold_metrics)
        results["model"]         = model_name
        results["n_features"]    = len(available_feat)
        results["features_used"] = available_feat
        results["n_folds"]       = len(fold_metrics)
        results["mean_accuracy"] = round(df_folds["accuracy"].mean(), 4)
        results["std_accuracy"]  = round(df_folds["accuracy"].std(), 4)
        results["mean_f1"]       = round(df_folds["f1_weighted"].mean(), 4)
        results["fold_details"]  = fold_metrics

        log.info(f"  ✅ WFV ({model_name}): {len(fold_metrics)} folds")
        log.info(f"     Accuracy = {results['mean_accuracy']:.1%} ± {results['std_accuracy']:.1%}")
        log.info(f"     F1 weighted = {results['mean_f1']:.4f}")

        # Dự báo mới nhất
        try:
            clf_final = clf_factory()
            clf_final.fit(X, y_mapped)
            X_latest = df[available_feat].dropna().iloc[-1:].values
            pred_class = clf_final.predict(X_latest)[0]
            pred_label = {0: "DOWN", 1: "NEUTRAL", 2: "UP"}
            results["latest_prediction"] = pred_label.get(pred_class, "UNKNOWN")
            try:
                proba = clf_final.predict_proba(X_latest)[0]
                results["latest_proba"] = {
                    k: round(float(v), 3)
                    for k, v in zip(["DOWN", "NEUTRAL", "UP"], proba)
                }
                results["latest_confidence"] = round(float(max(proba)), 3)
            except Exception:
                pass
            log.info(f"     Latest prediction: {results['latest_prediction']}")
        except Exception as e:
            log.warning(f"  Dự báo mới nhất lỗi: {e}")

    return results


# ── 5C: Feature Importance ────────────────────────────────────────────────────

def compute_feature_importance(df, wfv_results):
    if not wfv_results or "features_used" not in wfv_results:
        return {}

    feat_cols = wfv_results["features_used"]
    target = "target_dir_20d"
    df_ml = df[feat_cols + [target]].dropna().iloc[:-20]

    if len(df_ml) < 50:
        return {}

    X = df_ml[feat_cols].values
    y_raw = df_ml[target].values
    unique_y = sorted(np.unique(y_raw))
    class_map = {cls: idx for idx, cls in enumerate(unique_y)}
    y = np.array([class_map[v] for v in y_raw])

    fi_dict = {}
    try:
        from xgboost import XGBClassifier
        clf = XGBClassifier(n_estimators=200, max_depth=3, random_state=42,
                            eval_metric="mlogloss", verbosity=0)
        clf.fit(X, y)
        fi = clf.feature_importances_
        fi_dict = dict(sorted(zip(feat_cols, fi), key=lambda x: x[1], reverse=True))
    except ImportError:
        try:
            from sklearn.ensemble import RandomForestClassifier
            clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
            clf.fit(X, y)
            fi = clf.feature_importances_
            fi_dict = dict(sorted(zip(feat_cols, fi), key=lambda x: x[1], reverse=True))
        except ImportError:
            pass

    return fi_dict


# ── 5D: Backtesting tín hiệu RSI + MACD ──────────────────────────────────────

def run_backtest_simple_signals(df):
    """
    Backtest 2 chiến lược tín hiệu đơn giản dựa trên thực tế:
      Signal 1: RSI + MA Crossover
      Signal 2: MACD Histogram > 0

    Chỉ dùng data có sẵn, không nhìn trước tương lai.
    """
    log.info("[5D] Backtest tín hiệu kỹ thuật...")
    results = {}

    df_bt = df.copy()
    df_bt = df_bt.dropna(subset=["close", "rsi_14"]).reset_index(drop=True)

    # ── Signal 1: RSI-based (buy RSI<35, sell RSI>65) ─────────────────────────
    df_bt["sig1"] = 0
    df_bt.loc[df_bt["rsi_14"] < 35, "sig1"] = 1    # Buy
    df_bt.loc[df_bt["rsi_14"] > 65, "sig1"] = -1   # Sell

    # ── Signal 2: MA Cross (ma20 > ma50 = buy) ────────────────────────────────
    if "ma20" in df_bt.columns and "ma50" in df_bt.columns:
        df_bt["sig2"] = 0
        df_bt.loc[df_bt["ma20"] > df_bt["ma50"], "sig2"] = 1
        df_bt.loc[df_bt["ma20"] <= df_bt["ma50"], "sig2"] = -1

    # ── Signal 3: MACD > 0 ───────────────────────────────────────────────────
    if "macd_hist" in df_bt.columns:
        df_bt["sig3"] = np.where(df_bt["macd_hist"] > 0, 1, -1)

    # Tính PnL cho từng signal (next day return)
    df_bt["next_ret"] = df_bt["log_return"].shift(-1)

    for sig_name in ["sig1", "sig2", "sig3"]:
        if sig_name not in df_bt.columns:
            continue
        sig = df_bt[sig_name].shift(1)   # Tín hiệu từ hôm qua
        daily_pnl = sig * df_bt["next_ret"]
        valid = daily_pnl.dropna()

        cum_return = np.expm1(valid.sum())
        n_trading_years = len(valid) / 252

        if n_trading_years > 0:
            ann_return = (1 + cum_return) ** (1 / n_trading_years) - 1
        else:
            ann_return = 0

        # Sharpe (annualized)
        if valid.std() > 0:
            sharpe = valid.mean() / valid.std() * np.sqrt(252)
        else:
            sharpe = 0

        # Max Drawdown
        cum_log = valid.cumsum()
        roll_max = cum_log.cummax()
        dd = (cum_log - roll_max)
        max_dd = np.expm1(dd.min())

        # Win rate
        win_rate = (valid > 0).mean()

        results[sig_name] = {
            "strategy":         sig_name,
            "n_days":           int(len(valid)),
            "cumulative_return": round(float(cum_return), 4),
            "annualized_return": round(float(ann_return), 4),
            "sharpe_ratio":     round(float(sharpe), 4),
            "max_drawdown":     round(float(max_dd), 4),
            "win_rate":         round(float(win_rate), 4),
        }

    # Buy & Hold benchmark
    bh = df_bt["log_return"].dropna()
    bh_cum = np.expm1(bh.sum())
    bh_ann = (1 + bh_cum) ** (1 / (len(bh) / 252)) - 1
    bh_sharpe = bh.mean() / bh.std() * np.sqrt(252) if bh.std() > 0 else 0

    results["buy_hold"] = {
        "strategy":         "Buy & Hold",
        "cumulative_return": round(float(bh_cum), 4),
        "annualized_return": round(float(bh_ann), 4),
        "sharpe_ratio":     round(float(bh_sharpe), 4),
    }

    log.info(f"  ✅ Backtest xong {len(results)-1} signal + B&H benchmark")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BƯỚC 6: QUARTERLY SCORING
# ══════════════════════════════════════════════════════════════════════════════

def compute_live_score(df_vni, df_global, mlr_res, wfv_res):
    """
    Tính điểm Q3/2026 dựa trên DỮ LIỆU THỰC TẾ.
    Chỉ chấm điểm những nhóm có data thực, còn lại báo rõ MISSING.
    """
    log.info("[6/6] Tính Quarterly Score dựa trên dữ liệu thực...")

    latest_vni    = df_vni.iloc[-1]
    latest_global = df_global.dropna(subset=["dxy", "us10y"]).iloc[-1] if not df_global.empty else pd.Series()

    scores = {}
    details = {}

    # ── Nhóm A: Technical & Price (100% từ dữ liệu thực) ─────────────────────
    ta_score = 50.0  # Default
    ta_details = {}

    if "rsi_14" in latest_vni and pd.notna(latest_vni["rsi_14"]):
        rsi = latest_vni["rsi_14"]
        ta_details["rsi_14"] = rsi
        # RSI 30–50: mua, 50–70: trung tính/giữ, >70: bán, <30: rất rẻ
        if rsi < 30:
            rsi_s = 85
        elif rsi < 40:
            rsi_s = 70
        elif rsi < 55:
            rsi_s = 60
        elif rsi < 70:
            rsi_s = 45
        else:
            rsi_s = 25
        ta_details["rsi_score"] = rsi_s

    if "price_vs_ma200" in latest_vni and pd.notna(latest_vni["price_vs_ma200"]):
        p_vs_ma200 = latest_vni["price_vs_ma200"]
        ta_details["price_vs_ma200_pct"] = round(p_vs_ma200 * 100, 2)
        # Dưới MA200 → rẻ hơn, trên MA200 nhiều → overbought
        if p_vs_ma200 < -0.10:
            ma_s = 80
        elif p_vs_ma200 < 0:
            ma_s = 65
        elif p_vs_ma200 < 0.05:
            ma_s = 60
        elif p_vs_ma200 < 0.15:
            ma_s = 50
        else:
            ma_s = 35
        ta_details["ma200_score"] = ma_s

    if "drawdown_60d" in latest_vni and pd.notna(latest_vni["drawdown_60d"]):
        dd = latest_vni["drawdown_60d"]
        ta_details["drawdown_from_peak_60d_pct"] = round(dd * 100, 2)
        # Deep drawdown → cơ hội nhưng cũng risk
        if dd < -0.15:
            dd_s = 70
        elif dd < -0.08:
            dd_s = 60
        elif dd < -0.03:
            dd_s = 55
        else:
            dd_s = 50

    if "bb_pct" in latest_vni and pd.notna(latest_vni["bb_pct"]):
        bb = latest_vni["bb_pct"]
        ta_details["bb_position_pct"] = round(bb * 100, 2)
        bb_s = max(0, min(100, (1 - bb) * 80 + 10))
    else:
        bb_s = 50

    ta_score = np.nanmean([
        ta_details.get("rsi_score", 50),
        ta_details.get("ma200_score", 50),
        bb_s
    ])
    scores["technical_price"] = {"raw": round(ta_score, 2), "weight": 0.30,
                                  "data_source": "vnstock OHLCV (THỰC TẾ)"}
    details["technical_price"] = ta_details

    # ── Nhóm B: Global Intermarket (yfinance — THỰC TẾ) ──────────────────────
    global_score = 50.0
    global_details = {}

    if pd.notna(latest_global.get("dxy_zscore", np.nan)):
        dxy_z = latest_global["dxy_zscore"]
        global_details["dxy"]        = round(latest_global.get("dxy", 0), 2)
        global_details["dxy_zscore"] = round(dxy_z, 3)
        dxy_s = max(0, min(100, 50 - dxy_z * 20))
    else:
        dxy_s = 50.0

    if pd.notna(latest_global.get("us10y", np.nan)):
        us10y = latest_global["us10y"]
        global_details["us10y_yield"] = round(us10y, 3)
        # US10Y: 4-4.5% = neutral, >5% = bất lợi, <3% = thuận lợi
        us10y_s = max(0, min(100, 100 - us10y * 18))
        global_details["us10y_score"] = round(us10y_s, 1)
    else:
        us10y_s = 50.0

    if pd.notna(latest_global.get("vix_zscore", np.nan)):
        vix_z = latest_global["vix_zscore"]
        global_details["vix_zscore"] = round(vix_z, 3)
        vix_s = max(0, min(100, 50 - vix_z * 15))
    else:
        vix_s = 50.0

    if pd.notna(latest_global.get("spx_ret_5d", np.nan)):
        spx_r = latest_global["spx_ret_5d"]
        global_details["spx_5d_return_pct"] = round(spx_r * 100, 2)
        spx_s = max(0, min(100, 50 + spx_r * 500))
    else:
        spx_s = 50.0

    global_score = np.nanmean([dxy_s, us10y_s, vix_s, spx_s])
    scores["global_intermarket"] = {"raw": round(global_score, 2), "weight": 0.25,
                                     "data_source": "yfinance DXY+US10Y+VIX+SPX (THỰC TẾ)"}
    details["global_intermarket"] = global_details

    # ── Nhóm C: MLR Signal (tính từ dữ liệu thực) ────────────────────────────
    mlr_score = 50.0
    mlr_details = {}

    if mlr_res and "adj_r2" in mlr_res:
        mlr_details["adj_r2"]  = round(mlr_res["adj_r2"], 4)
        mlr_details["r2"]      = round(mlr_res["r2"], 4)
        mlr_details["dw"]      = round(mlr_res["dw"], 3)
        mlr_details["n_obs"]   = mlr_res["n_obs"]

        if mlr_res.get("latest_pred_ret") is not None:
            pred = mlr_res["latest_pred_ret"]
            mlr_details["predicted_return"] = round(pred, 6)
            mlr_score = max(0, min(100, 50 + pred * 3000))

        # Thưởng chất lượng model
        adj_r2_bonus = mlr_res.get("adj_r2", 0) * 10
        mlr_score = min(100, mlr_score + adj_r2_bonus)

    scores["mlr_signal"] = {"raw": round(mlr_score, 2), "weight": 0.20,
                             "data_source": "OLS trên VNI+DXY+US10Y+RSI (THỰC TẾ)"}
    details["mlr_signal"] = mlr_details

    # ── Nhóm D: ML Directional Signal ─────────────────────────────────────────
    ml_score = 50.0
    ml_details = {}

    if wfv_res and "mean_accuracy" in wfv_res:
        ml_details["model"]          = wfv_res["model"]
        ml_details["mean_accuracy"]  = round(wfv_res["mean_accuracy"], 4)
        ml_details["std_accuracy"]   = round(wfv_res["std_accuracy"], 4)
        ml_details["mean_f1"]        = round(wfv_res["mean_f1"], 4)
        ml_details["n_folds_wfv"]    = wfv_res["n_folds"]

        if "latest_prediction" in wfv_res:
            pred_dir = wfv_res["latest_prediction"]
            ml_details["direction_forecast"] = pred_dir
            conf = wfv_res.get("latest_confidence", 0.5)
            ml_details["confidence"] = conf

            if pred_dir == "UP":
                ml_score = 65 + conf * 20
            elif pred_dir == "DOWN":
                ml_score = 35 - conf * 20
            else:
                ml_score = 50

            # Điều chỉnh theo accuracy
            acc_adj = (wfv_res["mean_accuracy"] - 0.5) * 20
            ml_score = max(0, min(100, ml_score + acc_adj))

    scores["ml_direction"] = {"raw": round(ml_score, 2), "weight": 0.15,
                               "data_source": f"XGBoost/LR WFV {wfv_res.get('n_folds', 0)} folds (THỰC TẾ)"}
    details["ml_direction"] = ml_details

    # ── Nhóm E: Macro & Tiền tệ — BÁO RÕ THIẾU DATA ─────────────────────────
    scores["macro_monetary"] = {
        "raw": None,
        "weight": 0.10,
        "data_source": "⚠️ THIẾU DATA: SBV API không public. Cần nhập thủ công macro_sbv.csv"
    }
    details["macro_monetary"] = {
        "status": "MISSING",
        "lý do": "SBV (Ngân hàng Nhà nước VN) không có public REST API. Dữ liệu lãi suất OMO, tỷ giá trung tâm cần thu thập thủ công từ sbv.gov.vn",
        "cần": "data/raw/macro_sbv.csv với schema: date, omo_overnight_rate, deposit_12m_rate, usd_vnd_official",
        "nguồn": "https://www.sbv.gov.vn/webcenter/portal/en/home/fm/ti"
    }

    # ── Nhóm F: Định giá P/E, P/B — Tích hợp từ VN_PE_PB_analysis nếu có ──
    pepb_score = None
    pepb_details = {}

    pepb_path = Path(__file__).parent.parent / "VN_PE_PB_analysis" / "data" / "sector_history.parquet"
    if pepb_path.exists():
        try:
            df_pepb = pd.read_parquet(pepb_path)
            df_pepb["date"] = pd.to_datetime(df_pepb["date"])
            if "median_pe" in df_pepb.columns:
                market_pe = df_pepb.groupby("date")["median_pe"].median()
                zscore_pe = (
                    (market_pe - market_pe.rolling(252*5, min_periods=252).mean()) /
                    market_pe.rolling(252*5, min_periods=252).std()
                )
                if not zscore_pe.empty and pd.notna(zscore_pe.iloc[-1]):
                    z = zscore_pe.iloc[-1]
                    pepb_details["pe_zscore_5y"] = round(z, 3)
                    pepb_details["median_pe_market"] = round(market_pe.iloc[-1], 2)
                    pepb_score = max(0, min(100, 50 - z * 25))
                    pepb_details["source"] = "VN_PE_PB_analysis pipeline (THỰC TẾ)"
        except Exception as e:
            pepb_details["error"] = str(e)

    if pepb_score is None:
        pepb_details["status"] = "MISSING — VN_PE_PB_analysis pipeline chưa chạy"
        pepb_details["solution"] = "Chạy: python scripts/daily_compute.py trong VN_PE_PB_analysis"

    scores["valuation_pepb"] = {
        "raw": pepb_score,
        "weight": 0.0,  # Không tính nếu không có data
        "data_source": "VN_PE_PB_analysis" if pepb_score else "⚠️ MISSING"
    }
    details["valuation_pepb"] = pepb_details

    # ── Tổng hợp điểm (chỉ tính nhóm có data) ────────────────────────────────
    available_groups = {k: v for k, v in scores.items() if v["raw"] is not None}
    if not available_groups:
        log.error("Không có nhóm nào có dữ liệu!")
        return {}

    # Re-normalize weights
    total_weight = sum(v["weight"] for v in available_groups.values())
    weighted_total = sum(
        v["raw"] * v["weight"] / total_weight
        for v in available_groups.values()
        if v["weight"] > 0
    )

    # Phân loại
    def classify(s):
        if s >= 80: return "BUY", "🟢", "Môi trường rất thuận lợi"
        if s >= 65: return "ACCUMULATE", "🔵", "Tích lũy dần"
        if s >= 50: return "HOLD", "🟡", "Trung lập — chờ xác nhận"
        if s >= 35: return "REDUCE", "🟠", "Giảm tỷ trọng"
        return "SELL", "🔴", "Phòng thủ"

    label, emoji, desc = classify(weighted_total)

    final = {
        "quarter":          QUARTER,
        "computed_at":      datetime.now().strftime("%Y-%m-%d %H:%M ICT"),
        "total_score":      round(weighted_total, 2),
        "label":            label,
        "emoji":            emoji,
        "description":      desc,
        "groups":           scores,
        "group_details":    details,
        "latest_vni": {
            "date":       str(latest_vni.get("date", "")),
            "close":      round(float(latest_vni.get("close", 0)), 2),
            "log_return": round(float(latest_vni.get("log_return", 0)), 6),
            "rsi_14":     round(float(latest_vni.get("rsi_14", 0)), 2) if pd.notna(latest_vni.get("rsi_14", np.nan)) else None,
        },
        "data_gaps": [k for k, v in scores.items() if v["raw"] is None],
    }

    log.info(f"\n{'='*60}")
    log.info(f"QUARTERLY SCORE {QUARTER}: {emoji} {label} — {weighted_total:.1f}/100")
    log.info(f"(Tính từ {len(available_groups)}/{len(scores)} nhóm có data)")
    log.info(f"{'='*60}")

    return final


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def print_section(title):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def main():
    print(f"\n{'#'*70}")
    print(f"  VN-INDEX QUANTITATIVE SCORING — {QUARTER}")
    print(f"  Chạy lúc: {datetime.now().strftime('%Y-%m-%d %H:%M ICT')}")
    print(f"  Dữ liệu: {START_DATE} → {END_DATE}")
    print(f"  Yêu cầu: TRUNG THỰC — Chỉ kết quả từ dữ liệu thực tế")
    print(f"{'#'*70}\n")

    # ── Step 1–4: Fetch & Feature Engineering ────────────────────────────────
    df_vni    = fetch_vnindex()
    df_global = fetch_global()
    df_vni    = compute_technical_indicators(df_vni)
    df        = build_feature_matrix(df_vni, df_global)

    # ── Step 5A: MLR ─────────────────────────────────────────────────────────
    mlr_res = run_mlr(df)

    # ── Step 5B: Walk-Forward Validation ─────────────────────────────────────
    wfv_res = run_wfv_classification(df)

    # ── Step 5C: Feature Importance ─────────────────────────────────────────
    fi = compute_feature_importance(df, wfv_res)

    # ── Step 5D: Backtest ────────────────────────────────────────────────────
    bt_res = run_backtest_simple_signals(df)

    # ── Step 6: Scoring ───────────────────────────────────────────────────────
    score_record = compute_live_score(df_vni, df_global, mlr_res, wfv_res)

    # ══════════════════════════════════════════════════════════════════════════
    # IN KẾT QUẢ CHI TIẾT
    # ══════════════════════════════════════════════════════════════════════════

    # ── VNI hiện tại ─────────────────────────────────────────────────────────
    print_section("1. VN-INDEX — GIÁ TRỊ THỰC TẾ HIỆN TẠI")
    latest = df_vni.iloc[-1]
    print(f"  Ngày:            {latest['date'].date()}")
    print(f"  VNI Close:       {latest['close']:>10,.2f}")
    print(f"  Log Return:      {latest['log_return']:>+.4%}")
    print(f"  RSI 14:          {latest['rsi_14']:>10.2f}")
    print(f"  MA20:            {latest['ma20']:>10,.2f}")
    print(f"  MA200:           {latest['ma200']:>10,.2f}")
    print(f"  Price/MA200:     {latest['price_vs_ma200']:>+.2%}")
    print(f"  Drawdown 60D:    {latest['drawdown_60d']:>+.2%}")
    print(f"  Rvol 20D (ann):  {latest['rvol_20d']:>10.2%}")
    if pd.notna(latest.get("bb_pct")):
        print(f"  BB Position:     {latest['bb_pct']:>10.1%}")

    # ── Global ───────────────────────────────────────────────────────────────
    print_section("2. GLOBAL INDICATORS — DỮ LIỆU THỰC TẾ (yfinance)")
    latest_g = df_global.dropna(subset=["dxy"]).iloc[-1]
    print(f"  Ngày:            {latest_g['date'].date()}")
    if "dxy" in latest_g:
        print(f"  DXY:             {latest_g['dxy']:>10.2f}  (Z={latest_g.get('dxy_zscore',0):+.2f}σ)")
    if "us10y" in latest_g:
        print(f"  US10Y Yield:     {latest_g['us10y']:>10.2f}%  (Z={latest_g.get('us10y_zscore',0):+.2f}σ)")
    if "vix" in latest_g and pd.notna(latest_g.get("vix")):
        print(f"  VIX:             {latest_g['vix']:>10.2f}  (Z={latest_g.get('vix_zscore',0):+.2f}σ)")
    if "spx" in latest_g and pd.notna(latest_g.get("spx")):
        print(f"  SPX:             {latest_g['spx']:>12,.2f}")
        print(f"  SPX 5D return:   {latest_g.get('spx_ret_5d',0):>+.2%}")

    # ── MLR ──────────────────────────────────────────────────────────────────
    print_section("3. KẾT QUẢ HỒI QUY ĐA BIẾN (OLS + Newey-West HAC)")
    if mlr_res and "adj_r2" in mlr_res:
        print(f"  N observations:  {mlr_res['n_obs']}")
        print(f"  R²:              {mlr_res['r2']:.4f}")
        print(f"  Adjusted R²:     {mlr_res['adj_r2']:.4f}")
        print(f"  AIC:             {mlr_res['aic']:.2f}")
        print(f"  Durbin-Watson:   {mlr_res['dw']:.3f}  ({'OK' if 1.5 < mlr_res['dw'] < 2.5 else '⚠️ autocorr'})")
        if mlr_res.get("adf_resid_pvalue") is not None:
            stat = "✅ Stationary" if mlr_res["resid_stationary"] else "⚠️ Non-stationary"
            print(f"  ADF Residuals:   p={mlr_res['adf_resid_pvalue']:.4f}  {stat}")

        print(f"\n  {'Variable':<25} {'Beta':>10}  {'P-value':>8}  {'Sig':>4}")
        print(f"  {'-'*55}")
        params = mlr_res.get("params", {})
        pvals  = mlr_res.get("pvalues", {})
        feat_labels = mlr_res.get("feature_labels", {})
        for feat in mlr_res.get("features", []):
            b = params.get(feat, np.nan)
            p = pvals.get(feat, np.nan)
            lbl = feat_labels.get(feat, feat)[:22]
            sig = "***" if p < 0.01 else ("**" if p < 0.05 else ("*" if p < 0.10 else ""))
            print(f"  {lbl:<25} {b:>+10.5f}  {p:>8.4f}  {sig:>4}")

        if mlr_res.get("latest_pred_ret") is not None:
            print(f"\n  ▶ Dự báo log-return hiện tại: {mlr_res['latest_pred_ret']:+.5f} ({mlr_res['latest_pred_ret']*100:+.3f}%)")
    else:
        print("  ⚠️ MLR không chạy được (kiểm tra statsmodels)")

    # ── WFV ──────────────────────────────────────────────────────────────────
    print_section("4. WALK-FORWARD VALIDATION — MÁY HỌC DỰ BÁO HƯỚNG ĐI 20D")
    if wfv_res and "mean_accuracy" in wfv_res:
        print(f"  Model:           {wfv_res['model']}")
        print(f"  Features:        {wfv_res['n_features']} features")
        print(f"  N Folds (WFV):   {wfv_res['n_folds']}")
        print(f"  Mean Accuracy:   {wfv_res['mean_accuracy']:.1%} ± {wfv_res['std_accuracy']:.1%}")
        print(f"  Mean F1 (wtd):   {wfv_res['mean_f1']:.4f}")
        print(f"\n  Fold-by-Fold:")
        print(f"  {'Fold':>4}  {'Train':>6}  {'Test':>5}  {'Acc':>7}  {'F1':>7}")
        for fold in wfv_res.get("fold_details", []):
            print(f"  {fold['fold']:>4}  {fold['train_size']:>6}  {fold['test_size']:>5}  {fold['accuracy']:>7.1%}  {fold['f1_weighted']:>7.4f}")

        if "latest_prediction" in wfv_res:
            conf = wfv_res.get("latest_confidence", 0)
            print(f"\n  ▶ Dự báo hướng T+20D: {wfv_res['latest_prediction']} (confidence: {conf:.1%})")
            if "latest_proba" in wfv_res:
                proba = wfv_res["latest_proba"]
                print(f"    Xác suất: DOWN={proba.get('DOWN',0):.1%}  NEUTRAL={proba.get('NEUTRAL',0):.1%}  UP={proba.get('UP',0):.1%}")
    else:
        print("  ⚠️ WFV không chạy được — kiểm tra XGBoost/sklearn")

    # ── Feature Importance ────────────────────────────────────────────────────
    if fi:
        print_section("5. FEATURE IMPORTANCE (Top 10)")
        total_fi = sum(fi.values())
        for rank, (feat, imp) in enumerate(list(fi.items())[:10], 1):
            pct = imp / total_fi * 100
            bar = "█" * int(pct / 3) + "░" * max(0, 10 - int(pct / 3))
            print(f"  #{rank:>2} {feat:<30} [{bar}] {pct:>5.1f}%")

    # ── Backtest ─────────────────────────────────────────────────────────────
    print_section("6. BACKTEST KẾT QUẢ (2021–2026)")
    if bt_res:
        print(f"  {'Strategy':<22}  {'Cum Ret':>9}  {'Ann Ret':>9}  {'Sharpe':>7}  {'Max DD':>8}  {'WinRate':>8}")
        print(f"  {'-'*75}")
        for name, r in bt_res.items():
            if name == "buy_hold":
                print(f"  {'─'*75}")
                print(f"  {'Buy & Hold (Benchmark)':<22}  {r['cumulative_return']:>+9.1%}  {r['annualized_return']:>+9.1%}  {r['sharpe_ratio']:>7.3f}  {'N/A':>8}  {'N/A':>8}")
            else:
                print(f"  {name:<22}  {r['cumulative_return']:>+9.1%}  {r['annualized_return']:>+9.1%}  {r['sharpe_ratio']:>7.3f}  {r['max_drawdown']:>+8.1%}  {r['win_rate']:>8.1%}")

    # ── Quarterly Score ───────────────────────────────────────────────────────
    print_section(f"7. QUARTERLY SCORE — {QUARTER}")
    if score_record:
        total = score_record["total_score"]
        print(f"\n  {score_record['emoji']} TỔNG ĐIỂM: {total:.2f}/100  →  {score_record['label']}")
        print(f"  {score_record['description']}")
        print(f"\n  Chi tiết từng nhóm:")
        print(f"  {'Nhóm':<25}  {'Score':>7}  {'Trọng số':>9}  {'Nguồn dữ liệu'}")
        print(f"  {'-'*75}")
        for grp, gdata in score_record["groups"].items():
            score_str = f"{gdata['raw']:.1f}" if gdata["raw"] is not None else "N/A"
            w = gdata["weight"]
            src = gdata["data_source"][:35]
            print(f"  {grp:<25}  {score_str:>7}  {w:>9.0%}  {src}")

        if score_record.get("data_gaps"):
            print(f"\n  ⚠️ DATA GAPS (không tính vào điểm):")
            for gap in score_record["data_gaps"]:
                print(f"    - {gap}: {score_record['group_details'][gap].get('lý do','N/A')}")

    # ── Lưu kết quả ──────────────────────────────────────────────────────────
    output = {
        "metadata": {
            "quarter":      QUARTER,
            "generated_at": datetime.now().isoformat(),
            "data_range":   f"{START_DATE} → {END_DATE}",
            "disclaimer":   "Kết quả từ dữ liệu thực tế. Nguồn thiếu được báo rõ."
        },
        "latest_market_data": {
            "vni_close":    float(df_vni.iloc[-1]["close"]),
            "vni_date":     str(df_vni.iloc[-1]["date"].date()),
            "dxy":          float(df_global.dropna(subset=["dxy"]).iloc[-1]["dxy"]) if "dxy" in df_global.columns else None,
            "us10y":        float(df_global.dropna(subset=["us10y"]).iloc[-1]["us10y"]) if "us10y" in df_global.columns else None,
        },
        "mlr_results":  {k: v for k, v in mlr_res.items() if not isinstance(v, dict)} if mlr_res else {},
        "wfv_results":  {k: v for k, v in wfv_res.items() if k not in ["fold_details", "features_used"]} if wfv_res else {},
        "backtest":     bt_res,
        "quarterly_score": score_record,
        "feature_importance_top10": dict(list(fi.items())[:10]) if fi else {},
    }

    out_dir = Path(__file__).parent / "output" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"live_score_{QUARTER.replace('-','_')}.json"

    def _conv(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)): return bool(obj)
        if isinstance(obj, (np.ndarray,)): return obj.tolist()
        if isinstance(obj, pd.Timestamp): return str(obj)
        raise TypeError(type(obj))

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=_conv)

    print(f"\n  ✅ Kết quả đã lưu: {out_path}")
    print(f"\n{'#'*70}")
    print("  HOÀN THÀNH — Tất cả số liệu từ API thực tế")
    print(f"{'#'*70}\n")

    return output


if __name__ == "__main__":
    main()
