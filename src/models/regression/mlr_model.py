"""
mlr_model.py — Mô hình Hồi quy Đa biến DỰ BÁO FORWARD (Predictive MLR)
=======================================================================
Phương trình hồi quy cốt lõi (PREDICTIVE — không phải nowcast):

  R̄_VNI,(t+1..t+h) = α + β₁·Δ IR_t + β₂·Δ DXY_t + β₃·NFF_t + β₄·ZPE_t
                        + β₅·Δ MRG_t + β₆·ΔUS10Y_t + β₇·ΔUSDJPY_t + ε_t

Trong đó:
  R̄_(t+1..t+h) = TRUNG BÌNH log-return/ngày của h phiên KẾ TIẾP
                 (h = MLR_FORECAST_HORIZON_DAYS, mặc định 21 ~ 1 tháng).
                 Features tại t chỉ dùng thông tin đã biết cuối phiên t
                 → dự báo thuần túy, không look-ahead.
  Δ IR      = Thay đổi lãi suất VN 1Y
  Δ DXY     = Pct thay đổi Dollar Index
  NFF       = Net Foreign Flow (tỷ VND)
  ZPE       = Z-score P/E (5Y rolling)
  Δ MRG     = Pct thay đổi dư nợ margin
  Δ US10Y   = Thay đổi lợi suất TPCP Mỹ 10Y

Phương pháp:
  - OLS với Newey-West HAC standard errors, maxlags ≥ horizon để xử lý
    autocorrelation do overlapping forward windows
  - Kiểm định: ADF (stationary), Durbin-Watson (autocorr), VIF (multicollinearity)
  - Train/Test split: 75%/25% (không shuffle — tôn trọng tính thời gian)
  - Đánh giá OUT-OF-SAMPLE trên 25% cuối: hit-rate (đúng dấu), OOS R²
"""

import logging
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import MLR_FORECAST_HORIZON_DAYS

logger = logging.getLogger(__name__)


def make_forward_target(returns: pd.Series, horizon: int) -> pd.Series:
    """
    Tạo target dự báo forward: y_t = mean(r_{t+1}, ..., r_{t+horizon}).

    Per-day scale (chia cho horizon) để giữ tương thích với hệ số quy đổi
    điểm hiện hành. h hàng cuối sẽ là NaN (chưa biết tương lai) — bị loại
    khỏi tập huấn luyện một cách tự nhiên qua dropna().

    KHÔNG chứa r_t (return cùng ngày) — đây là điểm phân biệt then chốt
    giữa mô hình DỰ BÁO và mô hình nowcast.
    """
    if horizon < 1:
        raise ValueError(f"horizon phải ≥ 1, nhận {horizon}")
    r = pd.to_numeric(returns, errors="coerce")
    # shift(-h).rolling(h).sum() tại t = tổng r_{t+1..t+h} (xem ml_model.py)
    return r.shift(-horizon).rolling(horizon).sum() / horizon

# Tên biến cho mô hình MLR lõi (ưu tiên lý thuyết)
CORE_FEATURES = [
    "delta_vn1y_yield",        # β₁: Δ Lợi suất TPCP 1Y
    "delta_dxy",               # β₂: Δ DXY
    "net_foreign_flow_b_vnd",  # β₃: Net Foreign Flow
    "pe_zscore",               # β₄: Z-score P/E
    "delta_margin_debt_pct",   # β₅: Δ Dư nợ margin (%)
    "delta_us10y",             # β₆: Δ US10Y yield
    "delta_usdjpy",            # β₇: Δ USD/JPY (Yen Carry Trade)
]

# Fallback khi P/E, NFF, margin lịch sử thiếu — vẫn fit được trên dữ liệu OHLCV + global
FALLBACK_FEATURES = [
    "delta_dxy",
    "delta_us10y",
    "delta_usdjpy",
    "delta_vn1y_yield",
    "usd_vnd_pct_change",
    "rsi_14",
    "macd_hist",
    "bb_pct",
    "rvol_20d",
    "drawdown_from_peak",
    "price_vs_ma200",
    "log_return_lag1",
    "log_return_lag5",
]

MIN_FEATURE_COVERAGE = 0.55
MIN_MLR_OBS = 80

# Dấu kỳ vọng theo lý thuyết kinh tế
EXPECTED_SIGNS = {
    "delta_vn1y_yield":         -1,   # β₁ < 0: tăng lãi suất → VNI giảm
    "delta_dxy":                -1,   # β₂ < 0: USD mạnh → VNI giảm
    "net_foreign_flow_b_vnd":  +1,   # β₃ > 0: ngoại mua → VNI tăng
    "pe_zscore":                -1,   # β₄ < 0: định giá đắt → mean reversion ↓
    "delta_margin_debt_pct":   -1,   # β₅ < 0: margin tăng nhanh → rủi ro call
    "delta_us10y":             -1,   # β₆ < 0: LS Mỹ tăng → vốn rút khỏi EM
    "delta_usdjpy":            +1,   # β₇ > 0: USD/JPY giảm (Yen mạnh) → VNI giảm
}


class MLRModel:
    """
    Multiple Linear Regression với Newey-West HAC standard errors.

    Attributes
    ----------
    coefs_    : dict {feature: beta}
    pvalues_  : dict {feature: p-value}
    r2_       : float — R-squared
    adj_r2_   : float — Adjusted R-squared
    sign_ok_  : dict {feature: bool} — dấu beta đúng kỳ vọng?
    """

    def __init__(
        self,
        feature_cols: List[str] = None,
        target_col: str = "log_return",
        train_ratio: float = 0.75,
        max_lags_nw: int = 5,   # Newey-West lag truncation (floor)
        horizon: int = MLR_FORECAST_HORIZON_DAYS,  # số phiên forward của target
    ):
        self.feature_cols = feature_cols or CORE_FEATURES
        self.target_col   = target_col
        self.train_ratio  = train_ratio
        self.horizon      = int(horizon)
        # Overlapping forward windows tạo autocorrelation bậc (h-1) trong
        # residuals → NW maxlags tối thiểu phải bằng horizon
        self.max_lags_nw  = max(int(max_lags_nw), self.horizon)
        self.oos_metrics_ = {}

        # Kết quả sau khi fit
        self.coefs_    = {}
        self.pvalues_  = {}
        self.r2_       = None
        self.adj_r2_   = None
        self.sign_ok_  = {}
        self.residuals_ = None
        self.model_     = None

    def _select_usable_features(self, df: pd.DataFrame) -> List[str]:
        """Chọn cột có đủ coverage; bổ sung fallback nếu CORE quá thưa."""
        def _ok(col: str) -> bool:
            if col not in df.columns or col == self.target_col:
                return False
            series = pd.to_numeric(df[col], errors="coerce")
            if float(series.notna().mean()) < MIN_FEATURE_COVERAGE:
                return False
            if float(series.std(skipna=True) or 0) < 1e-10:
                return False
            return True

        available = [f for f in self.feature_cols if _ok(f)]
        missing = [f for f in self.feature_cols if f not in df.columns]
        sparse = [
            f for f in self.feature_cols
            if f in df.columns and f not in available
        ]
        if missing:
            logger.warning(f"[MLR] Thiếu features: {missing} — bỏ qua trong model")
        if sparse:
            logger.warning(f"[MLR] Features quá thưa/hằng (bỏ): {sparse}")

        extra = [f for f in FALLBACK_FEATURES if _ok(f) and f not in available]
        available.extend(extra)
        if extra:
            logger.info(f"[MLR] Bổ sung fallback features: {extra}")

        return available

    def _prepare_data(
        self, df: pd.DataFrame, min_obs: Optional[int] = None
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Chuẩn bị X, y cho hồi quy DỰ BÁO:
          X_t = features đã biết cuối phiên t
          y_t = mean log-return/ngày của {horizon} phiên KẾ TIẾP (t+1..t+h)
        Chỉ dropna trên cột đã đủ coverage (không bắt P/E/NFF).
        """
        if self.target_col not in df.columns:
            raise ValueError(f"Target column '{self.target_col}' không tồn tại")

        available = self._select_usable_features(df)
        if len(available) < 2:
            raise ValueError(
                f"[MLR] Không đủ feature usable (cần ≥2). Có: {available}"
            )

        fwd_col = "_forward_target"
        sub = df[available].copy()
        sub[fwd_col] = make_forward_target(df[self.target_col], self.horizon)
        sub = sub.dropna()
        if min_obs is None:
            min_obs = MIN_MLR_OBS
        if len(sub) < min_obs:
            raise ValueError(
                f"[MLR] Chỉ còn {len(sub)} obs sau dropna — cần ≥{min_obs}. "
                f"Features: {available}"
            )
        self.feature_cols = available
        X = sub[available]
        y = sub[fwd_col]
        return X, y

    def _drop_collinear_features(self, X: pd.DataFrame, threshold: float = 0.9) -> pd.DataFrame:
        """Loại bỏ các biến có độ tương quan cao để tránh ma trận suy biến."""
        corr_matrix = X.corr().abs()
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        to_drop = [column for column in upper.columns if any(upper[column] > threshold)]
        if to_drop:
            logger.warning(f"[MLR] Loại bỏ các biến do đa cộng tuyến (corr > {threshold}): {to_drop}")
            return X.drop(columns=to_drop)
        return X

    def fit(self, df: pd.DataFrame) -> "MLRModel":
        """
        Huấn luyện mô hình MLR.

        Parameters
        ----------
        df : DataFrame chứa features và target (đã tính xong từ pipeline features)

        Returns
        -------
        self
        """
        try:
            import statsmodels.api as sm
        except ImportError:
            logger.error("[MLR] statsmodels chưa cài — thêm vào requirements.txt")
            raise

        X, y = self._prepare_data(df)
        X = self._drop_collinear_features(X)
        
        n = len(X)
        split = int(n * self.train_ratio)

        X_train, y_train = X.iloc[:split], y.iloc[:split]

        # Thêm hằng số (intercept α)
        X_train_const = sm.add_constant(X_train)

        # Fit OLS với Newey-West HAC covariance
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                ols = sm.OLS(y_train, X_train_const)
                self.model_ = ols.fit(
                    cov_type="HAC",
                    cov_kwds={"maxlags": self.max_lags_nw}
                )
            except Exception as e:
                logger.error(f"[MLR] Lỗi ma trận suy biến không thể khắc phục: {e}. Vui lòng kiểm tra lại tập dữ liệu.")
                raise

        # Lưu kết quả
        self.coefs_   = dict(self.model_.params.drop("const", errors="ignore"))
        self.pvalues_ = dict(self.model_.pvalues.drop("const", errors="ignore"))
        self.r2_      = self.model_.rsquared
        self.adj_r2_  = self.model_.rsquared_adj

        # Kiểm tra dấu kỳ vọng
        for feat, beta in self.coefs_.items():
            expected = EXPECTED_SIGNS.get(feat, 0)
            if expected != 0:
                self.sign_ok_[feat] = (expected * beta > 0)

        self.residuals_ = self.model_.resid

        # ── Đánh giá OUT-OF-SAMPLE trên 25% cuối (không dùng khi fit) ────────
        # Đây là thước đo trung thực duy nhất về khả năng DỰ BÁO của model.
        self.oos_metrics_ = {}
        X_test, y_test = X.iloc[split:], y.iloc[split:]
        if len(X_test) >= 10:
            try:
                X_test_const = sm.add_constant(X_test, has_constant="add")
                X_test_const = X_test_const[list(self.model_.model.exog_names)]
                y_hat = self.model_.predict(X_test_const)
                ss_res = float(((y_test - y_hat) ** 2).sum())
                ss_tot = float(((y_test - y_test.mean()) ** 2).sum())
                oos_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
                hit = float((np.sign(y_hat) == np.sign(y_test)).mean())
                self.oos_metrics_ = {
                    "oos_r2":       round(oos_r2, 4),
                    "oos_hit_rate": round(hit, 4),
                    "oos_n":        int(len(y_test)),
                }
            except Exception as e:
                logger.warning(f"[MLR-OOS] Không tính được OOS metrics: {e}")

        logger.info(
            f"[MLR] Fit xong (PREDICTIVE, horizon={self.horizon} phiên). "
            f"R²-train = {self.r2_:.4f}, Adj-R² = {self.adj_r2_:.4f}\n"
            f"       Train size = {len(X_train)}, Test size = {n - split} "
            f"| OOS: {self.oos_metrics_ or 'N/A'}"
        )
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """
        Dự báo R_VNI trên tập test (hoặc toàn bộ data).
        """
        if self.model_ is None:
            raise RuntimeError("Model chưa được fit — gọi .fit() trước")
        import statsmodels.api as sm
        used = [c for c in self.feature_cols if c in df.columns and c in self.coefs_]
        if not used:
            used = list(self.coefs_.keys())
        X = df[used].apply(pd.to_numeric, errors="coerce").ffill().dropna()
        if X.empty:
            raise ValueError("[MLR] Predict: không còn hàng sau dropna")
        X_const = sm.add_constant(X, has_constant="add")
        exog_names = list(self.model_.model.exog_names)
        for name in exog_names:
            if name not in X_const.columns:
                X_const[name] = 0.0 if name != "const" else 1.0
        X_const = X_const[exog_names]
        return self.model_.predict(X_const)

    def diagnostics(self) -> Dict:
        """
        Chạy các kiểm định thống kê cơ bản.

        Returns
        -------
        dict gồm:
          - durbin_watson   : [0–4], gần 2 = không autocorr
          - jb_pvalue       : Jarque-Bera test (residuals normality)
          - vif             : {feature: VIF} (>10 → multicollinearity)
          - adf_residuals   : ADF test p-value cho residuals
        """
        if self.model_ is None:
            raise RuntimeError("Model chưa được fit")

        result = {}

        # Out-of-sample (25% holdout) — thước đo khả năng dự báo trung thực
        result["oos"] = dict(self.oos_metrics_)

        # Durbin-Watson
        try:
            from statsmodels.stats.stattools import durbin_watson
            dw = durbin_watson(self.residuals_)
            result["durbin_watson"] = round(float(dw), 4)
        except Exception as e:
            result["durbin_watson"] = None
            logger.warning(f"[MLR-DW] {e}")

        # Jarque-Bera
        try:
            from statsmodels.stats.stattools import jarque_bera
            jb_stat, jb_p, skew, kurt = jarque_bera(self.residuals_)
            result["jb_pvalue"] = round(float(jb_p), 4)
            result["residual_skewness"] = round(float(skew), 4)
            result["residual_kurtosis"] = round(float(kurt), 4)
        except Exception as e:
            result["jb_pvalue"] = None
            logger.warning(f"[MLR-JB] {e}")

        # VIF (Variance Inflation Factor)
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor
            import statsmodels.api as sm
            X = self.model_.model.exog
            feature_names = self.model_.model.exog_names
            vif_data = {
                name: round(variance_inflation_factor(X, i), 2)
                for i, name in enumerate(feature_names)
                if name != "const"
            }
            result["vif"] = vif_data
        except Exception as e:
            result["vif"] = {}
            logger.warning(f"[MLR-VIF] {e}")

        # ADF test cho residuals (kiểm tra stationary)
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_stat, adf_p, *_ = adfuller(
                self.residuals_.dropna(), autolag="AIC"
            )
            result["adf_residuals_pvalue"] = round(float(adf_p), 4)
            result["residuals_stationary"]  = (adf_p < 0.05)
        except Exception as e:
            result["adf_residuals_pvalue"] = None
            logger.warning(f"[MLR-ADF] {e}")

        return result

    def summary_table(self) -> pd.DataFrame:
        """
        Tạo bảng tóm tắt kết quả hồi quy theo chuẩn Quant Analyst.

        Columns: Variable, Beta (β), P-value, Sign Expected,
                 Sign Actual, Sign_OK, Significance
        """
        rows = []
        for feat in self.coefs_:
            beta   = self.coefs_.get(feat, np.nan)
            pval   = self.pvalues_.get(feat, np.nan)
            exp_s  = EXPECTED_SIGNS.get(feat, 0)
            sign_ok = self.sign_ok_.get(feat, None)

            if pval < 0.01:
                sig = "***"
            elif pval < 0.05:
                sig = "**"
            elif pval < 0.10:
                sig = "*"
            else:
                sig = ""

            rows.append({
                "Variable":       feat,
                "Beta (β)":       round(beta, 6),
                "P-value":        round(pval, 4),
                "Sign Expected":  "+" if exp_s > 0 else ("-" if exp_s < 0 else "?"),
                "Sign Actual":    "+" if beta > 0 else "-",
                "Sign OK":        "✅" if sign_ok else ("❌" if sign_ok is not None else "—"),
                "Significance":   sig,
            })

        df = pd.DataFrame(rows)
        return df
