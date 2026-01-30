"""
GP Factors - Genetically Programmed Factor Library

This module provides a dynamic factor library for GP-mined factors.
Instead of generating thousands of class files, factors are stored
as expressions in a JSON registry and evaluated on-demand.

Usage in Notebook:
==================

    from factorlib.factors.gp_factors import (
        gp_library,              # Factor registry
        compute_gp_factor,       # Compute single factor
        backtest_gp_factor,      # Compute + backtest
        batch_backtest_gp_factors,  # Batch backtest
        get_top_gp_factors,      # Get top factors
        print_factor_info,       # Show factor details
    )

    # View top factors
    top = get_top_gp_factors(min_sharpe=5.0, max_turnover=60000, limit=10)

    # Compute and backtest a factor
    result = backtest_gp_factor(panel, 'gp_2828bb83')

    # Or use raw expression
    result = backtest_gp_factor(panel,
        "ops.clip(ops.ts_zscore(ops.highday_10(Close), 1440), -3.0, 3.0)",
        factor_name='my_factor')

    # Batch backtest top 50 factors
    results_df = batch_backtest_gp_factors(panel, min_sharpe=5.0, limit=50)
"""

from .gp_library import GPFactorLibrary, gp_library
from .screener import screen_factors, batch_backtest
from .utils import (
    gp_factor_to_func,
    compute_gp_factor,
    batch_compute_gp_factors,
    backtest_gp_factor,
    batch_backtest_gp_factors,
    get_top_gp_factors,
    print_factor_info,
)

__all__ = [
    # Library
    'GPFactorLibrary',
    'gp_library',
    # Screener
    'screen_factors',
    'batch_backtest',
    # Notebook utils
    'gp_factor_to_func',
    'compute_gp_factor',
    'batch_compute_gp_factors',
    'backtest_gp_factor',
    'batch_backtest_gp_factors',
    'get_top_gp_factors',
    'print_factor_info',
]
