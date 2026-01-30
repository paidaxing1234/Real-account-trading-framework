"""
Base classes for factor computation.

This module provides abstract base classes that define the interface
for all factor implementations in the library.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import pandas as pd
import numpy as np


class FactorFrequency(Enum):
    """Factor computation frequency."""
    TICK = "tick"
    SECOND = "1s"
    MINUTE = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR = "1h"
    DAILY = "1d"


class FactorCategory(Enum):
    """Factor category classification."""
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    PRICE = "price"
    TREND = "trend"
    MICROSTRUCTURE = "microstructure"
    ORDERFLOW = "orderflow"
    LIQUIDITY = "liquidity"
    CUSTOM = "custom"


class BaseFactor(ABC):
    """
    Abstract base class for all factors.

    All factor implementations should inherit from this class and implement
    the required methods.

    Attributes:
        name: Factor identifier
        category: Factor category (momentum, volatility, etc.)
        frequency: Computation frequency
        lookback: Required lookback period in bars
        description: Human-readable description
    """

    def __init__(
        self,
        name: str,
        category: FactorCategory = FactorCategory.CUSTOM,
        frequency: FactorFrequency = FactorFrequency.MINUTE,
        lookback: int = 1,
        description: str = ""
    ):
        self.name = name
        self.category = category
        self.frequency = frequency
        self.lookback = lookback
        self.description = description or f"{name} factor"
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate factor configuration."""
        if self.lookback < 1:
            raise ValueError(f"lookback must be >= 1, got {self.lookback}")

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute the factor values.

        Args:
            df: Input DataFrame with required columns

        Returns:
            DataFrame with original columns plus factor column(s)
        """
        pass

    @abstractmethod
    def required_columns(self) -> List[str]:
        """
        Return list of required input columns.

        Returns:
            List of column names required for computation
        """
        pass

    def output_columns(self) -> List[str]:
        """
        Return list of output column names.

        Returns:
            List of column names produced by this factor
        """
        return [self.name]

    def validate_input(self, df: pd.DataFrame) -> None:
        """
        Validate input DataFrame has required columns.

        Args:
            df: Input DataFrame to validate

        Raises:
            ValueError: If required columns are missing
        """
        missing = set(self.required_columns()) - set(df.columns)
        if missing:
            raise ValueError(
                f"Factor '{self.name}' requires columns {missing} "
                f"but they are not in DataFrame. Available: {list(df.columns)}"
            )

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        """Allow factor to be called as function."""
        self.validate_input(df)
        return self.compute(df)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"category={self.category.value}, "
            f"lookback={self.lookback})"
        )


class KlineFactorBase(BaseFactor):
    """
    Base class for K-line (OHLCV) based factors.

    K-line factors operate on standard candlestick data with
    Open, High, Low, Close, Volume columns.
    """

    STANDARD_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']

    def __init__(
        self,
        name: str,
        category: FactorCategory = FactorCategory.CUSTOM,
        lookback: int = 1,
        description: str = ""
    ):
        super().__init__(
            name=name,
            category=category,
            frequency=FactorFrequency.MINUTE,
            lookback=lookback,
            description=description
        )

    def required_columns(self) -> List[str]:
        """Default required columns for K-line factors."""
        return ['Close']

    def ensure_return_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure 'return' column exists in DataFrame."""
        out = df.copy()
        if 'return' not in out.columns:
            if 'Close' not in out.columns:
                raise ValueError("Need 'Close' column to compute returns")
            out['return'] = np.log(out['Close']).diff().fillna(0)
        return out


class TradeFactorBase(BaseFactor):
    """
    Base class for trade/tick based factors.

    Trade factors operate on tick-level data with individual
    trade records including price, quantity, and aggressor side.
    """

    STANDARD_COLUMNS = ['price', 'quantity', 'tradeTime', 'is_buyer_maker']

    def __init__(
        self,
        name: str,
        category: FactorCategory = FactorCategory.MICROSTRUCTURE,
        lookback: int = 1,
        window_ms: int = 60000,
        description: str = ""
    ):
        super().__init__(
            name=name,
            category=category,
            frequency=FactorFrequency.TICK,
            lookback=lookback,
            description=description
        )
        self.window_ms = window_ms  # Aggregation window in milliseconds

    def required_columns(self) -> List[str]:
        """Default required columns for trade factors."""
        return ['price', 'quantity', 'tradeTime']

    def aggregate_to_minute(
        self,
        df: pd.DataFrame,
        agg_func: str = 'last'
    ) -> pd.DataFrame:
        """
        Aggregate tick-level factor to minute level.

        Args:
            df: DataFrame with tick-level factor values
            agg_func: Aggregation function ('last', 'mean', 'sum', etc.)

        Returns:
            DataFrame aggregated to 1-minute frequency
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have DatetimeIndex")

        return df.resample('1min').agg(agg_func)


class FactorPipeline:
    """
    Pipeline for chaining multiple factors together.

    Example:
        pipeline = FactorPipeline([
            MomentumFactor(window=20),
            VolatilityFactor(window=60),
            TrendFactor()
        ])
        result = pipeline.run(df)
    """

    def __init__(self, factors: List[BaseFactor]):
        self.factors = factors
        self._validate_pipeline()

    def _validate_pipeline(self) -> None:
        """Validate that pipeline factors are compatible."""
        names = [f.name for f in self.factors]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate factor names in pipeline")

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run all factors in the pipeline.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with all factor columns added
        """
        result = df.copy()
        for factor in self.factors:
            result = factor(result)
        return result

    def get_factor_names(self) -> List[str]:
        """Get list of all factor names in pipeline."""
        names = []
        for factor in self.factors:
            names.extend(factor.output_columns())
        return names

    def __repr__(self) -> str:
        factor_names = [f.name for f in self.factors]
        return f"FactorPipeline({factor_names})"
