# -*- coding: utf-8 -*-
"""
事件驱动回测引擎 - 订单管理模式

核心特性:
    - 模拟实盘推进: 按时间戳逐个推送K线数据
    - 订单管理: 使用 Order 和 Position 对象管理交易
    - 票池进出控制: 只在进出票池时开平仓
    - 仓位漂移: 在票池内的持仓允许随价格自然漂移
    - 资金费率: 支持加载Binance资金费率数据，自动扣除

执行时序:
    - T时刻收盘: 策略根据T时刻数据计算信号
    - T+1时刻开盘: 执行交易（仅进出票池的标的）
    - 收益计算: 基于持仓市值变化 - 资金费率
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from five_mom_factor_strategy import FiveMomFactorStrategy


# ============================================================
# 订单与持仓数据结构
# ============================================================

class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"      # 买入开多 / 买入平空
    SELL = "SELL"    # 卖出平多 / 卖出开空


class OrderType(Enum):
    """订单类型"""
    OPEN_LONG = "OPEN_LONG"     # 开多
    CLOSE_LONG = "CLOSE_LONG"   # 平多
    OPEN_SHORT = "OPEN_SHORT"   # 开空
    CLOSE_SHORT = "CLOSE_SHORT" # 平空


@dataclass
class Order:
    """订单对象"""
    order_id: str
    ticker: str
    order_type: OrderType
    quantity: float       # 数量（份额）
    price: float          # 执行价格
    value: float          # 订单价值
    timestamp: pd.Timestamp
    filled: bool = False


@dataclass
class Position:
    """持仓对象"""
    ticker: str
    side: str             # 'long' / 'short'
    shares: float         # 持仓份额
    entry_price: float    # 入场价格
    entry_value: float    # 入场市值
    current_price: float  # 当前价格
    current_value: float  # 当前市值
    unrealized_pnl: float # 未实现盈亏

    def update_price(self, new_price: float):
        """更新价格，计算未实现盈亏"""
        self.current_price = new_price
        self.current_value = self.shares * new_price

        if self.side == 'long':
            self.unrealized_pnl = self.current_value - self.entry_value
        else:  # short
            self.unrealized_pnl = self.entry_value - self.current_value


@dataclass
class Trade:
    """成交记录"""
    trade_id: str
    order_id: str
    ticker: str
    order_type: OrderType
    side: str             # 'long' / 'short'
    quantity: float
    price: float
    value: float
    realized_pnl: float   # 平仓时的已实现盈亏
    commission: float     # 手续费
    timestamp: pd.Timestamp


# ============================================================
# 订单管理器
# ============================================================

class OrderManager:
    """订单管理器 - 负责订单创建、执行、持仓跟踪"""

    def __init__(self, commission_rate: float = 0.0005):
        self.commission_rate = commission_rate
        self.positions: Dict[str, Position] = {}  # ticker -> Position
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.order_counter = 0
        self.trade_counter = 0

    def reset(self):
        """重置状态"""
        self.positions = {}
        self.orders = []
        self.trades = []
        self.order_counter = 0
        self.trade_counter = 0

    def get_long_tickers(self) -> Set[str]:
        """获取当前多头持仓标的"""
        return {t for t, p in self.positions.items() if p.side == 'long'}

    def get_short_tickers(self) -> Set[str]:
        """获取当前空头持仓标的"""
        return {t for t, p in self.positions.items() if p.side == 'short'}

    def get_total_equity(self, cash: float) -> float:
        """计算总权益 = 现金 + 持仓市值(含盈亏)"""
        equity = cash
        for pos in self.positions.values():
            equity += pos.entry_value + pos.unrealized_pnl
        return equity

    def update_positions_price(self, prices: Dict[str, float]):
        """更新所有持仓的价格"""
        for ticker, pos in self.positions.items():
            if ticker in prices:
                pos.update_price(prices[ticker])

    def create_open_order(
        self,
        ticker: str,
        side: str,  # 'long' / 'short'
        value: float,
        price: float,
        timestamp: pd.Timestamp
    ) -> Order:
        """创建开仓订单"""
        self.order_counter += 1
        order_type = OrderType.OPEN_LONG if side == 'long' else OrderType.OPEN_SHORT
        quantity = value / price

        order = Order(
            order_id=f"O{self.order_counter:06d}",
            ticker=ticker,
            order_type=order_type,
            quantity=quantity,
            price=price,
            value=value,
            timestamp=timestamp
        )
        self.orders.append(order)
        return order

    def create_close_order(
        self,
        ticker: str,
        price: float,
        timestamp: pd.Timestamp
    ) -> Optional[Order]:
        """创建平仓订单"""
        if ticker not in self.positions:
            return None

        pos = self.positions[ticker]
        self.order_counter += 1

        order_type = OrderType.CLOSE_LONG if pos.side == 'long' else OrderType.CLOSE_SHORT
        value = pos.shares * price

        order = Order(
            order_id=f"O{self.order_counter:06d}",
            ticker=ticker,
            order_type=order_type,
            quantity=pos.shares,
            price=price,
            value=value,
            timestamp=timestamp
        )
        self.orders.append(order)
        return order

    def execute_order(self, order: Order) -> tuple:
        """
        执行订单，返回 (Trade, cash_delta, commission)
        cash_delta: 对现金的影响 (正数=现金增加，负数=现金减少)
        """
        if order.filled:
            return None, 0.0, 0.0

        self.trade_counter += 1
        commission = order.value * self.commission_rate
        realized_pnl = 0.0
        cash_delta = 0.0

        if order.order_type == OrderType.OPEN_LONG:
            # 开多: 现金减少，建立多头持仓
            pos = Position(
                ticker=order.ticker,
                side='long',
                shares=order.quantity,
                entry_price=order.price,
                entry_value=order.value,
                current_price=order.price,
                current_value=order.value,
                unrealized_pnl=0.0
            )
            self.positions[order.ticker] = pos
            cash_delta = -order.value

        elif order.order_type == OrderType.OPEN_SHORT:
            # 开空: 现金减少（保证金），建立空头持仓
            pos = Position(
                ticker=order.ticker,
                side='short',
                shares=order.quantity,
                entry_price=order.price,
                entry_value=order.value,
                current_price=order.price,
                current_value=order.value,
                unrealized_pnl=0.0
            )
            self.positions[order.ticker] = pos
            cash_delta = -order.value

        elif order.order_type == OrderType.CLOSE_LONG:
            # 平多: 现金增加，计算盈亏
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                realized_pnl = order.value - pos.entry_value
                cash_delta = pos.entry_value + realized_pnl
                del self.positions[order.ticker]

        elif order.order_type == OrderType.CLOSE_SHORT:
            # 平空: 现金增加，计算盈亏
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                realized_pnl = pos.entry_value - order.value
                cash_delta = pos.entry_value + realized_pnl
                del self.positions[order.ticker]

        # 扣除手续费
        cash_delta -= commission

        trade = Trade(
            trade_id=f"T{self.trade_counter:06d}",
            order_id=order.order_id,
            ticker=order.ticker,
            order_type=order.order_type,
            side='long' if order.order_type in [OrderType.OPEN_LONG, OrderType.CLOSE_LONG] else 'short',
            quantity=order.quantity,
            price=order.price,
            value=order.value,
            realized_pnl=realized_pnl,
            commission=commission,
            timestamp=order.timestamp
        )
        self.trades.append(trade)
        order.filled = True

        return trade, cash_delta, commission


# ============================================================
# 事件驱动回测引擎
# ============================================================

class EventDrivenBacktest:
    """
    事件驱动回测引擎 - 订单管理模式

    模拟实盘推进，使用订单管理而非向量化计算
    支持资金费率计算
    """

    def __init__(
        self,
        strategy: FiveMomFactorStrategy,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.0005,
        funding_path: str = None,
        apply_funding: bool = False,
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.funding_path = funding_path
        self.apply_funding = apply_funding

        self.order_manager = OrderManager(commission_rate)
        self.equity_curve: List[dict] = []
        self.total_turnover = 0.0
        self.total_commission = 0.0
        self.total_funding = 0.0

        # 加载资金费率数据
        self.funding_dict = {}  # {ticker: (times_ns_array, rates_array)}
        if self.apply_funding and self.funding_path:
            self._load_funding_data()

    def _load_funding_data(self):
        """加载资金费率数据，预构建numpy数组加速查询"""
        print(f">> 加载资金费率数据: {self.funding_path}")
        df = pd.read_parquet(self.funding_path)
        df['Calc_Time'] = pd.to_datetime(df['Calc_Time'])
        df = df.sort_values(['Ticker', 'Calc_Time'])
        print(f"   资金费率数据量: {len(df)} 条")

        # 预构建字典: {ticker: (times_ns数组, rates数组)} 用于二分查找
        for ticker, group in df.groupby('Ticker'):
            times_ns = group['Calc_Time'].values.astype('int64')
            rates = group['last_funding_rate'].values.astype(np.float64)
            self.funding_dict[ticker] = (times_ns, rates)
        print(f"   构建查询字典: {len(self.funding_dict)} 个标的")

    def _get_funding_rate(self, ticker: str, start_time: pd.Timestamp, end_time: pd.Timestamp) -> float:
        """
        获取指定时间段内的资金费率总和（numpy二分查找）
        资金费率按8小时结算一次，每日 0:00, 8:00, 16:00 UTC
        """
        if ticker not in self.funding_dict:
            return 0.0

        times_ns, rates = self.funding_dict[ticker]
        start_ns = start_time.value
        end_ns = end_time.value

        # 二分查找 (start_time, end_time] 范围内的索引
        left = np.searchsorted(times_ns, start_ns, side='right')
        right = np.searchsorted(times_ns, end_ns, side='right')

        if left >= right:
            return 0.0
        return float(rates[left:right].sum())

    def run(
        self,
        df: pd.DataFrame,
        start_date: str = None,
        end_date: str = None,
    ):
        """
        运行回测

        Args:
            df: K线数据 (需包含 Time, Ticker, Open, High, Low, Close, Volume, Amount)
            start_date: 回测开始日期
            end_date: 回测结束日期
        """
        print("=" * 60)
        print("事件驱动回测开始（订单管理模式）")
        print("=" * 60)

        # 数据准备
        df = df.copy()
        df['Time'] = pd.to_datetime(df['Time'])

        if start_date:
            df = df[df['Time'] >= start_date].copy()
        if end_date:
            df = df[df['Time'] <= end_date].copy()

        df = df.sort_values('Time').reset_index(drop=True)

        # 按时间分组
        grouped = df.groupby('Time')
        times = sorted(grouped.groups.keys())

        print(f"\n数据准备完成: {len(times)} 个时间截面")

        # 重置状态
        self.strategy.reset()
        self.order_manager.reset()
        self.equity_curve = []
        self.total_turnover = 0.0
        self.total_commission = 0.0
        self.total_funding = 0.0

        # 状态变量
        pending_signal = None  # 待执行信号
        cash = self.initial_capital
        prev_time = None  # 上一个时间点（用于计算资金费率）

        # 逐时间截面处理
        for i, time in enumerate(times):
            group_df = grouped.get_group(time)

            # 构建当前价格字典（使用开盘价执行）
            current_prices = {}
            for _, row in group_df.iterrows():
                ticker = row['Ticker']
                current_prices[ticker] = float(row['Open'])

            # 步骤1: 更新持仓市值（仓位漂移）
            self.order_manager.update_positions_price(current_prices)

            # 步骤2: 执行待执行信号
            period_turnover = 0.0
            period_commission = 0.0

            if pending_signal is not None:
                new_long_set = set(pending_signal.get('long', []))
                new_short_set = set(pending_signal.get('short', []))

                current_long_set = self.order_manager.get_long_tickers()
                current_short_set = self.order_manager.get_short_tickers()

                # 计算需要平仓的标的（退出票池）
                to_close_long = current_long_set - new_long_set
                to_close_short = current_short_set - new_short_set

                # 计算需要开仓的标的（进入票池）
                to_open_long = new_long_set - current_long_set
                to_open_short = new_short_set - current_short_set

                # 执行平仓订单
                for ticker in to_close_long | to_close_short:
                    if ticker in current_prices:
                        order = self.order_manager.create_close_order(
                            ticker=ticker,
                            price=current_prices[ticker],
                            timestamp=time
                        )
                        if order:
                            trade, cash_delta, commission = self.order_manager.execute_order(order)
                            cash += cash_delta
                            period_turnover += order.value
                            period_commission += commission

                # 计算新开仓的资金���配
                n_new_long = len(to_open_long)
                n_new_short = len(to_open_short)
                n_new_positions = n_new_long + n_new_short

                if n_new_positions > 0:
                    # 计算当前总权益
                    equity = self.order_manager.get_total_equity(cash)

                    # 计算目标持仓数
                    target_n_long = len(new_long_set)
                    target_n_short = len(new_short_set)
                    target_total = target_n_long + target_n_short

                    if target_total > 0:
                        # 每个仓位分配等额资金
                        per_position_value = equity / target_total

                        # 执行多头开仓
                        for ticker in to_open_long:
                            if ticker in current_prices:
                                order = self.order_manager.create_open_order(
                                    ticker=ticker,
                                    side='long',
                                    value=per_position_value,
                                    price=current_prices[ticker],
                                    timestamp=time
                                )
                                trade, cash_delta, commission = self.order_manager.execute_order(order)
                                cash += cash_delta
                                period_turnover += order.value
                                period_commission += commission

                        # 执行空头开仓
                        for ticker in to_open_short:
                            if ticker in current_prices:
                                order = self.order_manager.create_open_order(
                                    ticker=ticker,
                                    side='short',
                                    value=per_position_value,
                                    price=current_prices[ticker],
                                    timestamp=time
                                )
                                trade, cash_delta, commission = self.order_manager.execute_order(order)
                                cash += cash_delta
                                period_turnover += order.value
                                period_commission += commission

                pending_signal = None

            self.total_turnover += period_turnover
            self.total_commission += period_commission

            # 步骤3: 计算并扣除资金费率
            period_funding = 0.0
            if self.apply_funding and prev_time is not None:
                for ticker, pos in self.order_manager.positions.items():
                    # 获取该标的在 (prev_time, time] 区间的资金费率
                    funding_rate = self._get_funding_rate(ticker, prev_time, time)
                    if funding_rate != 0.0:
                        # 资金费 = 持仓市值 * 资金费率
                        # 多头持仓: funding > 0 表示支付资金费 (现金减少)
                        # 空头持仓: funding > 0 表示收取资金费 (现金增加)
                        funding_cost = pos.current_value * funding_rate
                        if pos.side == 'long':
                            cash -= funding_cost  # 多头支付
                            period_funding += funding_cost
                        else:
                            cash += funding_cost  # 空头收取
                            period_funding -= funding_cost

            self.total_funding += period_funding

            # 步骤4: 计算当前总权益
            equity = self.order_manager.get_total_equity(cash)

            # 步骤5: 推送数据给策略，获取信号
            signal = self.strategy.on_bar(group_df)

            # 步骤6: 如果有新信号，设置为待执行
            if signal is not None:
                pending_signal = signal

            # 步骤7: 记录状态
            n_long = len(self.order_manager.get_long_tickers())
            n_short = len(self.order_manager.get_short_tickers())

            self.equity_curve.append({
                'Time': time,
                'Equity': equity,
                'Cash': cash,
                'Turnover': period_turnover / self.initial_capital,
                'Commission': period_commission,
                'Funding': period_funding,
                'N_Long': n_long,
                'N_Short': n_short,
                'N_Positions': len(self.order_manager.positions),
            })

            # 更新上一个时间点
            prev_time = time

            # 进度输出
            if i % 500 == 0:
                nav = equity / self.initial_capital
                print(f"  进度: {i}/{len(times)}, 权益: {equity:,.0f}, "
                      f"净值: {nav:.4f}, 持仓: {len(self.order_manager.positions)}")

        # 计算回测结果
        self._calculate_results()

        return self._get_results_df()

    def _calculate_results(self):
        """计算回测结果统计"""
        if not self.equity_curve:
            return

        df = pd.DataFrame(self.equity_curve)
        df.set_index('Time', inplace=True)
        df['NAV'] = df['Equity'] / self.initial_capital
        df['Period_Return'] = df['NAV'].pct_change().fillna(0)

        self.results_df = df

    def _get_results_df(self) -> pd.DataFrame:
        """获取回测结果DataFrame"""
        return self.results_df if hasattr(self, 'results_df') else pd.DataFrame()

    def print_performance(self):
        """打印回测绩效统计"""
        if not hasattr(self, 'results_df') or self.results_df is None:
            print("请先运行回测")
            return

        df = self.results_df

        # 计算年化系数
        if len(df) > 2:
            total_seconds = (df.index.max() - df.index.min()).total_seconds()
            years = total_seconds / (365.25 * 24 * 3600)
            ann_factor = len(df) / years if years > 0 else 252.0
        else:
            ann_factor = 252.0

        # 收益统计
        r = df['Period_Return'].dropna()
        ann_ret = r.mean() * ann_factor
        ann_vol = r.std() * np.sqrt(ann_factor)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

        # 回撤统计
        nav = df['NAV']
        running_max = nav.cummax()
        drawdown = (nav - running_max) / running_max
        max_dd = drawdown.min()

        # 总收益
        total_ret = df['NAV'].iloc[-1] - 1.0

        # 年化换手
        ann_turnover = df['Turnover'].mean() * ann_factor

        # 卡玛比率
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0

        print("\n" + "=" * 60)
        print("回测绩效统计（订单管理模式）")
        print("=" * 60)
        print(f"回测区间: {df.index.min()} ~ {df.index.max()}")
        print(f"K线数量: {len(df)}")
        print(f"年化系数: {ann_factor:.2f}")
        print("-" * 60)
        print(f"年化收益: {ann_ret:10.2%}")
        print(f"年化波动: {ann_vol:10.2%}")
        print(f"夏普比率: {sharpe:10.2f}")
        print(f"卡玛比率: {calmar:10.2f}")
        print(f"最大回撤: {max_dd:10.2%}")
        print(f"总收益:   {total_ret:10.2%}")
        print(f"年化换手: {ann_turnover:10.2f}x")
        print(f"累计手续费: {self.total_commission:,.0f}")
        print(f"累计资金费: {self.total_funding:,.2f} (正=支付, 负=收取)")
        print(f"总成交笔数: {len(self.order_manager.trades)}")
        print("=" * 60)

    def plot_curve(self, figsize=(14, 6), save_path=None):
        """绘制净值曲线和回撤图"""
        import matplotlib.pyplot as plt

        if not hasattr(self, 'results_df') or self.results_df is None:
            print("请先运行回测")
            return

        df = self.results_df

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True, height_ratios=[3, 1])

        # 净值曲线
        ax1.plot(df.index, df['NAV'], label='Net Value', linewidth=2)
        ax1.set_ylabel('Net Value')
        ax1.set_title('Event-Driven Backtest (Order Management Mode)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # 回撤曲线
        nav = df['NAV']
        running_max = nav.cummax()
        drawdown = (nav - running_max) / running_max
        ax2.fill_between(df.index, drawdown, 0, color='red', alpha=0.3)
        ax2.set_ylabel('Drawdown')
        ax2.set_xlabel('Time')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {save_path}")

        plt.show()

    def get_trades(self) -> pd.DataFrame:
        """获取所有成交记录"""
        if not self.order_manager.trades:
            return pd.DataFrame()

        trades_data = []
        for t in self.order_manager.trades:
            trades_data.append({
                'trade_id': t.trade_id,
                'order_id': t.order_id,
                'ticker': t.ticker,
                'order_type': t.order_type.value,
                'side': t.side,
                'quantity': t.quantity,
                'price': t.price,
                'value': t.value,
                'realized_pnl': t.realized_pnl,
                'commission': t.commission,
                'timestamp': t.timestamp
            })
        return pd.DataFrame(trades_data)


# ============================================================
# 数据重采样
# ============================================================

def resample_1h_to_8h(df: pd.DataFrame) -> pd.DataFrame:
    """将1小时K线数据重采样为8小时K线"""
    print(">> 重采样1h数据到8h...")

    df = df.copy()
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.sort_values(['Ticker', 'Time'])

    resampled_list = []

    for ticker, group in df.groupby('Ticker'):
        group = group.set_index('Time').sort_index()

        ohlcv = group.resample('8h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum',
            'Amount': 'sum'
        }).dropna()

        ohlcv['Ticker'] = ticker
        ohlcv = ohlcv.reset_index()
        resampled_list.append(ohlcv)

    result = pd.concat(resampled_list, ignore_index=True)
    result = result.sort_values(['Time', 'Ticker']).reset_index(drop=True)

    print(f"   重采样完成: {len(df)} 行 -> {len(result)} 行")
    print(f"   时间范围: {result['Time'].min()} ~ {result['Time'].max()}")
    print(f"   标的数量: {result['Ticker'].nunique()}")

    return result


# ============================================================
# 主函数入口
# ============================================================

def main():
    """
    主函数 - 运行5动量因子策略回测（订单管理模式）
    """
    # 加载数据
    print("=" * 60)
    print("加载1小时K线数据...")
    print("=" * 60)

    data_path = "./20200101-20260131-1h-binance-swap.parquet"
    df_1h = pd.read_parquet(data_path)
    print(f"原始数据: {len(df_1h)} 行")
    print(f"时间范围: {df_1h['Time'].min()} ~ {df_1h['Time'].max()}")
    print(f"标的数量: {df_1h['Ticker'].nunique()}")

    # 重采样
    df_8h = resample_1h_to_8h(df_1h)

    # 初始化5动量因子策略
    print("\n" + "=" * 60)
    print("初始化5动量因子策略...")
    print("=" * 60)

    strategy = FiveMomFactorStrategy(
        liq_quantile=0.2,        # 流动性过滤: 保留前20%
        liquidity_period=60,     # 流动性滚动窗口: 60周期
        long_short_ratio=5,      # 多空比例: 各取20%（5组）
        direction='descending',  # 因子方向: 因子值高做多
        min_bars=120             # 最小K线数: 120根
    )

    print(f"策略参数:")
    print(f"  - 因子: alpha_077 + alpha_078 + alpha_094 + alpha_007 - alpha_080")
    print(f"  - 流动性过滤: 前 {strategy.liq_quantile*100:.0f}%")
    print(f"  - 流动性窗口: {strategy.liq_period} 周期")
    print(f"  - 多空比例: 1/{strategy.ls_ratio} (各取{100/strategy.ls_ratio:.0f}%)")
    print(f"  - 因子方向: {strategy.direction}")
    print(f"  - 最小K线数: {strategy.min_bars}")
    print(f"  - 交易模式: 票池进出控制（订单管理）")

    # 初始化回测引擎
    backtest = EventDrivenBacktest(
        strategy=strategy,
        initial_capital=1_000_000,
        commission_rate=0.0005,  # 5bp
        funding_path="./binance_funding_rate.parquet",
        apply_funding=True
    )

    # 运行回测
    print("\n" + "=" * 60)
    print("运行事件驱动回测...")
    print("=" * 60)

    result = backtest.run(
        df_8h,
        start_date='2023-01-01',
    )

    # 输出结果
    backtest.print_performance()
    backtest.plot_curve(save_path='./backtest_incremental_result.png')

    # 导出成交记录
    trades_df = backtest.get_trades()
    if len(trades_df) > 0:
        trades_df.to_csv('./trades.csv', index=False, encoding='utf-8-sig')
        print(f"\n成交记录已导出: trades.csv ({len(trades_df)} 笔)")
        print("\n最近10笔成交记录:")
        print(trades_df.tail(10).to_string())

    return result


if __name__ == "__main__":
    main()
