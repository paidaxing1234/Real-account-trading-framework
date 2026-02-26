# Alpha 077+094-080 截面动量策略

## 策略概述

基于三因子组合的加密货币永续合约截面动量策略，采用事件驱动架构实现增量计算。

## 因子定义

```
al = alpha_077 + alpha_094 - alpha_080
```


| 因子      | 公式                           | 含义                             |
| --------- | ------------------------------ | -------------------------------- |
| alpha_077 | (Close - LL20) / (HH20 - LL20) | 收盘价在20周期价格区间中的位置   |
| alpha_094 | (VWAP - MA20) / STD20          | VWAP相对20周期均线的标准化偏离   |
| alpha_080 | (HH20 - Close) / (HH20 - LL20) | 收盘价距离20周期最高价的相对距离 |

## 执行时序

```
时刻 T (收盘)          时刻 T+1 (开盘)        时刻 T+2 (开盘)
    |                      |                      |
    v                      v                      v
+--------+            +--------+            +--------+
| 计算   |    --->    | 执行   |    --->    | 结算   |
| 信号   |            | 交易   |            | 收益   |
+--------+            +--------+            +--------+

收益计算: Return = Open[T+2] / Open[T+1] - 1
```

## 策略参数


| 参数             | 默认值     | 说明                              |
| ---------------- | ---------- | --------------------------------- |
| liq_quantile     | 0.1        | 流动性过滤，保留成交额前10%的标的 |
| liquidity_period | 60         | 流动性滚动均值窗口（60个8h周期）  |
| long_short_ratio | 2          | 多空分组比例，各取50%             |
| direction        | descending | 因子方向，因子值高做多            |
| min_bars         | 120        | 开始交易所需的最小K线数量         |
| commission_rate  | 0.0005     | 交易费率（5bp）                   |

## 仓位权重

- 多头总权重: 1.0 (100%)
- 空头总权重: -1.0 (-100%)
- 净敞口: 0 (市场中性)
- 杠杆: 2倍

## 文件结构

```
3_mom_factor_cs/
├── alpha_077_094_080_strategy.py   # 策略核心类（增量计算）
├── event_driven_backtest.py        # 事件驱动回测框架
├── README.md                       # 本文档
└── *.parquet                       # K线数据文件
```

## 使用示例

### 回测运行

```python
from alpha_077_094_080_strategy import Alpha077_094_080Strategy
from event_driven_backtest import EventDrivenBacktest, resample_1h_to_8h
import pandas as pd

# 加载数据
df_1h = pd.read_parquet("./20200101-20260131-1h-binance-swap.parquet")
df_8h = resample_1h_to_8h(df_1h)

# 初始化策略
strategy = Alpha077_094_080Strategy(
    liq_quantile=0.1,
    liquidity_period=60,
    long_short_ratio=2,
    direction='descending',
    min_bars=120
)

# 运行回测
backtest = EventDrivenBacktest(
    strategy=strategy,
    initial_capital=1_000_000,
    commission_rate=0.0005
)

result = backtest.run(df_8h, start_date='2021-01-01')
backtest.print_performance()
backtest.plot_curve()
```

### 实盘调用

```python
from alpha_077_094_080_strategy import Alpha077_094_080Strategy, Bar

# 初始化策略（只需初始化一次）
strategy = Alpha077_094_080Strategy(
    liq_quantile=0.1,
    liquidity_period=60,
    long_short_ratio=2,
    direction='descending',
    min_bars=120
)

# 每8小时触发一次
def on_8h_bar(bars: list):
    """
    Args:
        bars: 当前时间截面所有标的的K线数据
              [Bar(time, ticker, open, high, low, close, volume, amount), ...]

    Returns:
        目标仓位 {ticker: weight}，正数做多，负数做空
    """
    positions = strategy.on_time_event(bars)
    return positions
```

## 核心特性

1. **增量计算**: 每次只计算最新时点的仓位，不重复计算历史数据
2. **状态管理**: 内部维护每个标的的历史数据，支持断点续算
3. **截面标准化**: 对因子值进行截面Z-score标准化
4. **流动性过滤**: 基于成交额滚动均值筛选流动性最好的标的
5. **延迟执行**: 信号T时刻产生，T+1时刻执行，模拟实盘延迟

## 注意事项

1. 数据频率必须为8小时，使用其他频率需先重采样
2. 策略需要至少120根K线的预热期才能开始生成信号
3. 流动性过滤基于成交额滚动均值，需要足够的历史数据
4. 回测结果与实盘可能存在差异，需关注滑点和流动性冲击
