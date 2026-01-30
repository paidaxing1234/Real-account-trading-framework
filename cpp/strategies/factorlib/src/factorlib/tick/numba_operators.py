"""
Numba优化的因子计算算子（整合自 tick_factor）
"""
import numpy as np
from numba import njit, prange
import warnings
from typing import List, Tuple

warnings.filterwarnings('ignore')

@njit(parallel=True, cache=True)
def calculate_top_volume_ratio_numba(volumes: np.ndarray, threshold: float = 0.99) -> float:
    n = len(volumes)
    if n == 0:
        return np.nan
    sorted_volumes = np.sort(volumes)[::-1]
    cumsum_volumes = np.cumsum(sorted_volumes)
    total_volume = cumsum_volumes[-1]
    if total_volume == 0:
        return np.nan
    threshold_volume = total_volume * threshold
    top_count = np.searchsorted(cumsum_volumes, threshold_volume) + 1
    return min(top_count, n) / n

@njit(parallel=True, cache=True)
def batch_calculate_factors(volume_arrays: List[np.ndarray], threshold: float = 0.99) -> np.ndarray:
    n_windows = len(volume_arrays)
    results = np.empty(n_windows, dtype=np.float32)
    for i in prange(n_windows):
        if len(volume_arrays[i]) > 0:
            results[i] = calculate_top_volume_ratio_numba(volume_arrays[i], threshold)
        else:
            results[i] = np.nan
    return results

@njit(cache=True)
def analyze_sample_window_numba(volumes: np.ndarray, threshold: float = 0.99) -> Tuple[float, float, float, float]:
    if len(volumes) == 0:
        return np.nan, np.nan, np.nan, np.nan
    sorted_volumes = np.sort(volumes)[::-1]
    cumsum_volumes = np.cumsum(sorted_volumes)
    total_volume = cumsum_volumes[-1]
    if total_volume == 0:
        return float(len(volumes)), 0.0, np.nan, np.nan
    threshold_volume = total_volume * threshold
    top_count = np.searchsorted(cumsum_volumes, threshold_volume) + 1
    top_count = min(top_count, len(volumes))
    factor_value = top_count / len(volumes)
    return float(len(volumes)), float(total_volume), float(top_count), factor_value

@njit(cache=True)
def fast_rolling_stats(values: np.ndarray, window: int) -> Tuple[np.ndarray, np.ndarray]:
    n = len(values)
    means = np.empty(n, dtype=np.float32)
    stds = np.empty(n, dtype=np.float32)
    for i in range(n):
        start_idx = max(0, i - window + 1)
        window_values = values[start_idx:i+1]
        means[i] = np.mean(window_values)
        stds[i] = np.std(window_values)
    return means, stds

@njit
def fast_big_data_stats(values: np.ndarray) -> Tuple[float, float, float, float, float]:
    if len(values) == 0:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    mean_val = np.mean(values)
    std_val = np.std(values)
    min_val = np.min(values)
    max_val = np.max(values)
    median_val = np.median(values)
    return mean_val, std_val, min_val, max_val, median_val

@njit
def smart_sampling(values: np.ndarray, max_points: int = 10000) -> Tuple[np.ndarray, np.ndarray]:
    n = len(values)
    if n <= max_points:
        return values, np.arange(n)
    step = n // max_points
    indices = np.arange(0, n, step)
    return values[indices], indices

@njit
def process_timestamps_batch(timestamps: np.ndarray) -> np.ndarray:
    return timestamps

@njit
def calculate_volume_weighted_price(prices: np.ndarray, volumes: np.ndarray) -> float:
    if len(prices) != len(volumes) or len(prices) == 0:
        return np.nan
    total_value = np.sum(prices * volumes)
    total_volume = np.sum(volumes)
    if total_volume == 0:
        return np.nan
    return total_value / total_volume

@njit(cache=True)
def calculate_trade_intensity(trade_counts: np.ndarray, window_size_ms: int = 60000) -> np.ndarray:
    return trade_counts

@njit(cache=True)
def calculate_large_trade_ratio(volumes: np.ndarray, threshold_percentile: float = 0.95) -> float:
    if len(volumes) == 0:
        return np.nan
    threshold = np.percentile(volumes, threshold_percentile * 100)
    large_trades = np.sum(volumes >= threshold)
    return large_trades / len(volumes)

@njit(cache=True)
def calculate_order_imbalance(buy_volumes: np.ndarray, sell_volumes: np.ndarray) -> float:
    total_buy = np.sum(buy_volumes)
    total_sell = np.sum(sell_volumes)
    total_volume = total_buy + total_sell
    if total_volume == 0:
        return 0.0
    return (total_buy - total_sell) / total_volume
