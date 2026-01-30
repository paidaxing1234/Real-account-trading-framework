"""
Batch utilities for computing large-order minute factors from tick files.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd

from .io import load_tick, extract_symbol
from ..factors.large_order_tick import parallel_compute_large_order_factors
from ..factors.ofi_directional import parallel_compute_ofi_directional_factors

__all__ = [
    "compute_large_order_factors_for_file",
    "compute_factors_with_symbol",
    "compute_ofi_factors_for_file",
    "compute_ofi_with_symbol",
]


def compute_large_order_factors_for_file(
    path: str,
    fixed_threshold: float = 2,
    adaptive_q: Optional[float] = None,
    cv_limit: float = 0.25,
    min_run: int = 3,
    use_adaptive: bool = False,
    max_workers: int = 1,
) -> pd.DataFrame:
    """
    读取一个 tick/aggTrades 文件，标准化为所需列并计算 10 个大单分钟因子。

    返回以 CloseTime 为索引的 DataFrame（按时间排序）。
    """
    df_tick = load_tick(path)
    fac = parallel_compute_large_order_factors(
        tick_df=df_tick,
        fixed_threshold=fixed_threshold,
        adaptive_quantile=adaptive_q,
        cv_limit=cv_limit,
        min_run=min_run,
        use_adaptive=use_adaptive,
        max_workers=max_workers,
    )
    return fac.sort_index()


def compute_factors_with_symbol(
    path: str,
    fixed_threshold: float = 2,
    adaptive_q: Optional[float] = None,
    cv_limit: float = 0.25,
    min_run: int = 3,
    use_adaptive: bool = False,
    max_workers: int = 1,
) -> pd.DataFrame:
    """
    读取一个文件并计算分钟因子，同时附加 symbol 列并 reset_index（便于后续合并保存）。
    """
    fac = compute_large_order_factors_for_file(
        path,
        fixed_threshold=fixed_threshold,
        adaptive_q=adaptive_q,
        cv_limit=cv_limit,
        min_run=min_run,
        use_adaptive=use_adaptive,
        max_workers=max_workers,
    )
    df = fac.reset_index()
    df.insert(0, "symbol", extract_symbol(path))
    return df


def compute_ofi_factors_for_file(
    path: str,
    max_workers: int = 1,
) -> pd.DataFrame:
    """
    读取一个 tick/aggTrades 文件并计算 OFI（方向/订单流不平衡）分钟因子。

    返回以 CloseTime 为索引的 DataFrame（按时间排序）。
    """
    df_tick = load_tick(path)
    fac = parallel_compute_ofi_directional_factors(
        tick_df=df_tick,
        max_workers=max_workers,
    )
    return fac.sort_index()


def compute_ofi_with_symbol(
    path: str,
    max_workers: int = 1,
) -> pd.DataFrame:
    """
    读取一个文件并计算 OFI 分钟因子，同时附加 symbol 列并 reset_index（便于后续合并保存）。
    """
    fac = compute_ofi_factors_for_file(path, max_workers=max_workers)
    df = fac.reset_index()
    df.insert(0, "symbol", extract_symbol(path))
    return df
