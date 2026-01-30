# FactorLib

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Industrial-grade factor engineering and backtesting framework for quantitative trading.

## Features

- **Unified Factor Library**: Centralized factor system with registration, metadata, and performance tracking
- **High-Performance Operators**: Numba JIT-compiled operators for time-series and cross-sectional computations
- **K-line Factors**: 18 built-in factors (momentum, volatility, volume, price, trend, anomaly)
- **Trades Factors**: 16 built-in factors (orderflow, microstructure, liquidity) for tick data
- **Backtesting Engine**: Compound/simple returns, performance metrics, visualization
- **Performance Tracking**: Automatic performance storage with `FactorPerformance`
- **Parallel Computing**: Multi-threaded factor computation for large datasets
- **ClickHouse Integration**: Native support for ClickHouse data loading

## Installation

```bash
# Basic installation
pip install -e .

# With ClickHouse support
pip install -e ".[clickhouse]"

# Full installation (dev + docs)
pip install -e ".[all]"
```

## Quick Start

### Using the Factor Library

```python
from factorlib.factors.library import library
from factorlib.utils.operators import ops

# List available factors
print(library.list_factors())
# ['ret_skew', 'momentum', 'volatility', 'atr', ...]

# Compute single factor
df = library.compute('ret_skew', df)

# Compute all factors
df = library.compute_all(df, include_signals=True)

# Backtest a factor
bt_df, perf_df = library.backtest('ret_skew', df, compound=True)
print(library.get('ret_skew').performance)
```

### Using Operators

```python
from factorlib.utils.operators import ops

# Time-series operators (Numba optimized)
ma20 = ops.ts_mean(df['Close'], 20)
zscore = ops.ts_zscore(df['return'], 60)
rank = ops.ts_rank(df['volume'], 20)
slope = ops.ts_slope(df['Close'], 20)

# Cross-sectional operators
weights = ops.cs_softmax(df_universe, tau=0.5)
weights = ops.cs_cap_and_renorm(weights, cap=0.1)

# Data processing
clipped = ops.clip(df['factor'], -3, 3)
filtered = ops.filter_range(df['signal'], 0.4, 1.0)
```

### Creating Custom Factors

```python
from factorlib.factors.library import library, FactorBase
from factorlib.utils.operators import ops

@library.register
class MyCustomFactor(FactorBase):
    """Custom factor with exponential decay."""

    name = "my_factor"
    description = "Custom momentum factor"
    category = "momentum"

    window: int = 20
    decay_alpha: float = 2.0

    def compute(self, df):
        out = self.ensure_return(df)
        out[self.name] = ops.ts_mean(out['return'], self.window)
        out[self.name] = ops.decay_exp(out[self.name], self.decay_alpha)
        return out

# Use the factor
df = library.compute('my_factor', df)
```

### Trades Factor Library

```python
from factorlib.factors.trades_library import trades_library

# List available factors
print(trades_library.list_factors())
# ['large_buy_ratio', 'ofi', 'trade_intensity', ...]

# Compute single factor (returns minute-level data)
df_minute = trades_library.compute('large_buy_ratio', df_tick)

# Compute all factors
df_minute = trades_library.compute_all(df_tick)

# Merge with kline data
df_kline = df_kline.join(df_minute)
```

## Project Structure

```
factorlib/
├── src/factorlib/
│   ├── factors/
│   │   ├── library.py         # K-line factor library (18 factors)
│   │   ├── trades_library.py  # Trades factor library (16 factors)
│   │   └── custom.py          # Legacy functional interface
│   ├── backtest/
│   │   └── engine.py          # Backtesting with performance tracking
│   ├── utils/
│   │   ├── operators.py       # High-performance operators (ops.*)
│   │   └── signals.py         # Signal generation
│   ├── tick/                  # Tick data processing
│   ├── data/                  # Data loaders
│   └── config/                # Configuration management
├── scripts/
│   └── compute_all_factors.py # Batch factor computation
├── notebooks/                 # Research notebooks
├── tests/                     # Unit & integration tests
└── docs/                      # Documentation
```

## Built-in Factors

### K-line Factors (library)

| Category | Factors |
|----------|---------|
| **Momentum** | ret_skew, momentum, mom_reversal |
| **Volatility** | volatility, atr, realized_vol |
| **Volume** | buy2sell_ratio, volume_anomaly |
| **Price** | price_stable, price_range, price_position |
| **Trend** | trend_strength, atr_trend |
| **Anomaly** | trade_count_anomaly, trade_value_anomaly, volume_ratio, money_ratio |

### Trades Factors (trades_library)

| Category | Factors |
|----------|---------|
| **Orderflow** | large_buy_ratio, large_dir_imbalance, ofi, trade_direction, aggressor_ratio |
| **Microstructure** | trade_intensity, price_impact, arrival_cv, price_reversal |
| **Liquidity** | spread_estimate, volume_concentration |

## Operators Reference

### Time Series (ts_*)

```python
# Rolling window operations (Numba JIT optimized)
ops.ts_mean(x, window)      # Rolling mean
ops.ts_std(x, window)       # Rolling standard deviation
ops.ts_zscore(x, window)    # Rolling z-score
ops.ts_rank(x, window)      # Rolling rank (percentile)
ops.ts_skew(x, window)      # Rolling skewness
ops.ts_slope(x, window)     # Rolling slope (linear regression)
ops.ts_min(x, window)       # Rolling minimum
ops.ts_max(x, window)       # Rolling maximum

# Decay weighted
ops.decay_linear(x, window) # Linear decay weighted average
ops.decay_exp(x, alpha)     # Exponential decay (EMA)
```

### Cross Section (cs_*)

```python
ops.cs_rank(x)              # Cross-sectional rank
ops.cs_zscore(x)            # Cross-sectional z-score
ops.cs_demean(x)            # Cross-sectional demean
ops.cs_softmax(x, tau)      # Cross-sectional softmax weights
```

### Data Processing

```python
ops.clip(x, min_val, max_val)      # Clip values (parallel)
ops.filter_range(x, min, max)      # Filter outside range to 0
ops.winsorize(x, lower, upper)     # Winsorize to quantiles
ops.fill_na(x, method='ffill')     # Fill NaN values
```

## Performance

Benchmark on 1.7M rows (BTC-USDT 1-minute data):

| Operator | Time |
|----------|------|
| ts_mean(20) | 9.3ms |
| ts_std(20) | 1.6ms |
| ts_zscore(60) | 3.7ms |
| ts_rank(20) | 1.0ms |
| clip(-2, 2) | 1.6ms |

Factor computation: **14 factors in 1.4s** (10.2 factors/sec)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FACTORLIB_DATA_DIR` | Data directory | `/home/ch/data` |
| `FACTORLIB_OUTPUT_DIR` | Output directory | `/home/ch/data/result` |
| `FACTORLIB_DB_HOST` | ClickHouse host | `192.168.193.1` |
| `FACTORLIB_DB_PORT` | ClickHouse port | `8123` |

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=factorlib

# Format code
black src/
isort src/

# Lint code
ruff check src/
mypy src/
```

## Research Workflow

1. **Research**: Develop factor in `notebooks/factor_research_template.ipynb`
2. **Backtest**: Use `library.backtest()` to evaluate performance
3. **Register**: Add good factors to library with `@library.register`
4. **Track**: Performance automatically saved to `FactorPerformance`
5. **Filter**: Use `library.filter_factors()` to select best factors
6. **Deploy**: Use `library.compute_all()` for model input

## License

MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2024-2025 Sequence Quant Technology Limited

## Author

- **Neil CHAN** - Sequence Quant Technology Limited

## Contributing

Contributions are welcome! Please read our contributing guidelines for details.
