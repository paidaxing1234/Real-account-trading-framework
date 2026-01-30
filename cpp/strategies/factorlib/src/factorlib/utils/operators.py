"""
FactorLib Operators - High Performance Time Series & Cross-Section Operators

All operators are optimized for maximum performance using:
- NumPy vectorized operations where possible
- Numba JIT compilation for loop-intensive operations
- Parallel execution for large arrays

Usage:
    from factorlib.utils.operators import ops

    result = ops.ts_mean(series, window=20)
    result = ops.ts_zscore(series, window=60)
    result = ops.clip(series, -3, 3)
"""

import numpy as np
import pandas as pd
from numba import jit, prange
from typing import Union, Optional

# ============================================================================
# Numba JIT compiled core functions (internal use)
# ============================================================================

@jit(nopython=True, cache=True)
def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Optimized rolling mean using cumsum trick."""
    n = len(values)
    out = np.full(n, np.nan)
    if n < window:
        return out

    # Use cumsum for O(n) complexity
    cumsum = np.zeros(n + 1)
    for i in range(n):
        if np.isnan(values[i]):
            cumsum[i + 1] = cumsum[i]
        else:
            cumsum[i + 1] = cumsum[i] + values[i]

    for i in range(window - 1, n):
        out[i] = (cumsum[i + 1] - cumsum[i - window + 1]) / window

    return out


@jit(nopython=True, cache=True)
def _rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    """Optimized rolling sum using cumsum trick."""
    n = len(values)
    out = np.full(n, np.nan)
    if n < window:
        return out

    cumsum = np.zeros(n + 1)
    for i in range(n):
        if np.isnan(values[i]):
            cumsum[i + 1] = cumsum[i]
        else:
            cumsum[i + 1] = cumsum[i] + values[i]

    for i in range(window - 1, n):
        out[i] = cumsum[i + 1] - cumsum[i - window + 1]

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Parallel rolling standard deviation."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        w = values[i - window + 1:i + 1]
        valid_count = 0
        sum_val = 0.0
        sum_sq = 0.0

        for j in range(window):
            if not np.isnan(w[j]):
                valid_count += 1
                sum_val += w[j]
                sum_sq += w[j] * w[j]

        if valid_count > 1:
            mean = sum_val / valid_count
            var = (sum_sq / valid_count) - (mean * mean)
            out[i] = np.sqrt(max(var, 0.0))

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    """Parallel rolling z-score."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        w = values[i - window + 1:i + 1]
        valid_count = 0
        sum_val = 0.0
        sum_sq = 0.0

        for j in range(window):
            if not np.isnan(w[j]):
                valid_count += 1
                sum_val += w[j]
                sum_sq += w[j] * w[j]

        if valid_count > 1:
            mean = sum_val / valid_count
            var = (sum_sq / valid_count) - (mean * mean)
            std = np.sqrt(max(var, 0.0))
            if std > 1e-10:
                out[i] = (values[i] - mean) / std
            else:
                out[i] = 0.0

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_rank(values: np.ndarray, window: int) -> np.ndarray:
    """Parallel rolling rank (percentile)."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        w = values[i - window + 1:i + 1]
        current = values[i]

        if np.isnan(current):
            continue

        count = 0
        less_than = 0
        for j in range(window):
            if not np.isnan(w[j]):
                count += 1
                if w[j] < current:
                    less_than += 1

        if count > 0:
            out[i] = less_than / count

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_skew(values: np.ndarray, window: int) -> np.ndarray:
    """Parallel rolling skewness."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        w = values[i - window + 1:i + 1]
        valid_count = 0
        sum_val = 0.0

        for j in range(window):
            if not np.isnan(w[j]):
                valid_count += 1
                sum_val += w[j]

        if valid_count < 3:
            continue

        mean = sum_val / valid_count

        m2 = 0.0
        m3 = 0.0
        for j in range(window):
            if not np.isnan(w[j]):
                d = w[j] - mean
                m2 += d * d
                m3 += d * d * d

        m2 /= valid_count
        m3 /= valid_count

        if m2 > 1e-10:
            out[i] = m3 / (m2 ** 1.5)

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_kurt(values: np.ndarray, window: int) -> np.ndarray:
    """Parallel rolling kurtosis."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        w = values[i - window + 1:i + 1]
        valid_count = 0
        sum_val = 0.0

        for j in range(window):
            if not np.isnan(w[j]):
                valid_count += 1
                sum_val += w[j]

        if valid_count < 4:
            continue

        mean = sum_val / valid_count

        m2 = 0.0
        m4 = 0.0
        for j in range(window):
            if not np.isnan(w[j]):
                d = w[j] - mean
                d2 = d * d
                m2 += d2
                m4 += d2 * d2

        m2 /= valid_count
        m4 /= valid_count

        if m2 > 1e-10:
            out[i] = (m4 / (m2 * m2)) - 3.0

    return out


@jit(nopython=True, cache=True)
def _rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling minimum."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        min_val = np.inf
        for j in range(window):
            if not np.isnan(w[j]) and w[j] < min_val:
                min_val = w[j]
        if min_val < np.inf:
            out[i] = min_val

    return out


@jit(nopython=True, cache=True)
def _rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling maximum."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        max_val = -np.inf
        for j in range(window):
            if not np.isnan(w[j]) and w[j] > max_val:
                max_val = w[j]
        if max_val > -np.inf:
            out[i] = max_val

    return out


@jit(nopython=True, cache=True)
def _rolling_argmin(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling argmin (days since min)."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        min_val = np.inf
        min_idx = 0
        for j in range(window):
            if not np.isnan(w[j]) and w[j] < min_val:
                min_val = w[j]
                min_idx = j
        if min_val < np.inf:
            out[i] = min_idx

    return out


@jit(nopython=True, cache=True)
def _rolling_argmax(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling argmax (days since max)."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        max_val = -np.inf
        max_idx = 0
        for j in range(window):
            if not np.isnan(w[j]) and w[j] > max_val:
                max_val = w[j]
                max_idx = j
        if max_val > -np.inf:
            out[i] = max_idx

    return out


@jit(nopython=True, cache=True)
def _rolling_slope(values: np.ndarray, window: int) -> np.ndarray:
    """Rolling slope (linear regression against time)."""
    n = len(values)
    out = np.full(n, np.nan)

    # Precompute time index sums for window
    t = np.arange(window, dtype=np.float64)
    sum_t = np.sum(t)
    sum_t2 = np.sum(t * t)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]

        # Check for NaN
        has_nan = False
        for j in range(window):
            if np.isnan(w[j]):
                has_nan = True
                break

        if has_nan:
            continue

        sum_x = np.sum(w)
        sum_tx = 0.0
        for j in range(window):
            sum_tx += t[j] * w[j]

        denom = window * sum_t2 - sum_t * sum_t
        if abs(denom) > 1e-10:
            out[i] = (window * sum_tx - sum_t * sum_x) / denom

    return out


@jit(nopython=True, cache=True)
def _decay_linear(values: np.ndarray, window: int) -> np.ndarray:
    """Linear decay weighted average."""
    n = len(values)
    out = np.full(n, np.nan)

    # Precompute weights
    weights = np.arange(1, window + 1, dtype=np.float64)
    weight_sum = np.sum(weights)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]

        # Check for NaN
        has_nan = False
        for j in range(window):
            if np.isnan(w[j]):
                has_nan = True
                break

        if has_nan:
            continue

        weighted_sum = 0.0
        for j in range(window):
            weighted_sum += weights[j] * w[j]

        out[i] = weighted_sum / weight_sum

    return out


@jit(nopython=True, cache=True)
def _highday(values: np.ndarray, window: int) -> np.ndarray:
    """Days since highest value in window."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        max_val = -np.inf
        max_idx = 0
        for j in range(window):
            if not np.isnan(w[j]) and w[j] > max_val:
                max_val = w[j]
                max_idx = j
        if max_val > -np.inf:
            out[i] = window - 1 - max_idx

    return out


@jit(nopython=True, cache=True)
def _lowday(values: np.ndarray, window: int) -> np.ndarray:
    """Days since lowest value in window."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = values[i - window + 1:i + 1]
        min_val = np.inf
        min_idx = 0
        for j in range(window):
            if not np.isnan(w[j]) and w[j] < min_val:
                min_val = w[j]
                min_idx = j
        if min_val < np.inf:
            out[i] = window - 1 - min_idx

    return out


@jit(nopython=True, parallel=True, cache=True)
def _clip(values: np.ndarray, min_val: float, max_val: float) -> np.ndarray:
    """Parallel clip values to range."""
    n = len(values)
    out = np.empty(n)

    for i in prange(n):
        v = values[i]
        if np.isnan(v):
            out[i] = np.nan
        elif v < min_val:
            out[i] = min_val
        elif v > max_val:
            out[i] = max_val
        else:
            out[i] = v

    return out


@jit(nopython=True, parallel=True, cache=True)
def _filter_range(values: np.ndarray, min_val: float, max_val: float) -> np.ndarray:
    """Filter values outside range to 0."""
    n = len(values)
    out = np.empty(n)

    for i in prange(n):
        v = values[i]
        if np.isnan(v):
            out[i] = np.nan
        elif v < min_val or v > max_val:
            out[i] = 0.0
        else:
            out[i] = v

    return out


@jit(nopython=True, cache=True)
def _pct_change(values: np.ndarray, period: int = 1) -> np.ndarray:
    """Percentage change."""
    n = len(values)
    out = np.full(n, np.nan)

    for i in range(period, n):
        prev = values[i - period]
        if not np.isnan(prev) and not np.isnan(values[i]) and abs(prev) > 1e-10:
            out[i] = (values[i] - prev) / prev

    return out


@jit(nopython=True, cache=True)
def _forward_fill(values: np.ndarray) -> np.ndarray:
    """Forward fill NaN values."""
    n = len(values)
    out = values.copy()

    for i in range(1, n):
        if np.isnan(out[i]):
            out[i] = out[i - 1]

    return out


def _forward_fill_signal(values: np.ndarray, fill_length: int = 10) -> np.ndarray:
    """
    Forward fill non-zero signals for specified length (vectorized).

    新信号覆盖旧填充，使用 NumPy 切片实现向量化。

    Example: values = [1, 0, 2, 0, 0, 0], fill_length = 2
             result = [1, 1, 2, 2, 2, 0]
    """
    n = len(values)
    out = np.zeros(n, dtype=values.dtype)

    # 找出所有信号位置
    mask = (values != 0) & ~np.isnan(values)
    indices = np.where(mask)[0]

    # 向量化切片填充：后面的信号自动覆盖前面的
    for idx in indices:
        out[idx:idx + fill_length + 1] = values[idx]

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_corr(x: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    """Rolling correlation between two arrays."""
    n = len(x)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        wx = x[i - window + 1:i + 1]
        wy = y[i - window + 1:i + 1]

        # Calculate correlation
        sum_x = 0.0
        sum_y = 0.0
        sum_xy = 0.0
        sum_x2 = 0.0
        sum_y2 = 0.0
        count = 0

        for j in range(window):
            if not np.isnan(wx[j]) and not np.isnan(wy[j]):
                sum_x += wx[j]
                sum_y += wy[j]
                sum_xy += wx[j] * wy[j]
                sum_x2 += wx[j] * wx[j]
                sum_y2 += wy[j] * wy[j]
                count += 1

        if count > 1:
            mean_x = sum_x / count
            mean_y = sum_y / count

            var_x = sum_x2 / count - mean_x * mean_x
            var_y = sum_y2 / count - mean_y * mean_y
            cov_xy = sum_xy / count - mean_x * mean_y

            denom = np.sqrt(var_x * var_y)
            if denom > 1e-10:
                out[i] = cov_xy / denom

    return out


@jit(nopython=True, parallel=True, cache=True)
def _rolling_cov(x: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    """Rolling covariance between two arrays."""
    n = len(x)
    out = np.full(n, np.nan)

    for i in prange(window - 1, n):
        wx = x[i - window + 1:i + 1]
        wy = y[i - window + 1:i + 1]

        sum_x = 0.0
        sum_y = 0.0
        sum_xy = 0.0
        count = 0

        for j in range(window):
            if not np.isnan(wx[j]) and not np.isnan(wy[j]):
                sum_x += wx[j]
                sum_y += wy[j]
                sum_xy += wx[j] * wy[j]
                count += 1

        if count > 1:
            mean_x = sum_x / count
            mean_y = sum_y / count
            out[i] = sum_xy / count - mean_x * mean_y

    return out


# ============================================================================
# Unified Operator Interface
# ============================================================================

class ops:
    """
    High-performance time series and cross-section operators.

    All operators are optimized using NumPy vectorization and Numba JIT compilation.
    Use via the unified interface: ops.function_name()

    Categories:
    - Basic math: add, subtract, multiply, divide, power, abs_val, log, exp, sqrt, sign
    - Time series: ts_mean, ts_std, ts_zscore, ts_rank, ts_skew, ts_slope, etc.
    - Cross section: cs_rank, cs_zscore, cs_demean, etc.
    - Signal processing: clip, filter_range, winsorize, fill_na, etc.
    """

    # ========================= Helper Functions =========================

    @staticmethod
    def col(df: pd.DataFrame, col_name: str):
        """
        Get column from DataFrame.

        Args:
            df: DataFrame (single asset) or Dict[str, DataFrame] (panel data)
            col_name: Column name to extract

        Returns:
            Series (single asset) or DataFrame (panel data)
        """
        if isinstance(df, dict):
            # Panel data: build DataFrame from dict
            panel_dict = {}
            for inst, data in df.items():
                if col_name in data.columns:
                    panel_dict[inst] = data[col_name]
            return pd.DataFrame(panel_dict)
        return df[col_name]

    @staticmethod
    def _to_array(x: Union[np.ndarray, pd.Series]) -> np.ndarray:
        """Convert input to numpy array."""
        if isinstance(x, pd.Series):
            return x.to_numpy(dtype=np.float64)
        return np.asarray(x, dtype=np.float64)

    @staticmethod
    def _wrap_result(result: np.ndarray, original: Union[np.ndarray, pd.Series, pd.DataFrame]) -> Union[np.ndarray, pd.Series]:
        """Wrap numpy result back to original type."""
        if isinstance(original, pd.Series):
            return pd.Series(result, index=original.index, name=original.name)
        return result

    @staticmethod
    def _apply_df(df: pd.DataFrame, func, *args, **kwargs) -> pd.DataFrame:
        """Apply function to each column of DataFrame."""
        return df.apply(lambda col: func(col, *args, **kwargs))

    # ========================= Basic Math =========================

    @staticmethod
    def add(x, y):
        """Element-wise addition."""
        return x + y

    @staticmethod
    def subtract(x, y):
        """Element-wise subtraction."""
        return x - y

    @staticmethod
    def multiply(x, y):
        """Element-wise multiplication."""
        return x * y

    @staticmethod
    def divide(x, y):
        """Element-wise division."""
        return x / y

    @staticmethod
    def power(x, y):
        """Element-wise power."""
        return np.power(x, y)

    @staticmethod
    def abs(x):
        """Absolute value."""
        return np.abs(x)

    @staticmethod
    def log(x):
        """Natural logarithm."""
        return np.log(x)

    @staticmethod
    def log10(x):
        """Base-10 logarithm."""
        return np.log10(x)

    @staticmethod
    def exp(x):
        """Exponential."""
        return np.exp(x)

    @staticmethod
    def sqrt(x):
        """Square root."""
        return np.sqrt(x)

    @staticmethod
    def square(x):
        """Square."""
        return np.square(x)

    @staticmethod
    def sign(x):
        """Sign function (-1, 0, 1)."""
        return np.sign(x)

    @staticmethod
    def tanh(x):
        """Hyperbolic tangent. Output range: (-1, 1)."""
        return np.tanh(x)

    # ========================= Time Series Basics =========================

    @staticmethod
    def delay(x: Union[pd.Series, pd.DataFrame], period: int):
        """Shift values by period (lag)."""
        return x.shift(period)

    @staticmethod
    def delta(x: Union[pd.Series, pd.DataFrame], period: int = 1):
        """Difference from period ago."""
        return x - x.shift(period)

    @staticmethod
    def returns(x: Union[pd.Series, pd.DataFrame], period: int = 1):
        """Simple returns: x/x_lag - 1."""
        return x / x.shift(period) - 1

    @staticmethod
    def pct_change(x: Union[pd.Series, pd.DataFrame], period: int = 1):
        """Percentage change (optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.pct_change, period)
        arr = ops._to_array(x)
        result = _pct_change(arr, period)
        return ops._wrap_result(result, x)

    # ========================= Rolling Window Operations =========================

    @staticmethod
    def ts_mean(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling mean (optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_mean, window)
        arr = ops._to_array(x)
        result = _rolling_mean(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_sum(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling sum (optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_sum, window)
        arr = ops._to_array(x)
        result = _rolling_sum(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_std(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling standard deviation (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_std, window)
        arr = ops._to_array(x)
        result = _rolling_std(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_var(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling variance."""
        std = ops.ts_std(x, window)
        return std ** 2

    @staticmethod
    def ts_zscore(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling z-score (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_zscore, window)
        arr = ops._to_array(x)
        result = _rolling_zscore(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_rank(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling rank/percentile (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_rank, window)
        arr = ops._to_array(x)
        result = _rolling_rank(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_skew(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling skewness (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_skew, window)
        arr = ops._to_array(x)
        result = _rolling_skew(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_kurt(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling kurtosis (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_kurt, window)
        arr = ops._to_array(x)
        result = _rolling_kurt(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_min(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling minimum."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_min, window)
        arr = ops._to_array(x)
        result = _rolling_min(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_max(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling maximum."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_max, window)
        arr = ops._to_array(x)
        result = _rolling_max(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_argmin(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling argmin (position of minimum in window)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_argmin, window)
        arr = ops._to_array(x)
        result = _rolling_argmin(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_argmax(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling argmax (position of maximum in window)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_argmax, window)
        arr = ops._to_array(x)
        result = _rolling_argmax(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_quantile(x: Union[pd.Series, pd.DataFrame], window: int, quantile: float):
        """Rolling quantile."""
        return x.rolling(window=window, min_periods=1).quantile(quantile)

    @staticmethod
    def ts_median(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling median."""
        return x.rolling(window=window, min_periods=1).median()

    @staticmethod
    def ts_slope(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling slope (linear regression against time)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.ts_slope, window)
        arr = ops._to_array(x)
        result = _rolling_slope(arr, window)
        return ops._wrap_result(result, x)

    # ========================= Correlation & Regression =========================

    @staticmethod
    def correlation(x: Union[pd.Series, pd.DataFrame, np.ndarray], y: Union[pd.Series, pd.DataFrame, np.ndarray], window: int):
        """Rolling correlation (parallel optimized)."""
        if isinstance(x, pd.DataFrame) and isinstance(y, pd.DataFrame):
            # For DataFrames, apply column-wise
            result = pd.DataFrame(index=x.index, columns=x.columns)
            for col in x.columns:
                if col in y.columns:
                    arr_x = ops._to_array(x[col])
                    arr_y = ops._to_array(y[col])
                    result[col] = _rolling_corr(arr_x, arr_y, window)
            return result
        arr_x = ops._to_array(x)
        arr_y = ops._to_array(y)
        result = _rolling_corr(arr_x, arr_y, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def covariance(x: Union[pd.Series, np.ndarray], y: Union[pd.Series, np.ndarray], window: int):
        """Rolling covariance (parallel optimized)."""
        arr_x = ops._to_array(x)
        arr_y = ops._to_array(y)
        result = _rolling_cov(arr_x, arr_y, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def beta(x: Union[pd.Series, pd.DataFrame], y: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling beta (cov(x,y) / var(y))."""
        if isinstance(x, pd.DataFrame) or isinstance(y, pd.DataFrame):
            # For DataFrames, use pandas rolling
            return x.rolling(window).cov(y) / y.rolling(window).var()
        cov_xy = ops.covariance(x, y, window)
        var_y = ops.ts_var(y, window)
        return cov_xy / var_y

    @staticmethod
    def ts_regression(y: Union[pd.Series, pd.DataFrame], x: Union[pd.Series, pd.DataFrame], window: int, rettype: str = 'slope'):
        """
        Rolling linear regression.

        Args:
            y: Dependent variable
            x: Independent variable
            window: Rolling window size
            rettype: 'slope', 'intercept', or 'r2'
        """
        def reg_func(arr_y, arr_x):
            if len(arr_y) < 2:
                return np.nan
            n = len(arr_y)
            sum_x = np.sum(arr_x)
            sum_y = np.sum(arr_y)
            sum_xy = np.sum(arr_x * arr_y)
            sum_x2 = np.sum(arr_x * arr_x)
            denom = n * sum_x2 - sum_x * sum_x
            if denom == 0:
                return np.nan
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            if rettype == 'slope':
                return slope
            elif rettype == 'intercept':
                return intercept
            elif rettype == 'r2':
                y_pred = slope * arr_x + intercept
                ss_res = np.sum((arr_y - y_pred) ** 2)
                ss_tot = np.sum((arr_y - np.mean(arr_y)) ** 2)
                return 1 - (ss_res / ss_tot) if ss_tot != 0 else np.nan
            return slope

        return y.rolling(window=window, min_periods=2).apply(
            lambda w: reg_func(w.values, x.loc[w.index].values), raw=False
        )

    @staticmethod
    def ts_resid(y, x, window: int):
        """Rolling regression residual."""
        slope = ops.ts_regression(y, x, window, 'slope')
        intercept = ops.ts_regression(y, x, window, 'intercept')
        return y - (slope * x + intercept)

    # ========================= Decay Weighted =========================

    @staticmethod
    def decay_linear(x: Union[pd.Series, pd.DataFrame], window: int):
        """Linear decay weighted average."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.decay_linear, window)
        arr = ops._to_array(x)
        result = _decay_linear(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def ts_ema(x: Union[pd.Series, pd.DataFrame], alpha: float):
        """Exponential decay weighted average (EMA)."""
        return x.ewm(alpha=1/alpha, adjust=False).mean()
    # ========================= Specialized Rolling Ops =========================
    @staticmethod
    def highday(x: Union[pd.Series, pd.DataFrame], window: int):
        """Days since highest value in window."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.highday, window)
        arr = ops._to_array(x)
        result = _highday(arr, window)
        return ops._wrap_result(result, x)

    @staticmethod
    def lowday(x: Union[pd.Series, pd.DataFrame], window: int):
        """Days since lowest value in window."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.lowday, window)
        arr = ops._to_array(x)
        result = _lowday(arr, window)
        return ops._wrap_result(result, x)

    # ========================= Advanced Time Series =========================

    @staticmethod
    def ts_realized_vol(ret: Union[pd.Series, pd.DataFrame], window: int):
        """Realized volatility: sqrt(sum of squared returns)."""
        return np.sqrt(ops.ts_sum(ret ** 2, window) + 1e-12)

    @staticmethod
    def ts_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int):
        """Average True Range (ATR)."""
        prev_close = close.shift(1)
        tr = np.maximum.reduce([
            np.abs(high - low),
            np.abs(high - prev_close),
            np.abs(low - prev_close)
        ])
        tr_series = pd.Series(tr, index=close.index)
        return ops.ts_mean(tr_series, window)

    @staticmethod
    def rsi(x: Union[pd.Series, pd.DataFrame], window: int):
        """
        Relative Strength Index (RSI).

        RSI = 100 - 100 / (1 + RS)
        RS = avg_gain / avg_loss

        Output range: [0, 100]
        """
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.rsi, window)

        delta = x.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.ewm(span=window, adjust=False).mean()
        avg_loss = loss.ewm(span=window, adjust=False).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        rsi_val = 100 - 100 / (1 + rs)
        return rsi_val

    @staticmethod
    def ts_crossover(x: pd.Series, y: pd.Series):
        """Signal when x crosses above y."""
        return (x > y) & (x.shift(1) <= y.shift(1))

    @staticmethod
    def ts_crossunder(x: pd.Series, y: pd.Series):
        """Signal when x crosses below y."""
        return (x < y) & (x.shift(1) >= y.shift(1))

    @staticmethod
    def ts_drawdown(x: pd.Series):
        """Drawdown from peak."""
        peak = x.cummax()
        return (x - peak) / peak.replace(0, np.nan)

    @staticmethod
    def ts_minmax_norm(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling min-max normalization to [0, 1]."""
        mn = ops.ts_min(x, window)
        mx = ops.ts_max(x, window)
        return (x - mn) / (mx - mn + 1e-10)

    @staticmethod
    def ts_rank_signed(x: Union[pd.Series, pd.DataFrame], window: int):
        """Rolling rank mapped to [-1, 1]."""
        return 2 * ops.ts_rank(x, window) - 1

    # ========================= Conditional Operations =========================

    @staticmethod
    def condition(cond, x, y):
        """Where condition is True, use x; else use y."""
        return np.where(cond, x, y)

    @staticmethod
    def greater(x, y):
        """Element-wise greater than."""
        return x > y

    @staticmethod
    def less(x, y):
        """Element-wise less than."""
        return x < y

    @staticmethod
    def equal(x, y):
        """Element-wise equality."""
        return x == y

    # ========================= Cross Section Operations =========================
    # These operators work on DataFrame where:
    # - rows = timestamps (time dimension)
    # - columns = assets (cross-sectional dimension)
    # CS operations compute statistics ACROSS assets at each timestamp (axis=1)

    @staticmethod
    def cs_rank(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional rank (percentile).
        For DataFrame: rank across columns (assets) at each row (timestamp).
        Output range: [0, 1]
        """
        if isinstance(x, pd.DataFrame):
            return x.rank(axis=1, pct=True)
        return x.rank(pct=True)

    @staticmethod
    def cs_zscore(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional z-score standardization.
        For DataFrame: standardize across columns (assets) at each row (timestamp).
        Output: approximately mean=0, std=1 across assets.
        """
        if isinstance(x, pd.DataFrame):
            mean = x.mean(axis=1)
            std = x.std(axis=1).replace(0, np.nan)
            result = x.sub(mean, axis=0).div(std, axis=0)
            return result.fillna(0)
        return (x - x.mean()) / (x.std() + 1e-10)

    @staticmethod
    def cs_demean(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional demean (subtract cross-sectional mean).
        For DataFrame: demean across columns (assets) at each row (timestamp).
        """
        if isinstance(x, pd.DataFrame):
            return x.sub(x.mean(axis=1), axis=0)
        return x - x.mean()

    @staticmethod
    def cs_scale(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional scale to sum(abs) = 1.
        For DataFrame: scale across columns (assets) at each row (timestamp).
        Useful for generating portfolio weights.
        """
        if isinstance(x, pd.DataFrame):
            abs_sum = x.abs().sum(axis=1).replace(0, np.nan)
            return x.div(abs_sum, axis=0).fillna(0)
        abs_sum = x.abs().sum()
        return x / abs_sum if abs_sum > 0 else x * 0

    @staticmethod
    def cs_normalize(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional min-max normalization to [0, 1].
        For DataFrame: normalize across columns (assets) at each row (timestamp).
        """
        if isinstance(x, pd.DataFrame):
            min_val = x.min(axis=1)
            max_val = x.max(axis=1)
            range_val = (max_val - min_val).replace(0, np.nan)
            return x.sub(min_val, axis=0).div(range_val, axis=0).fillna(0.5)
        min_val, max_val = x.min(), x.max()
        range_val = max_val - min_val
        return (x - min_val) / range_val if range_val > 0 else x * 0 + 0.5

    @staticmethod
    def cs_quantile(x: Union[pd.Series, pd.DataFrame], q: float):
        """Cross-sectional quantile value at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.quantile(q, axis=1)
        return x.quantile(q)

    @staticmethod
    def cs_median(x: Union[pd.Series, pd.DataFrame]):
        """Cross-sectional median at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.median(axis=1)
        return x.median()

    @staticmethod
    def cs_std(x: Union[pd.Series, pd.DataFrame]):
        """Cross-sectional standard deviation at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.std(axis=1)
        return x.std()

    @staticmethod
    def cs_mean(x: Union[pd.Series, pd.DataFrame]):
        """Cross-sectional mean at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.mean(axis=1)
        return x.mean()

    @staticmethod
    def cs_max(x: Union[pd.Series, pd.DataFrame]):
        """Cross-sectional max at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.max(axis=1)
        return x.max()

    @staticmethod
    def cs_min(x: Union[pd.Series, pd.DataFrame]):
        """Cross-sectional min at each timestamp."""
        if isinstance(x, pd.DataFrame):
            return x.min(axis=1)
        return x.min()

    @staticmethod
    def cs_winsor(x: Union[pd.Series, pd.DataFrame], lower: float = 0.05, upper: float = 0.95):
        """
        Cross-sectional winsorization.
        Clip values at each timestamp to the [lower, upper] quantile range.
        """
        if isinstance(x, pd.DataFrame):
            def winsor_row(row):
                q_low = row.quantile(lower)
                q_high = row.quantile(upper)
                return row.clip(lower=q_low, upper=q_high)
            return x.apply(winsor_row, axis=1)
        q_low = x.quantile(lower)
        q_high = x.quantile(upper)
        return x.clip(lower=q_low, upper=q_high)

    @staticmethod
    def cs_rank_signed(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional rank mapped to [-1, 1].
        Useful for long-short portfolio construction.
        """
        return 2 * ops.cs_rank(x) - 1

    @staticmethod
    def cs_rank_gauss(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional rank with Gaussian (inverse normal) transformation.
        Maps ranks to standard normal distribution.
        """
        from scipy import stats
        if isinstance(x, pd.DataFrame):
            ranks = x.rank(axis=1, pct=True)
            # Clip to avoid inf at 0 and 1
            ranks = ranks.clip(lower=0.001, upper=0.999)
            return ranks.apply(lambda row: pd.Series(stats.norm.ppf(row), index=row.index), axis=1)
        ranks = x.rank(pct=True).clip(lower=0.001, upper=0.999)
        return pd.Series(stats.norm.ppf(ranks), index=x.index)

    @staticmethod
    def cs_softmax(x: Union[pd.Series, pd.DataFrame], tau: float = 1.0):
        """
        Cross-sectional softmax weights.
        tau controls temperature: higher tau = more uniform weights.
        """
        if isinstance(x, pd.DataFrame):
            # Subtract max for numerical stability
            x_shifted = x.sub(x.max(axis=1), axis=0) / max(tau, 1e-8)
            e = np.exp(x_shifted)
            return e.div(e.sum(axis=1), axis=0).fillna(0)
        x_shifted = (x - x.max()) / max(tau, 1e-8)
        e = np.exp(x_shifted)
        return e / (e.sum() + 1e-12)

    @staticmethod
    def cs_top_n_mask(x: Union[pd.Series, pd.DataFrame], n: int):
        """
        Cross-sectional top-N mask (1 for top N, 0 otherwise).
        Useful for selecting top N assets at each timestamp.
        """
        if isinstance(x, pd.DataFrame):
            ranks = x.rank(axis=1, ascending=False, method='first')
            return (ranks <= n).astype(float)
        ranks = x.rank(ascending=False, method='first')
        return (ranks <= n).astype(float)

    @staticmethod
    def cs_bottom_n_mask(x: Union[pd.Series, pd.DataFrame], n: int):
        """
        Cross-sectional bottom-N mask (-1 for bottom N, 0 otherwise).
        Useful for selecting bottom N assets (short) at each timestamp.
        """
        if isinstance(x, pd.DataFrame):
            ranks = x.rank(axis=1, ascending=True, method='first')
            return -(ranks <= n).astype(float)
        ranks = x.rank(ascending=True, method='first')
        return -(ranks <= n).astype(float)

    @staticmethod
    def cs_long_short(x: Union[pd.Series, pd.DataFrame], n: int = None, pct: float = None):
        """
        Cross-sectional long-short position.
        Long top N (or top pct%) assets, short bottom N (or bottom pct%) assets.

        Args:
            x: factor values (DataFrame: rows=timestamps, columns=assets)
            n: number of assets to long/short (mutually exclusive with pct)
            pct: percentage of assets to long/short (e.g., 0.2 = top/bottom 20%)

        Returns:
            Position matrix: +1 for long, -1 for short, 0 otherwise
        """
        if isinstance(x, pd.DataFrame):
            if pct is not None:
                n = max(1, int(x.shape[1] * pct))
            elif n is None:
                n = max(1, x.shape[1] // 5)  # Default: top/bottom 20%

            ranks_asc = x.rank(axis=1, ascending=True, method='first')
            ranks_desc = x.rank(axis=1, ascending=False, method='first')

            long_mask = (ranks_desc <= n).astype(float)
            short_mask = (ranks_asc <= n).astype(float)

            return long_mask - short_mask

        # For Series (single timestamp)
        if pct is not None:
            n = max(1, int(len(x) * pct))
        elif n is None:
            n = max(1, len(x) // 5)

        ranks_asc = x.rank(ascending=True, method='first')
        ranks_desc = x.rank(ascending=False, method='first')

        long_mask = (ranks_desc <= n).astype(float)
        short_mask = (ranks_asc <= n).astype(float)

        return long_mask - short_mask

    @staticmethod
    def cs_cap_and_renorm(weights: Union[pd.Series, pd.DataFrame], cap: float = 0.1):
        """
        Cap individual weights and renormalize to sum(|w|) = 1.
        Useful for portfolio weight constraints.
        """
        if isinstance(weights, pd.DataFrame):
            w = weights.clip(-cap, cap)
            denom = w.abs().sum(axis=1).replace(0, np.nan)
            return w.div(denom, axis=0).fillna(0)
        w = weights.clip(-cap, cap)
        denom = w.abs().sum()
        return w / denom if denom > 0 else w * 0

    @staticmethod
    def cs_neutralize_mean(x: Union[pd.Series, pd.DataFrame]):
        """
        Cross-sectional neutralization (same as cs_demean).
        Removes cross-sectional mean to make factor market-neutral.
        """
        return ops.cs_demean(x)

    @staticmethod
    def cs_clip(x: Union[pd.Series, pd.DataFrame], n_std: float = 3.0):
        """
        Cross-sectional clipping based on standard deviation.
        Clips values to [mean - n_std * std, mean + n_std * std] at each timestamp.
        """
        if isinstance(x, pd.DataFrame):
            mean = x.mean(axis=1)
            std = x.std(axis=1).replace(0, 1)  # Avoid division by zero
            lower = mean - n_std * std
            upper = mean + n_std * std
            return x.clip(lower=lower, upper=upper, axis=0)
        mean, std = x.mean(), x.std()
        std = std if std > 0 else 1
        return x.clip(lower=mean - n_std * std, upper=mean + n_std * std)

    # ========================= Data Processing =========================

    @staticmethod
    def clip(x: Union[pd.Series, pd.DataFrame, np.ndarray], min_val: float, max_val: float):
        """Clip values to range [min_val, max_val] (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.clip, min_val, max_val)
        arr = ops._to_array(x)
        result = _clip(arr, min_val, max_val)
        return ops._wrap_result(result, x)

    @staticmethod
    def filter_range(x: Union[pd.Series, pd.DataFrame, np.ndarray], min_val: float, max_val: float):
        """Set values outside range to 0 (parallel optimized)."""
        if isinstance(x, pd.DataFrame):
            return ops._apply_df(x, ops.filter_range, min_val, max_val)
        arr = ops._to_array(x)
        result = _filter_range(arr, min_val, max_val)
        return ops._wrap_result(result, x)

    @staticmethod
    def winsorize(x: Union[pd.Series, pd.DataFrame], lower: float = 0.05, upper: float = 0.95):
        """Winsorize values to quantile range."""
        if isinstance(x, pd.DataFrame):
            return x.apply(lambda col: col.clip(lower=col.quantile(lower), upper=col.quantile(upper)))
        return x.clip(lower=x.quantile(lower), upper=x.quantile(upper))

    @staticmethod
    def neutralize(x: Union[pd.Series, pd.DataFrame], groups):
        """Group neutralization (demean within groups)."""
        if isinstance(x, pd.DataFrame):
            result = x.copy()
            for col in x.columns:
                result[col] = x[col] - x[col].groupby(groups).transform('mean')
            return result
        return x - x.groupby(groups).transform('mean')

    @staticmethod
    def fill_na(x: Union[pd.Series, pd.DataFrame], value_or_method: Union[float, int, str] = 0):
        """
        Fill NaN values.

        Args:
            x: Input Series/DataFrame/array
            value_or_method: If numeric, fill with this value (default: 0);
                           if string, use method ('ffill', 'bfill')
        """
        # 如果是数字，直接填充
        if isinstance(value_or_method, (int, float)):
            if isinstance(x, (pd.Series, pd.DataFrame)):
                return x.fillna(value_or_method)
            return np.nan_to_num(x, nan=value_or_method)

        # 否则按 method 处理
        method = value_or_method
        if method == 'ffill':
            if isinstance(x, (pd.Series, pd.DataFrame)):
                return x.ffill()
            return ops._wrap_result(_forward_fill(ops._to_array(x)), x)
        elif method == 'bfill':
            return x.bfill() if isinstance(x, (pd.Series, pd.DataFrame)) else x
        return x.fillna(0) if isinstance(x, (pd.Series, pd.DataFrame)) else np.nan_to_num(x, nan=0.0)

    @staticmethod
    def replace_inf(x: Union[pd.Series, pd.DataFrame]):
        """Replace inf values with NaN."""
        return x.replace([np.inf, -np.inf], np.nan)

    @staticmethod
    def filter_extreme(x: Union[pd.Series, pd.DataFrame], method: str = 'mad', n: float = 3):
        """Filter extreme values using MAD or std method."""
        if isinstance(x, pd.DataFrame):
            return x.apply(lambda col: ops.filter_extreme(col, method, n))
        if method == 'mad':
            median = x.median()
            mad = (x - median).abs().median()
            cond = (x - median).abs() <= n * mad
            return x.where(cond, np.nan)
        elif method == 'std':
            mean = x.mean()
            std = x.std()
            cond = (x - mean).abs() <= n * std
            return x.where(cond, np.nan)
        return x

    @staticmethod
    def forward_fill_signal(x: Union[pd.Series, np.ndarray], fill_length: int = 10):
        """Forward fill non-zero signals for specified length."""
        arr = ops._to_array(x)
        result = _forward_fill_signal(arr, fill_length)
        return ops._wrap_result(result, x)

    @staticmethod
    def strategy_signal(x: Union[pd.Series, pd.DataFrame, np.ndarray], threshold: float = 1.0):
        """
        生成策略信号 (-1/0/1)，并前向填充。

        Args:
            x: 因子值 (Series, DataFrame 或 ndarray)
            threshold: 阈值，factor >= threshold 做多，factor <= -threshold 做空

        Returns:
            signal: -1 (做空), 0 (无仓位), 1 (做多)
        """
        if isinstance(x, pd.DataFrame):
            # 对 DataFrame 的每列应用
            return x.apply(lambda col: ops.strategy_signal(col, threshold))
        elif isinstance(x, pd.Series):
            sig = x.apply(lambda v: 1.0 if v >= threshold else (-1.0 if v <= -threshold else np.nan))
            sig = sig.ffill().fillna(0.0)
            return sig
        else:
            arr = np.asarray(x, dtype=np.float64)
            sig = np.where(arr >= threshold, 1.0, np.where(arr <= -threshold, -1.0, np.nan))
            # forward fill
            for i in range(1, len(sig)):
                if np.isnan(sig[i]):
                    sig[i] = sig[i - 1]
            sig = np.nan_to_num(sig, nan=0.0)
            return sig


# ============================================================================
# Tick Data Optimized Functions (Numba JIT)
# ============================================================================

@jit(nopython=True, cache=True)
def _run_persistence(side: np.ndarray) -> float:
    """
    Calculate run persistence: longest consecutive same-side run / total count.

    Args:
        side: int8 array of sides (1=buy, 0=sell or -1=sell)

    Returns:
        float: longest run / n
    """
    n = len(side)
    if n == 0:
        return 0.0
    longest = 0
    run = 1
    for i in range(1, n):
        if side[i] == side[i-1]:
            run += 1
        else:
            if run > longest:
                longest = run
            run = 1
    if run > longest:
        longest = run
    return float(longest / max(1, n))


@jit(nopython=True, cache=True)
def _lag1_autocorr(x: np.ndarray) -> float:
    """
    Calculate lag-1 autocorrelation of array.

    Args:
        x: float64 array

    Returns:
        float: correlation between x[:-1] and x[1:]
    """
    n = len(x)
    if n < 2:
        return np.nan

    # Calculate mean
    total = 0.0
    count = 0
    for i in range(n):
        if not np.isnan(x[i]):
            total += x[i]
            count += 1
    if count == 0:
        return np.nan
    x_mean = total / count

    # Calculate autocorrelation
    sum_x0_sq = 0.0
    sum_x1_sq = 0.0
    sum_prod = 0.0

    for i in range(n - 1):
        if not np.isnan(x[i]) and not np.isnan(x[i + 1]):
            x0 = x[i] - x_mean
            x1 = x[i + 1] - x_mean
            sum_x0_sq += x0 * x0
            sum_x1_sq += x1 * x1
            sum_prod += x0 * x1

    denom = np.sqrt(sum_x0_sq * sum_x1_sq)
    if denom < 1e-10:
        return np.nan
    return sum_prod / denom


@jit(nopython=True, cache=True)
def _vectorized_impact(prices: np.ndarray, mask: np.ndarray, lookahead: int = 4) -> float:
    """
    Vectorized price impact calculation for large orders.

    Args:
        prices: float64 array of prices
        mask: boolean array where True indicates large order
        lookahead: number of future prices to average

    Returns:
        float: average log price impact
    """
    n = len(prices)
    if n == 0:
        return np.nan

    total_impact = 0.0
    count = 0

    for i in range(n):
        if mask[i] and i + lookahead < n:
            # Calculate mean of next `lookahead` prices
            future_sum = 0.0
            for j in range(1, lookahead + 1):
                future_sum += np.log(prices[i + j])
            future_mean = future_sum / lookahead
            impact = future_mean - np.log(prices[i])
            total_impact += impact
            count += 1

    if count == 0:
        return np.nan
    return total_impact / count


@jit(nopython=True, cache=True)
def _slicing_score(side: np.ndarray, sizes: np.ndarray, min_run: int, cv_limit: float) -> float:
    """
    Calculate order slicing score (numba optimized).

    Detects potential order slicing by identifying runs of same-side orders
    with similar sizes (low coefficient of variation).

    Args:
        side: int8 array (1=buy, 0=sell)
        sizes: float64 array of order sizes
        min_run: minimum run length to count
        cv_limit: maximum CV to count as slicing

    Returns:
        float: slicing score
    """
    score = 0.0
    n = len(side)
    if n == 0:
        return score

    run_start = 0
    for i in range(1, n + 1):
        if i == n or side[i] != side[run_start]:
            length = i - run_start
            if length >= min_run:
                # Calculate mean and std of sizes in this run
                run_sum = 0.0
                for j in range(run_start, i):
                    run_sum += sizes[j]
                mean_sz = run_sum / length

                if mean_sz > 0:
                    # Calculate std
                    var_sum = 0.0
                    for j in range(run_start, i):
                        diff = sizes[j] - mean_sz
                        var_sum += diff * diff
                    std_sz = np.sqrt(var_sum / length)
                    cv = std_sz / (mean_sz + 1e-12)

                    if cv <= cv_limit:
                        # Find median for scoring
                        run_sizes = sizes[run_start:i].copy()
                        run_sizes.sort()
                        mid = length // 2
                        if length % 2 == 0:
                            median_sz = (run_sizes[mid - 1] + run_sizes[mid]) / 2
                        else:
                            median_sz = run_sizes[mid]
                        score += (length ** 2) * median_sz
            run_start = i
    return score


# ============================================================================
# Export
# ============================================================================

__all__ = ['ops', '_run_persistence', '_lag1_autocorr', '_vectorized_impact', '_slicing_score']
