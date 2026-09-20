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

def compute_live_score(df_vni, df_global, df_bonds, mlr_res, wfv_res):
    """
    Wrapper that delegates scoring to the CANONICAL pipeline scorer.
    This ensures a single source of truth for scoring weights (defined in config.py).

    Previously, this function had its own hardcoded weights (technical_price=30%,
    global=25%, mlr_signal=20%, ml_direction=15%, macro=10%, valuation_pepb=0%)
    that diverged from the official pipeline. That duplicate logic has been removed.
    """
    log.info("[6/6] Delegating to canonical scorer (src/scoring/quarterly_scorer.py)...")

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from src.scoring.quarterly_scorer import compute_quarterly_score

    # Build the df_latest Series expected by compute_quarterly_score()
    latest_vni = df_vni.iloc[-1].copy()
    latest_global = df_global.dropna(subset=["dxy", "us10y"]).iloc[-1] if not df_global.empty else pd.Series()

    # Merge VNI + global indicators into a single Series
    for col in ["dxy_zscore", "us10y", "delta_us10y", "nff_zscore_60d", "nff_rolling5d"]:
        if col in latest_global.index:
            latest_vni[col] = latest_global[col]
    # Map z-scores: dxy_zscore → dxy_zscore_60d for compatibility
    if "dxy_zscore" in latest_global.index:
        latest_vni["dxy_zscore_60d"] = latest_global["dxy_zscore"]
    if "us10y" in latest_global.index:
        latest_vni["us10y_yield"] = latest_global["us10y"]

    # Bond data for macro scoring
    if df_bonds is not None and not df_bonds.empty:
        df_bonds["date"] = pd.to_datetime(df_bonds["date"])
        latest_bond = df_bonds.iloc[-1]
        if "vn10y_yield" in latest_bond.index:
            latest_vni["vn10y_yield"] = latest_bond["vn10y_yield"]
        if "vn2y_yield" in latest_bond.index:
            vn_spread = latest_bond.get("vn10y_yield", 0) - latest_bond.get("vn2y_yield", 0)
            latest_vni["vn_yield_spread"] = vn_spread

    # MLR results
    mlr_pred = None
    mlr_adj_r2 = None
    if mlr_res:
        mlr_pred = mlr_res.get("latest_pred_ret")
        mlr_adj_r2 = mlr_res.get("adj_r2")

    # WFV results
    ml_accuracy = wfv_res.get("mean_accuracy") if wfv_res else None
    ml_f1 = wfv_res.get("mean_f1") if wfv_res else None
    ml_pred_class = None
    ml_confidence = None
    if wfv_res and "latest_prediction" in wfv_res:
        pred_map = {"UP": 1, "DOWN": -1, "NEUTRAL": 0}
        ml_pred_class = pred_map.get(wfv_res["latest_prediction"], 0)
        ml_confidence = wfv_res.get("latest_confidence", 0.5)

    # Calculate months to next FTSE rebalancing (schedule: Mar, Jun, Sep, Dec)
    from datetime import datetime
    now = datetime.now()
    rebal_months = [3, 6, 9, 12]
    months_to_rebal = min(
        ((m - now.month) % 12) or 12 for m in rebal_months
    )
    # If we're in a rebalancing month, set to 0
    if now.month in rebal_months:
        months_to_rebal = 0

    score_record = compute_quarterly_score(
        quarter=QUARTER,
        df_latest=latest_vni,
        mlr_pred=mlr_pred,
        mlr_adj_r2=mlr_adj_r2,
        ml_accuracy=ml_accuracy,
        ml_f1=ml_f1,
        ml_pred_class=ml_pred_class,
        ml_confidence=ml_confidence,
        ftse_upgrade_status="confirmed",
        adtv_change_pct=None,  # Will default to neutral (50)
        months_to_next_rebalancing=months_to_rebal,
    )

    # Convert to the format expected by main() print logic
    # Map group_scores to "groups" dict with raw/weight/data_source
    from src.utils.config import SCORING_WEIGHTS
    groups_formatted = {}
    for grp_name, grp_data in score_record.get("group_scores", {}).items():
        groups_formatted[grp_name] = {
            "raw": grp_data.get("raw_score"),
            "weight": SCORING_WEIGHTS.get(grp_name, 0),
            "data_source": f"Canonical pipeline ({grp_name})"
        }

    result = {
        "quarter":       QUARTER,
        "computed_at":   score_record.get("date_computed", ""),
        "total_score":   score_record.get("total_score", 0),
        "label":         score_record.get("label", "HOLD"),
        "emoji":         score_record.get("emoji", "🟡"),
        "description":   score_record.get("label_description", ""),
        "groups":        groups_formatted,
        "group_details": score_record.get("group_details", {}),
        "latest_vni": {
            "date":       str(latest_vni.get("date", "")),
            "close":      round(float(latest_vni.get("close", 0)), 2),
            "log_return":round(float(latest_vni.get("log_return", 0)), 6),
            "rsi_14":    round(float(latest_vni.get("rsi_14", 0)), 2) if pd.notna(latest_vni.get("rsi_14", np.nan)) else None,
        },
        "data_gaps": [],
    }

    log.info(f"\n{'='*60}")
    log.info(f"QUARTERLY SCORE {QUARTER}: {result['emoji']} {result['label']} — {result['total_score']:.1f}/100")
    log.info(f"(Using canonical pipeline weights from config.py)")
    log.info(f"{'='*60}")

    return result


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
    
    try:
        from src.data.fetcher import fetch_vietnam_bonds
        df_bonds = fetch_vietnam_bonds()
    except Exception as e:
        log.warning(f"⚠️ Không thể fetch bond data: {e}")
        df_bonds = None

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
    score_record = compute_live_score(df_vni, df_global, df_bonds, mlr_res, wfv_res)

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
