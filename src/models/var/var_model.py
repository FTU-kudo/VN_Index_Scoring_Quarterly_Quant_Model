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

# Ánh xạ tên cột config → tên thực tế sau feature engineering
VAR_COLUMN_ALIASES = {
    "net_foreign_flow": ["net_foreign_flow", "net_foreign_flow_b_vnd"],
    "delta_margin_debt": ["delta_margin_debt", "delta_margin_debt_pct"],
}

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
        self.data_          = None   # bảng đã làm sạch dùng để fit/forecast

    def _resolve_column(self, df: pd.DataFrame, name: str) -> Optional[str]:
        aliases = VAR_COLUMN_ALIASES.get(name, [name])
        for alias in aliases:
            if alias in df.columns and pd.api.types.is_numeric_dtype(df[alias]):
                coverage = float(df[alias].notna().mean())
                if coverage >= 0.40:
                    return alias
        return None

    def _prepare_var_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Chọn biến có coverage đủ, forward-fill chuỗi thưa, rồi dropna.
        Không bắt buộc P/E hay NFF nếu lịch sử không có.
        """
        resolved = {}
        missing = []
        for name in self.variable_cols:
            col = self._resolve_column(df, name)
            if col is None:
                missing.append(name)
            else:
                resolved[name] = col
        if missing:
            logger.warning(f"[VAR] Thiếu / quá thưa biến: {missing}")
        if len(resolved) < 3:
            raise ValueError(
                f"[VAR] Cần ít nhất 3 biến usable. Chỉ có: {list(resolved)}"
            )

        frame = pd.DataFrame({name: df[col] for name, col in resolved.items()})
        frame = frame.apply(pd.to_numeric, errors="coerce").ffill()
        low_var = [c for c in frame.columns if float(frame[c].std(skipna=True) or 0) < 1e-10]
        if low_var:
            logger.warning(f"[VAR] Bỏ biến gần như hằng: {low_var}")
            frame = frame.drop(columns=low_var)
        df_var = frame.dropna()
        if len(df_var.columns) < 3:
            raise ValueError(
                f"[VAR] Cần ít nhất 3 biến usable. Chỉ có: {list(df_var.columns)}"
            )
        if len(df_var) < 80:
            raise ValueError(
                f"[VAR] Chỉ còn {len(df_var)} obs sau làm sạch — cần ≥80"
            )
        logger.info(
            f"[VAR] Sử dụng {len(resolved)} biến {list(resolved.keys())}, "
            f"{len(df_var)} obs"
        )
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
                f"[VAR] Biến non-stationary: {non_stat} — difference từng cột, "
                "không difference cả hệ (tránh biến return thành Δreturn)."
            )
            for col in non_stat:
                if col in df_var.columns:
                    df_var[col] = df_var[col].diff()
            df_var = df_var.dropna()

        # Chọn lag
        df_var = df_var.reset_index(drop=True)
        model = StatsVAR(df_var)
        if lag is None:
            try:
                lag_obj = model.select_order(maxlags=self.max_lags)
                self.optimal_lag_ = int(lag_obj.selected_orders.get("aic", 2) or 2)
                self.optimal_lag_ = max(1, self.optimal_lag_)
            except Exception as e:
                logger.warning(f"[VAR] select_order thất bại ({e}) — dùng lag=2")
                self.optimal_lag_ = 2
        else:
            self.optimal_lag_ = lag

        self.data_ = df_var
        logger.info(f"[VAR] Fitting VAR({self.optimal_lag_})...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.results_ = model.fit(self.optimal_lag_)
            except Exception as e:
                logger.warning(f"[VAR] Lỗi fit với lag {self.optimal_lag_} ({e}). Thử lag=1...")
                self.optimal_lag_ = 1
                try:
                    self.results_ = model.fit(self.optimal_lag_)
                except Exception as e2:
                    logger.warning(f"[VAR] Lỗi fit với lag=1 ({e2}). Bỏ qua VAR model.")
                    self.results_ = None
                    return self

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
