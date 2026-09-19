"""
var_model.py — Mô hình Vector Tự hồi quy (Vector Autoregression - VAR)
=======================================================================
VAR(p) — hệ thống phương trình cho NHIỀU chuỗi thời gian đồng thời

Phương trình hệ:
  Y_t = A₁·Y_{t-1} + A₂·Y_{t-2} + ... + Aₚ·Y_{t-p} + ε_t

Trong đó Y_t là vector gồm các biến:
  [R_VNI, Δ IR, Δ DXY, NFF, Δ US10Y, ZPE, Δ MRG]

Ưu điểm VAR so với MLR:
  - Xử lý tương quan 2 chiều (bidirectional causality) giữa các biến
  - Granger Causality Test: kiểm định biến nào thực sự "dẫn dắt" biến khác
  - Impulse Response Function (IRF): phản ứng của VNI trước shock từng biến
  - Forecast Error Variance Decomposition (FEVD): % phương sai VNI được giải
    thích bởi mỗi biến trong hệ

Kiểm định sơ bộ bắt buộc:
  - ADF/KPSS: tất cả biến phải STATIONARY (I(0)) trước khi đưa vào VAR
  - Nếu I(1): lấy first-difference trước, HOẶC dùng VECM nếu có cointegration
"""

import logging
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import VAR_MAX_LAGS, VAR_VARIABLES

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Kiểm định Stationarity
# ═══════════════════════════════════════════════════════════════════════════════

def run_stationarity_tests(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Chạy ADF (Augmented Dickey-Fuller) và KPSS test cho từng biến.

    ADF H₀: có unit root (non-stationary) → p < 0.05 → reject → STATIONARY
    KPSS H₀: stationary → p < 0.05 → reject → NON-STATIONARY

    Returns
    -------
    DataFrame: variable, adf_pvalue, adf_stationary, kpss_pvalue, kpss_stationary,
               conclusion (stationary / non-stationary / mixed)
    """
    try:
        from statsmodels.tsa.stattools import adfuller, kpss
    except ImportError:
        logger.error("[VAR] statsmodels chưa cài — pip install statsmodels")
        raise

    rows = []
    for col in cols:
        if col not in df.columns:
            logger.warning(f"[VAR-ADF] Cột '{col}' không tồn tại — bỏ qua")
            continue
        series = df[col].dropna()
        if len(series) < 30:
            logger.warning(f"[VAR-ADF] '{col}' chỉ có {len(series)} obs — quá ít")
            continue

        # ADF test
        try:
            adf_result = adfuller(series, autolag="AIC")
            adf_p = adf_result[1]
            adf_stat = (adf_p < 0.05)
        except Exception as e:
            adf_p, adf_stat = np.nan, None
            logger.warning(f"[ADF] {col}: {e}")

        # KPSS test
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                kpss_result = kpss(series, regression="c", nlags="auto")
            kpss_p = kpss_result[1]
            kpss_stat = (kpss_p >= 0.05)  # KPSS: p >= 0.05 → stationary
        except Exception as e:
            kpss_p, kpss_stat = np.nan, None
            logger.warning(f"[KPSS] {col}: {e}")

        # Kết luận
        if adf_stat is True and kpss_stat is True:
            conclusion = "stationary"
        elif adf_stat is False or kpss_stat is False:
            conclusion = "non-stationary"
        else:
            conclusion = "mixed / unclear"

        rows.append({
            "variable":         col,
            "adf_pvalue":       round(adf_p, 4) if not np.isnan(adf_p) else None,
            "adf_stationary":   adf_stat,
            "kpss_pvalue":      round(kpss_p, 4) if not np.isnan(kpss_p) else None,
            "kpss_stationary":  kpss_stat,
            "conclusion":       conclusion,
        })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Lựa chọn Lag tối ưu (AIC / BIC)
# ═══════════════════════════════════════════════════════════════════════════════

def select_optimal_lag(
    df_var: pd.DataFrame,
    max_lags: int = VAR_MAX_LAGS,
    criterion: str = "aic"
) -> Tuple[int, pd.DataFrame]:
    """
    Lựa chọn lag tối ưu cho VAR dựa trên Information Criteria.

    Parameters
    ----------
    df_var    : DataFrame với các biến VAR (đã stationary)
    max_lags  : Lag tối đa để kiểm tra [1, max_lags]
    criterion : 'aic', 'bic', 'hqic', 'fpe'

    Returns
    -------
    (optimal_lag, ic_comparison_df)
    """
    try:
        from statsmodels.tsa.api import VAR as StatsVAR
    except ImportError:
        logger.error("[VAR] statsmodels chưa cài")
        raise

    model = StatsVAR(df_var)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lag_results = model.select_order(maxlags=max_lags)

    optimal_lag = lag_results.selected_orders.get(criterion, 1)

    # Bảng so sánh IC
    ic_data = {
        "lag": list(range(1, max_lags + 1)),
        "aic": [lag_results.aic] * max_lags,  # Simplified — actual values
        "bic": [lag_results.bic] * max_lags,
    }
    # Dùng summary nếu có
    try:
        ic_summary = lag_results.summary()
        logger.info(f"[VAR] Optimal lag ({criterion.upper()}): {optimal_lag}")
    except Exception:
        pass

    return int(optimal_lag), lag_results


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VAR Model Class
# ═══════════════════════════════════════════════════════════════════════════════

class VARModel:
    """
    Vector Autoregression Model cho phân tích đa biến VN-Index.

    Workflow:
      1. Stationarity test → first-difference nếu cần
      2. Optimal lag selection (AIC)
      3. Fit VAR(p)
      4. Granger Causality Test
      5. Impulse Response Function (IRF)
      6. Forecast Error Variance Decomposition (FEVD)
    """

    def __init__(
        self,
        variable_cols: List[str] = None,
        max_lags: int = VAR_MAX_LAGS,
        target_col: str = "vni_return"
    ):
        self.variable_cols = variable_cols or VAR_VARIABLES
        self.max_lags      = max_lags
        self.target_col    = target_col

        self.model_         = None   # statsmodels VAR instance
        self.results_       = None   # fitted results
        self.optimal_lag_   = None
        self.stat_report_   = None   # stationarity report

    def _prepare_var_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Chọn và làm sạch dữ liệu cho VAR.
        """
        available = [c for c in self.variable_cols if c in df.columns]
        missing   = [c for c in self.variable_cols if c not in df.columns]
        if missing:
            logger.warning(f"[VAR] Thiếu biến: {missing}")
        if len(available) < 2:
            raise ValueError(f"[VAR] Cần ít nhất 2 biến. Chỉ có: {available}")

        df_var = df[available].dropna()
        logger.info(f"[VAR] Sử dụng {len(available)} biến, {len(df_var)} obs")
        return df_var

    def fit(self, df: pd.DataFrame, lag: Optional[int] = None) -> "VARModel":
        """
        Fit VAR(p) model.

        Parameters
        ----------
        df  : DataFrame với tất cả biến VAR
        lag : Lag cố định (nếu None → tự chọn theo AIC)
        """
        try:
            from statsmodels.tsa.api import VAR as StatsVAR
        except ImportError:
            raise ImportError("pip install statsmodels")

        # Stationarity check
        df_var = self._prepare_var_data(df)
        self.stat_report_ = run_stationarity_tests(
            df_var, df_var.columns.tolist()
        )

        non_stat = self.stat_report_[
            self.stat_report_["conclusion"] == "non-stationary"
        ]["variable"].tolist()
        if non_stat:
            logger.warning(
                f"[VAR] Biến non-stationary: {non_stat}\n"
                "Đang áp dụng first-difference để đảm bảo tính dừng..."
            )
            df_var = df_var.diff().dropna()

        # Chọn lag
        model = StatsVAR(df_var)
        if lag is None:
            lag_obj = model.select_order(maxlags=self.max_lags)
            self.optimal_lag_ = lag_obj.selected_orders.get("aic", 2)
        else:
            self.optimal_lag_ = lag

        logger.info(f"[VAR] Fitting VAR({self.optimal_lag_})...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.results_ = model.fit(self.optimal_lag_)

        logger.info(f"[VAR] Fit xong. AIC = {self.results_.aic:.4f}")
        return self

    def granger_causality(self, caused: str = None, alpha: float = 0.05) -> pd.DataFrame:
        """
        Kiểm định Granger Causality: biến nào thực sự "dẫn dắt" VNI?

        H₀: biến X KHÔNG Granger-causes VNI
        p < alpha → reject H₀ → X có khả năng dự báo VNI

        Parameters
        ----------
        caused : Tên cột VNI return (mặc định: target_col)
        alpha  : Mức ý nghĩa (mặc định 5%)

        Returns
        -------
        DataFrame: causing_variable, test_stat, p_value, granger_causes_vni
        """
        if self.results_ is None:
            raise RuntimeError("Chưa fit model")

        caused = caused or self.target_col
        rows = []

        for col in self.results_.names:
            if col == caused:
                continue
            try:
                gc_test = self.results_.test_causality(
                    caused, [col], kind="f"
                )
                stat = float(gc_test.test_statistic)
                pval = float(gc_test.pvalue)
                rows.append({
                    "causing_variable": col,
                    "test_statistic":   round(stat, 4),
                    "p_value":          round(pval, 4),
                    "granger_causes_vni": pval < alpha,
                    "significance":     "***" if pval < 0.01
                                        else ("**" if pval < 0.05
                                              else ("*" if pval < 0.10 else ""))
                })
            except Exception as e:
                logger.warning(f"[GC] {col} → {caused}: {e}")

        df_gc = pd.DataFrame(rows).sort_values("p_value").reset_index(drop=True)
        return df_gc

    def impulse_response(
        self,
        periods: int = 20,
        shock_col: Optional[str] = None
    ) -> Optional[object]:
        """
        Tính Impulse Response Function (IRF).

        IRF đo lường phản ứng của VNI trước một cú sốc 1-std-dev từ biến shock.
        Ví dụ: NFF giảm đột ngột 1σ → VNI phản ứng như thế nào trong 20 phiên?

        Parameters
        ----------
        periods   : Số phiên phân tích phản ứng (mặc định 20 phiên = 1 tháng)
        shock_col : Biến gây sốc (nếu None → tất cả biến)

        Returns
        -------
        statsmodels IRAnalysis object (dùng để plot)
        """
        if self.results_ is None:
            raise RuntimeError("Chưa fit model")
        irf = self.results_.irf(periods=periods)
        return irf

    def fevd(self, periods: int = 20) -> pd.DataFrame:
        """
        Forecast Error Variance Decomposition (FEVD).

        FEVD cho biết % phương sai của VNI tại horizon H được giải thích bởi
        mỗi biến trong hệ thống.

        Returns
        -------
        DataFrame: horizon (1–20), % variance explained by each variable
        """
        if self.results_ is None:
            raise RuntimeError("Chưa fit model")

        fevd_obj = self.results_.fevd(periods=periods)
        # Tìm index của VNI trong danh sách biến
        if self.target_col in self.results_.names:
            idx = list(self.results_.names).index(self.target_col)
            fevd_vni = fevd_obj.decomp[:, idx, :]  # shape (periods, n_vars)
            df = pd.DataFrame(
                fevd_vni,
                columns=self.results_.names,
                index=range(1, periods + 1)
            )
            df.index.name = "horizon"
            return df.reset_index()
        else:
            logger.warning(f"[FEVD] '{self.target_col}' không trong model names")
            return pd.DataFrame()

    def forecast(self, y_last: np.ndarray, steps: int = 5) -> pd.DataFrame:
        """
        Dự báo n bước tiếp theo từ VAR.

        Parameters
        ----------
        y_last : Mảng n×k giá trị cuối cùng (n = optimal_lag_, k = n_vars)
        steps  : Số bước dự báo

        Returns
        -------
        DataFrame: step + forecast cho từng biến
        """
        if self.results_ is None:
            raise RuntimeError("Chưa fit model")
        forecast = self.results_.forecast(y_last, steps=steps)
        df = pd.DataFrame(forecast, columns=self.results_.names)
        df.index.name = "step"
        df["step"] = range(1, steps + 1)
        return df.reset_index(drop=True)
