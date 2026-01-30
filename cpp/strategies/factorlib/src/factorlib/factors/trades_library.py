"""
Factor Library System - Trades/Tick Factors

A comprehensive factor library for tick-level data with:
- Base class for all trades factors with expression and metadata
- Performance tracking and storage
- Easy factor registration and retrieval
- Aggregation to minute-level for model input

Usage:
    from factorlib.factors.trades_library import trades_library

    # Compute single factor (returns minute-level data)
    df_minute = trades_library.compute('large_buy_ratio', df_tick)

    # Compute all factors
    df_minute = trades_library.compute_all(df_tick)

    # Merge with kline data
    df_kline = df_kline.join(df_minute)
"""

import json
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type
import numba


@dataclass
class TradeFactorPerformance:
    """Trade factor performance metrics."""
    # Information coefficient
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ir: float = 0.0  # Information ratio = ic_mean / ic_std

    # Coverage
    coverage: float = 0.0  # Percentage of non-null values

    # Metadata
    backtest_date: str = ""
    data_start: str = ""
    data_end: str = ""
    n_samples: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'TradeFactorPerformance':
        return cls(**d)

    def __repr__(self):
        return (
            f"TradeFactorPerformance(\n"
            f"  ic_mean={self.ic_mean:.4f},\n"
            f"  ir={self.ir:.2f},\n"
            f"  coverage={self.coverage:.2%}\n"
            f")"
        )


class TradeFactorBase(ABC):
    """
    Base class for all trades/tick factors in the library.

    Trades factors operate on tick-level data and output minute-level aggregations.

    Subclasses must implement:
    - name: Factor identifier
    - expression: Formula/expression string for documentation
    - compute(): Factor computation logic (returns minute-level DataFrame)

    Example:
        @trades_library.register
        class MyTradeFactor(TradeFactorBase):
            name = "my_trade_factor"
            expression = "sum(quantity[is_large]) / sum(quantity)"
            description = "Large order volume ratio"
            category = "orderflow"

            def compute(self, df):
                # df is tick-level data
                # returns minute-level aggregated factor
                ...
    """

    # Required class attributes
    name: str = ""
    expression: str = ""
    description: str = ""
    author: str = ""
    version: str = "1.0"
    category: str = "orderflow"  # orderflow, microstructure, liquidity

    # Performance storage
    performance: Optional[TradeFactorPerformance] = None

    def __init__(self, **kwargs):
        """Initialize with optional parameter overrides."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.created_at = datetime.now().isoformat()

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute factor values from tick data.

        Args:
            df: Input tick-level DataFrame with required columns

        Returns:
            Minute-level DataFrame with factor column (column name = self.name)
        """
        pass

    def required_columns(self) -> List[str]:
        """Return list of required input columns."""
        return ['quantity', 'tradeTime']

    def validate_input(self, df: pd.DataFrame) -> None:
        """Validate input DataFrame."""
        missing = set(self.required_columns()) - set(df.columns)
        if missing:
            raise ValueError(f"Trade factor '{self.name}' requires columns: {missing}")

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        """Allow factor to be called as function."""
        return self.compute(df)

    def to_dict(self) -> dict:
        """Export factor metadata as dict."""
        return {
            'name': self.name,
            'expression': self.expression,
            'description': self.description,
            'author': self.author,
            'version': self.version,
            'category': self.category,
            'created_at': self.created_at,
            'performance': self.performance.to_dict() if self.performance else None
        }

    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}', category='{self.category}')"


class TradeFactorLibrary:
    """
    Central registry for all trades/tick factors.

    Usage:
        from factorlib.factors.trades_library import trades_library

        # Register a factor
        @trades_library.register
        class MyTradeFactor(TradeFactorBase):
            ...

        # Compute single factor
        df_minute = trades_library.compute('large_buy_ratio', df_tick)

        # Compute all factors
        df_minute = trades_library.compute_all(df_tick)
    """

    def __init__(self):
        self._factors: Dict[str, Type[TradeFactorBase]] = {}
        self._instances: Dict[str, TradeFactorBase] = {}

    def register(self, cls: Type[TradeFactorBase]) -> Type[TradeFactorBase]:
        """Register a factor class (decorator)."""
        if not issubclass(cls, TradeFactorBase):
            raise TypeError(f"{cls} must inherit from TradeFactorBase")

        instance = cls()
        self._factors[instance.name] = cls
        self._instances[instance.name] = instance
        return cls

    def register_factor(self, cls: Type[TradeFactorBase], **kwargs) -> None:
        """Register a factor class manually."""
        instance = cls(**kwargs)
        self._factors[instance.name] = cls
        self._instances[instance.name] = instance

    def get(self, name: str) -> TradeFactorBase:
        """Get factor instance by name."""
        if name not in self._instances:
            raise KeyError(f"Trade factor '{name}' not found. Available: {list(self._factors.keys())}")
        return self._instances[name]

    def compute(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Compute a single factor."""
        factor = self.get(name)
        return factor.compute(df)

    def compute_many(self, names: List[str], df: pd.DataFrame) -> pd.DataFrame:
        """Compute multiple factors and merge into single DataFrame."""
        results = []
        for name in names:
            factor = self.get(name)
            result = factor.compute(df)
            results.append(result)

        if not results:
            return pd.DataFrame()

        # Merge all factors on minute index
        merged = results[0]
        for r in results[1:]:
            merged = merged.join(r, how='outer')
        return merged

    def compute_all(
        self,
        df: pd.DataFrame,
        categories: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Compute all registered factors.

        Args:
            df: Input tick-level DataFrame
            categories: Only compute factors in these categories

        Returns:
            Minute-level DataFrame with all factor columns
        """
        results = []
        for name, factor in self._instances.items():
            if categories and factor.category not in categories:
                continue
            try:
                result = factor.compute(df)
                results.append(result)
            except Exception as e:
                print(f"Warning: Trade factor '{name}' failed: {e}")

        if not results:
            return pd.DataFrame()

        # Merge all factors on minute index
        merged = results[0]
        for r in results[1:]:
            merged = merged.join(r, how='outer')
        return merged

    def list_factors(self) -> List[str]:
        """List all registered factor names."""
        return list(self._factors.keys())

    def list_by_category(self) -> Dict[str, List[str]]:
        """List factors grouped by category."""
        result = {}
        for name, factor in self._instances.items():
            cat = factor.category
            if cat not in result:
                result[cat] = []
            result[cat].append(name)
        return result

    def save(self, path: str) -> None:
        """Save library metadata to JSON."""
        data = {
            name: factor.to_dict()
            for name, factor in self._instances.items()
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def __len__(self):
        return len(self._factors)

    def __contains__(self, name: str):
        return name in self._factors

    def __repr__(self):
        return f"TradeFactorLibrary({len(self)} factors: {list(self._factors.keys())})"


# Global library instance
trades_library = TradeFactorLibrary()


# ============================================================================
# Numba-optimized helper functions
# ============================================================================

@numba.njit
def _compute_large_threshold(quantities: np.ndarray, percentile: float = 0.99) -> float:
    """Compute large order threshold using percentile."""
    sorted_q = np.sort(quantities)
    idx = int(len(sorted_q) * percentile)
    return sorted_q[min(idx, len(sorted_q) - 1)]


@numba.njit
def _compute_large_buy_ratio(
    quantities: np.ndarray,
    is_buyer_maker: np.ndarray,
    threshold: float
) -> float:
    """Compute large buy volume ratio."""
    is_large = quantities >= threshold
    is_buy = ~is_buyer_maker

    large_buy = np.sum(quantities[is_large & is_buy])
    total = np.sum(quantities)

    return large_buy / total if total > 0 else 0.0


# ============================================================================
# Built-in Trades Factors - Order Flow
# ============================================================================

@trades_library.register
class LargeBuyRatioFactor(TradeFactorBase):
    """Large order buy ratio factor."""

    name = "large_buy_ratio"
    expression = "sum(quantity[is_large & is_buy]) / sum(quantity)"
    description = "Large buy volume ratio (top 1% orders)"
    category = "orderflow"

    percentile: float = 0.99

    def __init__(self, **kwargs):
        self.percentile = kwargs.pop('percentile', 0.99)
        super().__init__(**kwargs)

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        threshold = _compute_large_threshold(out['quantity'].values, self.percentile)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            return _compute_large_buy_ratio(
                group['quantity'].values,
                group['is_buyer_maker'].values,
                threshold
            )

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class LargeDirImbalanceFactor(TradeFactorBase):
    """Large order directional imbalance factor."""

    name = "large_dir_imbalance"
    expression = "(large_buy - large_sell) / (large_buy + large_sell)"
    description = "Large order buy-sell imbalance"
    category = "orderflow"

    percentile: float = 0.99

    def __init__(self, **kwargs):
        self.percentile = kwargs.pop('percentile', 0.99)
        super().__init__(**kwargs)

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        threshold = _compute_large_threshold(out['quantity'].values, self.percentile)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            is_large = group['quantity'] >= threshold
            is_buy = ~group['is_buyer_maker']

            large_buy = group.loc[is_large & is_buy, 'quantity'].sum()
            large_sell = group.loc[is_large & ~is_buy, 'quantity'].sum()
            total = large_buy + large_sell

            return (large_buy - large_sell) / total if total > 0 else 0.0

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class LargeOrderDensityFactor(TradeFactorBase):
    """Large order density (count per minute)."""

    name = "large_order_density"
    expression = "count(quantity >= threshold)"
    description = "Large order count per minute"
    category = "orderflow"

    percentile: float = 0.99

    def __init__(self, **kwargs):
        self.percentile = kwargs.pop('percentile', 0.99)
        super().__init__(**kwargs)

    def required_columns(self) -> List[str]:
        return ['quantity', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        threshold = _compute_large_threshold(out['quantity'].values, self.percentile)
        out['is_large'] = out['quantity'] >= threshold
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        result = out.groupby('minute')['is_large'].sum()
        result.name = self.name
        return result.to_frame()


@trades_library.register
class OrderFlowImbalanceFactor(TradeFactorBase):
    """Order Flow Imbalance (OFI) factor."""

    name = "ofi"
    expression = "sum(signed_volume) / sum(abs_volume)"
    description = "Order flow imbalance"
    category = "orderflow"

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        sign = np.where(out['is_buyer_maker'], -1, 1)
        out['signed_volume'] = out['quantity'] * sign
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            signed_sum = group['signed_volume'].sum()
            total = group['quantity'].sum()
            return signed_sum / total if total > 0 else 0.0

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class TradeDirectionFactor(TradeFactorBase):
    """Trade direction momentum factor."""

    name = "trade_direction"
    expression = "sum(direction) / count"
    description = "Net trade direction normalized"
    category = "orderflow"

    def required_columns(self) -> List[str]:
        return ['is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out['direction'] = np.where(out['is_buyer_maker'], -1, 1)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            if len(group) == 0:
                return 0.0
            return group['direction'].sum() / len(group)

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class AggressorRatioFactor(TradeFactorBase):
    """Aggressor ratio factor - aggressive buy volume ratio."""

    name = "aggressor_ratio"
    expression = "sum(quantity[is_aggressive_buy]) / sum(quantity)"
    description = "Aggressive buy volume ratio"
    category = "orderflow"

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            agg_buy = group.loc[~group['is_buyer_maker'], 'quantity'].sum()
            total = group['quantity'].sum()
            return agg_buy / total if total > 0 else 0.5

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class VolumeWeightedOFIFactor(TradeFactorBase):
    """Volume-weighted Order Flow Imbalance."""

    name = "vw_ofi"
    expression = "sum(sign * quantity^2) / sum(quantity^2)"
    description = "Volume-weighted OFI (emphasizes large trades)"
    category = "orderflow"

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        sign = np.where(out['is_buyer_maker'], -1, 1)
        out['weighted_sign'] = sign * (out['quantity'] ** 2)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            weighted_sum = group['weighted_sign'].sum()
            total_weight = (group['quantity'] ** 2).sum()
            return weighted_sum / total_weight if total_weight > 0 else 0.0

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class TradeAccelerationFactor(TradeFactorBase):
    """Trade acceleration - rate of change in trading intensity."""

    name = "trade_acceleration"
    expression = "pct_change(volume_per_minute)"
    description = "Trade intensity acceleration"
    category = "orderflow"

    def required_columns(self) -> List[str]:
        return ['quantity', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        vol_per_min = out.groupby('minute')['quantity'].sum()
        result = vol_per_min.pct_change().fillna(0)
        result.name = self.name
        return result.to_frame()


# ============================================================================
# Built-in Trades Factors - Microstructure
# ============================================================================

@trades_library.register
class TradeIntensityFactor(TradeFactorBase):
    """Trade intensity - number of trades per minute."""

    name = "trade_intensity"
    expression = "count(trades)"
    description = "Trade count per minute"
    category = "microstructure"

    def required_columns(self) -> List[str]:
        return ['tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        result = out.groupby('minute').size()
        result.name = self.name
        return result.to_frame()


@trades_library.register
class PriceImpactFactor(TradeFactorBase):
    """Price impact - average price change per unit volume."""

    name = "price_impact"
    expression = "sum(abs(price_change)) / sum(quantity)"
    description = "Price change per unit volume"
    category = "microstructure"

    def required_columns(self) -> List[str]:
        return ['price', 'quantity', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out['price_change'] = out['price'].diff().abs()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            total_change = group['price_change'].sum()
            total_volume = group['quantity'].sum()
            return total_change / total_volume if total_volume > 0 else 0.0

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class LargeSellImpactFactor(TradeFactorBase):
    """Large sell price impact."""

    name = "large_sell_impact"
    expression = "mean(price_change[is_large_sell])"
    description = "Average price change after large sells"
    category = "microstructure"

    percentile: float = 0.99

    def __init__(self, **kwargs):
        self.percentile = kwargs.pop('percentile', 0.99)
        super().__init__(**kwargs)

    def required_columns(self) -> List[str]:
        return ['quantity', 'price', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        threshold = _compute_large_threshold(out['quantity'].values, self.percentile)
        out['price_change'] = out['price'].diff().shift(-1)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            large_sells = group[(group['quantity'] >= threshold) & group['is_buyer_maker']]
            if len(large_sells) == 0:
                return 0.0
            return large_sells['price_change'].mean()

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class TradeArrivalCVFactor(TradeFactorBase):
    """Trade arrival coefficient of variation."""

    name = "arrival_cv"
    expression = "std(interarrival) / mean(interarrival)"
    description = "Trade arrival regularity (lower = more regular)"
    category = "microstructure"

    def required_columns(self) -> List[str]:
        return ['tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out['interarrival'] = out['tradeTime'].diff()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            intervals = group['interarrival'].dropna()
            if len(intervals) < 2:
                return 0.0
            mean = intervals.mean()
            if mean == 0:
                return 0.0
            return intervals.std() / mean

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class PriceReversalFactor(TradeFactorBase):
    """Price reversal frequency."""

    name = "price_reversal"
    expression = "count(direction_changes) / count(trades)"
    description = "Price reversal frequency"
    category = "microstructure"

    def required_columns(self) -> List[str]:
        return ['price', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out['direction'] = np.sign(out['price'].diff())
        out['reversal'] = (out['direction'] != out['direction'].shift(1)).astype(int)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            n_trades = len(group)
            if n_trades < 3:
                return 0.0
            return group['reversal'].sum() / (n_trades - 1)

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class LargeSlicingScoreFactor(TradeFactorBase):
    """Order slicing detection score."""

    name = "large_slicing_score"
    expression = "count(consecutive_similar_large_orders) / total_large_volume"
    description = "Order slicing pattern detection"
    category = "microstructure"

    percentile: float = 0.99
    size_tolerance: float = 0.1

    def __init__(self, **kwargs):
        self.percentile = kwargs.pop('percentile', 0.99)
        self.size_tolerance = kwargs.pop('size_tolerance', 0.1)
        super().__init__(**kwargs)

    def required_columns(self) -> List[str]:
        return ['quantity', 'is_buyer_maker', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        threshold = _compute_large_threshold(out['quantity'].values, self.percentile)
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')
        out['is_large'] = out['quantity'] >= threshold

        def agg_func(group):
            large = group[group['is_large']].copy()
            if len(large) < 2:
                return 0.0

            sizes = large['quantity'].values
            directions = large['is_buyer_maker'].values

            slicing_score = 0
            for i in range(1, len(large)):
                same_dir = directions[i] == directions[i - 1]
                size_ratio = min(sizes[i], sizes[i - 1]) / max(sizes[i], sizes[i - 1])
                similar_size = size_ratio > (1 - self.size_tolerance)

                if same_dir and similar_size:
                    slicing_score += 1

            total_large = group.loc[group['is_large'], 'quantity'].sum()
            return slicing_score / total_large if total_large > 0 else 0.0

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


# ============================================================================
# Built-in Trades Factors - Liquidity
# ============================================================================

@trades_library.register
class SpreadEstimateFactor(TradeFactorBase):
    """Effective spread estimate using Roll's method."""

    name = "spread_estimate"
    expression = "2 * sqrt(-cov(dp_t, dp_{t-1}))"
    description = "Estimated bid-ask spread (Roll method)"
    category = "liquidity"

    def required_columns(self) -> List[str]:
        return ['price', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out['price_change'] = out['price'].diff()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            if len(group) < 3:
                return 0.0

            changes = group['price_change'].dropna().values
            if len(changes) < 2:
                return 0.0

            cov = np.cov(changes[1:], changes[:-1])[0, 1]
            if cov >= 0:
                return 0.0
            return 2 * np.sqrt(-cov)

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()


@trades_library.register
class VolumeConcentrationFactor(TradeFactorBase):
    """Volume concentration (Herfindahl index)."""

    name = "volume_concentration"
    expression = "sum((quantity / total)^2)"
    description = "Volume concentration Herfindahl index"
    category = "liquidity"

    def required_columns(self) -> List[str]:
        return ['quantity', 'tradeTime']

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out['minute'] = pd.to_datetime(out['tradeTime'], unit='ms').dt.floor('1min')

        def agg_func(group):
            total = group['quantity'].sum()
            if total == 0:
                return 0.0
            shares = group['quantity'] / total
            return (shares ** 2).sum()

        result = out.groupby('minute').apply(agg_func)
        result.name = self.name
        return result.to_frame()
