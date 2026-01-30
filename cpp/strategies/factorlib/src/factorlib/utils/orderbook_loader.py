"""
Orderbook Data Loader - 极致性能盘口数据加载与对齐

使用 Polars + Numba JIT 实现最高性能
- Polars: 高性能 parquet 读取 (比 pandas 快 5-10x)
- Numba JIT: 高性能时间戳对齐
- ThreadPoolExecutor: 并行加载避免 pickle 开销
- 智能缓存: 首次读取后缓存，下次直接加载 (~10x faster)

Usage:
    from factorlib.utils.orderbook_loader import load_orderbook_panel, align_orderbook_to_kline

    panel = load_orderbook_panel(panel, orderbook_dir='/home/ch/data/orderbook', ob_levels=5)
"""

import os
import hashlib
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob
from numba import jit, prange

# Polars for high-performance parquet reading
try:
    import polars as pl
    HAS_POLARS = True
except ImportError:
    HAS_POLARS = False
    import pyarrow.dataset as ds


DEFAULT_ORDERBOOK_DIR = '/home/ch/data/orderbooks/OKX_PERP'
DEFAULT_CACHE_DIR = '/home/ch/data/feature_research/orderbook_cache'


# ============================================================================
# Numba JIT 加速核心函数
# ============================================================================

@jit(nopython=True, cache=True, fastmath=True)
def _compute_indices(
    ob_times: np.ndarray,     # int64 纳秒时间戳
    kline_times: np.ndarray,  # int64 纳秒时间戳
) -> np.ndarray:
    """
    计算对齐索引 - 找每个 kline 时间点之前最近的 orderbook
    使用二分查找，O(n log m) 复杂度
    """
    n = len(kline_times)
    indices = np.empty(n, dtype=np.int64)
    n_ob = len(ob_times)

    for i in range(n):
        # 二分查找 right side - 1
        lo, hi = 0, n_ob
        v = kline_times[i]
        while lo < hi:
            mid = (lo + hi) >> 1
            if ob_times[mid] <= v:
                lo = mid + 1
            else:
                hi = mid
        indices[i] = lo - 1  # right - 1 = 最后一个 <= v 的位置

    return indices


# ============================================================================
# 缓存管理 - 带元数据验证
# ============================================================================

import json
from datetime import datetime

def _get_cache_paths(
    instrument: str,
    start_date: str,
    end_date: str,
    ob_levels: int,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> tuple:
    """获取缓存文件路径 (data + metadata)"""
    # 标准化品种名称
    inst_clean = instrument.replace('-SWAP', '').replace('-', '_')
    inst_cache_dir = os.path.join(cache_dir, inst_clean)

    # 缓存文件名: {instrument}/{start}_{end}_L{levels}.parquet
    base_name = f"{start_date}_{end_date}_L{ob_levels}"
    data_path = os.path.join(inst_cache_dir, f"{base_name}.parquet")
    meta_path = os.path.join(inst_cache_dir, f"{base_name}.meta.json")

    return data_path, meta_path


def _create_cache_metadata(
    instrument: str,
    start_date: str,
    end_date: str,
    ob_levels: int,
    orderbook_dir: str,
    df: pd.DataFrame,
) -> dict:
    """创建缓存元数据"""
    return {
        'instrument': instrument,
        'start_date': start_date,
        'end_date': end_date,
        'ob_levels': ob_levels,
        'orderbook_dir': orderbook_dir,
        'row_count': len(df),
        'columns': list(df.columns),
        'created_at': datetime.now().isoformat(),
        'version': '1.0',
    }


def _validate_cache_metadata(
    meta: dict,
    instrument: str,
    start_date: str,
    end_date: str,
    ob_levels: int,
    orderbook_dir: str,
    verbose: bool = True,
) -> bool:
    """验证缓存元数据是否匹配"""
    checks = [
        ('instrument', meta.get('instrument'), instrument),
        ('start_date', meta.get('start_date'), start_date),
        ('end_date', meta.get('end_date'), end_date),
        ('ob_levels', meta.get('ob_levels'), ob_levels),
        ('orderbook_dir', meta.get('orderbook_dir'), orderbook_dir),
    ]

    all_match = True
    for name, cached_val, expected_val in checks:
        if cached_val != expected_val:
            if verbose:
                print(f"  Cache mismatch: {name} = {cached_val} (cached) vs {expected_val} (requested)")
            all_match = False

    return all_match


def _load_from_cache(
    instrument: str,
    start_date: str,
    end_date: str,
    ob_levels: int,
    orderbook_dir: str,
    cache_dir: str = DEFAULT_CACHE_DIR,
    verbose: bool = True,
) -> Optional[pd.DataFrame]:
    """从缓存加载数据 - 带完整参数验证"""
    data_path, meta_path = _get_cache_paths(instrument, start_date, end_date, ob_levels, cache_dir)

    # 检查文件是否存在
    if not os.path.exists(data_path) or not os.path.exists(meta_path):
        return None

    try:
        # 加载并验证元数据
        with open(meta_path, 'r') as f:
            meta = json.load(f)

        if verbose:
            print(f"  Found cache: {os.path.basename(data_path)}")
            print(f"    Created: {meta.get('created_at', 'unknown')}")
            print(f"    Params: instrument={meta.get('instrument')}, "
                  f"start={meta.get('start_date')}, end={meta.get('end_date')}, "
                  f"levels={meta.get('ob_levels')}")
            print(f"    Rows: {meta.get('row_count', 'unknown'):,}")

        # 严格验证所有参数
        if not _validate_cache_metadata(meta, instrument, start_date, end_date, ob_levels, orderbook_dir, verbose):
            if verbose:
                print("  Cache parameters mismatch, will reload from source")
            return None

        # 加载数据
        if HAS_POLARS:
            df = pl.read_parquet(data_path).to_pandas()
        else:
            df = pd.read_parquet(data_path)

        # 恢复时间戳索引
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            df = df.set_index('timestamp')

        if verbose:
            print(f"  ✓ Cache loaded successfully")

        return df

    except Exception as e:
        print(f"Warning: Failed to load cache {data_path}: {e}")
        return None


def _save_to_cache(
    df: pd.DataFrame,
    instrument: str,
    start_date: str,
    end_date: str,
    ob_levels: int,
    orderbook_dir: str,
    cache_dir: str = DEFAULT_CACHE_DIR,
    verbose: bool = True,
) -> bool:
    """保存数据到缓存 - 同时保存元数据"""
    data_path, meta_path = _get_cache_paths(instrument, start_date, end_date, ob_levels, cache_dir)

    try:
        # 确保目录存在
        cache_dir_path = os.path.dirname(data_path)
        os.makedirs(cache_dir_path, exist_ok=True)

        # 保存数据
        df_to_save = df.reset_index()
        if HAS_POLARS:
            pl.from_pandas(df_to_save).write_parquet(data_path, compression='zstd')
        else:
            df_to_save.to_parquet(data_path, compression='zstd')

        # 保存元数据
        meta = _create_cache_metadata(instrument, start_date, end_date, ob_levels, orderbook_dir, df)
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

        if verbose:
            file_size = os.path.getsize(data_path) / (1024 * 1024)  # MB
            print(f"  ✓ Cache saved: {os.path.basename(data_path)} ({file_size:.1f} MB)")

        return True

    except Exception as e:
        print(f"Warning: Failed to save cache {data_path}: {e}")
        return False


def clear_cache(instrument: str = None, cache_dir: str = DEFAULT_CACHE_DIR):
    """
    清除缓存

    Args:
        instrument: 品种名称，None 表示清除所有
        cache_dir: 缓存目录
    """
    import shutil

    if instrument is None:
        # 清除所有缓存
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            print(f"Cleared all cache in {cache_dir}")
    else:
        # 清除特定品种的缓存
        inst_clean = instrument.replace('-SWAP', '').replace('-', '_')
        inst_cache_dir = os.path.join(cache_dir, inst_clean)
        if os.path.exists(inst_cache_dir):
            shutil.rmtree(inst_cache_dir)
            print(f"Cleared cache for {instrument}")


# ============================================================================
# 核心加载函数
# ============================================================================

def _normalize_instrument(name: str, suffix: str = '-SWAP') -> str:
    """标准化品种名称，自动添加后缀"""
    if not name.endswith(suffix):
        return name + suffix
    return name


def _get_selected_files(inst_dir: str, start_date: str, end_date: str = None) -> List[str]:
    """获取日期范围内的文件列表"""
    files = sorted(glob(os.path.join(inst_dir, '*.parquet')))
    if not files:
        return []

    start_dt = pd.to_datetime(start_date).date()
    end_dt = pd.to_datetime(end_date).date() if end_date else None

    selected_files = []
    for f in files:
        fname = os.path.basename(f)
        try:
            file_date = pd.to_datetime(fname.replace('.parquet', '')).date()
            if file_date >= start_dt:
                if end_dt is None or file_date <= end_dt:
                    selected_files.append(f)
        except:
            continue

    return selected_files


def _load_orderbook_raw_polars(
    instrument: str,
    start_date: str,
    end_date: str,
    orderbook_dir: str,
    ob_levels: int,
) -> pd.DataFrame:
    """
    从原始文件加载 orderbook 数据 - Polars 版
    """
    # 自动添加 -SWAP 后缀
    instrument = _normalize_instrument(instrument)

    inst_dir = os.path.join(orderbook_dir, instrument)
    if not os.path.exists(inst_dir):
        raise FileNotFoundError(f"Orderbook directory not found: {inst_dir}")

    selected_files = _get_selected_files(inst_dir, start_date, end_date)
    if not selected_files:
        raise FileNotFoundError(f"No files found for date range {start_date} - {end_date}")

    # 构建需要的列名
    cols_to_load = ['timestamp']
    rename_map = {}
    for lvl in range(ob_levels):
        for side, ob_side in [('asks', 'asks'), ('bids', 'bids')]:
            for attr in ['price', 'amount']:
                old_col = f'{side}_{lvl}__{attr}'
                new_col = f'ob_{ob_side}_{lvl}_{attr}'
                cols_to_load.append(old_col)
                rename_map[old_col] = new_col

    # Polars lazy scan + collect
    lf = pl.scan_parquet(selected_files, n_rows=None)
    lf = lf.select(cols_to_load).rename(rename_map)
    df_pl = lf.collect()

    # 转换为 pandas
    df = df_pl.to_pandas()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.set_index('timestamp')

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    return df


def _load_orderbook_raw_pyarrow(
    instrument: str,
    start_date: str,
    end_date: str,
    orderbook_dir: str,
    ob_levels: int,
) -> pd.DataFrame:
    """
    从原始文件加载 orderbook 数据 - PyArrow 版
    """
    import pyarrow.dataset as ds

    instrument = _normalize_instrument(instrument)

    inst_dir = os.path.join(orderbook_dir, instrument)
    if not os.path.exists(inst_dir):
        raise FileNotFoundError(f"Orderbook directory not found: {inst_dir}")

    selected_files = _get_selected_files(inst_dir, start_date, end_date)
    if not selected_files:
        raise FileNotFoundError(f"No files found for date range {start_date} - {end_date}")

    cols_to_load = ['timestamp']
    for lvl in range(ob_levels):
        cols_to_load.extend([
            f'asks_{lvl}__price', f'asks_{lvl}__amount',
            f'bids_{lvl}__price', f'bids_{lvl}__amount'
        ])

    dataset = ds.dataset(selected_files, format='parquet')
    table = dataset.to_table(columns=cols_to_load)
    df = table.to_pandas(split_blocks=True, self_destruct=True)

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

    rename_map = {'timestamp': 'timestamp'}
    for lvl in range(ob_levels):
        rename_map[f'asks_{lvl}__price'] = f'ob_asks_{lvl}_price'
        rename_map[f'asks_{lvl}__amount'] = f'ob_asks_{lvl}_amount'
        rename_map[f'bids_{lvl}__price'] = f'ob_bids_{lvl}_price'
        rename_map[f'bids_{lvl}__amount'] = f'ob_bids_{lvl}_amount'

    df = df.rename(columns=rename_map)
    df = df.set_index('timestamp')

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    return df


def load_orderbook_files(
    instrument: str,
    start_date: str,
    end_date: str = None,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    加载单个品种的 orderbook 数据 - 带智能缓存

    首次读取从原始文件加载并缓存，后续直接从缓存加载 (~10x faster)
    只有所有参数完全匹配时才使用缓存

    Args:
        instrument: 品种名称
        start_date: 起始日期
        end_date: 结束日期
        orderbook_dir: 原始数据目录
        ob_levels: 档位数
        cache_dir: 缓存目录
        use_cache: 是否使用缓存
        verbose: 是否显示详细缓存信息

    Returns:
        DataFrame with orderbook data

    Cache validation parameters:
        - instrument: 品种名称
        - start_date: 起始日期
        - end_date: 结束日期
        - ob_levels: 档位数
        - orderbook_dir: 数据源目录
    """
    # 标准化品种名称
    inst_normalized = _normalize_instrument(instrument)

    # 确定结束日期
    if end_date is None:
        inst_dir = os.path.join(orderbook_dir, inst_normalized)
        if os.path.exists(inst_dir):
            files = sorted(glob(os.path.join(inst_dir, '*.parquet')))
            if files:
                end_date = os.path.basename(files[-1]).replace('.parquet', '')
            else:
                end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        else:
            end_date = pd.Timestamp.now().strftime('%Y-%m-%d')

    # 尝试从缓存加载（严格参数验证）
    if use_cache:
        df = _load_from_cache(
            instrument=inst_normalized,
            start_date=start_date,
            end_date=end_date,
            ob_levels=ob_levels,
            orderbook_dir=orderbook_dir,
            cache_dir=cache_dir,
            verbose=verbose,
        )
        if df is not None:
            return df

    # 从原始文件加载
    if verbose:
        print(f"  Loading from source: {orderbook_dir}/{inst_normalized}")
    if HAS_POLARS:
        df = _load_orderbook_raw_polars(instrument, start_date, end_date, orderbook_dir, ob_levels)
    else:
        df = _load_orderbook_raw_pyarrow(instrument, start_date, end_date, orderbook_dir, ob_levels)

    # 保存到缓存
    if use_cache:
        _save_to_cache(
            df=df,
            instrument=inst_normalized,
            start_date=start_date,
            end_date=end_date,
            ob_levels=ob_levels,
            orderbook_dir=orderbook_dir,
            cache_dir=cache_dir,
            verbose=verbose,
        )

    return df


# 保持旧 API 兼容
def load_orderbook_files_polars(
    instrument: str,
    start_date: str,
    end_date: str = None,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
) -> pd.DataFrame:
    """Polars 版本（不使用缓存）"""
    if end_date is None:
        inst = _normalize_instrument(instrument)
        inst_dir = os.path.join(orderbook_dir, inst)
        files = sorted(glob(os.path.join(inst_dir, '*.parquet')))
        end_date = os.path.basename(files[-1]).replace('.parquet', '') if files else pd.Timestamp.now().strftime('%Y-%m-%d')
    return _load_orderbook_raw_polars(instrument, start_date, end_date, orderbook_dir, ob_levels)


def load_orderbook_files_pyarrow(
    instrument: str,
    start_date: str,
    end_date: str = None,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
) -> pd.DataFrame:
    """PyArrow 版本（不使用缓存）"""
    if end_date is None:
        inst = _normalize_instrument(instrument)
        inst_dir = os.path.join(orderbook_dir, inst)
        files = sorted(glob(os.path.join(inst_dir, '*.parquet')))
        end_date = os.path.basename(files[-1]).replace('.parquet', '') if files else pd.Timestamp.now().strftime('%Y-%m-%d')
    return _load_orderbook_raw_pyarrow(instrument, start_date, end_date, orderbook_dir, ob_levels)


def align_orderbook_to_kline(
    ob_df: pd.DataFrame,
    kline_index: pd.DatetimeIndex,
    method: str = 'snapshot'
) -> pd.DataFrame:
    """
    将 orderbook 数据对齐到 K线时间戳 - 极致性能版

    使用 Numba JIT 二分查找 + NumPy fancy indexing

    Args:
        ob_df: orderbook DataFrame (timestamp index)
        kline_index: K线时间索引
        method: 对齐方式 ('snapshot' 默认)

    Returns:
        DataFrame aligned to kline_index
    """
    # 确保时间戳是有序的
    if not ob_df.index.is_monotonic_increasing:
        ob_df = ob_df.sort_index()

    # 转换为 int64 纳秒时间戳（Numba 兼容）
    ob_times = ob_df.index.values.astype('datetime64[ns]').view(np.int64)
    kline_times = kline_index.values.astype('datetime64[ns]').view(np.int64)

    # JIT 加速：计算对齐索引
    indices = _compute_indices(ob_times, kline_times)

    # Clip 索引范围（处理边界）
    indices = np.clip(indices, 0, len(ob_df) - 1)

    # NumPy fancy indexing - 直接提取（最快方式）
    columns = ob_df.columns
    ob_values = ob_df.values
    out = ob_values[indices]

    # 处理无效位置（kline 时间早于 orderbook）
    first_ob_time = ob_times[0]
    invalid_mask = kline_times < first_ob_time
    if invalid_mask.any():
        out = out.astype(np.float64)  # 确保可以写入 NaN
        out[invalid_mask] = np.nan

    # 构建 DataFrame
    return pd.DataFrame(out, index=kline_index, columns=columns, copy=False)


def load_orderbook_aligned(
    instrument: str,
    kline_index: pd.DatetimeIndex,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    加载单个品种的 orderbook 并对齐到 K线时间戳
    """
    start_date = kline_index.min().strftime('%Y-%m-%d')
    end_date = kline_index.max().strftime('%Y-%m-%d')

    # 加载原始数据（带缓存）
    ob_df = load_orderbook_files(
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
        orderbook_dir=orderbook_dir,
        ob_levels=ob_levels,
        cache_dir=cache_dir,
        use_cache=use_cache,
    )

    # 对齐
    aligned = align_orderbook_to_kline(ob_df, kline_index)

    return aligned


def _load_one_instrument_thread(
    inst: str,
    kline_index: pd.DatetimeIndex,
    orderbook_dir: str,
    ob_levels: int,
    start_date: str,
    end_date: str,
    cache_dir: str,
    use_cache: bool,
):
    """线程池 worker 函数 - 避免 pickle 开销"""
    try:
        # 加载原始数据（带缓存）
        ob_df = load_orderbook_files(
            inst, start_date, end_date, orderbook_dir, ob_levels,
            cache_dir=cache_dir, use_cache=use_cache
        )

        # 对齐
        aligned = align_orderbook_to_kline(ob_df, kline_index)

        return inst, aligned
    except Exception as e:
        print(f"Warning: Failed to load orderbook for {inst}: {e}")
        return inst, None


def load_orderbook_multi(
    instruments: List[str],
    kline_index: pd.DatetimeIndex,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
    max_workers: int = None,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    并行加载多个品种的 orderbook 数据并对齐

    使用 ThreadPoolExecutor 避免 multiprocessing 的 pickle 开销
    支持智能缓存，首次加载后下次直接从缓存读取

    Args:
        instruments: 品种列表
        kline_index: K线时间索引
        orderbook_dir: orderbook 目录
        ob_levels: 档位数
        max_workers: 并行线程数
        cache_dir: 缓存目录
        use_cache: 是否使用缓存

    Returns:
        Dict[instrument -> aligned DataFrame]
    """
    if max_workers is None:
        max_workers = min(len(instruments), os.cpu_count() or 4)

    start_date = kline_index.min().strftime('%Y-%m-%d')
    end_date = kline_index.max().strftime('%Y-%m-%d')

    results = {}

    # 使用 ThreadPoolExecutor (共享内存，无 pickle 开销)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _load_one_instrument_thread,
                inst, kline_index, orderbook_dir, ob_levels, start_date, end_date,
                cache_dir, use_cache
            ): inst
            for inst in instruments
        }

        for future in as_completed(futures):
            inst, df = future.result()
            if df is not None:
                results[inst] = df

    return results


def add_orderbook_to_panel(
    panel,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
):
    """
    将 orderbook 数据添加到 PanelData

    Args:
        panel: PanelData 对象（包含 K线数据）
        orderbook_dir: orderbook 数据目录
        ob_levels: 加载几档深度
        cache_dir: 缓存目录
        use_cache: 是否使用缓存

    Returns:
        更新后的 PanelData（包含 orderbook 列）

    Cache Key Parameters (all must match for cache hit):
        - instrument: 品种名称
        - start_date: 数据起始日期
        - end_date: 数据结束日期
        - ob_levels: 订单簿档位数
        - orderbook_dir: 数据源目录
    """
    instruments = panel.assets
    kline_index = panel.index
    start_date = kline_index.min().strftime('%Y-%m-%d')
    end_date = kline_index.max().strftime('%Y-%m-%d')

    print(f"Loading orderbook data for {len(instruments)} instruments...")
    print(f"  Parameters:")
    print(f"    - start_date: {start_date}")
    print(f"    - end_date: {end_date}")
    print(f"    - ob_levels: {ob_levels}")
    print(f"    - orderbook_dir: {orderbook_dir}")
    print(f"    - cache_dir: {cache_dir}")
    print(f"    - use_cache: {use_cache}")
    if HAS_POLARS:
        print("  Using Polars for high-performance parquet reading")

    # 并行加载并对齐
    ob_data = load_orderbook_multi(
        instruments=instruments,
        kline_index=kline_index,
        orderbook_dir=orderbook_dir,
        ob_levels=ob_levels,
        cache_dir=cache_dir,
        use_cache=use_cache,
    )

    if not ob_data:
        print("Warning: No orderbook data loaded")
        return panel

    # 获取 orderbook 的列名
    sample_df = next(iter(ob_data.values()))
    ob_columns = sample_df.columns.tolist()

    # 为每个 orderbook 列创建 Panel DataFrame
    for col in ob_columns:
        col_dict = {}
        for inst in instruments:
            if inst in ob_data:
                col_dict[inst] = ob_data[inst][col]
            else:
                col_dict[inst] = pd.Series(np.nan, index=kline_index)

        panel_df = pd.DataFrame(col_dict)
        panel[col] = panel_df

    loaded_count = len(ob_data)
    print(f"Loaded orderbook for {loaded_count}/{len(instruments)} instruments")
    print(f"Added {len(ob_columns)} orderbook columns to panel")

    return panel


# ============================================================================
# 便捷函数
# ============================================================================

def load_panel_with_orderbook(
    instruments: List[str],
    start_date: str,
    kline_data_dir: str,
    orderbook_dir: str = DEFAULT_ORDERBOOK_DIR,
    ob_levels: int = 5,
    max_workers: int = None,
    cache_dir: str = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
):
    """
    一次性加载 K线 + Orderbook 数据

    Args:
        instruments: 品种列表
        start_date: 起始日期
        kline_data_dir: K线数据目录
        orderbook_dir: orderbook 数据目录
        ob_levels: 档位数
        max_workers: 并行数
        cache_dir: 缓存目录
        use_cache: 是否使用缓存

    Returns:
        PanelData with both kline and orderbook data
    """
    from factorlib.cli import load_panel_data_parquet

    # 加载 K线
    panel = load_panel_data_parquet(
        instruments=instruments,
        start_date=start_date,
        data_dir=kline_data_dir,
        max_workers=max_workers
    )

    # 添加 orderbook
    panel = add_orderbook_to_panel(
        panel, orderbook_dir, ob_levels,
        cache_dir=cache_dir, use_cache=use_cache
    )

    return panel


# ============================================================================
# Export
# ============================================================================

__all__ = [
    'load_orderbook_files',
    'align_orderbook_to_kline',
    'load_orderbook_aligned',
    'load_orderbook_multi',
    'add_orderbook_to_panel',
    'load_panel_with_orderbook',
    'clear_cache',
    'DEFAULT_CACHE_DIR',
]
