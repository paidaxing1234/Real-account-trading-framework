# -*- coding: utf-8 -*-
"""
5动量因子截面策略 (Five Momentum Factor Strategy)

实盘接口:
    strategy = FiveMomFactorStrategy(...)
    signal = strategy.on_bar(df_8h_klines)  # 传入8h K线数据
    # signal = {'long': ['BTC', 'ETH', ...], 'short': ['DOGE', ...]}

因子定义:
    al = alpha_077 + alpha_078 + alpha_094 + alpha_007 - alpha_080

其中:
    alpha_077: (Close - LL20) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的位置
    alpha_078: (Close - LL60) / (HH60 - LL60)  -- 收盘价在60周期价格区间中的位置
    alpha_094: (VWAP - MA20) / STD20           -- VWAP相对20周期均线的标准化偏离
    alpha_007: sum_ret_20 / std_ret_60         -- 风险调整动量
    alpha_080: (HH20 - Close) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的反向位置

核心特性:
    - 增量计算: 每次只计算最新时点的仓位，不重复计算历史
    - 状态管理: 内部维护每个标的的历史数据状态
    - 截面标准化: 对因子值进行截面Z-score标准化
    - 流动性过滤: 基于成交额滚动均值筛选流动性最好的标的
    - 输出格式: {'long': [ticker_list], 'short': [ticker_list]}
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Set
from dataclasses import dataclass


@dataclass
class Bar:
    """
    K线数据结构

    Attributes:
        time: K线时间戳
        ticker: 标的代码
        open: 开盘价
        high: 最高价
        low: 最低价
        close: 收盘价
        volume: 成交量
        amount: 成交额
    """
    time: pd.Timestamp
    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class CircularBuffer:
    """
    环形缓冲区

    用于高效存储固定长度的滚动窗口数据，避免频繁的内存分配和数据移动。
    当缓冲区满时，新数据会覆盖最旧的数据。
    """

    def __init__(self, size: int):
        self.size = size
        self.buffer = np.full(size, np.nan, dtype=np.float64)
        self.idx = 0
        self.count = 0

    def append(self, value: float):
        self.buffer[self.idx] = value
        self.idx = (self.idx + 1) % self.size
        self.count = min(self.count + 1, self.size)

    def get_all(self) -> np.ndarray:
        """获取所有有效数据（按时间顺序）"""
        if self.count < self.size:
            return self.buffer[:self.count].copy()
        # 环形缓冲区满时���需要重新排列
        result = np.empty(self.size, dtype=np.float64)
        result[:self.size - self.idx] = self.buffer[self.idx:]
        result[self.size - self.idx:] = self.buffer[:self.idx]
        return result

    def get_latest(self, n: int = 1) -> np.ndarray:
        """获取最近n个数据"""
        if n > self.count:
            n = self.count
        if n == 0:
            return np.array([], dtype=np.float64)

        all_data = self.get_all()
        return all_data[-n:]

    def is_full(self) -> bool:
        return self.count >= self.size


class TickerState:
    """
    单个标的的状态管理器

    维护该标的的历史K线数据，用于计算滚动指标。
    """

    def __init__(self, lookback: int = 120):
        """
        Args:
            lookback: 回溯周期，用于计算60周期指标需要至少60根K线
        """
        self.lookback = lookback
        self.bar_count = 0
        self.last_time = None

        # 最新K线数据
        self.latest_close = None
        self.latest_high = None
        self.latest_low = None
        self.latest_volume = None
        self.latest_amount = None
        self.latest_open = None

        # 滚动窗口历史数据
        self.close_history = CircularBuffer(lookback)
        self.high_history = CircularBuffer(lookback)
        self.low_history = CircularBuffer(lookback)
        self.amount_history = CircularBuffer(lookback)
        self.ret_history = CircularBuffer(lookback)

    def update(self, bar: Bar) -> bool:
        """
        更新状态

        Args:
            bar: 新的K线数据

        Returns:
            bool: 是否有足够数据计算因子（至少min_bars根K线）
        """
        # 计算收益率（需要前一个close）
        ret = np.nan
        if self.latest_close is not None and self.latest_close > 0:
            ret = (bar.close / self.latest_close) - 1

        # 更新最新值
        self.latest_close = bar.close
        self.latest_high = bar.high
        self.latest_low = bar.low
        self.latest_volume = bar.volume
        self.latest_amount = bar.amount
        self.latest_open = bar.open
        self.last_time = bar.time

        # 更新滚动窗口
        self.close_history.append(bar.close)
        self.high_history.append(bar.high)
        self.low_history.append(bar.low)
        self.amount_history.append(bar.amount)
        if not np.isnan(ret):
            self.ret_history.append(ret)

        self.bar_count += 1
        return self.bar_count >= 60  # 至少60根K线才能计算因子

    def get_vwap(self) -> float:
        """获取当前K线的VWAP"""
        if self.latest_volume and self.latest_volume > 0:
            return self.latest_amount / self.latest_volume
        return self.latest_close

    def get_rolling_mean(self, data: np.ndarray, window: int) -> Optional[float]:
        """计算滚动均值"""
        if len(data) < window:
            return None
        return np.nanmean(data[-window:])

    def get_rolling_std(self, data: np.ndarray, window: int) -> Optional[float]:
        """计算滚动标准差"""
        if len(data) < window:
            return None
        valid = data[-window:]
        valid = valid[~np.isnan(valid)]
        if len(valid) < 2:
            return None
        return np.std(valid, ddof=1)

    def get_rolling_max(self, data: np.ndarray, window: int) -> Optional[float]:
        """计算滚动最大值"""
        if len(data) < window:
            return None
        return np.nanmax(data[-window:])

    def get_rolling_min(self, data: np.ndarray, window: int) -> Optional[float]:
        """计算滚动最小值"""
        if len(data) < window:
            return None
        return np.nanmin(data[-window:])

    def get_rolling_sum(self, data: np.ndarray, window: int) -> Optional[float]:
        """计算滚动求和"""
        if len(data) < window:
            return None
        return np.nansum(data[-window:])

    def get_liquidity_ma(self, window: int) -> Optional[float]:
        """获取流动性滚动均值"""
        data = self.amount_history.get_all()
        if len(data) < window:
            window = len(data)
        if window == 0:
            return None
        return np.nanmean(data[-window:])


class FiveMomFactorStrategy:
    """
    5动量因子截面策略

    实盘调用示例:
        strategy = FiveMomFactorStrategy()

        # 每8小时调用一次
        signal = strategy.on_bar(df_8h_klines)

        # signal = {'long': ['BTCUSDT', 'ETHUSDT', ...], 'short': ['DOGEUSDT', ...]}
    """

    def __init__(
        self,
        liq_quantile: float = 0.2,
        liquidity_period: int = 60,
        long_short_ratio: int = 5,
        direction: str = 'descending',
        min_bars: int = 60,
        lookback: int = 120
    ):
        """
        初始化策略

        Args:
            liq_quantile: 流动性过���分位数，0.2表示保留流动性前20%的标的
            liquidity_period: 流动性滚动均值窗口，默认60周期
            long_short_ratio: 多空分组比例，5表示做多前20%、做空后20%
            direction: 因子方向，'descending'表示因子值高的做多
            min_bars: 开始交易所需的最小K线数量，默认60根
            lookback: 历史数据回溯周期，默认120根
        """
        self.liq_quantile = liq_quantile
        self.liq_period = liquidity_period
        self.ls_ratio = long_short_ratio
        self.direction = direction
        self.min_bars = min_bars
        self.lookback = lookback

        # 内部状态：每个标的的历史数据
        self.ticker_states: Dict[str, TickerState] = {}
        self.current_time = None

    def _get_or_create_state(self, ticker: str) -> TickerState:
        """获取或创建标的状态"""
        if ticker not in self.ticker_states:
            self.ticker_states[ticker] = TickerState(lookback=self.lookback)
        return self.ticker_states[ticker]

    def _compute_alpha_077(self, state: TickerState) -> Optional[float]:
        """(Close - LL20) / (HH20 - LL20)"""
        low_data = state.low_history.get_all()
        high_data = state.high_history.get_all()

        ll20 = state.get_rolling_min(low_data, 20)
        hh20 = state.get_rolling_max(high_data, 20)

        if ll20 is None or hh20 is None:
            return None
        rng20 = hh20 - ll20
        if rng20 == 0:
            return None
        return (state.latest_close - ll20) / rng20

    def _compute_alpha_078(self, state: TickerState) -> Optional[float]:
        """(Close - LL60) / (HH60 - LL60)"""
        low_data = state.low_history.get_all()
        high_data = state.high_history.get_all()

        ll60 = state.get_rolling_min(low_data, 60)
        hh60 = state.get_rolling_max(high_data, 60)

        if ll60 is None or hh60 is None:
            return None
        rng60 = hh60 - ll60
        if rng60 == 0:
            return None
        return (state.latest_close - ll60) / rng60

    def _compute_alpha_094(self, state: TickerState) -> Optional[float]:
        """(VWAP - MA20) / STD20"""
        close_data = state.close_history.get_all()

        vwap = state.get_vwap()
        ma20 = state.get_rolling_mean(close_data, 20)
        std_c20 = state.get_rolling_std(close_data, 20)

        if vwap is None or ma20 is None or std_c20 is None or std_c20 == 0:
            return None
        return (vwap - ma20) / std_c20

    def _compute_alpha_007(self, state: TickerState) -> Optional[float]:
        """sum_ret_20 / std_ret_60"""
        ret_data = state.ret_history.get_all()

        sum_ret_20 = state.get_rolling_sum(ret_data, 20)
        std_ret_60 = state.get_rolling_std(ret_data, 60)

        if sum_ret_20 is None or std_ret_60 is None or std_ret_60 == 0:
            return None
        return sum_ret_20 / std_ret_60

    def _compute_alpha_080(self, state: TickerState) -> Optional[float]:
        """(HH20 - Close) / (HH20 - LL20)"""
        low_data = state.low_history.get_all()
        high_data = state.high_history.get_all()

        ll20 = state.get_rolling_min(low_data, 20)
        hh20 = state.get_rolling_max(high_data, 20)

        if ll20 is None or hh20 is None:
            return None
        rng20 = hh20 - ll20
        if rng20 == 0:
            return None
        return (hh20 - state.latest_close) / rng20

    def _zscore(self, values: Dict[str, float]) -> Dict[str, float]:
        """截面Z-score标准化"""
        valid_values = {k: v for k, v in values.items()
                       if v is not None and np.isfinite(v)}
        if len(valid_values) == 0:
            return values

        vals = np.array(list(valid_values.values()))
        mean_val = np.mean(vals)
        std_val = np.std(vals)

        if std_val == 0 or np.isnan(std_val):
            return {k: (v - mean_val if v is not None and np.isfinite(v) else None)
                    for k, v in values.items()}

        result = {}
        for k, v in values.items():
            if v is not None and np.isfinite(v):
                result[k] = (v - mean_val) / std_val
            else:
                result[k] = None
        return result

    def _compute_long_short_lists(self, factors: Dict[str, float]) -> Optional[Dict[str, List[str]]]:
        """根据因子值计算多空票池"""
        valid_factors = {k: v for k, v in factors.items()
                        if v is not None and np.isfinite(v)}

        if len(valid_factors) < 2 * self.ls_ratio:
            return None

        is_descending = (self.direction == 'descending')
        sorted_tickers = sorted(valid_factors.keys(),
                               key=lambda x: valid_factors[x],
                               reverse=is_descending)

        n_total = len(sorted_tickers)
        n_pos = int(n_total / self.ls_ratio)

        if n_pos < 1:
            return None

        long_tickers = sorted_tickers[:n_pos]
        short_tickers = sorted_tickers[-n_pos:]

        return {'long': long_tickers, 'short': short_tickers}

    def on_bar(self, df: pd.DataFrame) -> Optional[Dict[str, List[str]]]:
        """
        实盘调用接口：传入当前时刻的K线数据，返回多空票池

        Args:
            df: K线数据DataFrame，必须包含以下列:
                - Time: 时间戳
                - Ticker: 标的代码
                - Open, High, Low, Close: OHLC价格
                - Volume: 成交量
                - Amount: 成交额

        Returns:
            {'long': [ticker_list], 'short': [ticker_list]} 或 None
        """
        if df is None or len(df) == 0:
            return None

        # 获取当前时间
        current_time = pd.to_datetime(df['Time'].iloc[0])
        self.current_time = current_time

        # 更新所有标的的状态
        ready_tickers = set()
        for _, row in df.iterrows():
            bar = Bar(
                time=pd.Timestamp(row['Time']),
                ticker=row['Ticker'],
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=float(row['Volume']),
                amount=float(row['Amount'])
            )

            state = self._get_or_create_state(bar.ticker)
            is_ready = state.update(bar)
            if is_ready:
                ready_tickers.add(bar.ticker)

        if len(ready_tickers) < 2 * self.ls_ratio:
            return None

        # 计算各标的的5个因子值
        alpha_077_vals = {}
        alpha_078_vals = {}
        alpha_094_vals = {}
        alpha_007_vals = {}
        alpha_080_vals = {}
        liquidity_vals = {}

        for ticker in ready_tickers:
            state = self.ticker_states[ticker]
            alpha_077_vals[ticker] = self._compute_alpha_077(state)
            alpha_078_vals[ticker] = self._compute_alpha_078(state)
            alpha_094_vals[ticker] = self._compute_alpha_094(state)
            alpha_007_vals[ticker] = self._compute_alpha_007(state)
            alpha_080_vals[ticker] = self._compute_alpha_080(state)
            liquidity_vals[ticker] = state.get_liquidity_ma(self.liq_period)

        # 截面Z-score标准化
        alpha_077_z = self._zscore(alpha_077_vals)
        alpha_078_z = self._zscore(alpha_078_vals)
        alpha_094_z = self._zscore(alpha_094_vals)
        alpha_007_z = self._zscore(alpha_007_vals)
        alpha_080_z = self._zscore(alpha_080_vals)

        # 计算组合因子: al = alpha_077 + alpha_078 + alpha_094 + alpha_007 - alpha_080
        al_values = {}
        for ticker in ready_tickers:
            a077 = alpha_077_z.get(ticker)
            a078 = alpha_078_z.get(ticker)
            a094 = alpha_094_z.get(ticker)
            a007 = alpha_007_z.get(ticker)
            a080 = alpha_080_z.get(ticker)

            if any(v is None for v in [a077, a078, a094, a007, a080]):
                continue
            if any(not np.isfinite(v) for v in [a077, a078, a094, a007, a080]):
                continue

            al_values[ticker] = a077 + a078 + a094 + a007 - a080

        # 流动性过滤
        if liquidity_vals:
            sorted_by_liq = sorted(
                liquidity_vals.items(),
                key=lambda x: x[1] if x[1] is not None else 0,
                reverse=True
            )
            n_keep = max(1, int(len(sorted_by_liq) * self.liq_quantile))
            valid_tickers = set(k for k, _ in sorted_by_liq[:n_keep])
            al_values = {k: v for k, v in al_values.items() if k in valid_tickers}

        # 计算多空票池
        result = self._compute_long_short_lists(al_values)
        return result

    def reset(self):
        """重置策略状态（用于回测）"""
        self.ticker_states = {}
        self.current_time = None

    def get_state_summary(self) -> Dict:
        """获取策略状态摘要（用于调试）"""
        return {
            'current_time': self.current_time,
            'num_tickers': len(self.ticker_states),
            'tickers_with_data': [t for t, s in self.ticker_states.items()
                                  if s.bar_count >= self.min_bars]
        }


# 保持向后兼容
Alpha5FactorStrategy = FiveMomFactorStrategy
