import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import os
import numba

from factorlib.utils.time_utils import to_datetime_utc
from factorlib.utils.operators import _run_persistence, _vectorized_impact, _slicing_score

"""Large Order (大单) 分钟级因子工具集
====================================================================
提供基于逐笔成交(agg trade) 数据按分钟聚合的大单相关因子 + 并行批量计算接口。

因子列表 (scalar per minute):
1. large_buy_ratio         : 大单主动买成交量 / 当分钟总成交量
2. large_sell_impact       : 大单主动卖后价格冲击（向量化优化）
3. large_order_density     : 大单笔数（出现频次）
4. large_dir_imbalance     : (大单主动买成交量 - 大单主动卖成交量) / 大单总量
5. large_slicing_score     : 大单拆单迹象评分
6. large_signed_impact     : 大单方向加权的价格变化均值
7. large_interarrival_cv   : 大单到达间隔变异系数
8. large_tail_concentration: 大单尺寸分布尾部集中度
9. large_run_persistence   : 大单同侧最长连击比例
10. large_move_coverage    : 大单触发的价格变化覆盖度
11. top_volume_ratio       : 顶端累计成交量覆盖比例

主动方向(Aggressor) 判定：
- is_buyer_maker == False -> 买方为 taker -> 主动买 (+1)
- is_buyer_maker == True  -> 卖方为 taker -> 主动卖 (-1)

Main entry:
- parallel_compute_large_order_factors(tick_df, ...) -> DataFrame(index=minute)
- list_large_order_factor_names() -> List[str]
"""

# ----------------------------------------------------------------------------
# 单因子函数（对单分钟 DataFrame）
# ----------------------------------------------------------------------------

def large_buy_ratio(df: pd.DataFrame, size_threshold: float = 100) -> float:
    if df.empty:
        return np.nan
    large_buy = df[(df['size'] >= size_threshold) & (df['is_buyer_maker'] == False)]
    total = df['size'].sum()
    if total <= 0:
        return np.nan
    return large_buy['size'].sum() / total


def large_sell_impact(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """
    计算大单主动卖后的价格冲击（向量化优化）。

    使用 numba 加速的 _vectorized_impact 函数计算。
    """
    if df.empty:
        return np.nan
    prices = df['price'].to_numpy(dtype=np.float64)
    sizes = df['size'].to_numpy(dtype=np.float64)
    is_buyer_maker = df['is_buyer_maker'].to_numpy(dtype=np.bool_)

    # 大单卖出: size >= threshold AND is_buyer_maker == True
    mask = (sizes >= size_threshold) & is_buyer_maker
    if not mask.any():
        return np.nan

    return _vectorized_impact(prices, mask, lookahead=4)


def large_buy_impact(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """
    计算大单主动买后的价格冲击（向量化优化）。

    使用 numba 加速的 _vectorized_impact 函数计算。
    """
    if df.empty:
        return np.nan
    prices = df['price'].to_numpy(dtype=np.float64)
    sizes = df['size'].to_numpy(dtype=np.float64)
    is_buyer_maker = df['is_buyer_maker'].to_numpy(dtype=np.bool_)

    # 大单买入: size >= threshold AND is_buyer_maker == False
    mask = (sizes >= size_threshold) & (~is_buyer_maker)
    if not mask.any():
        return np.nan

    return _vectorized_impact(prices, mask, lookahead=4)


def large_order_density(df: pd.DataFrame, size_threshold: float = 100) -> int:
    if df.empty:
        return 0
    return int((df['size'] >= size_threshold).sum())


def large_order_directional_imbalance(df: pd.DataFrame, size_threshold: float = 100) -> float:
    if df.empty:
        return np.nan
    large = df[df['size'] >= size_threshold]
    if large.empty:
        return 0.0
    buy_vol = large[large['is_buyer_maker'] == False]['size'].sum()
    sell_vol = large[large['is_buyer_maker'] == True]['size'].sum()
    denom = buy_vol + sell_vol
    if denom <= 10:
        return 0.0
    return float((buy_vol - sell_vol) / denom)


def large_order_slicing_score(df: pd.DataFrame, size_threshold: float = 100, cv_limit: float = 0.25, min_run: int = 3) -> float:
    """
    大单拆单迹象评分（使用统一的 _slicing_score 函数）。
    """
    if df.empty:
        return np.nan
    dfl = df[df['size'] >= size_threshold]
    if dfl.empty:
        return 0.0
    # 确保时间顺序
    if not dfl.index.is_monotonic_increasing:
        dfl = dfl.sort_index()
    side = (~dfl['is_buyer_maker']).astype(np.int8).to_numpy(dtype=np.int8)
    sizes = dfl['size'].to_numpy(dtype=np.float64)
    score = _slicing_score(side, sizes, min_run, cv_limit)
    total_vol = df['size'].sum()
    if total_vol <= 0:
        return 0.0
    return float(score / total_vol)

# ======================== 新增 5 个大单事件相关因子 ========================

def large_signed_impact(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """大单方向加权的下一笔价格变化均值：买(+1)×Δp，卖(-1)×Δp"""
    if df.empty:
        return np.nan
    dfm = df
    mask_large = dfm['size'] >= size_threshold
    if not mask_large.any():
        return np.nan
    prices = dfm['price'].to_numpy()
    side = np.where(dfm['is_buyer_maker'].to_numpy() == False, 1.0, -1.0)
    idxs = np.flatnonzero(mask_large.to_numpy())
    valid = idxs[idxs + 1 < len(dfm)]
    if valid.size == 0:
        return np.nan
    dp = prices[valid + 1] - prices[valid]
    vals = side[valid] * dp
    return float(vals.mean()) if vals.size else np.nan


def large_interarrival_cv(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """大单到达间隔变异系数 CV=std/mean（使用统一的时间转换函数）。"""
    if df.empty or 'tradeTime' not in df.columns:
        return np.nan
    dfl = df[df['size'] >= size_threshold]
    if dfl.shape[0] < 2:
        return np.nan
    t = to_datetime_utc(dfl['tradeTime'])
    t_ns = t.astype('int64').to_numpy(dtype=np.int64)
    dt_ms = np.diff(t_ns) / 1e6  # 转毫秒
    if dt_ms.size == 0:
        return np.nan
    mu = np.mean(dt_ms)
    if mu <= 0:
        return np.nan
    return float(np.std(dt_ms) / mu)


def large_tail_concentration(df: pd.DataFrame, size_threshold: float = 100, q: float = 0.8) -> float:
    """大单尺寸分布尾部集中度：Top q 分位以上体量 / 大单总体量"""
    if df.empty:
        return np.nan
    dfl = df[df['size'] >= size_threshold]
    if dfl.empty:
        return 0.0
    thr = float(dfl['size'].quantile(q))
    top_vol = dfl.loc[dfl['size'] >= thr, 'size'].sum()
    total_vol = dfl['size'].sum()
    if total_vol <= 0:
        return 0.0
    return float(top_vol / total_vol)


def large_run_persistence(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """大单同侧最长连击比例（使用统一的 _run_persistence 函数）。"""
    if df.empty:
        return np.nan
    dfl = df[df['size'] >= size_threshold]
    n = len(dfl)
    if n == 0:
        return 0.0
    side = (~dfl['is_buyer_maker']).astype(np.int8).to_numpy(dtype=np.int8)
    return _run_persistence(side)


def large_move_coverage(df: pd.DataFrame, size_threshold: float = 100) -> float:
    """大单触发的相邻价格变化绝对值之和 / 分钟价格区间(High-Low)"""
    if df.empty:
        return np.nan
    pr = df['price'].to_numpy()
    rng = float(pr.max() - pr.min()) if len(pr) else 0.0
    if rng <= 0:
        return 0.0
    mask_large = (df['size'] >= size_threshold).to_numpy()
    idxs = np.flatnonzero(mask_large)
    valid = idxs[idxs + 1 < len(pr)]
    if valid.size == 0:
        return 0.0
    move = np.abs(pr[valid + 1] - pr[valid]).sum()
    return float(move / rng)


def top_volume_ratio(df: pd.DataFrame, threshold: float = 0.99) -> float:
    """顶端累计成交量覆盖比例因子: 计算顶部 threshold 分位数成交量累计占比"""
    if df.empty or 'size' not in df.columns:
        return np.nan
    
    volumes = df['size'].values.astype(np.float32)
    if len(volumes) == 0:
        return np.nan
    
    total = volumes.sum()
    if total <= 0:
        return np.nan
    
    # 排序（降序）
    sorted_volumes = np.sort(volumes)[::-1]
    cumsum = np.cumsum(sorted_volumes)
    
    # 找到累计体量达到 threshold 的位置
    target_volume = total * threshold
    idx = np.searchsorted(cumsum, target_volume)
    
    if idx >= len(sorted_volumes):
        return 1.0  # 所有成交量都需要
    
    # 计算覆盖比例（成交笔数占比）
    ratio = (idx + 1) / len(volumes)
    return float(ratio)

# ----------------------------------------------------------------------------
# 单分钟整合计算（返回 dict）
# ----------------------------------------------------------------------------

def compute_large_order_minute_factors(df: pd.DataFrame,
                                       size_threshold: float = 2,
                                       cv_limit: float = 0.25,
                                       min_run: int = 3) -> dict:
    """完全加速版本的大单分钟因子计算，使用 numba JIT 编译。逐笔时间列使用 tradeTime。"""
    if df.empty:
        return {
            'large_buy_ratio': np.nan,
            'large_sell_impact': np.nan,
            'large_order_density': 0,
            'large_dir_imbalance': np.nan,
            'large_slicing_score': np.nan,
            'large_signed_impact': np.nan,
            'large_interarrival_cv': np.nan,
            'large_tail_concentration': np.nan,
            'large_run_persistence': np.nan,
            'large_move_coverage': np.nan,
            'top_volume_ratio': np.nan,
        }
    
    # 确保按时间顺序（若需要，可在外层统一排序）
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    
    # 提取数据到 numpy 数组 (明确指定数据类型，避免 numba 类型推断失败)
    prices = df['price'].astype('float64').to_numpy(dtype=np.float64)
    sizes = df['size'].astype('float64').to_numpy(dtype=np.float64)  
    is_buyer_maker = df['is_buyer_maker'].astype('bool').to_numpy(dtype=np.bool_)
    
    # 时间戳处理：逐笔使用 tradeTime。若缺失则生成全 0 的占位数组，保证类型匹配
    if 'tradeTime' in df.columns:
        dt = _to_datetime_utc(df['tradeTime'])
        timestamps_ns = dt.astype('int64').to_numpy(dtype=np.int64, copy=False)
    else:
        timestamps_ns = np.zeros(len(df), dtype=np.int64)

    # 调用 numba 加速的核心计算函数 (所有参数类型已明确)
    lbr, lsi, lod, ldi, lss, lsi_signed, liacv, ltc, lrp, lmc = _compute_large_order_factors_numba(
        prices, sizes, is_buyer_maker, timestamps_ns, 
        np.float64(size_threshold), np.float64(cv_limit), np.int32(min_run)
    )
    
    # 计算 top_volume_ratio 因子（不使用 numba，直接调用函数）
    tvr = top_volume_ratio(df, threshold=0.99)

    return {
        'large_buy_ratio': float(lbr),
        'large_sell_impact': float(lsi),
        'large_order_density': int(lod),
        'large_dir_imbalance': float(ldi),
        'large_slicing_score': float(lss),
        'large_signed_impact': float(lsi_signed),
        'large_interarrival_cv': float(liacv),
        'large_tail_concentration': float(ltc),
        'large_run_persistence': float(lrp),
        'large_move_coverage': float(lmc),
        'top_volume_ratio': float(tvr),
    }

# ----------------------------------------------------------------------------
# 并行整表分钟聚合
# ----------------------------------------------------------------------------

def parallel_compute_large_order_factors(tick_df: pd.DataFrame,
                                         fixed_threshold: float = 2,
                                         adaptive_quantile: float | None = None,
                                         cv_limit: float = 0.25,
                                         min_run: int = 3,
                                         use_adaptive: bool = False,
                                         max_workers: int | None = None,
                                         MAX_WORKERS: int | None = None) -> pd.DataFrame:
    """并行计算大单分钟因子。
    逐笔时间列为 tradeTime（unix 秒/毫秒或 datetime）；内部统一转为 UTC datetime 分钟聚合。
    max_workers: None/<=0 时自动取 CPU 一半(向上取整)，且不超过分钟数；支持环境变量 FACTORLIB_MAX_WORKERS 覆盖。
    兼容参数别名 MAX_WORKERS。
    """
    # 兼容参数别名
    if MAX_WORKERS is not None:
        max_workers = MAX_WORKERS
    if tick_df.empty:
        raise ValueError('tick_df 为空')
    if 'tradeTime' not in tick_df.columns:
        raise ValueError('缺少 tradeTime 列（逐笔使用 tradeTime，K线才使用 CloseTime）')
    for col in ('price', 'size', 'is_buyer_maker'):
        if col not in tick_df.columns:
            raise KeyError(f'missing required column: {col}')

    # 转换并排序（使用统一的时间转换函数）
    tdt = to_datetime_utc(tick_df['tradeTime'])
    dfw = tick_df.assign(_tradeTime_dt=tdt).sort_values('_tradeTime_dt')

    # 按分钟分组
    groups = list(dfw.groupby(dfw['_tradeTime_dt'].dt.floor('T')))

    # -------- 自动 worker 数量判定 --------
    if max_workers is None or max_workers <= 0:
        env_override = os.getenv('FACTORLIB_MAX_WORKERS')
        if env_override:
            try:
                max_workers = int(env_override)
            except ValueError:
                max_workers = None
        if max_workers is None or max_workers <= 0:
            cpu = os.cpu_count() or 1
            # 一半向上取整（“一半多一些”）
            suggested = max(1, (cpu + 1) // 2)
            max_workers = suggested
    # 不超过分钟数
    max_workers = max(1, min(max_workers, len(groups)))

    def _task(item):
        minute, dfm = item
        if use_adaptive and adaptive_quantile is not None:
            thr = max(1e-9, float(dfm['size'].quantile(adaptive_quantile)))
        else:
            thr = fixed_threshold
        d = compute_large_order_minute_factors(dfm, size_threshold=thr, cv_limit=cv_limit, min_run=min_run)
        d['size_threshold_used'] = thr
        d['CloseTime'] = minute
        return d
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for ret in ex.map(_task, groups):
            results.append(ret)
    if not results:
        raise RuntimeError('无分钟聚合结果')
    out = pd.DataFrame(results).set_index('CloseTime').sort_index()
    return out

# ----------------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------------

def list_large_order_factor_names():
    return [
        'large_buy_ratio',
        'large_sell_impact',
        'large_buy_impact',
        'large_order_density',
        'large_dir_imbalance',
        'large_slicing_score',
        # 新增 5 因子
        'large_signed_impact',
        'large_interarrival_cv',
        'large_tail_concentration',
        'large_run_persistence',
        'large_move_coverage',
        # 新增 top_volume_ratio 因子
        'top_volume_ratio',
    ]


def add_aggressor_side(df: pd.DataFrame, col: str = 'is_buyer_maker', out_col: str = 'side') -> pd.DataFrame:
    if col not in df.columns:
        raise KeyError(f'missing column: {col}')
    out = df.copy()
    out[out_col] = np.where(out[col] == False, 1, -1).astype(np.int8)
    return out

FACTOR_FUNC_MAP = {
    'large_buy_ratio': large_buy_ratio,
    'large_sell_impact': large_sell_impact,
    'large_buy_impact': large_buy_impact,
    'large_order_density': large_order_density,
    'large_dir_imbalance': large_order_directional_imbalance,
    'large_slicing_score': large_order_slicing_score,
    'large_signed_impact': large_signed_impact,
    'large_interarrival_cv': large_interarrival_cv,
    'large_tail_concentration': large_tail_concentration,
    'large_run_persistence': large_run_persistence,
    'large_move_coverage': large_move_coverage,
    'top_volume_ratio': top_volume_ratio,
}

__all__ = [
    'large_buy_ratio',
    'large_sell_impact',
    'large_buy_impact',
    'large_order_density',
    'large_order_directional_imbalance',
    'large_order_slicing_score',
    'compute_large_order_minute_factors',
    'parallel_compute_large_order_factors',
    'list_large_order_factor_names',
    'add_aggressor_side',
    'FACTOR_FUNC_MAP',
    'large_signed_impact',
    'large_interarrival_cv',
    'large_tail_concentration',
    'large_run_persistence',
    'large_move_coverage',
    'top_volume_ratio',
]

# ----------------------------------------------------------------------------
# 内部 numba 函数（供 _compute_large_order_factors_numba 使用）
# ----------------------------------------------------------------------------

@numba.njit('float64(int8[:])', cache=True)
def _run_persistence_numba(side):
    """内部使用的 run persistence（numba JIT）。"""
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


@numba.njit('float64(int8[:], float64[:], int32, float64)', cache=True)
def _slicing_score_numba(side, sizes, min_run, cv_limit):
    """
    numba 加速的拆单评分计算 (明确指定参数类型)
    
    参数类型:
    - side: int8[:] 方向数组 (1=买, 0=卖)
    - sizes: float64[:] 尺寸数组
    - min_run: int32 最小run长度
    - cv_limit: float64 CV限制
    
    返回: float64 拆单评分
    """
    score = 0.0
    n = len(side)
    run_start = 0
    for i in range(1, n + 1):
        if i == n or side[i] != side[run_start]:
            length = i - run_start
            if length >= min_run:
                run_sizes = sizes[run_start:i]
                mean_sz = np.mean(run_sizes)
                if mean_sz > 0:
                    cv = np.std(run_sizes) / (mean_sz + 1e-12)
                    if cv <= cv_limit:
                        score += (length ** 2) * float(np.median(run_sizes))
            run_start = i
    return score

@numba.njit('(float64[:], float64[:], boolean[:], int64[:], float64, float64, int32)', cache=True)
def _compute_large_order_factors_numba(prices, sizes, is_buyer_maker, timestamps_ns, 
                                       size_threshold, cv_limit, min_run):
    """
    使用 numba 加速的大单因子计算核心函数 (明确指定所有参数类型)
    
    参数类型:
    - prices: float64[:] 价格数组
    - sizes: float64[:] 成交量数组  
    - is_buyer_maker: boolean[:] 买方是否做市商数组
    - timestamps_ns: int64[:] 时间戳数组 (纳秒)
    - size_threshold: float64 大单阈值
    - cv_limit: float64 CV限制
    - min_run: int32 最小run长度
    
    返回: (lbr, lsi, lod, ldi, lss, lsi_signed, liacv, ltc, lrp, lmc)
    """
    n = len(prices)
    if n == 0:
        return np.nan, np.nan, 0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan
    
    # 预计算所有需要的数组
    mask_large = sizes >= size_threshold
    mask_buy = ~is_buyer_maker  # True = 主动买
    mask_sell = is_buyer_maker  # True = 主动卖
    
    # 总成交量
    total_vol = np.sum(sizes)
    if total_vol <= 0:
        return np.nan, np.nan, 0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan
    
    # 1. large_buy_ratio
    large_buy_vol = np.sum(sizes[mask_large & mask_buy])
    lbr = large_buy_vol / total_vol
    
    # 2. large_sell_impact - 大单卖出后价格变化
    large_sell_indices = np.where(mask_large & mask_sell)[0]
    valid_sell = large_sell_indices[large_sell_indices < n - 1]  # 有下一笔的大单卖出
    if len(valid_sell) > 0:
        impacts = prices[valid_sell + 1] - prices[valid_sell]
        lsi = np.mean(impacts)
    else:
        lsi = np.nan
    
    # 3. large_order_density
    lod = int(np.sum(mask_large))
    
    # 4. large_dir_imbalance
    large_buy_vol_total = np.sum(sizes[mask_large & mask_buy])
    large_sell_vol_total = np.sum(sizes[mask_large & mask_sell])
    large_total_vol = large_buy_vol_total + large_sell_vol_total
    if large_total_vol > 10:
        ldi = (large_buy_vol_total - large_sell_vol_total) / large_total_vol
    else:
        ldi = 0.0
    
    # 5. large_slicing_score - 使用之前的 numba 函数
    large_indices = np.where(mask_large)[0]
    if len(large_indices) > 0:
        large_sides = mask_buy[large_indices].astype(np.int8)  # 1=买, 0=卖
        large_sizes = sizes[large_indices]
        score = _slicing_score_numba(large_sides, large_sizes, min_run, cv_limit)
        lss = score / total_vol
    else:
        lss = 0.0
    
    # 6. large_signed_impact - 大单方向加权价格变化
    large_indices_impact = np.where(mask_large)[0]
    valid_large = large_indices_impact[large_indices_impact < n - 1]
    if len(valid_large) > 0:
        dp = prices[valid_large + 1] - prices[valid_large]
        side_signs = np.where(mask_buy[valid_large], 1.0, -1.0)
        signed_impacts = side_signs * dp
        lsi_signed = np.mean(signed_impacts)
    else:
        lsi_signed = np.nan
    
    # 7. large_interarrival_cv - 大单到达间隔CV
    large_time_indices = np.where(mask_large)[0]
    if len(large_time_indices) >= 2:
        large_timestamps = timestamps_ns[large_time_indices]
        dt_ms = np.diff(large_timestamps) / 1e6  # 转毫秒
        if len(dt_ms) > 0:
            mu = np.mean(dt_ms)
            if mu > 0:
                liacv = np.std(dt_ms) / mu
            else:
                liacv = np.nan
        else:
            liacv = np.nan
    else:
        liacv = np.nan
    
    # 8. large_tail_concentration - 大单尺寸尾部集中度
    large_sizes_all = sizes[mask_large]
    if len(large_sizes_all) > 0:
        # 手动计算80%分位数
        sorted_large_sizes = np.sort(large_sizes_all)
        q_idx = int(0.8 * len(sorted_large_sizes))
        if q_idx >= len(sorted_large_sizes):
            q_idx = len(sorted_large_sizes) - 1
        threshold_80 = sorted_large_sizes[q_idx]
        
        top_vol = np.sum(large_sizes_all[large_sizes_all >= threshold_80])
        large_total_vol_concentration = np.sum(large_sizes_all)
        if large_total_vol_concentration > 0:
            ltc = top_vol / large_total_vol_concentration
        else:
            ltc = 0.0
    else:
        ltc = np.nan
    
    # 9. large_run_persistence - 使用之前的 numba 函数
    if len(large_indices) > 0:
        large_sides_persist = mask_buy[large_indices].astype(np.int8)
        lrp = _run_persistence_numba(large_sides_persist)
    else:
        lrp = np.nan
    
    # 10. large_move_coverage - 大单触发的价格变化覆盖度
    price_range = np.max(prices) - np.min(prices)
    if price_range > 0 and len(valid_large) > 0:
        moves = np.abs(prices[valid_large + 1] - prices[valid_large])
        total_move = np.sum(moves)
        lmc = total_move / price_range
    else:
        lmc = 0.0
    
    return lbr, lsi, lod, ldi, lss, lsi_signed, liacv, ltc, lrp, lmc
