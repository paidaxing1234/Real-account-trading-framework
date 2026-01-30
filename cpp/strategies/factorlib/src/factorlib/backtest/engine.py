import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime
from zoneinfo import ZoneInfo


# 仅用于UTC显示/分组的辅助函数（不改变原数据）
def _to_utc_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    try:
        if getattr(idx, 'tz', None) is not None:
            return idx.tz_convert('UTC')
        return idx.tz_localize('UTC')
    except Exception:
        return idx


def shift_factor(df: pd.DataFrame, factor_col: str) -> pd.DataFrame:
    out = df.copy()
    out[factor_col] = out[factor_col].shift(1)
    return out


def run_backtest(df: pd.DataFrame, factor_col: str, compound: bool = True) -> pd.DataFrame:
    """
    运行回测策略
    
    参数:
    - df: 包含因子和收益的DataFrame
    - factor_col: 因子列名
    - compound: True为复利模式（默认），False为单利模式
    """
    df_bt = df.copy()
    df_bt = shift_factor(df_bt, factor_col)
    ret_col = f'{factor_col}_ret'
    cum_ret_col = f'{factor_col}_cum_ret'
    simple_cum_ret_col = f'{factor_col}_simple_cum_ret'
    df_bt[ret_col] = df_bt[factor_col] * df_bt['return']
    
    if compound:
        # 复利累计
        df_bt[cum_ret_col] = (1 + df_bt[ret_col]).cumprod()
        # 单利累计（逐期简单相加 + 1，用于直观对比）
        df_bt[simple_cum_ret_col] = 1 + df_bt[ret_col].cumsum()
    else:
        # 单利模式：主要累计收益使用单利计算
        df_bt[cum_ret_col] = 1 + df_bt[ret_col].cumsum()
        # 保持复利列用于对比
        df_bt[simple_cum_ret_col] = (1 + df_bt[ret_col]).cumprod()
    
    return df_bt


def calculate_max_drawdown(cum_returns: pd.Series) -> float:
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / peak
    return float(drawdown.min())


def performance_by_period(df: pd.DataFrame, factor_col: str, group_by: str = 'auto', compound: bool = True) -> pd.DataFrame:
    """
    按周期分组计算绩效指标
    
    参数:
    - df: 含回测结果的DataFrame
    - factor_col: 因子列名
    - group_by: 分组方式 'year'|'month'|'auto'，auto根据数据长度自动选择
    - compound: True为复利模式（默认），False为单利模式
    """
    x = df.copy()
    idx_utc = _to_utc_index(x.index)
    
    # 自动选择分组方式
    if group_by == 'auto':
        total_days = (idx_utc.max() - idx_utc.min()).days
        group_by = 'month' if total_days < 400 else 'year'  # 约13个月的阈值
    
    # 根据分组方式设置分组列
    if group_by == 'year':
        x['period'] = idx_utc.year
        period_label = 'Year'
    elif group_by == 'month':
        x['period'] = idx_utc.to_period('M')
        period_label = 'Month'
    else:
        raise ValueError("group_by must be 'year', 'month', or 'auto'")
    
    rows = []
    ret_col = f'{factor_col}_ret'
    cum_ret_col = f'{factor_col}_cum_ret'
    
    for period, g in x.groupby('period'):
        if compound:
            # 复利计算
            ann_ret = (1 + g[ret_col]).prod() - 1
        else:
            # 单利计算
            ann_ret = g[ret_col].sum()
        
        ann_simple_sum = g[ret_col].sum()  # 单利总和
        # 年化 Sharpe: mean / std * sqrt(一年的分钟数)
        sharpe = g[ret_col].mean() / g[ret_col].std() * np.sqrt(365*24*60) if g[ret_col].std() != 0 else 0
        weight_changes = g[factor_col].diff().abs().sum()
        ann_turnover = weight_changes / len(g) * 24 * 60 * 365
        long_ratio = g[g[factor_col] > 0][factor_col].sum() / len(g)
        short_ratio = g[g[factor_col] < 0][factor_col].sum() / len(g)
        mdd = calculate_max_drawdown(g[cum_ret_col])
        kamma = abs(ann_ret / mdd) if mdd != 0 else 0
        ret_over_turnover = ann_simple_sum / ann_turnover if ann_turnover != 0 else 0
        g_idx_utc = _to_utc_index(g.index)
        rows.append({
            period_label: str(period),
            'Start Date': g_idx_utc.min().strftime('%Y-%m-%d'),
            'End Date': g_idx_utc.max().strftime('%Y-%m-%d'),
            'Long Ratio': round(long_ratio, 2),
            'Short Ratio': round(short_ratio, 2),
            'Return': round(ann_ret * 100, 2),
            'Sharpe': round(sharpe, 2),
            'Turnover': round(ann_turnover, 2),
            'Ret/Turnover': round(ret_over_turnover, 4),
            'Max Drawdown': round(mdd, 2),
            'Kamma Ratio': round(kamma, 2)
        })

    # 总体
    total = x
    if compound:
        # 复利计算
        tot_ret = (1 + total[ret_col]).prod() - 1
    else:
        # 单利计算
        tot_ret = total[ret_col].sum()
        
    tot_simple_sum = total[ret_col].sum()
    # 年化 Sharpe: mean / std * sqrt(一年的分钟数)
    tot_sharpe = total[ret_col].mean() / total[ret_col].std() * np.sqrt(365*24*60) if total[ret_col].std() != 0 else 0
    tot_turnover = total[factor_col].diff().abs().sum() / len(total) * 365 * 24 * 60
    tot_mdd = calculate_max_drawdown(total[cum_ret_col])
    tot_kamma = (-(tot_ret / tot_mdd)) if tot_mdd != 0 else 0  # 按用户逻辑保留负号处理
    total_idx_utc = _to_utc_index(total.index)
    total_ret_over_turnover = tot_simple_sum / tot_turnover if tot_turnover != 0 else 0

    rows.append({
        period_label: 'Total',
        'Start Date': total_idx_utc.min().strftime('%Y-%m-%d'),
        'End Date': total_idx_utc.max().strftime('%Y-%m-%d'),
        'Long Ratio': round(total[total[factor_col] > 0][factor_col].sum() / len(total), 2),
        'Short Ratio': round(total[total[factor_col] < 0][factor_col].sum() / len(total), 2),
        'Return': round(tot_ret * 100, 2),
        'Sharpe': round(tot_sharpe, 2),
        'Turnover': round(tot_turnover, 2),
        'Ret/Turnover': round(total_ret_over_turnover, 4),
        'Max Drawdown': round(tot_mdd, 2),
        'Kamma Ratio': round(tot_kamma, 2)
    })
    return pd.DataFrame(rows)


def plot_cum_return(df_bt: pd.DataFrame, factor_col: str, downsample: int = 10, title: str | None = None, save: bool = True, plot_dir: str | None = None):
    # 按用户逻辑进行下采样绘图
    series = df_bt[f'{factor_col}_cum_ret']
    if downsample and downsample > 1:
        series = series.iloc[::downsample]
    plt.figure(figsize=(8, 4))
    # 默认英文标题
    plt_title = title or f'Cumulative Return - {factor_col}'
    series.plot(title=plt_title, grid=True)
    plt.ylabel('Cumulative Return')
    plt.tight_layout()

    saved_path = None
    if save:
        base_dir = plot_dir or os.getenv('FACTORLIB_PLOT_DIR', '/home/ch/data/result/plots')
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
        fname = f'cumret_{factor_col}_{ts}.png'
        saved_path = os.path.join(base_dir, fname)
        plt.savefig(saved_path, dpi=150)
        print(f'[Plot] Saved cumulative return to: {saved_path}')

    plt.show()
    return saved_path


def performance_by_year(df: pd.DataFrame, factor_col: str, compound: bool = True) -> pd.DataFrame:
    """向后兼容的年度绩效函数"""
    return performance_by_period(df, factor_col, group_by='year', compound=compound)


# Deprecated: Use factorlib.cli.backtest instead
def backtest_and_plot(
    df_result: pd.DataFrame,
    factor_col: str,
    mode: str = 'all',
    test_date: str = '2025-01-01 00:00:00',
    begin_time: str = '2022-01-01 00:00:00',
    print_simple: bool = False,
    group_by: str = 'auto',
    compound: bool = True,
    plot: bool = True,
):
    """
    [Deprecated] 回测 + 绘图。推荐使用 factorlib.cli.backtest

    参数:
    - df_result: 含分钟收益(return)及因子列的DataFrame
    - factor_col: 因子/仓位列
    - mode: 'all' / 'in-sample' / 'out-sample'
    - test_date: 分割日期
    - begin_time: 起始过滤时间
    - compound: True为复利模式（默认），False为单利模式
    - plot: 是否绘图（默认True）
    """
    import warnings
    warnings.warn("backtest_and_plot is deprecated. Use factorlib.cli.backtest instead.", DeprecationWarning)

    # Filter by time
    test_df = df_result.copy()[df_result.index >= begin_time]
    if mode == 'out-sample':
        test_df = test_df[test_df['CloseTime'] >= test_date] if 'CloseTime' in test_df.columns else test_df.loc[test_df.index >= test_date]
    elif mode == 'in-sample':
        test_df = test_df[test_df['CloseTime'] < test_date] if 'CloseTime' in test_df.columns else test_df.loc[test_df.index < test_date]

    bt_df = run_backtest(test_df, factor_col, compound=compound)
    perf_df = performance_by_period(bt_df, factor_col, group_by=group_by, compound=compound)

    # Print results
    mode_text = "Compound" if compound else "Simple Interest"
    header = f"Backtest - {factor_col} ({mode_text})"
    print("=" * 70)
    print(f" {header} ")
    print("=" * 70)
    print(perf_df.to_string(index=False))

    # Plot if requested
    saved = None
    if plot:
        saved = plot_cum_return(bt_df, factor_col, downsample=10, title=header, save=True)

    return bt_df, perf_df, saved


# ============================================================================
# Panel Data Backtest (Multi-Asset with CS Operators)
# ============================================================================

def run_backtest_panel(
    factor_panel: pd.DataFrame,
    returns_panel: pd.DataFrame,
    position_mode: str = 'long_short',
    long_short_pct: float = 0.2,
    compound: bool = True,
) -> dict:
    """
    运行 Panel Data 回测（多资产，支持 CS 算子）。

    Args:
        factor_panel: 因子 Panel DataFrame (rows=timestamps, cols=assets)
        returns_panel: 收益率 Panel DataFrame (rows=timestamps, cols=assets)
        position_mode: 仓位模式
            - 'long_short': 多空对冲（做多 top pct，做空 bottom pct）
            - 'direct': 直接使用因子值作为仓位
        long_short_pct: long_short 模式下的 top/bottom 比例
        compound: 是否使用复利计算

    Returns:
        dict with:
        - portfolio_returns: Series，组合收益率
        - cumulative_returns: Series，累计收益率
        - positions: DataFrame，仓位
        - metrics: dict，绩效指标
    """
    from factorlib.utils.operators import ops

    # 对齐数据
    common_index = factor_panel.index.intersection(returns_panel.index)
    common_cols = factor_panel.columns.intersection(returns_panel.columns)

    factor_aligned = factor_panel.loc[common_index, common_cols]
    returns_aligned = returns_panel.loc[common_index, common_cols]

    # 计算仓位
    if position_mode == 'long_short':
        positions = ops.cs_long_short(factor_aligned, pct=long_short_pct)
    elif position_mode == 'direct':
        # 直接使用因子值，但进行 cs_scale 归一化
        positions = ops.cs_scale(factor_aligned)
    else:
        raise ValueError(f"Unknown position_mode: {position_mode}")

    # Shift positions by 1 to avoid lookahead bias
    positions_shifted = positions.shift(1)

    # 计算策略收益
    strategy_returns = positions_shifted * returns_aligned
    portfolio_returns = strategy_returns.mean(axis=1).dropna()

    # 计算累计收益
    if compound:
        cumulative_returns = (1 + portfolio_returns).cumprod()
    else:
        cumulative_returns = 1 + portfolio_returns.cumsum()

    # 计算绩效指标
    total_return = cumulative_returns.iloc[-1] - 1 if len(cumulative_returns) > 0 else 0
    ann_factor = np.sqrt(365 * 24 * 60)  # 1-minute data
    sharpe = (portfolio_returns.mean() / portfolio_returns.std() * ann_factor) if portfolio_returns.std() > 0 else 0

    # Max drawdown
    peak = cumulative_returns.cummax()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown = float(drawdown.min())

    # Turnover
    position_changes = positions_shifted.diff().abs().mean(axis=1).sum()
    n_periods = len(positions_shifted.dropna())
    turnover = (position_changes / n_periods) * 365 * 24 * 60 if n_periods > 0 else 0

    # Long/Short ratios
    pos_flat = positions_shifted.values.flatten()
    pos_flat = pos_flat[np.isfinite(pos_flat)]
    long_ratio = np.mean(pos_flat[pos_flat > 0]) if np.any(pos_flat > 0) else 0
    short_ratio = np.mean(pos_flat[pos_flat < 0]) if np.any(pos_flat < 0) else 0

    metrics = {
        'total_return': total_return * 100,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'turnover': turnover,
        'long_ratio': long_ratio,
        'short_ratio': short_ratio,
        'n_assets': len(common_cols),
        'n_periods': len(portfolio_returns),
    }

    return {
        'portfolio_returns': portfolio_returns,
        'cumulative_returns': cumulative_returns,
        'positions': positions_shifted,
        'metrics': metrics,
    }


def performance_panel(result: dict, factor_name: str = 'factor', compound: bool = True) -> pd.DataFrame:
    """
    计算 Panel 回测的年度绩效。

    Args:
        result: run_backtest_panel 的返回结果
        factor_name: 因子名称
        compound: 是否使用复利计算

    Returns:
        绩效 DataFrame
    """
    portfolio_returns = result['portfolio_returns']
    cumulative_returns = result['cumulative_returns']

    # 按年分组
    idx_utc = _to_utc_index(portfolio_returns.index)
    years = idx_utc.year

    rows = []
    for year in sorted(years.unique()):
        mask = years == year
        year_returns = portfolio_returns[mask]
        year_cum = cumulative_returns[mask]

        if len(year_returns) == 0:
            continue

        if compound:
            ann_ret = (1 + year_returns).prod() - 1
        else:
            ann_ret = year_returns.sum()

        ann_vol = year_returns.std() * np.sqrt(len(year_returns))
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

        # Max drawdown for year
        peak = year_cum.cummax()
        dd = (year_cum - peak) / peak
        mdd = float(dd.min())

        rows.append({
            'Year': year,
            'Return': round(ann_ret * 100, 2),
            'Sharpe': round(sharpe, 2),
            'Max Drawdown': round(mdd, 2),
            'N Periods': len(year_returns),
        })

    # Total
    if compound:
        tot_ret = (1 + portfolio_returns).prod() - 1
    else:
        tot_ret = portfolio_returns.sum()

    tot_sharpe = result['metrics']['sharpe']
    tot_mdd = result['metrics']['max_drawdown']

    rows.append({
        'Year': 'Total',
        'Return': round(tot_ret * 100, 2),
        'Sharpe': round(tot_sharpe, 2),
        'Max Drawdown': round(tot_mdd, 2),
        'N Periods': len(portfolio_returns),
    })

    return pd.DataFrame(rows)


def plot_panel_cumret(
    result: dict,
    factor_name: str = 'factor',
    title: str = None,
    save: bool = True,
    plot_dir: str = None
) -> str:
    """
    绘制 Panel 回测的累计收益曲线。

    Args:
        result: run_backtest_panel 的返回结果
        factor_name: 因子名称
        title: 图表标题
        save: 是否保存图片
        plot_dir: 保存目录

    Returns:
        保存路径（如果 save=True）
    """
    cumulative_returns = result['cumulative_returns']
    metrics = result['metrics']

    plt.figure(figsize=(10, 5))
    cumulative_returns.plot(grid=True)

    plt_title = title or f'Panel Backtest - {factor_name}'
    plt_title += f" (Sharpe={metrics['sharpe']:.2f}, N={metrics['n_assets']} assets)"
    plt.title(plt_title)
    plt.ylabel('Cumulative Return')
    plt.xlabel('Time')
    plt.tight_layout()

    saved_path = None
    if save:
        base_dir = plot_dir or os.getenv('FACTORLIB_PLOT_DIR', '/home/ch/data/result/plots')
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')
        fname = f'panel_cumret_{factor_name}_{ts}.png'
        saved_path = os.path.join(base_dir, fname)
        plt.savefig(saved_path, dpi=150)
        print(f'[Plot] Saved panel cumulative return to: {saved_path}')

    plt.show()
    return saved_path


def generate_trade_blotter(
    df_bt: pd.DataFrame,
    factor_col: str,
    price_col: str = 'Close',
    kind: str = 'segments',
    execution_shift: int = 1,
    tol: float = 1e-12,
) -> pd.DataFrame:
    """
    生成交割单（支持连续仓位，幅度+方向都考虑）。

    参数
    - df_bt: 含回测结果的DataFrame（已由 run_backtest 对因子 shift(1)）
    - factor_col: 仓位列（连续实数，幅度与方向有效）
    - price_col: 价格列，用于记录进/出场价格
    - kind: 'segments' 基于“持仓水平”恒定的区段；'orders' 基于“仓位变化”的逐笔指令
    - execution_shift: 交割时间前移的bar数（满足“本分钟预测、上一分钟下单”，传1）
    - tol: 浮点容差，用于判断仓位变化

    返回
    - kind='segments': 列 [EntryTime, ExitTime, Position, Bars, EntryPrice, ExitPrice, Return]
    - kind='orders'  : 列 [Time, Side, SizeChange, PositionBefore, PositionAfter, Price]
    """
    if factor_col not in df_bt.columns:
        raise ValueError(f"列不存在: {factor_col}")

    x = df_bt.copy()
    pos = x[factor_col].astype(float).fillna(0.0)
    idx = x.index

    if kind not in ('segments', 'orders'):
        raise ValueError("kind 必须是 'segments' 或 'orders'")

    # 订单级交割单：每次仓位变化都记一笔
    print(kind)
    if kind == 'orders':
        pos_prev = pos.shift(1)
        delta = pos - pos_prev
        mask = delta.abs() > tol
        rows = []
        if mask.any():
            change_locs = np.flatnonzero(mask.values)
            for loc in change_locs:
                time_i = idx[loc]
                # 执行时间前移 execution_shift 根（若可）
                exec_loc = max(0, loc - execution_shift)
                exec_time = idx[exec_loc]
                price = (x[price_col].iloc[exec_loc]
                         if price_col in x.columns else np.nan)
                d = float(delta.iloc[loc])
                side = 'Buy' if d > 0 else 'Sell'
                rows.append({
                    'Time': exec_time,
                    'Side': side,
                    'SizeChange': d,
                    'PositionBefore': float(pos_prev.iloc[loc]) if pd.notna(pos_prev.iloc[loc]) else 0.0,
                    'PositionAfter': float(pos.iloc[loc]),
                    'Price': float(price) if pd.notna(price) else np.nan,
                })
        return pd.DataFrame(rows)

    # 区段级交割单：每个恒定仓位水平构成一段（幅度+方向均纳入）
    # 分段条件：仓位数值发生变化（含幅度）
    changed = (pos.fillna(0.0).diff().abs() > tol)
    grp = changed.cumsum()

    trades = []
    ret_col = f'{factor_col}_ret'

    print(x.groupby(grp))
    for _, g in x.groupby(grp):
        
        first_idx = g.index[0]
        last_idx = g.index[-1]
        level = pos.loc[first_idx]
        if abs(level) <= tol:
            continue  # 忽略纯空仓段

        # 进场：将记录时间和价格前移 execution_shift 根（若可）
        try:
            first_loc = idx.get_loc(first_idx)
        except Exception:
            first_loc = 0
        entry_loc = max(0, first_loc - execution_shift)
        entry_time = idx[entry_loc]
        entry_price = (x[price_col].iloc[entry_loc]
                       if price_col in x.columns else np.nan)

        # 出场：段尾
        exit_time = last_idx
        exit_price = (g[price_col].iloc[-1]
                      if price_col in g.columns else np.nan)

        # 段收益：优先使用已计算好的 {factor}_ret
        if ret_col in x.columns:
            seg_ret = (1 + x.loc[g.index, ret_col].fillna(0)).prod() - 1
        elif 'return' in x.columns:
            seg_ret = (1 + x.loc[g.index, 'return'].fillna(0) * level).prod() - 1
        else:
            seg_ret = np.nan

        trades.append({
            'EntryTime': entry_time,
            'ExitTime': exit_time,
            'Position': float(level),
            'Bars': len(g),
            'EntryPrice': float(entry_price) if pd.notna(entry_price) else np.nan,
            'ExitPrice': float(exit_price) if pd.notna(exit_price) else np.nan,
            'Return': float(seg_ret) if pd.notna(seg_ret) else np.nan,
        })

    return pd.DataFrame(trades)