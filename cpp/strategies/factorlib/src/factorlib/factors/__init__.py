"""
FactorLib Factors Module

Unified factor library system with:
- K-line factors: library (momentum, volatility, volume, price, trend, anomaly)
- Trades factors: trades_library (orderflow, microstructure, liquidity)

Usage:
    # K-line Factor Library
    from factorlib.factors.library import library, FactorBase

    df = library.compute('ret_skew', df)
    df = library.compute_all(df)
    library.list_factors()

    # Trades Factor Library
    from factorlib.factors.trades_library import trades_library

    df_minute = trades_library.compute('large_buy_ratio', df_tick)

    # Create custom factor
    @library.register
    class MyFactor(FactorBase):
        name = "my_factor"
        description = "My custom factor"
        category = "custom"

        def compute(self, df):
            out = self.ensure_return(df)
            out[self.name] = ops.ts_mean(out['return'], 20)
            return out
"""

# K-line Factor Library
from .library import (
    library,
    FactorBase,
    FactorLibrary,
    FactorPerformance,
)

# Trades Factor Library
from .trades_library import (
    trades_library,
    TradeFactorBase,
    TradeFactorLibrary,
    TradeFactorPerformance,
)

__all__ = [
    # K-line Library
    'library',
    'FactorBase',
    'FactorLibrary',
    'FactorPerformance',
    # Trades Library
    'trades_library',
    'TradeFactorBase',
    'TradeFactorLibrary',
    'TradeFactorPerformance',
]
