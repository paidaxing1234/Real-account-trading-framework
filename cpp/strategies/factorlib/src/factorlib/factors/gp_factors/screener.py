"""
GP Factor Screener - Batch Evaluation and Ranking

Provides tools for:
1. Batch backtesting GP factors
2. Performance screening and ranking
3. Factor correlation analysis
4. Report generation
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
import warnings

from .gp_library import GPFactorLibrary, gp_library, GPFactorInfo


def compute_ic(
    factor_values: pd.DataFrame,
    returns: pd.DataFrame,
    method: str = 'spearman'
) -> pd.Series:
    """
    Compute Information Coefficient (IC) time series.

    Args:
        factor_values: Factor panel (rows=time, cols=assets)
        returns: Returns panel (rows=time, cols=assets)
        method: 'spearman' or 'pearson'

    Returns:
        Series of IC values per timestamp
    """
    # Align data
    common_idx = factor_values.index.intersection(returns.index)
    common_cols = factor_values.columns.intersection(returns.columns)

    factor_aligned = factor_values.loc[common_idx, common_cols]
    returns_aligned = returns.loc[common_idx, common_cols]

    # Shift factor by 1 to avoid lookahead
    factor_shifted = factor_aligned.shift(1)

    # Compute IC per row
    ic_series = []
    for idx in factor_shifted.index:
        f = factor_shifted.loc[idx].dropna()
        r = returns_aligned.loc[idx].dropna()
        common = f.index.intersection(r.index)
        if len(common) < 5:
            ic_series.append(np.nan)
            continue

        if method == 'spearman':
            ic = f[common].rank().corr(r[common].rank())
        else:
            ic = f[common].corr(r[common])
        ic_series.append(ic)

    return pd.Series(ic_series, index=factor_shifted.index)


def backtest_factor(
    factor_values: pd.DataFrame,
    returns: pd.DataFrame,
    position_mode: str = 'direct',
    long_short_pct: float = 0.2,
) -> Dict[str, Any]:
    """
    Quick backtest a single factor.

    Args:
        factor_values: Factor panel
        returns: Returns panel
        position_mode: 'direct' or 'long_short'
        long_short_pct: Percentage for long/short mode

    Returns:
        Dict with performance metrics
    """
    from factorlib.utils.operators import ops

    # Align
    common_idx = factor_values.index.intersection(returns.index)
    common_cols = factor_values.columns.intersection(returns.columns)

    factor_aligned = factor_values.loc[common_idx, common_cols]
    returns_aligned = returns.loc[common_idx, common_cols]

    # Positions
    if position_mode == 'long_short':
        positions = ops.cs_long_short(factor_aligned, pct=long_short_pct)
    else:
        # Direct: scale to sum to 0 (market neutral)
        positions = ops.cs_demean(factor_aligned)
        # Scale to have abs sum = 1 per row
        abs_sum = positions.abs().sum(axis=1).replace(0, 1)
        positions = positions.div(abs_sum, axis=0)

    # Shift to avoid lookahead
    positions_shifted = positions.shift(1)

    # Strategy returns
    strategy_returns = (positions_shifted * returns_aligned).sum(axis=1)
    strategy_returns = strategy_returns.dropna()

    if len(strategy_returns) == 0:
        return {'sharpe': 0, 'returns': 0, 'turnover': 0, 'ic_mean': 0, 'ir': 0}

    # Metrics
    ann_factor = np.sqrt(365 * 24 * 60)
    total_return = strategy_returns.sum()
    sharpe = (strategy_returns.mean() / strategy_returns.std() * ann_factor
              if strategy_returns.std() > 0 else 0)

    # Turnover
    turnover = positions_shifted.diff().abs().sum().sum()
    n_periods = len(positions_shifted.dropna())
    ann_turnover = (turnover / n_periods) * 365 * 24 * 60 if n_periods > 0 else 0

    # IC
    ic_series = compute_ic(factor_aligned, returns_aligned.shift(-1))
    ic_mean = ic_series.mean()
    ic_std = ic_series.std()
    ir = ic_mean / ic_std if ic_std > 0 else 0

    # Max drawdown
    cum_ret = (1 + strategy_returns).cumprod()
    peak = cum_ret.cummax()
    dd = (cum_ret - peak) / peak
    max_dd = float(dd.min())

    return {
        'sharpe': sharpe,
        'returns': total_return * 100,
        'turnover': ann_turnover,
        'ic_mean': ic_mean,
        'ir': ir,
        'max_drawdown': max_dd,
        'n_periods': len(strategy_returns),
    }


def _backtest_single_factor(args) -> Tuple[str, Dict[str, Any]]:
    """Worker function for parallel backtesting."""
    factor_id, factor_expr, panel_data, returns, position_mode = args

    from factorlib.utils.operators import ops

    # Build namespace
    local_ns = {'ops': ops, 'np': np}
    for col_name in panel_data:
        local_ns[col_name] = panel_data[col_name]
    local_ns['neg'] = lambda x: -x

    try:
        # Compute factor
        factor_values = eval(factor_expr, {"__builtins__": {}}, local_ns)

        # Backtest
        metrics = backtest_factor(factor_values, returns, position_mode)
        return factor_id, metrics

    except Exception as e:
        return factor_id, {'error': str(e), 'sharpe': 0}


def screen_factors(
    panel_data: Dict[str, pd.DataFrame],
    returns: pd.DataFrame,
    library: GPFactorLibrary = None,
    factor_ids: List[str] = None,
    min_sharpe: float = 0,
    max_turnover: float = float('inf'),
    position_mode: str = 'direct',
    top_k: int = 100,
    n_workers: int = 8,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Screen and rank GP factors by backtested performance.

    Args:
        panel_data: Dict of column -> DataFrame (rows=time, cols=assets)
        returns: Returns panel DataFrame
        library: GPFactorLibrary to use (default: global gp_library)
        factor_ids: Specific factors to screen (default: all)
        min_sharpe: Pre-filter by GP-reported sharpe
        max_turnover: Pre-filter by GP-reported turnover
        position_mode: 'direct' or 'long_short'
        top_k: Return top K factors
        n_workers: Number of parallel workers
        verbose: Print progress

    Returns:
        DataFrame with factor rankings and metrics
    """
    lib = library or gp_library

    # Get factors to screen
    if factor_ids:
        factors = [lib.get_info(fid) for fid in factor_ids if fid in lib]
    else:
        factors = lib.list_factors(min_sharpe=min_sharpe, max_turnover=max_turnover)

    if verbose:
        print(f"Screening {len(factors)} factors...")

    # Prepare arguments for parallel processing
    # Note: For simplicity, we'll use sequential processing here
    # since panel_data is large and serialization overhead is high
    results = []
    for i, factor in enumerate(factors):
        if verbose and i % 100 == 0:
            print(f"  Progress: {i}/{len(factors)}")

        try:
            from factorlib.utils.operators import ops

            # Build namespace
            local_ns = {'ops': ops, 'np': np}
            for col_name in panel_data:
                local_ns[col_name] = panel_data[col_name]
            local_ns['neg'] = lambda x: -x

            # Compute factor
            factor_values = eval(factor.expression, {"__builtins__": {}}, local_ns)

            # Backtest
            metrics = backtest_factor(factor_values, returns, position_mode)
            metrics['factor_id'] = factor.factor_id
            metrics['expression'] = factor.expression
            metrics['gp_sharpe'] = factor.sharpe
            metrics['gp_turnover'] = factor.turnover
            results.append(metrics)

        except Exception as e:
            if verbose:
                print(f"  Failed {factor.factor_id}: {e}")

    if not results:
        return pd.DataFrame()

    # Create result DataFrame
    df = pd.DataFrame(results)

    # Sort by backtested sharpe
    df = df.sort_values('sharpe', ascending=False)

    # Return top K
    if top_k and len(df) > top_k:
        df = df.head(top_k)

    return df


def batch_backtest(
    panel_data: Dict[str, pd.DataFrame],
    returns: pd.DataFrame,
    factor_ids: List[str] = None,
    library: GPFactorLibrary = None,
    save_path: str = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Batch backtest factors and optionally save results.

    Args:
        panel_data: Panel data dict
        returns: Returns panel
        factor_ids: Specific factors (default: all)
        library: Factor library
        save_path: Path to save results CSV
        verbose: Print progress

    Returns:
        DataFrame with all backtest results
    """
    results = screen_factors(
        panel_data=panel_data,
        returns=returns,
        library=library,
        factor_ids=factor_ids,
        top_k=None,  # Return all
        verbose=verbose,
    )

    if save_path:
        results.to_csv(save_path, index=False)
        if verbose:
            print(f"Results saved to: {save_path}")

    return results


def factor_correlation_matrix(
    panel_data: Dict[str, pd.DataFrame],
    factor_ids: List[str],
    library: GPFactorLibrary = None,
    sample_ratio: float = 0.1,
) -> pd.DataFrame:
    """
    Compute correlation matrix between factors.

    Args:
        panel_data: Panel data dict
        factor_ids: Factor IDs to analyze
        library: Factor library
        sample_ratio: Sample ratio for speed (default 10%)

    Returns:
        Correlation matrix DataFrame
    """
    lib = library or gp_library

    # Compute factors
    factor_values = {}
    for fid in factor_ids:
        try:
            factor_values[fid] = lib.compute(fid, panel_data)
        except Exception:
            pass

    if len(factor_values) < 2:
        return pd.DataFrame()

    # Sample for speed
    first_df = list(factor_values.values())[0]
    n_samples = int(len(first_df) * sample_ratio)
    sample_idx = first_df.index[::max(1, len(first_df) // n_samples)]

    # Flatten to correlation
    flat_data = {}
    for fid, df in factor_values.items():
        sampled = df.loc[sample_idx].values.flatten()
        flat_data[fid] = sampled[np.isfinite(sampled)]

    # Compute correlations
    n_factors = len(factor_ids)
    corr_matrix = np.eye(n_factors)

    for i, fid1 in enumerate(factor_ids):
        for j, fid2 in enumerate(factor_ids):
            if i >= j:
                continue
            if fid1 not in flat_data or fid2 not in flat_data:
                continue

            v1, v2 = flat_data[fid1], flat_data[fid2]
            min_len = min(len(v1), len(v2))
            if min_len < 100:
                continue

            corr = np.corrcoef(v1[:min_len], v2[:min_len])[0, 1]
            corr_matrix[i, j] = corr
            corr_matrix[j, i] = corr

    return pd.DataFrame(corr_matrix, index=factor_ids, columns=factor_ids)


def generate_report(
    screening_results: pd.DataFrame,
    output_path: str = None,
    title: str = "GP Factor Screening Report",
) -> str:
    """
    Generate a markdown report from screening results.

    Args:
        screening_results: DataFrame from screen_factors()
        output_path: Path to save report (optional)
        title: Report title

    Returns:
        Markdown report string
    """
    report = []
    report.append(f"# {title}")
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"\n## Summary")
    report.append(f"- Total factors screened: {len(screening_results)}")

    if len(screening_results) > 0:
        report.append(f"- Sharpe range: {screening_results['sharpe'].min():.2f} - {screening_results['sharpe'].max():.2f}")
        report.append(f"- Mean Sharpe: {screening_results['sharpe'].mean():.2f}")
        report.append(f"- Mean IC: {screening_results['ic_mean'].mean():.4f}")

        report.append(f"\n## Top 20 Factors")
        top20 = screening_results.head(20)
        report.append("\n| Rank | Factor ID | Sharpe | IC | Turnover | Expression |")
        report.append("|------|-----------|--------|-----|----------|------------|")

        for i, row in top20.iterrows():
            expr_short = row['expression'][:60] + "..." if len(row['expression']) > 60 else row['expression']
            report.append(f"| {i+1} | {row['factor_id']} | {row['sharpe']:.2f} | {row['ic_mean']:.4f} | {row['turnover']:.0f} | `{expr_short}` |")

        report.append(f"\n## Sharpe Distribution")
        sharpe_bins = pd.cut(screening_results['sharpe'], bins=10)
        dist = sharpe_bins.value_counts().sort_index()
        report.append("\n| Sharpe Range | Count |")
        report.append("|--------------|-------|")
        for bin_range, count in dist.items():
            report.append(f"| {bin_range} | {count} |")

    report_str = "\n".join(report)

    if output_path:
        with open(output_path, 'w') as f:
            f.write(report_str)

    return report_str


__all__ = [
    'compute_ic',
    'backtest_factor',
    'screen_factors',
    'batch_backtest',
    'factor_correlation_matrix',
    'generate_report',
]
