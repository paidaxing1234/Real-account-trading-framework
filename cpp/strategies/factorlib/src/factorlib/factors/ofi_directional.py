import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from factorlib.utils.time_utils import to_datetime_utc
from factorlib.utils.operators import _run_persistence, _lag1_autocorr

"""Directional OFI (方向与订单流不平衡) 因子集
================================================
基于逐笔成交(tick)数据，按分钟聚合，计算5个方向/订单流不平衡相关因子。

因子:
1) signed_vol_1m - 签名成交量不平衡
2) signed_notional_1m - 签名名义价值不平衡
3) count_imbalance_ratio_1m - 笔数不平衡比率
4) dir_run_persistence_1m - 方向持续性
5) dir_sign_autocorr_1m - 方向自相关

输入数据要求：
- 必需列：price, size, is_buyer_maker, tradeTime
- 可选列：quoteSize（若缺失，将使用 price*size 作为 notional）

主入口：
- parallel_compute_ofi_directional_factors(tick_df, max_workers=None) -> DataFrame
- compute_ofi_minute_factors(df_minute) -> dict
- list_ofi_factor_names() -> List[str]

方向判定：
- is_buyer_maker == False → 买方主动(taker buy) → side=+1
- is_buyer_maker == True  → 卖方主动(taker sell) → side=-1
"""

# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------

def _require_columns(df: pd.DataFrame, cols: Tuple[str, ...]):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"missing required columns: {missing}")


def _get_side_array(df: pd.DataFrame) -> np.ndarray:
    """返回方向数组：+1 表示买方主动，-1 表示卖方主动。"""
    return np.where(df['is_buyer_maker'].to_numpy() == False, 1.0, -1.0)


# ----------------------------------------------------------------------------
# 单分钟因子计算
# ----------------------------------------------------------------------------

def compute_ofi_minute_factors(df: pd.DataFrame) -> Dict[str, float]:
    """对单分钟的逐笔数据计算5个方向/订单流不平衡因子。"""
    if df.empty:
        return {k: (0.0 if 'persistence' in k else np.nan) for k in list_ofi_factor_names()}

    prices = df['price'].to_numpy(dtype=np.float64)
    sizes = df['size'].to_numpy(dtype=np.float64)
    side = _get_side_array(df)  # +1 / -1

    if 'quoteSize' in df.columns:
        notionals = df['quoteSize'].to_numpy(dtype=np.float64)
    else:
        notionals = prices * sizes

    sum_abs_sizes = np.abs(sizes).sum()
    sum_abs_notionals = np.abs(notionals).sum()

    buy_mask = side > 0
    n_buy = int(buy_mask.sum())
    n_sell = len(side) - n_buy

    # 1) signed_vol_1m
    signed_vol = (side * sizes).sum()
    signed_vol_1m = signed_vol / sum_abs_sizes if sum_abs_sizes > 0 else np.nan

    # 2) signed_notional_1m
    signed_notional = (side * notionals).sum()
    signed_notional_1m = signed_notional / sum_abs_notionals if sum_abs_notionals > 0 else np.nan

    # 3) count_imbalance_ratio_1m
    denom_cnt = n_buy + n_sell
    count_imbalance_ratio_1m = float((n_buy - n_sell) / denom_cnt) if denom_cnt > 0 else np.nan

    # 4) dir_run_persistence_1m（使用统一的 _run_persistence）
    side_bin = (side > 0).astype(np.int8)
    dir_run_persistence_1m = _run_persistence(side_bin)

    # 5) dir_sign_autocorr_1m（使用统一的 _lag1_autocorr）
    dir_sign_autocorr_1m = _lag1_autocorr(side)

    return {
        'signed_vol_1m': float(signed_vol_1m),
        'signed_notional_1m': float(signed_notional_1m),
        'count_imbalance_ratio_1m': float(count_imbalance_ratio_1m),
        'dir_run_persistence_1m': float(dir_run_persistence_1m),
        'dir_sign_autocorr_1m': float(dir_sign_autocorr_1m),
    }


# ----------------------------------------------------------------------------
# 并行整表分钟聚合（与 large_order_tick 类似的接口与行为）
# ----------------------------------------------------------------------------

def parallel_compute_ofi_directional_factors(
    tick_df: pd.DataFrame,
    max_workers: int | None = None,
    MAX_WORKERS: int | None = None,
) -> pd.DataFrame:
    """并行计算方向/订单流不平衡类因子（按分钟）。
    - 逐笔时间列：tradeTime（自动识别秒/毫秒或 datetime）
    - 将以 floor('T') 聚合到分钟，返回以 CloseTime 为索引的 DataFrame。
    - max_workers 未指定时，默认使用 CPU 一半（向上取整），不超过分钟数。
    """
    # 兼容别名
    if MAX_WORKERS is not None:
        max_workers = MAX_WORKERS

    _require_columns(tick_df, ('price', 'size', 'is_buyer_maker', 'tradeTime'))

    # 统一时间并排序（使用统一的时间转换函数）
    tdt = to_datetime_utc(tick_df['tradeTime'])
    dfw = tick_df.assign(_tradeTime_dt=tdt).sort_values('_tradeTime_dt')

    # 分钟分组
    groups = list(dfw.groupby(dfw['_tradeTime_dt'].dt.floor('T')))

    # 自动 worker
    if max_workers is None or max_workers <= 0:
        env_override = os.getenv('FACTORLIB_MAX_WORKERS')
        if env_override:
            try:
                max_workers = int(env_override)
            except ValueError:
                max_workers = None
        if max_workers is None or max_workers <= 0:
            cpu = os.cpu_count() or 1
            max_workers = max(1, (cpu + 1) // 2)
    max_workers = max(1, min(max_workers, len(groups)))

    def _task(item):
        minute, dfm = item
        d = compute_ofi_minute_factors(dfm)
        d['CloseTime'] = minute
        return d

    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for ret in ex.map(_task, groups):
            results.append(ret)

    if not results:
        raise RuntimeError('无分钟聚合结果')

    out = pd.DataFrame(results).set_index('CloseTime').sort_index()
    return out


def list_ofi_factor_names() -> List[str]:
    return [
        'signed_vol_1m',
        'signed_notional_1m',
        'count_imbalance_ratio_1m',
        'dir_run_persistence_1m',
        'dir_sign_autocorr_1m',
    ]


__all__ = [
    'compute_ofi_minute_factors',
    'parallel_compute_ofi_directional_factors',
    'list_ofi_factor_names',
]
