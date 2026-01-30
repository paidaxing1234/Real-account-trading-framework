"""
FactorLib: Industrial-grade factor engineering and backtesting framework.

A comprehensive library for quantitative trading factor research with:
- K-line (OHLCV) factors
- Trade/tick-level factors
- Backtesting engine
- ClickHouse data integration

Quick Start:
    from factorlib.factors.library import library
    from factorlib.utils.operators import ops
    from factorlib.backtest import run_backtest

    # Compute factors
    df = library.compute('ret_skew', df)

    # Backtest
    result = run_backtest(df, 'ret_skew')
"""

__version__ = '0.3.0'

# Core classes
from .core import (
    BaseFactor,
    KlineFactorBase,
    TradeFactorBase,
    FactorPipeline,
    FactorCategory,
    FactorFrequency,
)

# Configuration
from .config import settings

# Logging
from .logging import get_logger, setup_logging, log_execution_time

# Exceptions
from .exceptions import (
    FactorLibError,
    DataError,
    FactorError,
    BacktestError,
)

# Tick processor
from .tick.processor import TickFactorProcessor

# Instrument normalization
from .cli import normalize_instrument, normalize_instruments

# Large order factors (legacy)
try:
    from .factors.large_order_tick import (
        parallel_compute_large_order_factors as parallel_large_order_factors,
        list_large_order_factor_names as list_large_order_tick_factor_names,
    )
except ImportError:
    pass

__all__ = [
    # Version
    '__version__',
    # Core
    'BaseFactor',
    'KlineFactorBase',
    'TradeFactorBase',
    'FactorPipeline',
    'FactorCategory',
    'FactorFrequency',
    # Config
    'settings',
    # Logging
    'get_logger',
    'setup_logging',
    'log_execution_time',
    # Exceptions
    'FactorLibError',
    'DataError',
    'FactorError',
    'BacktestError',
    # Processor
    'TickFactorProcessor',
    # Instrument normalization
    'normalize_instrument',
    'normalize_instruments',
]
