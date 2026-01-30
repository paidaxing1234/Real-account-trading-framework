"""
Factor Library System - K-line Factors

A comprehensive factor library with:
- Base class for all factors with expression and metadata
- Easy factor registration and retrieval
- Batch computation for model input

Usage:
    from factorlib.factors.library import library

    # Compute single factor
    df = library.compute('ret_skew', df)

    # Compute all factors
    df = library.compute_all(df)

    # Get factor info
    factor = library.get('ret_skew')
    print(factor.expression)  # 自动生成的表达式
    print(factor.require)     # 需要的数据列
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Type

from factorlib.utils.operators import ops


# ============================================================================
# Base Classes
# ============================================================================

@dataclass
class FactorPerformance:
    """Factor performance metrics."""
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
    def from_dict(cls, d: dict) -> 'FactorPerformance':
        return cls(**d)

    def __repr__(self):
        return (
            f"FactorPerformance(\n"
            f"  ic_mean={self.ic_mean:.4f},\n"
            f"  ir={self.ir:.2f},\n"
            f"  coverage={self.coverage:.2%}\n"
            f")"
        )


class FactorBase(ABC):
    """
    因子基类 - 自动追踪表达式

    只需要实现 factor_func 方法，表达式会自动生成。

    Example:
        @library.register
        class MyFactor(FactorBase):
            name = "my_factor"
            description = "My custom factor"
            category = "momentum"
            require = ['Close']

            def factor_func(self, df, ops):
                close = ops.col(df, 'Close')
                ma3 = ops.ts_mean(close, 3)
                ma60 = ops.ts_mean(close, 60)
                momentum = ops.divide(ma3, ma60) - 1
                momentum = ops.fill_na(momentum)
                return -ops.ts_ema(ops.clip(ops.ts_zscore(momentum, 1440), -3, 3), 2)
    """

    name: str = ""
    expression: str = ""
    description: str = ""
    category: str = "custom"
    require: List[str] = ['Close']
    _auto_expression: str = ""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.created_at = datetime.now().isoformat()

    @abstractmethod
    def factor_func(self, df: pd.DataFrame, ops) -> 'Expr':
        """定义因子计算逻辑（子类必须实现）"""
        raise NotImplementedError("Subclass must implement factor_func")

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算因子值（自动追踪表达式）"""
        from factorlib.utils.expr_tracker import tracked_ops, Expr

        out = df.copy()
        result = self.factor_func(out, tracked_ops)

        if isinstance(result, Expr):
            out[self.name] = result.data
            if not self.expression or self.expression == "":
                self.expression = result.formula
                self._auto_expression = result.formula
        else:
            out[self.name] = result

        return out

    def required_columns(self) -> List[str]:
        return self.require

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.compute(df)

    def __repr__(self):
        return f"{self.__class__.__name__}(name='{self.name}', category='{self.category}')"


# ============================================================================
# Factor Library
# ============================================================================

class FactorLibrary:
    """因子库 - 注册和管理所有因子"""

    def __init__(self):
        self._factors: Dict[str, Type[FactorBase]] = {}
        self._instances: Dict[str, FactorBase] = {}

    def register(self, cls: Type[FactorBase]) -> Type[FactorBase]:
        """注册因子（装饰器）"""
        if not issubclass(cls, FactorBase):
            raise TypeError(f"{cls} must inherit from FactorBase")
        instance = cls()
        self._factors[instance.name] = cls
        self._instances[instance.name] = instance
        return cls

    def get(self, name: str) -> FactorBase:
        """获取因子实例"""
        if name not in self._instances:
            raise KeyError(f"Factor '{name}' not found. Available: {list(self._factors.keys())}")
        return self._instances[name]

    def compute(self, name: str, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """计算单个因子（单资产 DataFrame）"""
        factor = self.get(name)
        return factor.compute(df)

    def compute_many(self, names: List[str], df: pd.DataFrame) -> pd.DataFrame:
        """计算多个因子（单资产）"""
        out = df.copy()
        for name in names:
            out = self.get(name).compute(out)
        return out

    def compute_all(self, df: pd.DataFrame, categories: Optional[List[str]] = None) -> pd.DataFrame:
        """计算所有因子（单资产）"""
        out = df.copy()
        for name, factor in self._instances.items():
            if categories and factor.category not in categories:
                continue
            try:
                out = factor.compute(out)
            except Exception as e:
                print(f"Warning: Factor '{name}' failed: {e}")
        return out

    def compute_panel(
        self,
        name: str,
        data_dict: Dict[str, pd.DataFrame],
        verbose: bool = True
    ) -> pd.DataFrame:
        """
        计算因子并返回 Panel DataFrame (rows=timestamps, cols=assets).

        支持 TS 和 CS 算子混合使用。

        Args:
            name: 因子名称
            data_dict: Dict[instrument_name -> DataFrame]
            verbose: 是否打印表达式

        Returns:
            Panel DataFrame (rows=timestamps, cols=assets)
        """
        factor = self.get(name)

        # 对每个资产计算因子
        factor_series = {}
        expression = None

        for inst, df in data_dict.items():
            try:
                result_df = factor.compute(df)
                if name in result_df.columns:
                    factor_series[inst] = result_df[name]
                    if expression is None and factor.expression:
                        expression = factor.expression
            except Exception as e:
                print(f"Warning: Factor '{name}' failed for {inst}: {e}")

        if not factor_series:
            raise ValueError(f"Factor '{name}' failed for all instruments")

        # 合并为 Panel DataFrame
        panel_df = pd.DataFrame(factor_series)

        if verbose and expression:
            print(f"[{name}] Formula: {expression}")

        return panel_df

    def compute_panel_many(
        self,
        names: List[str],
        data_dict: Dict[str, pd.DataFrame],
        verbose: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        计算多个因子，返回 Dict[factor_name -> Panel DataFrame].

        Args:
            names: 因子名称列表
            data_dict: Dict[instrument_name -> DataFrame]
            verbose: 是否打印表达式

        Returns:
            Dict[factor_name -> Panel DataFrame]
        """
        result = {}
        for name in names:
            try:
                result[name] = self.compute_panel(name, data_dict, verbose=verbose)
            except Exception as e:
                print(f"Warning: Factor '{name}' failed: {e}")
        return result

    def list_factors(self) -> List[str]:
        """列出所有因子名称"""
        return list(self._factors.keys())

    def list_by_category(self) -> Dict[str, List[str]]:
        """按类别列出因子"""
        result = {}
        for name, factor in self._instances.items():
            cat = factor.category
            if cat not in result:
                result[cat] = []
            result[cat].append(name)
        return result

    def __len__(self):
        return len(self._factors)

    def __contains__(self, name: str):
        return name in self._factors

    def __repr__(self):
        return f"FactorLibrary({len(self)} factors: {list(self._factors.keys())})"


# Global library instance
library = FactorLibrary()


# ============================================================================
# Momentum Factors
# ============================================================================

@library.register
class RetSkewFactor(FactorBase):
    """收益率偏度因子"""

    name = "ret_skew"
    description = "Return skewness with z-score normalization"
    category = "momentum"
    require = ['Close']

    skew_window: int = 600
    zscore_window: int = 14400
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.skew_window = kwargs.pop('skew_window', 600)
        self.zscore_window = kwargs.pop('zscore_window', 14400)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)
        skew = ops.ts_skew(ret, self.skew_window)
        zscore = ops.ts_zscore(skew, self.zscore_window)
        clipped = ops.clip(zscore, -3, 3)
        return ops.ts_ema(clipped, self.ema_alpha)


@library.register
class MomentumFactor(FactorBase):
    """简单动量因子"""

    name = "momentum"
    description = "Rolling mean of returns with EMA"
    category = "momentum"
    require = ['Close']

    window: int = 20
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 20)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)
        mean_ret = ops.ts_mean(ret, self.window)
        return ops.ts_ema(mean_ret, self.ema_alpha)


@library.register
class MomentumReversalFactor(FactorBase):
    """均值回归动量因子"""

    name = "mom_reversal"
    description = "Mean reversion momentum factor"
    category = "momentum"
    require = ['Close']

    window: int = 14400
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 14400)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)
        zscore = ops.ts_zscore(ret, self.window)
        clipped = ops.clip(zscore, -3, 3)
        return -ops.ts_ema(clipped, self.ema_alpha)


@library.register
class MomentumMAFactor(FactorBase):
    """动量均线因子"""

    name = "momentum_ma"
    description = "Close price momentum based on MA ratio"
    category = "momentum"
    require = ['Close']

    fast_window: int = 3
    slow_window: int = 60
    zscore_window: int = 1440
    ema_alpha: float = 2

    def __init__(self, **kwargs):
        self.fast_window = kwargs.pop('fast_window', 3)
        self.slow_window = kwargs.pop('slow_window', 60)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ma_fast = ops.ts_mean(close, self.fast_window)
        ma_slow = ops.ts_mean(close, self.slow_window)
        momentum = ops.divide(ma_fast, ma_slow) - 1
        momentum = ops.fill_na(momentum)
        momentum = ops.clip(ops.ts_zscore(momentum, self.zscore_window), -3, 3)
        return -ops.ts_ema(momentum, self.ema_alpha)


# ============================================================================
# Volatility Factors
# ============================================================================

@library.register
class VolatilityFactor(FactorBase):
    """收益率波动率因子"""

    name = "volatility"
    description = "Rolling standard deviation of returns"
    category = "volatility"
    require = ['Close']

    window: int = 60

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 60)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)
        return ops.ts_std(ret, self.window)


@library.register
class ATRFactor(FactorBase):
    """平均真实波幅因子"""

    name = "atr"
    description = "Average True Range"
    category = "volatility"
    require = ['High', 'Low', 'Close']

    window: int = 14

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 14)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        high = ops.col(df, 'High')
        low = ops.col(df, 'Low')
        close = ops.col(df, 'Close')
        return ops.ts_atr(high, low, close, self.window)


@library.register
class RealizedVolFactor(FactorBase):
    """已实现波动率因子"""

    name = "realized_vol"
    description = "Annualized realized volatility"
    category = "volatility"
    require = ['Close']

    window: int = 1440

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 1440)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)
        realized_vol = ops.ts_realized_vol(ret, self.window)
        return realized_vol * np.sqrt(525600)  # 年化


# ============================================================================
# Volume Factors
# ============================================================================

@library.register
class BuySellRatioFactor(FactorBase):
    """买卖比例因子"""

    name = "buy2sell_ratio"
    description = "Buy/Sell volume ratio"
    category = "volume"
    require = ['TakerBuyQuoteAssetVolume', 'TakerSellQuoteAssetVolume']

    window: int = 10
    threshold: float = 2.0
    extend_bars: int = 10

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 10)
        self.threshold = kwargs.pop('threshold', 2.0)
        self.extend_bars = kwargs.pop('extend_bars', 10)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        buy = ops.col(df, 'TakerBuyQuoteAssetVolume')
        sell = ops.col(df, 'TakerSellQuoteAssetVolume')

        buy_sum = ops.ts_sum(buy, self.window)
        sell_sum = ops.ts_sum(sell, self.window)

        ratio = ops.divide(buy_sum, sell_sum)
        ratio = ops.fill_na(ratio)

        # 当 sell_sum == 0 或 ratio 是 NaN 时，signal = 0；否则当 ratio > threshold 时 signal = 1
        is_invalid = ops.or_(ops.equal(sell_sum, 0), ops.is_nan(ratio))
        is_strong_buy = ops.greater(ratio, self.threshold)
        signal = ops.where(is_invalid, 0, ops.where(is_strong_buy, 1, 0))
        signal = ops.astype(signal, np.float64)

        return ops.forward_fill_signal(signal, self.extend_bars)


@library.register
class VolumeAnomalyFactor(FactorBase):
    """成交量异常因子"""

    name = "volume_anomaly"
    description = "Unusual volume detection"
    category = "volume"
    require = ['Volume']

    window: int = 30
    std_threshold: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 30)
        self.std_threshold = kwargs.pop('std_threshold', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        volume = ops.col(df, 'Volume')
        vol_zscore = ops.ts_zscore(volume, self.window)
        anomaly = ops.greater(ops.abs(vol_zscore), self.std_threshold)
        return ops.astype(anomaly, int)


# ============================================================================
# Price Factors
# ============================================================================

@library.register
class PriceStableFactor(FactorBase):
    """价格稳定因子"""

    name = "price_stable"
    description = "Price consolidation detection"
    category = "price"
    require = ['High', 'Low', 'Close']

    window: int = 5
    threshold: float = 0.001

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 5)
        self.threshold = kwargs.pop('threshold', 0.001)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        high = ops.col(df, 'High')
        low = ops.col(df, 'Low')
        close = ops.col(df, 'Close')
        range_pct = ops.divide(high - low, close)
        rolling_range = ops.ts_mean(range_pct, self.window)
        stable = ops.less(rolling_range, self.threshold)
        return ops.astype(stable, int)


@library.register
class PriceRangeFactor(FactorBase):
    """价格振幅因子"""

    name = "price_range"
    description = "Price range percentage"
    category = "price"
    require = ['High', 'Low', 'Close']

    def factor_func(self, df, ops):
        high = ops.col(df, 'High')
        low = ops.col(df, 'Low')
        close = ops.col(df, 'Close')
        return ops.divide(high - low, close)


@library.register
class PricePositionFactor(FactorBase):
    """价格位置因子"""

    name = "price_position"
    description = "Close position within high-low range"
    category = "price"
    require = ['High', 'Low', 'Close']

    def factor_func(self, df, ops):
        high = ops.col(df, 'High')
        low = ops.col(df, 'Low')
        close = ops.col(df, 'Close')
        range_val = high - low
        position = ops.divide(close - low, range_val)
        return ops.fill_na(position, 0.5)


# ============================================================================
# Trend Factors
# ============================================================================

@library.register
class TrendStrengthFactor(FactorBase):
    """趋势强度因子"""

    name = "trend_strength"
    description = "Trend strength (slope / std)"
    category = "trend"
    require = ['Close']

    window: int = 60

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 60)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        slope = ops.ts_slope(close, self.window)
        std = ops.ts_std(close, self.window)
        trend = ops.divide(slope, std)
        return ops.fill_na(trend)


@library.register
class ATRTrendFactor(FactorBase):
    """ATR通道突破因子"""

    name = "atr_trend"
    description = "ATR channel breakout signal"
    category = "trend"
    require = ['High', 'Low', 'Close']

    window: int = 14
    multiplier: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 14)
        self.multiplier = kwargs.pop('multiplier', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        high = ops.col(df, 'High')
        low = ops.col(df, 'Low')
        close = ops.col(df, 'Close')

        atr = ops.ts_atr(high, low, close, self.window)
        ma = ops.ts_mean(close, self.window)

        upper = ma + atr * self.multiplier
        lower = ma - atr * self.multiplier

        # close > upper -> 1, close < lower -> -1, else -> 0
        signal = ops.where(ops.greater(close, upper), 1,
                          ops.where(ops.less(close, lower), -1, 0))
        return signal


# ============================================================================
# Anomaly Factors
# ============================================================================

@library.register
class TradeCountAnomalyFactor(FactorBase):
    """交易笔数异常因子"""

    name = "trade_count_anomaly"
    description = "Trade count anomaly with zscore"
    category = "anomaly"
    require = ['NumberOfTrades']

    window: int = 30
    zscore_window: int = 1440
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 30)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        tc = ops.col(df, 'NumberOfTrades')
        tc_mean = ops.ts_mean(tc, self.window)
        tc_std = ops.ts_std(tc, self.window)

        # tc > mean + 2*std -> anomaly = 1, else 0
        threshold = tc_mean + tc_std * 2
        anomaly = ops.greater(tc, threshold)
        anomaly = ops.astype(anomaly, np.int8)

        zscore = ops.ts_zscore(anomaly, self.zscore_window)
        clipped = ops.clip(zscore, -1, 1)
        return ops.ts_ema(clipped, self.ema_alpha)


@library.register
class TradeValueAnomalyFactor(FactorBase):
    """交易额异常因子"""

    name = "trade_value_anomaly"
    description = "Trade value anomaly with zscore"
    category = "anomaly"
    require = ['Close', 'Volume']

    window: int = 30
    zscore_window: int = 1440
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.window = kwargs.pop('window', 30)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        volume = ops.col(df, 'Volume')
        tv = close * volume

        tv_mean = ops.ts_mean(tv, self.window)
        tv_std = ops.ts_std(tv, self.window)

        # tv > mean + 3*std -> anomaly = 1, else 0
        threshold = tv_mean + tv_std * 3
        anomaly = ops.greater(tv, threshold)
        anomaly = ops.astype(anomaly, np.int8)

        zscore = ops.ts_zscore(anomaly, self.zscore_window)
        clipped = ops.clip(zscore, -1, 1)
        return ops.ts_ema(clipped, self.ema_alpha)


@library.register
class VolumeRatioFactor(FactorBase):
    """成交量比率因子"""

    name = "volume_ratio"
    description = "Relative volume ratio"
    category = "anomaly"
    require = ['NumberOfTrades']

    mean_window: int = 60
    zscore_window: int = 1440
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.mean_window = kwargs.pop('mean_window', 60)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        tc = ops.col(df, 'NumberOfTrades')
        tc_mean = ops.ts_mean(tc, self.mean_window)
        ratio = -ops.divide(tc, tc_mean)
        ratio = ops.fill_na(ratio)
        zscore = ops.ts_zscore(ratio, self.zscore_window)
        clipped = ops.clip(zscore, -1, 1)
        return ops.ts_ema(clipped, self.ema_alpha)


@library.register
class MoneyRatioFactor(FactorBase):
    """资金流比率因子"""

    name = "money_ratio"
    description = "Relative money flow ratio"
    category = "anomaly"
    require = ['Close', 'Volume']

    mean_window: int = 60
    zscore_window: int = 1440
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.mean_window = kwargs.pop('mean_window', 60)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        volume = ops.col(df, 'Volume')
        tv = close * volume
        tv_mean = ops.ts_mean(tv, self.mean_window)
        ratio = -ops.divide(tv, tv_mean)
        ratio = ops.fill_na(ratio)
        zscore = ops.ts_zscore(ratio, self.zscore_window)
        clipped = ops.clip(zscore, -1, 1)
        return ops.ts_ema(clipped, self.ema_alpha)


# ============================================================================
# Custom Factors
# ============================================================================

@library.register
class LBRMomentum5mFactor(FactorBase):
    """大单买入比例动量因子（需要tick数据合并）"""

    name = "lbr_mom_5m"
    description = "Large order momentum with 5-min return"
    category = "custom"
    require = ['large_buy_ratio', 'Close']

    zscore_window: int = 1440
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        if 'large_buy_ratio' not in df.columns:
            raise ValueError("Missing 'large_buy_ratio' column. Merge tick factors first.")

        close = ops.col(df, 'Close')
        ret = ops.returns(close, 1)
        ret = ops.fill_na(ret)

        lbr = ops.col(df, 'large_buy_ratio')
        lbr_filter = ops.filter_range(lbr, 0.4, 1)

        ret_5m = ops.ts_sum(ret, 5)
        factor = ops.sign(lbr_filter) * ret_5m
        zscore = ops.ts_zscore(factor, self.zscore_window)
        clipped = ops.clip(zscore, -3, 3)
        result = ops.ts_ema(clipped, self.ema_alpha)
        return result


@library.register
class MARatioMomentumFactor(FactorBase):
    """均线比率动量因子"""

    name = "ma_ratio_momentum"
    description = "MA ratio momentum with zscore and filter_range"
    category = "momentum"
    require = ['Close']

    fast_window: int = 3
    slow_window: int = 60
    zscore_window: int = 1440
    filter_min: float = -1.5
    filter_max: float = 1.5
    clip_min: float = -1
    clip_max: float = 1
    ema_alpha: float = 2.0

    def __init__(self, **kwargs):
        self.fast_window = kwargs.pop('fast_window', 3)
        self.slow_window = kwargs.pop('slow_window', 60)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.filter_min = kwargs.pop('filter_min', -1.5)
        self.filter_max = kwargs.pop('filter_max', 1.5)
        self.clip_min = kwargs.pop('clip_min', -1)
        self.clip_max = kwargs.pop('clip_max', 1)
        self.ema_alpha = kwargs.pop('ema_alpha', 2.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')
        ma_fast = ops.ts_mean(close, self.fast_window)
        ma_slow = ops.ts_mean(close, self.slow_window)
        momentum = ops.divide(ma_fast, ma_slow) - 1
        momentum = ops.fill_na(momentum, 0)
        zscore = ops.ts_zscore(momentum, self.zscore_window)
        filtered = ops.filter_range(zscore, self.filter_min, self.filter_max)
        clipped = ops.clip(filtered, self.clip_min, self.clip_max)
        result = ops.ts_ema(clipped, self.ema_alpha)
        return -result


@library.register
class MomentumResidueFactor(FactorBase):
    """动量残差因子"""

    name = "mom_residue"
    description = "Momentum residue with double zscore and EMA smoothing"
    category = "momentum"
    require = ['Close']

    fast_window: int = 3
    slow_window: int = 60
    zscore_window: int = 1440
    residue_window: int = 3
    ema_alpha: float = 10.0
    clip_val: float = 3.0

    def __init__(self, **kwargs):
        self.fast_window = kwargs.pop('fast_window', 3)
        self.slow_window = kwargs.pop('slow_window', 60)
        self.zscore_window = kwargs.pop('zscore_window', 1440)
        self.residue_window = kwargs.pop('residue_window', 3)
        self.ema_alpha = kwargs.pop('ema_alpha', 10.0)
        self.clip_val = kwargs.pop('clip_val', 3.0)
        super().__init__(**kwargs)

    def factor_func(self, df, ops):
        close = ops.col(df, 'Close')

        # 计算 close momentum (ma_fast / ma_slow - 1)
        ma_fast = ops.ts_mean(close, self.fast_window)
        ma_slow = ops.ts_mean(close, self.slow_window)
        close_mom = ops.divide(ma_fast, ma_slow) - 1
        close_mom = ops.fill_na(close_mom, 0)

        # zscore close_mom
        close_mom_zscore = ops.ts_zscore(close_mom, self.zscore_window)

        # 计算残差: close_mom_zscore - rolling_mean(close_mom_zscore, residue_window)
        mom_residue = close_mom_zscore - ops.ts_mean(close_mom_zscore, self.residue_window)

        # zscore 残差
        mom_residue = ops.ts_zscore(mom_residue, self.zscore_window)

        # EMA 平滑
        mom_residue = ops.ts_ema(mom_residue, self.ema_alpha)

        # clip
        mom_residue = ops.clip(mom_residue, -self.clip_val, self.clip_val)

        return -mom_residue
