"""
GP Factor Utilities - Easy integration with notebook workflow

Provides convenient functions to:
1. Load GP factors as callable functions
2. Compute GP factors on PanelData
3. Batch compute and backtest GP factors
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable, Union, Any
from .gp_library import GPFactorLibrary, gp_library, GPFactorInfo


def _convert_gp_expression(expression: str) -> str:
    """
    Convert GP expression format to standard ops format.

    GP format:  ops.ts_rank_20(Close)
    Standard:   ops.ts_rank(Close, 20)
    """
    # Patterns to convert ops.xxx_N(...) to ops.xxx(..., N)
    patterns = [
        # Time series with window
        (r'ops\.ts_mean_(\d+)\(', r'ops.ts_mean('),
        (r'ops\.ts_sum_(\d+)\(', r'ops.ts_sum('),
        (r'ops\.ts_std_(\d+)\(', r'ops.ts_std('),
        (r'ops\.ts_var_(\d+)\(', r'ops.ts_var('),
        (r'ops\.ts_zscore_(\d+)\(', r'ops.ts_zscore('),
        (r'ops\.ts_rank_(\d+)\(', r'ops.ts_rank('),
        (r'ops\.ts_skew_(\d+)\(', r'ops.ts_skew('),
        (r'ops\.ts_kurt_(\d+)\(', r'ops.ts_kurt('),
        (r'ops\.ts_min_(\d+)\(', r'ops.ts_min('),
        (r'ops\.ts_max_(\d+)\(', r'ops.ts_max('),
        (r'ops\.ts_slope_(\d+)\(', r'ops.ts_slope('),
        (r'ops\.ts_median_(\d+)\(', r'ops.ts_median('),
        (r'ops\.ts_minmax_norm_(\d+)\(', r'ops.ts_minmax_norm('),
        (r'ops\.ts_rank_signed_(\d+)\(', r'ops.ts_rank_signed('),
        (r'ops\.ts_ema_(\d+)\(', r'ops.ts_ema('),
        # Decay weighted
        (r'ops\.decay_linear_(\d+)\(', r'ops.decay_linear('),
        # Time position
        (r'ops\.highday_(\d+)\(', r'ops.highday('),
        (r'ops\.lowday_(\d+)\(', r'ops.lowday('),
        # Returns/Delay/Delta
        (r'ops\.returns_(\d+)\(', r'ops.returns('),
        (r'ops\.delay_(\d+)\(', r'ops.delay('),
        (r'ops\.delta_(\d+)\(', r'ops.delta('),
    ]

    result = expression

    # For each pattern, we need to find the matching closing parenthesis
    # and insert the window parameter before it
    for pattern, replacement in patterns:
        while True:
            match = re.search(pattern, result)
            if not match:
                break

            window = match.group(1)
            start_idx = match.start()
            prefix_end = match.end()

            # Find the matching closing parenthesis
            paren_count = 1
            idx = prefix_end
            while idx < len(result) and paren_count > 0:
                if result[idx] == '(':
                    paren_count += 1
                elif result[idx] == ')':
                    paren_count -= 1
                idx += 1

            if paren_count == 0:
                # idx-1 is the position of closing paren
                close_idx = idx - 1
                # Insert ", window" before the closing paren
                inner_content = result[prefix_end:close_idx]
                new_func = replacement[:-1]  # Remove the trailing '('
                result = (result[:start_idx] +
                         new_func + '(' + inner_content + ', ' + window + ')' +
                         result[close_idx+1:])
            else:
                break

    return result


class _OpsWrapper:
    """
    Wrapper for ops that adds missing GP operations.
    """
    def __init__(self, ops):
        self._ops = ops

    def __getattr__(self, name):
        # First check if ops has this attribute
        if hasattr(self._ops, name):
            return getattr(self._ops, name)
        raise AttributeError(f"'ops' has no attribute '{name}'")

    # Add missing operations used in GP expressions
    def square(self, x):
        """Square: x^2"""
        return self._ops.multiply(x, x)

    def neg(self, x):
        """Negate: -x"""
        return self._ops.multiply(x, -1)


def gp_factor_to_func(expression: str) -> Callable:
    """
    Convert a GP expression string to a callable factor function.

    The returned function can be used with compute_factor_panel():

    Example:
        expr = "ops.clip(ops.ts_zscore(ops.highday_10(Close), 1440), -3.0, 3.0)"
        factor_func = gp_factor_to_func(expr)
        result = compute_factor_panel(panel, factor_func, 'my_gp_factor')

    Args:
        expression: GP expression string

    Returns:
        Callable function compatible with compute_factor_panel
    """
    # Convert GP format (ops.ts_rank_20) to standard format (ops.ts_rank(..., 20))
    converted_expr = _convert_gp_expression(expression)

    def factor_func(panel, ops):
        # Wrap ops to add missing GP operations
        wrapped_ops = _OpsWrapper(ops)

        # Build namespace with panel data
        local_ns = {'ops': wrapped_ops, 'np': np}

        # Add all panel columns to namespace
        for col in panel.columns:
            local_ns[col] = panel[col]

        # Common aliases
        local_ns['neg'] = lambda x: wrapped_ops.neg(x)
        local_ns['return'] = panel['return'] if 'return' in panel.columns else None

        # Evaluate expression
        result = eval(converted_expr, {"__builtins__": {}}, local_ns)
        return result

    return factor_func


def compute_gp_factor(
    panel,
    factor_id_or_expr: str,
    factor_name: str = None,
    library: GPFactorLibrary = None,
) -> pd.DataFrame:
    """
    Compute a GP factor on PanelData.

    Can use either factor_id from registry or raw expression.

    Example:
        # By factor ID
        result = compute_gp_factor(panel, 'gp_2828bb83')

        # By raw expression
        result = compute_gp_factor(panel,
            "ops.clip(ops.ts_zscore(ops.highday_10(Close), 1440), -3.0, 3.0)")

    Args:
        panel: PanelData object
        factor_id_or_expr: Factor ID from registry OR raw expression
        factor_name: Optional name for the factor
        library: GPFactorLibrary (default: global gp_library)

    Returns:
        DataFrame with factor values (rows=time, cols=assets)
    """
    from factorlib.utils import compute_factor_panel, ops

    lib = library or gp_library

    # Determine if it's a factor ID or expression
    if factor_id_or_expr.startswith('gp_') and factor_id_or_expr in lib:
        info = lib.get_info(factor_id_or_expr)
        expression = info.expression
        name = factor_name or factor_id_or_expr
    else:
        expression = factor_id_or_expr
        name = factor_name or 'gp_custom'

    # Create factor function
    factor_func = gp_factor_to_func(expression)

    # Compute using standard pipeline
    result = compute_factor_panel(panel, factor_func, name)

    return result


def batch_compute_gp_factors(
    panel,
    factor_ids: List[str] = None,
    expressions: List[str] = None,
    library: GPFactorLibrary = None,
    verbose: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Batch compute multiple GP factors.

    Example:
        # Compute top 10 factors
        top_ids = [f.factor_id for f in gp_library.list_factors(limit=10)]
        results = batch_compute_gp_factors(panel, factor_ids=top_ids)

    Args:
        panel: PanelData object
        factor_ids: List of factor IDs from registry
        expressions: List of raw expressions (alternative to factor_ids)
        library: GPFactorLibrary
        verbose: Print progress

    Returns:
        Dict of factor_name -> DataFrame
    """
    lib = library or gp_library
    results = {}

    if factor_ids:
        items = [(fid, lib.get_info(fid).expression) for fid in factor_ids if fid in lib]
    elif expressions:
        items = [(f'gp_expr_{i}', expr) for i, expr in enumerate(expressions)]
    else:
        raise ValueError("Must provide either factor_ids or expressions")

    for i, (name, expr) in enumerate(items):
        if verbose:
            print(f"Computing {i+1}/{len(items)}: {name}")
        try:
            results[name] = compute_gp_factor(panel, expr, factor_name=name, library=lib)
        except Exception as e:
            if verbose:
                print(f"  Failed: {e}")

    return results


def backtest_gp_factor(
    panel,
    factor_id_or_expr: str,
    factor_name: str = None,
    library: GPFactorLibrary = None,
    compound: bool = True,
    plot: bool = True,
    display: List[str] = None,
    mode: str = 'full',
    test_start: str = '2025-01-01',
    **kwargs
) -> dict:
    """
    Compute and backtest a GP factor in one step.

    Example:
        result = backtest_gp_factor(panel, 'gp_2828bb83')

        # Or with expression
        result = backtest_gp_factor(panel,
            "ops.clip(ops.ts_zscore(ops.highday_10(Close), 1440), -3.0, 3.0)",
            factor_name='my_factor')

        # Test mode (2025+)
        result = backtest_gp_factor(panel, 'gp_2828bb83', mode='test')

    Args:
        panel: PanelData object
        factor_id_or_expr: Factor ID or expression
        factor_name: Name for display
        library: GPFactorLibrary
        compound: Use compound returns
        plot: Show plot (True/False or list like ['average'])
        display: Display options for backtest_panel
        mode: 'full', 'train', or 'test' (default 'full')
        test_start: Test set start date (default '2025-01-01')
        **kwargs: Additional args for backtest_panel

    Returns:
        Backtest result dict
    """
    from factorlib.cli import backtest_panel

    lib = library or gp_library

    # Get name and expression
    if factor_id_or_expr.startswith('gp_') and factor_id_or_expr in lib:
        info = lib.get_info(factor_id_or_expr)
        name = factor_name or factor_id_or_expr
        print(f"Factor: {name}")
        print(f"Sharpe (GP): {info.sharpe:.2f}, Turnover: {info.turnover:.0f}")
        print(f"Expression: {info.expression[:100]}...")
    else:
        name = factor_name or 'gp_custom'

    # Compute factor
    factor_panel = compute_gp_factor(panel, factor_id_or_expr, name, lib)

    # Handle plot argument - convert bool to list for backtest_panel
    if isinstance(plot, bool):
        plot_arg = ['average'] if plot else False
    else:
        plot_arg = plot

    # Backtest
    result = backtest_panel(
        factor_panel=factor_panel,
        panel=panel,
        factor_name=name,
        compound=compound,
        plot=plot_arg,
        display=display or ['average'],
        mode=mode,
        test_start=test_start,
        **kwargs
    )

    return result


def batch_backtest_gp_factors(
    panel,
    factor_ids: List[str] = None,
    min_sharpe: float = 0,
    max_turnover: float = float('inf'),
    limit: int = 50,
    library: GPFactorLibrary = None,
    verbose: bool = True,
    plot: bool = False,
    mode: str = 'full',
    test_start: str = '2025-01-01',
) -> pd.DataFrame:
    """
    Batch backtest GP factors and return ranking DataFrame.

    Example:
        # Backtest top 50 factors with sharpe > 5
        results_df = batch_backtest_gp_factors(
            panel,
            min_sharpe=5.0,
            max_turnover=80000,
            limit=50
        )

        # Backtest on test set only
        results_df = batch_backtest_gp_factors(panel, mode='test')

    Args:
        panel: PanelData object
        factor_ids: Specific factors to test (optional)
        min_sharpe: Filter by GP-reported sharpe
        max_turnover: Filter by GP-reported turnover
        limit: Max number of factors to test
        library: GPFactorLibrary
        verbose: Print progress
        plot: Show individual plots (slow)
        mode: 'full', 'train', or 'test' (default 'full')
        test_start: Test set start date (default '2025-01-01')

    Returns:
        DataFrame with backtest results sorted by Sharpe
    """
    from factorlib.cli import backtest_panel
    import warnings

    lib = library or gp_library

    # Get factors to test
    if factor_ids:
        factors = [lib.get_info(fid) for fid in factor_ids if fid in lib]
    else:
        factors = lib.list_factors(
            min_sharpe=min_sharpe,
            max_turnover=max_turnover,
            sort_by='sharpe',
            limit=limit
        )

    if verbose:
        print(f"Backtesting {len(factors)} factors...")

    results = []
    for i, info in enumerate(factors):
        if verbose and i % 10 == 0:
            print(f"  Progress: {i}/{len(factors)}")

        try:
            # Compute factor
            factor_panel = compute_gp_factor(panel, info.expression, info.factor_id, lib)

            # Backtest (no plot for batch, minimal output)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = backtest_panel(
                    factor_panel=factor_panel,
                    panel=panel,
                    factor_name=info.factor_id,
                    compound=True,
                    plot=['average'] if plot else False,
                    display=[],  # No display for batch
                    show_ic_table=False,
                    mode=mode,
                    test_start=test_start,
                )

            # Extract metrics from portfolio result
            if 'portfolio' in result and result['portfolio']:
                perf_df = result['portfolio']['perf']
                total_row = perf_df[perf_df.iloc[:, 0] == 'Total'].iloc[0]
                results.append({
                    'factor_id': info.factor_id,
                    'backtest_sharpe': total_row.get('Sharpe', 0),
                    'backtest_return': total_row.get('Return', 0),
                    'backtest_turnover': total_row.get('Turnover', 0),
                    'backtest_mdd': total_row.get('Max Drawdown', 0),
                    'gp_sharpe': info.sharpe,
                    'gp_turnover': info.turnover,
                    'expression': info.expression,
                })
            else:
                # Single asset case
                first_asset = list(result['individual'].keys())[0]
                perf_df = result['individual'][first_asset]['perf']
                total_row = perf_df[perf_df.iloc[:, 0] == 'Total'].iloc[0]
                results.append({
                    'factor_id': info.factor_id,
                    'backtest_sharpe': total_row.get('Sharpe', 0),
                    'backtest_return': total_row.get('Return', 0),
                    'backtest_turnover': total_row.get('Turnover', 0),
                    'backtest_mdd': total_row.get('Max Drawdown', 0),
                    'gp_sharpe': info.sharpe,
                    'gp_turnover': info.turnover,
                    'expression': info.expression,
                })

        except Exception as e:
            if verbose:
                print(f"  Failed {info.factor_id}: {e}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values('backtest_sharpe', ascending=False)

    if verbose:
        print(f"\nTop 10 by backtested Sharpe:")
        print(df[['factor_id', 'backtest_sharpe', 'gp_sharpe', 'backtest_turnover']].head(10).to_string(index=False))

    return df


def get_top_gp_factors(
    min_sharpe: float = 5.0,
    max_turnover: float = 80000,
    limit: int = 20,
    library: GPFactorLibrary = None,
) -> List[GPFactorInfo]:
    """
    Get top GP factors by sharpe, filtered by turnover.

    Example:
        top = get_top_gp_factors(min_sharpe=5.0, max_turnover=60000, limit=10)
        for f in top:
            print(f"{f.factor_id}: sharpe={f.sharpe:.2f}")
    """
    lib = library or gp_library
    return lib.list_factors(
        min_sharpe=min_sharpe,
        max_turnover=max_turnover,
        sort_by='sharpe',
        limit=limit
    )


def print_factor_info(factor_id: str, library: GPFactorLibrary = None):
    """Print detailed info about a GP factor."""
    lib = library or gp_library
    info = lib.get_info(factor_id)

    print(f"{'=' * 60}")
    print(f"Factor: {info.factor_id}")
    print(f"{'=' * 60}")
    print(f"Sharpe:     {info.sharpe:.4f}")
    print(f"Returns:    {info.returns:.2f}%")
    print(f"Turnover:   {info.turnover:.0f}")
    print(f"Long Ratio: {info.long_ratio:.4f}")
    print(f"Short Ratio:{info.short_ratio:.4f}")
    print(f"Coverage:   {info.coverage:.2%}")
    print(f"\nExpression:")
    print(f"  {info.expression}")
    print(f"\nInner Expression:")
    print(f"  {info.inner_expression}")


__all__ = [
    'gp_factor_to_func',
    'compute_gp_factor',
    'batch_compute_gp_factors',
    'backtest_gp_factor',
    'batch_backtest_gp_factors',
    'get_top_gp_factors',
    'print_factor_info',
]
