#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha 077+094-080 截面动量因子策略 - 实盘版本

因子定义:
    al = alpha_077 + alpha_094 - alpha_080

其中:
    alpha_077: (Close - LL20) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的位置
    alpha_094: (VWAP - MA20) / STD20           -- VWAP相对20周期均线的标准化偏离
    alpha_080: (HH20 - Close) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的反向位置

运行方式:
    # 使用配置文件
    python alpha_077_094_080_live.py --config config.json

    # 命令行参数 (覆盖配置文件)
    python alpha_077_094_080_live.py --config config.json --exchange binance

编译依赖:
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import os
import json
import signal
import time
import numpy as np
from collections import deque
from typing import Optional, Dict, List, Any

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMPLEMENTATIONS_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
STRATEGIES_DIR = os.path.dirname(IMPLEMENTATIONS_DIR)  # cpp/strategies
sys.path.insert(0, STRATEGIES_DIR)

# 导入 C++ 策略基类
from strategy_base import StrategyBase, KlineBar


# ======================
# 配置加载
# ======================
def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config


def get_default_config() -> Dict[str, Any]:
    """获取默认配置"""
    return {
        "strategy_id": "alpha_077_094_080",
        "exchange": "okx",
        "api_key": "",
        "secret_key": "",
        "passphrase": "",
        "is_testnet": True,
        "symbols": [],  # 空列表表示动态获取全市场
        "dynamic_symbols": True,  # 是否动态获取全市场标的
        "factor_params": {
            "lookback_window": 20,
            "liquidity_period": 60,
            "liq_quantile": 0.1,
            "long_short_ratio": 2,
            "direction": "descending"
        },
        "trading_params": {
            "interval": "8h",  # K线周期（原策略使用8小时K线）
            "rebalance_interval_hours": 8,  # 调仓间隔（小时），原策略为8小时
            "position_ratio": 1,  # 仓位比例，占账户余额的比例
            "min_bars": 120,  # 120根8h K线 = 40天预热期
            "history_bars": 200  # 历史K线数量
        },
        "redis": {
            "host": "127.0.0.1",
            "port": 6379,
            "password": ""
        },
        "logging": {
            "log_file": ""
        }
    }


# ======================
# 标的数据存储
# ======================
class TickerDataLive:
    """单个标的的数据存储器"""

    def __init__(self, min_bars: int = 120):
        self.min_bars = min_bars
        self.bar_count = 0

        # 最新K线数据
        self.latest_close = None
        self.latest_high = None
        self.latest_low = None
        self.latest_volume = None
        self.latest_amount = None

        # 滚动窗口历史数据
        # close_history容量120: 用于计算MA20和STD20，预留足够历史
        # high/low/amount_history容量60: 用于计算HH20/LL20和流动性MA
        self.close_history = deque(maxlen=120)
        self.high_history = deque(maxlen=60)
        self.low_history = deque(maxlen=60)
        self.volume_history = deque(maxlen=60)
        self.amount_history = deque(maxlen=60)

    def add_bar(self, bar: KlineBar) -> bool:
        """添加新K线数据"""
        self.latest_close = bar.close
        self.latest_high = bar.high
        self.latest_low = bar.low
        self.latest_volume = bar.volume
        # 使用真实成交额（如果KlineBar有amount字段则使用，否则近似计算）
        self.latest_amount = getattr(bar, 'amount', bar.volume * bar.close)

        self.close_history.append(bar.close)
        self.high_history.append(bar.high)
        self.low_history.append(bar.low)
        self.volume_history.append(bar.volume)
        self.amount_history.append(self.latest_amount)

        self.bar_count += 1
        return self.bar_count >= self.min_bars

    def get_vwap(self) -> float:
        """计算VWAP"""
        if self.latest_volume and self.latest_volume > 0:
            return self.latest_amount / self.latest_volume
        return self.latest_close

    def get_rolling_mean(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            window = len(data)
        if window == 0:
            return None
        return np.mean(list(data)[-window:])

    def get_rolling_std(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            window = len(data)
        if window < 2:
            return None
        return np.std(list(data)[-window:], ddof=1)

    def get_rolling_max(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            window = len(data)
        if window == 0:
            return None
        return np.max(list(data)[-window:])

    def get_rolling_min(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            window = len(data)
        if window == 0:
            return None
        return np.min(list(data)[-window:])

    def get_liquidity_ma(self, window: int) -> Optional[float]:
        if len(self.amount_history) < window:
            window = len(self.amount_history)
        if window == 0:
            return None
        return np.mean(list(self.amount_history)[-window:])


# ======================
# 策略类
# ======================
class Alpha077094080LiveStrategy(StrategyBase):
    """Alpha 077+094-080 截面动量策略 - 支持 OKX / Binance"""

    def __init__(self, config: Dict[str, Any]):
        """初始化策略"""
        strategy_id = config.get("strategy_id", "alpha_077_094_080")
        trading_params = config.get("trading_params", {})
        history_bars = trading_params.get("history_bars", 200)

        # 日志配置 - 自动生成日志文件路径
        log_config = config.get("logging", {})
        log_file = log_config.get("log_file", "")
        if not log_file:
            # 自动生成日志文件: logs/alpha_077_094_080_YYYYMMDD_HHMMSS.log
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(STRATEGIES_DIR, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"{strategy_id}_{timestamp}.log")

        super().__init__(
            strategy_id,
            max_kline_bars=history_bars + 100,
            log_file_path=log_file
        )

        self.log_file_path = log_file
        self.log_info(f"[日志] 日志文件: {log_file}")

        # 保存配置
        self.config = config

        # 交易所配置
        self.exchange = config.get("exchange", "okx").lower()
        self.api_key = config.get("api_key", "")
        self.secret_key = config.get("secret_key", "")
        self.passphrase = config.get("passphrase", "")
        self.is_testnet = config.get("is_testnet", True)

        # 交易对列表 - 支持动态获取全市场
        self.dynamic_symbols = config.get("dynamic_symbols", False)
        config_symbols = config.get("symbols", [])
        if self.dynamic_symbols or not config_symbols:
            # 动态获取全市场标的（在on_init中执行）
            self.symbols = []
        else:
            self.symbols = config_symbols

        # 交易参数
        # 注意：原策略使用8小时K线进行因子计算，所以这里订阅8h K线
        self.interval = trading_params.get("interval", "8h")  # 因子计算使用8小时K线
        self.rebalance_interval_hours = trading_params.get("rebalance_interval_hours", 8)  # 调仓间隔（小时）
        self.position_ratio = trading_params.get("position_ratio", 0.8)  # 仓位比例，占账户余额的比例
        self.min_bars = trading_params.get("min_bars", 120)  # 120根8h K线 = 40天预热期
        self.history_bars = history_bars
        self.leverage = trading_params.get("leverage", 1)  # 杠杆倍数，默认1倍

        # 因子参数
        factor_params = config.get("factor_params", {})
        self.lookback_window = factor_params.get("lookback_window", 20)
        self.liq_period = factor_params.get("liquidity_period", 60)
        self.liq_quantile = factor_params.get("liq_quantile", 0.1)
        self.ls_ratio = factor_params.get("long_short_ratio", 2)
        self.direction = factor_params.get("direction", "descending")

        # 内部状态
        self.ticker_data: Dict[str, TickerDataLive] = {}
        self.target_positions: Dict[str, float] = {}
        self.account_ready = False
        self.data_ready = False

        # 统计
        self.total_trades = 0
        self.rebalance_count = 0

        # 调仓控制 - 防止重复调仓
        self.last_rebalance_ts = 0  # 上次调仓的时间戳（毫秒）
        self.rebalance_interval_ms = self.rebalance_interval_hours * 60 * 60 * 1000  # 调仓间隔（毫秒）

        # Redis 轮询控制
        self.last_redis_check_ts = 0  # 上次检查 Redis 的时间戳（秒）
        self.redis_check_interval = 60  # Redis 检查间隔（秒），每分钟检查一次
        self.last_kline_timestamps: Dict[str, int] = {}  # 每个标的最新 K 线时间戳

        self.log_info(f"策略参数: {self.exchange.upper()} | {len(self.symbols)}个标的 | K线周期:{self.interval} | 调仓间隔:{self.rebalance_interval_hours}小时")

    # ======================== 因子计算 ========================

    def _compute_alpha_077(self, data: TickerDataLive) -> Optional[float]:
        """alpha_077: (Close - LL20) / (HH20 - LL20)"""
        ll20 = data.get_rolling_min(data.low_history, self.lookback_window)
        hh20 = data.get_rolling_max(data.high_history, self.lookback_window)

        if ll20 is None or hh20 is None:
            return None

        rng20 = hh20 - ll20
        if rng20 == 0:
            return None

        return (data.latest_close - ll20) / rng20

    def _compute_alpha_094(self, data: TickerDataLive) -> Optional[float]:
        """alpha_094: (VWAP - MA20) / STD20"""
        vwap = data.get_vwap()
        ma20 = data.get_rolling_mean(data.close_history, self.lookback_window)
        std_c20 = data.get_rolling_std(data.close_history, self.lookback_window)

        if vwap is None or ma20 is None or std_c20 is None or std_c20 == 0:
            return None

        return (vwap - ma20) / std_c20

    def _compute_alpha_080(self, data: TickerDataLive) -> Optional[float]:
        """alpha_080: (HH20 - Close) / (HH20 - LL20)"""
        ll20 = data.get_rolling_min(data.low_history, self.lookback_window)
        hh20 = data.get_rolling_max(data.high_history, self.lookback_window)

        if ll20 is None or hh20 is None:
            return None

        rng20 = hh20 - ll20
        if rng20 == 0:
            return None

        return (hh20 - data.latest_close) / rng20

    def _zscore(self, values: Dict[str, float]) -> Dict[str, float]:
        """截面Z-score标准化"""
        valid_values = {k: v for k, v in values.items() if v is not None and np.isfinite(v)}

        if len(valid_values) == 0:
            return values

        mean_val = np.mean(list(valid_values.values()))
        std_val = np.std(list(valid_values.values()))

        if std_val == 0 or np.isnan(std_val):
            return {k: (v - mean_val if v is not None else None) for k, v in values.items()}

        return {k: ((v - mean_val) / std_val if v is not None else None) for k, v in values.items()}

    def _compute_target_positions(self) -> Dict[str, float]:
        """计算目标仓位权重"""
        ready_tickers = [s for s in self.symbols
                        if s in self.ticker_data and self.ticker_data[s].bar_count >= self.min_bars]

        if len(ready_tickers) < 2 * self.ls_ratio:
            return {}

        # 计算因子值
        alpha_077_vals = {}
        alpha_094_vals = {}
        alpha_080_vals = {}
        liquidity_vals = {}

        for symbol in ready_tickers:
            data = self.ticker_data[symbol]
            alpha_077_vals[symbol] = self._compute_alpha_077(data)
            alpha_094_vals[symbol] = self._compute_alpha_094(data)
            alpha_080_vals[symbol] = self._compute_alpha_080(data)
            liquidity_vals[symbol] = data.get_liquidity_ma(self.liq_period)

        # Z-score标准化
        alpha_077_z = self._zscore(alpha_077_vals)
        alpha_094_z = self._zscore(alpha_094_vals)
        alpha_080_z = self._zscore(alpha_080_vals)

        # 组合因子
        al_values = {}
        for symbol in alpha_077_z.keys():
            a077 = alpha_077_z.get(symbol)
            a094 = alpha_094_z.get(symbol)
            a080 = alpha_080_z.get(symbol)

            if a077 is None or a094 is None or a080 is None:
                continue
            if not np.isfinite(a077) or not np.isfinite(a094) or not np.isfinite(a080):
                continue

            al_values[symbol] = a077 + a094 - a080

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

        # 计算仓位
        valid_factors = {k: v for k, v in al_values.items() if v is not None and np.isfinite(v)}

        if len(valid_factors) < 2 * self.ls_ratio:
            return {}

        is_descending = (self.direction == 'descending')
        sorted_tickers = sorted(valid_factors.keys(), key=lambda x: valid_factors[x], reverse=is_descending)

        n_total = len(sorted_tickers)
        n_pos = int(n_total / self.ls_ratio)

        if n_pos < 1:
            return {}

        positions = {}

        # 多头
        long_tickers = sorted_tickers[:n_pos]
        if len(long_tickers) > 0:
            w_long = 1.0 / len(long_tickers)
            for t in long_tickers:
                positions[t] = w_long

        # 空头
        short_tickers = sorted_tickers[-n_pos:]
        if len(short_tickers) > 0:
            w_short = -1.0 / len(short_tickers)
            for t in short_tickers:
                positions[t] = w_short

        return positions

    # ======================== 交易执行 ========================

    def _preload_leverage(self):
        """预设所有交易对的杠杆倍数

        在策略启动时，为所有交易对设置统一的杠杆倍数。
        这样可以避免在下单时因杠杆设置不当导致的问题。
        """
        self.log_info(f"[杠杆预设] 开始为 {len(self.symbols)} 个交易对设置 {self.leverage}x 杠杆...")

        success_count = 0
        fail_count = 0

        for symbol in self.symbols:
            try:
                # 调用框架的 change_leverage 方法
                result = self.change_leverage(symbol, self.leverage, self.exchange)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
                    self.log_error(f"[杠杆预设] {symbol} 设置失败")

                # 添加短暂延迟，避免 API 限流
                time.sleep(0.1)

            except Exception as e:
                fail_count += 1
                self.log_error(f"[杠杆预设] {symbol} 异常: {e}")

        self.log_info(f"[杠杆预设] 完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    def _get_contract_multiplier(self, symbol: str) -> float:
        """获取合约乘数"""
        if self.exchange == "okx":
            # OKX 合约面值
            if "BTC" in symbol:
                return 0.01
            elif "ETH" in symbol:
                return 0.1
            else:
                return 1.0
        else:
            # Binance 直接用币数
            return 1.0

    def _check_initial_rebalance(self):
        """启动时检查是否需要立即调仓

        当账户和数据都就绪时调用，检查当前是否处于需要调仓的时间点。
        如果从未调仓过（last_rebalance_ts == 0），则立即执行一次调仓。
        """
        import time
        from datetime import datetime

        current_ts = int(time.time() * 1000)  # 当前时间戳（毫秒）
        ts_str = datetime.fromtimestamp(current_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

        self.log_info(f"[启动检查] 账户和数据都已就绪，检查是否需要调仓...")
        self.log_info(f"[启动检查] 当前时间: {ts_str}")

        # 如果从未调仓过，立即执行一次
        if self.last_rebalance_ts == 0:
            self.log_info(f"[启动检查] 首次启动，立即执行调仓")
            self.last_rebalance_ts = current_ts
            self._execute_rebalance()
        else:
            # 检查是否进入了新的8小时周期
            current_period = current_ts // self.rebalance_interval_ms
            last_period = self.last_rebalance_ts // self.rebalance_interval_ms

            if current_period > last_period:
                self.log_info(f"[启动检查] 已进入新的8h周期，执行调仓")
                self.last_rebalance_ts = current_ts
                self._execute_rebalance()
            else:
                # 计算距离下次调仓的时间
                next_rebalance_ts = (current_period + 1) * self.rebalance_interval_ms
                time_to_next = (next_rebalance_ts - current_ts) / 3600000  # 转换为小时
                next_ts_str = datetime.fromtimestamp(next_rebalance_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                self.log_info(f"[启动检查] 当前周期已调仓，等待下次调仓")
                self.log_info(f"[启动检查] 下次调仓时间: {next_ts_str} (约 {time_to_next:.1f} 小时后)")

    def _execute_rebalance(self):
        """执行调仓"""
        target_positions = self._compute_target_positions()

        if not target_positions:
            return

        self.target_positions = target_positions
        self.rebalance_count += 1

        # 获取账户余额
        usdt_available = self.get_usdt_available()
        total_capital = usdt_available * self.position_ratio  # 总可用资金

        # 计算所有权重的绝对值之和（多头1.0 + 空头1.0 = 2.0）
        total_weight = sum(abs(w) for w in target_positions.values())

        # 获取当前持仓
        current_positions = {}
        for pos in self.get_active_positions():
            if pos.symbol in self.symbols:
                current_positions[pos.symbol] = pos.quantity

        # 详细日志
        long_symbols = [(s, w) for s, w in target_positions.items() if w > 0]
        short_symbols = [(s, w) for s, w in target_positions.items() if w < 0]

        self.log_info("=" * 50)
        self.log_info(f"[调仓#{self.rebalance_count}] 开始执行")
        self.log_info(f"[账户] USDT余额: {usdt_available:.2f} | 总资金: {total_capital:.2f} USDT | 总权重: {total_weight:.2f}")
        self.log_info(f"[多头] {len(long_symbols)}个: {[s for s, _ in long_symbols]}")
        self.log_info(f"[空头] {len(short_symbols)}个: {[s for s, _ in short_symbols]}")

        # 收集所有订单
        close_orders = []  # 平仓订单
        open_orders = []   # 开仓订单

        for symbol, weight in target_positions.items():
            # 从 ticker_data 获取价格
            if symbol not in self.ticker_data or self.ticker_data[symbol].latest_close is None:
                self.log_error(f"[跳过] {symbol} 无K线数据")
                continue

            price = self.ticker_data[symbol].latest_close
            if price <= 0:
                self.log_error(f"[跳过] {symbol} 价格异常: {price}")
                continue

            # 计算目标仓位: 总资金 × (权重 / 总权重)
            target_value = total_capital * abs(weight) / total_weight
            multiplier = self._get_contract_multiplier(symbol)

            if self.exchange == "okx":
                target_qty = int(target_value / (price * multiplier))
                if target_qty < 1:
                    target_qty = 1
            else:
                # Binance: 使用框架的 calculate_order_quantity 方法，自动处理精度
                target_qty = self.calculate_order_quantity(self.exchange, symbol, target_value, price)
                if target_qty <= 0:
                    self.log_error(f"[跳过] {symbol} 计算下单数量失败")
                    continue

            # 当前持仓
            current_qty = current_positions.get(symbol, 0)

            # 平仓订单
            if current_qty != 0:
                close_side = "sell" if current_qty > 0 else "buy"
                close_qty = abs(current_qty)
                pos_side = "LONG" if current_qty > 0 else "SHORT"
                close_orders.append({
                    "symbol": symbol,
                    "side": close_side.upper(),
                    "quantity": close_qty,
                    "pos_side": pos_side,
                    "type": "MARKET"
                })

            # 开仓订单
            if weight != 0:
                open_side = "buy" if weight > 0 else "sell"
                pos_side = "LONG" if weight > 0 else "SHORT"
                open_orders.append({
                    "symbol": symbol,
                    "side": open_side.upper(),
                    "quantity": target_qty,
                    "pos_side": pos_side,
                    "type": "MARKET",
                    "target_value": target_value,
                    "price": price,
                    "weight": weight
                })

        # 批量下单（Binance 每批最多5个）
        batch_size = 5 if self.exchange == "binance" else 20

        # 1. 先批量平仓
        if close_orders:
            self.log_info(f"[平仓] 共 {len(close_orders)} 个订单，分批发送...")
            for i in range(0, len(close_orders), batch_size):
                batch = close_orders[i:i+batch_size]
                # 转换为框架需要的格式
                batch_for_send = [{
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "quantity": o["quantity"],
                    "pos_side": o["pos_side"],
                    "order_type": o["type"]
                } for o in batch]
                self.send_batch_orders(batch_for_send, self.exchange)
                self.log_info(f"[平仓] 发送第 {i//batch_size + 1} 批: {[o['symbol'] for o in batch]}")
                time.sleep(0.2)  # 批次间隔

        # 2. 再批量开仓
        if open_orders:
            self.log_info(f"[开仓] 共 {len(open_orders)} 个订单，分批发送...")
            for i in range(0, len(open_orders), batch_size):
                batch = open_orders[i:i+batch_size]
                # 转换为框架需要的格式
                batch_for_send = [{
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "quantity": o["quantity"],
                    "pos_side": o["pos_side"],
                    "order_type": o["type"]
                } for o in batch]
                self.send_batch_orders(batch_for_send, self.exchange)
                # 打印详细日志
                for o in batch:
                    direction = "多" if o["weight"] > 0 else "空"
                    self.log_info(f"[开仓] {o['symbol']} | {direction} {o['quantity']} @ {o['price']:.4f} | 价值: {o['target_value']:.2f} USDT")
                self.total_trades += len(batch)
                time.sleep(0.2)  # 批次间隔

        self.log_info(f"[调仓#{self.rebalance_count}] 完成 | 累计交易: {self.total_trades}笔")
        self.log_info("=" * 50)

    # ======================== 生命周期 ========================

    def _fetch_all_symbols(self) -> List[str]:
        """
        动态获取全市场USDT永续合约标的
        使用框架内置的 get_available_historical_symbols 接口
        """
        try:
            self.log_info(f"[币种池] 从 {self.exchange.upper()} 获取全市场永续合约...")

            # 使用框架内置接口获取可用标的
            all_symbols = self.get_available_historical_symbols(self.exchange)

            if all_symbols:
                # 过滤只保留USDT永续合约
                if self.exchange == "okx":
                    # OKX格式: BTC-USDT-SWAP
                    symbols = [s for s in all_symbols if s.endswith("-USDT-SWAP")]
                else:
                    # Binance格式: BTCUSDT
                    symbols = [s for s in all_symbols if s.endswith("USDT")]

                symbols.sort()
                self.log_info(f"[币种池] 获取到 {len(symbols)} 个USDT永续合约")
                return symbols
            else:
                self.log_error("[币种池] 获取标的列表为空")

        except Exception as e:
            self.log_error(f"[币种池] 获取标的失败: {e}")

        return []

    def on_init(self):
        """策略初始化"""
        print("=" * 60)
        print("  Alpha 077+094-080 截面动量策略 - 初始化")
        print("=" * 60)

        # 1. 注册账户
        if self.api_key and self.secret_key:
            self.log_info(f"[初始化] 注册 {self.exchange.upper()} 账户...")
            if self.exchange == "okx":
                self.register_account(
                    self.api_key,
                    self.secret_key,
                    self.passphrase,
                    self.is_testnet
                )
            else:
                self.register_binance_account(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    is_testnet=self.is_testnet
                )
        else:
            self.log_error("[初始化] 请在配置文件中设置 API 密钥")
            return

        # 2. 连接 Redis 历史数据服务
        self.log_info("[初始化] 连接 Redis 历史数据服务...")
        redis_connected = self.connect_historical_data()
        if not redis_connected:
            self.log_error("[初始化] 连接 Redis 失败")

        # 3. 动态获取全市场标的（如果配置为动态模式）
        if self.dynamic_symbols or not self.symbols:
            self.symbols = self._fetch_all_symbols()
            if not self.symbols:
                self.log_error("[初始化] 无法获取标的列表，请检查网络或交易所状态,程序终止")
                return

        # 4. 加载最小下单单位配置（Binance 需要）
        if self.exchange == "binance":
            self.log_info("[初始化] 加载 Binance 最小下单单位配置...")
            # 使用绝对路径，避免工作目录问题
            configs_dir = os.path.join(STRATEGIES_DIR, "configs")
            if not self.load_min_order_config("binance", configs_dir):
                self.log_error("[初始化] 加载 Binance 最小下单单位配置失败")

        # 5. 预设杠杆倍数（Binance 合约）
        if self.exchange == "binance" and self.leverage > 0:
            self._preload_leverage()

        # 5. 订阅K线并初始化数据存储
        for symbol in self.symbols:
            self.subscribe_kline(symbol, self.interval)
            self.ticker_data[symbol] = TickerDataLive(min_bars=self.min_bars)

        self.log_info(f"[初始化] 已订阅 {len(self.symbols)} 个标的，K线周期: {self.interval}")

        # 6. 从 Redis 加载历史 K 线数据
        if redis_connected:
            self._load_historical_data()

        print("=" * 60)

    def _load_historical_data(self):
        """从 Redis 加载历史 K 线数据（8小时K线）"""
        self.log_info(f"[历史数据] 开始从 Redis 加载历史 8h K 线...")
        loaded_count = 0
        ready_count = 0

        # 计算时间范围：最近 history_bars 个8小时周期
        # 8小时 = 8 * 60 * 60 * 1000 毫秒 = 28800000 毫秒
        import time
        end_time = int(time.time() * 1000)  # 当前时间（毫秒）
        start_time = end_time - self.history_bars * 8 * 60 * 60 * 1000  # history_bars 个8小时周期前

        for symbol in self.symbols:
            try:
                # 获取历史 K 线 (使用 start_time 和 end_time)
                klines = self.get_historical_klines(
                    symbol=symbol,
                    exchange=self.exchange,
                    interval=self.interval,
                    start_time=start_time,
                    end_time=end_time
                )

                if klines and len(klines) > 0:
                    data = self.ticker_data[symbol]
                    for kline in klines:
                        # 创建 KlineBar 对象
                        bar = KlineBar()
                        bar.open = float(kline.open)
                        bar.high = float(kline.high)
                        bar.low = float(kline.low)
                        bar.close = float(kline.close)
                        bar.volume = float(kline.volume)
                        bar.timestamp = int(kline.timestamp)
                        data.add_bar(bar)

                    loaded_count += 1
                    if data.bar_count >= self.min_bars:
                        ready_count += 1

            except Exception as e:
                # 只打印前几个错误，避免刷屏
                if loaded_count < 5:
                    self.log_error(f"[历史数据] {symbol} 加载失败: {e}")

        self.log_info(f"[历史数据] 加载完成: {loaded_count}/{len(self.symbols)} 个标的 | {ready_count} 个已就绪")

        # 检查是否有足够的数据
        if ready_count >= len(self.symbols) * 0.5:
            self.data_ready = True
            self.log_info(f"[历史数据] 数据就绪，可以开始调仓")

            # 数据就绪后，如果账户也就绪，立即触发一次调仓检查
            if self.account_ready:
                self._check_initial_rebalance()
        else:
            self.log_info(f"[历史数据] 数据不足，需要等待实时 8h K 线收集 (需要 {self.min_bars} 根8h K线)")

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] Alpha 077+094-080 策略停止")
        print(f"[统计] 总交易: {self.total_trades} | 调仓次数: {self.rebalance_count}")

        for symbol in self.symbols:
            self.unsubscribe_kline(symbol, self.interval)

        print("=" * 60)

    # ======================== 回调函数 ========================

    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.log_info("[账户] 注册成功")
            self.refresh_account()
        else:
            self.log_error(f"[账户] 注册失败: {error_msg}")

    def on_balance_update(self, balance):
        """余额更新回调"""
        if balance.currency == "USDT" and not self.account_ready:
            self.account_ready = True
            self.log_info(f"[账户] 余额就绪, USDT可用: {balance.available:.2f}")

            # 账户就绪后，如果数据也就绪，立即触发一次调仓检查
            if self.data_ready:
                self._check_initial_rebalance()

    def on_position_update(self, position):
        """持仓更新回调"""
        if position.symbol in self.symbols and position.quantity != 0:
            self.log_info(f"[持仓] {position.symbol} {position.quantity}张 盈亏: {position.unrealized_pnl:.2f}")

    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调 - 8小时K线到达时触发调仓

        原策略使用8小时K线进行因子计算，每8小时调仓一次。
        当使用8h K线时，每根K线到达自然对应一次调仓机会。
        """
        if symbol not in self.ticker_data:
            return

        if interval != self.interval:
            return

        data = self.ticker_data[symbol]
        data.add_bar(bar)

        # 检查数据是否就绪
        if not self.data_ready:
            ready_count = sum(1 for s in self.symbols
                           if s in self.ticker_data and self.ticker_data[s].bar_count >= self.min_bars)
            total = len(self.symbols)

            # 每收到一定数量的K线打印一次进度
            total_bars = sum(self.ticker_data[s].bar_count for s in self.symbols if s in self.ticker_data)
            if total_bars % 100 == 0:  # 每100根8h K线打印一次
                avg_bars = total_bars / total if total > 0 else 0
                self.log_info(f"[数据收集] 进度: {ready_count}/{total} 标的就绪 | 平均K线数: {avg_bars:.0f}/{self.min_bars}")

            if ready_count >= total * 0.8:
                self.data_ready = True
                self.log_info(f"[数据] 就绪，{ready_count}/{total} 个标的已准备好，开始调仓")

        # 8小时K线到达时触发调仓
        # 由于使用8h K线，每根K线到达自然对应一次调仓机会
        # 但需要确保同一时间截面只调仓一次（等待所有标的的K线都到达）
        if self.account_ready and self.data_ready:
            current_ts = bar.timestamp

            # 检查是否是新的8小时周期（避免同一周期重复调仓）
            # 使用8小时周期边界对齐
            current_period = current_ts // self.rebalance_interval_ms
            last_period = self.last_rebalance_ts // self.rebalance_interval_ms if self.last_rebalance_ts > 0 else 0

            if current_period > last_period:
                # 新的8小时周期开始，触发调仓
                from datetime import datetime
                ts_str = datetime.fromtimestamp(current_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                self.log_info(f"[调仓触发] 新8h周期开始 | 时间: {ts_str}")
                self.last_rebalance_ts = current_ts
                self._execute_rebalance()

    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")

        if status == "filled":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] {symbol} {side} {filled_qty} @ {filled_price:.2f}")
        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] {symbol} {side} | {error_msg}")

    def on_tick(self):
        """定时回调 - 定期轮询 Redis 检测新 8h K 线数据

        每分钟检查一次 Redis，如果发现新的 8h K 线数据，则更新本地数据并触发调仓。
        这样可以确保即使错过了实时 K 线推送，也能通过轮询 Redis 获取最新数据。
        """
        import time
        current_ts = int(time.time())

        # 检查是否到了轮询时间
        if current_ts - self.last_redis_check_ts < self.redis_check_interval:
            return

        self.last_redis_check_ts = current_ts

        # 如果账户或数据未就绪，跳过
        if not self.account_ready or not self.data_ready:
            return

        # 轮询 Redis 检测新 K 线
        new_klines_found = False
        new_kline_ts = 0

        for symbol in self.symbols:
            try:
                # 获取最新的 K 线数据（只取最近 5 根，减少数据量）
                end_time = int(time.time() * 1000)
                start_time = end_time - 5 * 8 * 60 * 60 * 1000  # 最近 5 个 8h 周期

                klines = self.get_historical_klines(
                    symbol=symbol,
                    exchange=self.exchange,
                    interval=self.interval,
                    start_time=start_time,
                    end_time=end_time
                )

                if not klines or len(klines) == 0:
                    continue

                # 获取最新 K 线的时间戳
                latest_kline = klines[-1]
                latest_ts = int(latest_kline.timestamp)

                # 检查是否有新 K 线
                last_known_ts = self.last_kline_timestamps.get(symbol, 0)
                if latest_ts > last_known_ts:
                    # 发现新 K 线，更新本地数据
                    data = self.ticker_data.get(symbol)
                    if data:
                        # 只添加新的 K 线（时间戳大于已知的）
                        for kline in klines:
                            kline_ts = int(kline.timestamp)
                            if kline_ts > last_known_ts:
                                bar = KlineBar()
                                bar.open = float(kline.open)
                                bar.high = float(kline.high)
                                bar.low = float(kline.low)
                                bar.close = float(kline.close)
                                bar.volume = float(kline.volume)
                                bar.timestamp = kline_ts
                                data.add_bar(bar)

                        self.last_kline_timestamps[symbol] = latest_ts
                        new_klines_found = True
                        if latest_ts > new_kline_ts:
                            new_kline_ts = latest_ts

            except Exception:
                # 忽略单个标的的错误，继续处理其他标的
                pass

        # 如果发现新 K 线，检查是否需要调仓
        if new_klines_found and new_kline_ts > 0:
            from datetime import datetime
            ts_str = datetime.fromtimestamp(new_kline_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

            # 检查是否是新的 8 小时周期
            current_period = new_kline_ts // self.rebalance_interval_ms
            last_period = self.last_rebalance_ts // self.rebalance_interval_ms if self.last_rebalance_ts > 0 else 0

            if current_period > last_period:
                self.log_info(f"[Redis轮询] 发现新8h K线 | 时间: {ts_str} | 触发调仓")
                self.last_rebalance_ts = new_kline_ts
                self._execute_rebalance()
            else:
                # 同一周期内，只更新数据，不重复调仓
                pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Alpha 077+094-080 截面动量策略")
    parser.add_argument("--config", default="alpha_077_094_080_config.json", help="配置文件路径")
    parser.add_argument("--exchange", default="", help="交易所 (覆盖配置文件)")

    args = parser.parse_args()

    # 加载配置
    config_path = args.config
    if not os.path.isabs(config_path):
        configs_dir = os.path.join(STRATEGIES_DIR, "configs")
        if os.path.exists(os.path.join(configs_dir, config_path)):
            config_path = os.path.join(configs_dir, config_path)
        elif os.path.exists(os.path.join(SCRIPT_DIR, config_path)):
            config_path = os.path.join(SCRIPT_DIR, config_path)
        else:
            config_path = os.path.join(configs_dir, config_path)

    try:
        config = load_config(config_path)
        print(f"[配置] 已加载: {config_path}")
    except FileNotFoundError:
        print(f"[配置] 文件不存在: {config_path}，使用默认配置")
        config = get_default_config()

    # 命令行参数覆盖
    if args.exchange:
        config["exchange"] = args.exchange

    # 创建策略
    strategy = Alpha077094080LiveStrategy(config)

    # 打印信息
    print("=" * 60)
    print("  Alpha 077+094-080 截面动量策略 - 实盘版本")
    print("=" * 60)
    print()
    print(f"交易所: {strategy.exchange.upper()} {'(测试网)' if strategy.is_testnet else '(主网)'}")
    print(f"标的数: {len(strategy.symbols)}")
    print(f"K线周期: {strategy.interval} | 调仓间隔: {strategy.rebalance_interval_hours}小时")
    print(f"仓位比例: {strategy.position_ratio * 100:.0f}% (动态计算，基于账户余额)")
    print()
    print(f"因子参数: lookback={strategy.lookback_window}, liq_quantile={strategy.liq_quantile}")
    print()
    print("-" * 60)

    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()
