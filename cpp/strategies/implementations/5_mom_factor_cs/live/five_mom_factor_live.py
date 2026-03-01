#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
5动量因子截面策略 (Five Momentum Factor Strategy) - 实盘版本

因子定义:
    al = alpha_077 + alpha_078 + alpha_094 + alpha_007 - alpha_080

其中:
    alpha_077: (Close - LL20) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的位置
    alpha_078: (Close - LL60) / (HH60 - LL60)  -- 收盘价在60周期价格区间中的位置
    alpha_094: (VWAP - MA20) / STD20           -- VWAP相对20周期均线的标准化偏离
    alpha_007: sum_ret_20 / std_ret_60         -- 风险调整动量
    alpha_080: (HH20 - Close) / (HH20 - LL20)  -- 收盘价在20周期价格区间中的反向位置

运行方式:
    # 使用配置文件
    python five_mom_factor_live.py --config five_mom_factor_config.json

    # 命令行参数 (覆盖配置文件)
    python five_mom_factor_live.py --config config.json --exchange binance

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
from concurrent.futures import ThreadPoolExecutor, as_completed

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIVE_MOM_DIR = os.path.dirname(SCRIPT_DIR)  # 5_mom_factor_cs
IMPLEMENTATIONS_DIR = os.path.dirname(FIVE_MOM_DIR)  # implementations
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
        "strategy_id": "five_mom_factor_binance_testnet",
        "exchange": "binance",
        "api_key": "",
        "secret_key": "",
        "passphrase": "",
        "is_testnet": True,
        "symbols": [],
        "dynamic_symbols": True,
        "factor_params": {
            "lookback_window_20": 20,
            "lookback_window_60": 60,
            "liquidity_period": 60,
            "liq_quantile": 0.2,
            "long_short_ratio": 5,
            "direction": "descending"
        },
        "trading_params": {
            "interval": "8h",
            "rebalance_interval_hours": 8,
            "position_ratio": 1,
            "min_bars": 60,
            "history_bars": 200
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
    """单个标的的数据存储器 - 支持5因子计算"""

    def __init__(self, min_bars: int = 60, lookback: int = 120):
        self.min_bars = min_bars
        self.lookback = lookback
        self.bar_count = 0

        # 最新K线数据
        self.latest_close = None
        self.latest_high = None
        self.latest_low = None
        self.latest_volume = None
        self.latest_amount = None
        self.latest_open = None
        self.prev_close = None  # 用于计算收益率

        # 滚动窗口历史数据
        self.close_history = deque(maxlen=lookback)
        self.high_history = deque(maxlen=lookback)
        self.low_history = deque(maxlen=lookback)
        self.volume_history = deque(maxlen=lookback)
        self.amount_history = deque(maxlen=lookback)
        self.ret_history = deque(maxlen=lookback)  # 收益率历史

    def add_bar(self, bar: KlineBar) -> bool:
        """添加新K线数据"""
        # 计算收益率
        if self.latest_close is not None and self.latest_close > 0:
            ret = (bar.close / self.latest_close) - 1
            self.ret_history.append(ret)

        # 更新最新值
        self.prev_close = self.latest_close
        self.latest_close = bar.close
        self.latest_high = bar.high
        self.latest_low = bar.low
        self.latest_volume = bar.volume
        self.latest_amount = getattr(bar, 'amount', bar.volume * bar.close)
        self.latest_open = bar.open

        # 更新滚动窗口
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
            return None
        return np.mean(list(data)[-window:])

    def get_rolling_std(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            return None
        vals = list(data)[-window:]
        if len(vals) < 2:
            return None
        return np.std(vals, ddof=1)

    def get_rolling_max(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            return None
        return np.max(list(data)[-window:])

    def get_rolling_min(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            return None
        return np.min(list(data)[-window:])

    def get_rolling_sum(self, data: deque, window: int) -> Optional[float]:
        if len(data) < window:
            return None
        return np.sum(list(data)[-window:])

    def get_liquidity_ma(self, window: int) -> Optional[float]:
        if len(self.amount_history) < window:
            window = len(self.amount_history)
        if window == 0:
            return None
        return np.mean(list(self.amount_history)[-window:])


# ======================
# 策略类
# ======================
class FiveMomFactorLiveStrategy(StrategyBase):
    """5动量因子截面策略 - 支持 OKX / Binance"""

    def __init__(self, config: Dict[str, Any]):
        """初始化策略"""
        strategy_id = config.get("strategy_id", "five_mom_factor")
        trading_params = config.get("trading_params", {})
        history_bars = trading_params.get("history_bars", 200)

        # 日志配置
        log_config = config.get("logging", {})
        log_file = log_config.get("log_file", "")
        if not log_file:
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
        self.exchange = config.get("exchange", "binance").lower()
        self.api_key = config.get("api_key", "")
        self.secret_key = config.get("secret_key", "")
        self.passphrase = config.get("passphrase", "")
        self.is_testnet = config.get("is_testnet", True)

        # 交易对列表
        self.dynamic_symbols = config.get("dynamic_symbols", False)
        config_symbols = config.get("symbols", [])
        if self.dynamic_symbols or not config_symbols:
            self.symbols = []
        else:
            self.symbols = config_symbols

        # 交易参数
        self.interval = trading_params.get("interval", "8h")
        self.rebalance_interval_hours = trading_params.get("rebalance_interval_hours", 8)
        self.position_ratio = trading_params.get("position_ratio", 0.8)
        self.min_bars = trading_params.get("min_bars", 60)
        self.history_bars = history_bars
        self.leverage = trading_params.get("leverage", 1)

        # 因子参数
        factor_params = config.get("factor_params", {})
        self.lookback_20 = factor_params.get("lookback_window_20", 20)
        self.lookback_60 = factor_params.get("lookback_window_60", 60)
        self.liq_period = factor_params.get("liquidity_period", 60)
        self.liq_quantile = factor_params.get("liq_quantile", 0.2)
        self.ls_ratio = factor_params.get("long_short_ratio", 5)
        self.direction = factor_params.get("direction", "descending")

        # 内部状态
        self.ticker_data: Dict[str, TickerDataLive] = {}
        self.target_positions: Dict[str, float] = {}
        self.account_ready = False
        self.data_ready = False

        # 统计
        self.total_trades = 0
        self.rebalance_count = 0

        # 订单回报统计
        self.current_batch_orders = {}
        self.current_batch_filled = []
        self.current_batch_rejected = []

        # 调仓控制
        self.last_rebalance_ts = 0
        self.rebalance_interval_ms = self.rebalance_interval_hours * 60 * 60 * 1000

        # Redis 实时轮询控制（on_tick每次都查，无间隔限制）
        self.last_kline_timestamps: Dict[str, int] = {}
        # IPC触发Redis检查的冷却（毫秒级），避免同一tick内重复
        self.last_ipc_redis_check_ms = 0
        self.ipc_redis_cooldown_ms = 10  # 10ms冷却

        # 全币种K线同步控制
        self.symbol_periods: Dict[str, int] = {}
        self.last_rebalance_period = 0
        self.kline_sync_threshold = 0.8

        self.log_info(f"策略参数: {self.exchange.upper()} | K线周期:{self.interval} | 调仓间隔:{self.rebalance_interval_hours}小时")

    # ======================== 因子计算 ========================

    def _compute_alpha_077(self, data: TickerDataLive) -> Optional[float]:
        """alpha_077: (Close - LL20) / (HH20 - LL20)"""
        ll20 = data.get_rolling_min(data.low_history, self.lookback_20)
        hh20 = data.get_rolling_max(data.high_history, self.lookback_20)

        if ll20 is None or hh20 is None:
            return None

        rng20 = hh20 - ll20
        if rng20 == 0:
            return None

        return (data.latest_close - ll20) / rng20

    def _compute_alpha_078(self, data: TickerDataLive) -> Optional[float]:
        """alpha_078: (Close - LL60) / (HH60 - LL60)"""
        ll60 = data.get_rolling_min(data.low_history, self.lookback_60)
        hh60 = data.get_rolling_max(data.high_history, self.lookback_60)

        if ll60 is None or hh60 is None:
            return None

        rng60 = hh60 - ll60
        if rng60 == 0:
            return None

        return (data.latest_close - ll60) / rng60

    def _compute_alpha_094(self, data: TickerDataLive) -> Optional[float]:
        """alpha_094: (VWAP - MA20) / STD20"""
        vwap = data.get_vwap()
        ma20 = data.get_rolling_mean(data.close_history, self.lookback_20)
        std_c20 = data.get_rolling_std(data.close_history, self.lookback_20)

        if vwap is None or ma20 is None or std_c20 is None or std_c20 == 0:
            return None

        return (vwap - ma20) / std_c20

    def _compute_alpha_007(self, data: TickerDataLive) -> Optional[float]:
        """alpha_007: sum_ret_20 / std_ret_60"""
        sum_ret_20 = data.get_rolling_sum(data.ret_history, self.lookback_20)
        std_ret_60 = data.get_rolling_std(data.ret_history, self.lookback_60)

        if sum_ret_20 is None or std_ret_60 is None or std_ret_60 == 0:
            return None

        return sum_ret_20 / std_ret_60

    def _compute_alpha_080(self, data: TickerDataLive) -> Optional[float]:
        """alpha_080: (HH20 - Close) / (HH20 - LL20)"""
        ll20 = data.get_rolling_min(data.low_history, self.lookback_20)
        hh20 = data.get_rolling_max(data.high_history, self.lookback_20)

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

        # 计算5个因子值
        alpha_077_vals = {}
        alpha_078_vals = {}
        alpha_094_vals = {}
        alpha_007_vals = {}
        alpha_080_vals = {}
        liquidity_vals = {}

        for symbol in ready_tickers:
            data = self.ticker_data[symbol]
            alpha_077_vals[symbol] = self._compute_alpha_077(data)
            alpha_078_vals[symbol] = self._compute_alpha_078(data)
            alpha_094_vals[symbol] = self._compute_alpha_094(data)
            alpha_007_vals[symbol] = self._compute_alpha_007(data)
            alpha_080_vals[symbol] = self._compute_alpha_080(data)
            liquidity_vals[symbol] = data.get_liquidity_ma(self.liq_period)

        # Z-score标准化
        alpha_077_z = self._zscore(alpha_077_vals)
        alpha_078_z = self._zscore(alpha_078_vals)
        alpha_094_z = self._zscore(alpha_094_vals)
        alpha_007_z = self._zscore(alpha_007_vals)
        alpha_080_z = self._zscore(alpha_080_vals)

        # 组合因子: al = alpha_077 + alpha_078 + alpha_094 + alpha_007 - alpha_080
        al_values = {}
        for symbol in ready_tickers:
            a077 = alpha_077_z.get(symbol)
            a078 = alpha_078_z.get(symbol)
            a094 = alpha_094_z.get(symbol)
            a007 = alpha_007_z.get(symbol)
            a080 = alpha_080_z.get(symbol)

            if any(v is None for v in [a077, a078, a094, a007, a080]):
                continue
            if any(not np.isfinite(v) for v in [a077, a078, a094, a007, a080]):
                continue

            al_values[symbol] = a077 + a078 + a094 + a007 - a080

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
        """预设所有交易对的杠杆倍数 - 多线程并发"""
        self.log_info(f"[杠杆预设] 开始为 {len(self.symbols)} 个交易对设置 {self.leverage}x 杠杆...")

        success_count = 0
        fail_count = 0

        def set_leverage(symbol):
            try:
                result = self.change_leverage(symbol, self.leverage, self.exchange)
                return (symbol, result, None)
            except Exception as e:
                return (symbol, False, str(e))

        # 使用线程池并发设置杠杆
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(set_leverage, symbol) for symbol in self.symbols]
            for future in as_completed(futures):
                symbol, result, error = future.result()
                if result:
                    success_count += 1
                else:
                    fail_count += 1
                    if error:
                        self.log_error(f"[杠杆预设] {symbol} 异常: {error}")
                    else:
                        self.log_error(f"[杠杆预设] {symbol} 设置失败")

        self.log_info(f"[杠杆预设] 完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    def _get_contract_multiplier(self, symbol: str) -> float:
        """获取合约乘数"""
        if self.exchange == "okx":
            if "BTC" in symbol:
                return 0.01
            elif "ETH" in symbol:
                return 0.1
            else:
                return 1.0
        else:
            return 1.0

    def _check_initial_rebalance(self):
        """启动时不调仓，只记录当前周期状态，等待新K线到达后再调仓"""
        from datetime import datetime

        current_ts = int(time.time() * 1000)
        ts_str = datetime.fromtimestamp(current_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
        current_period = current_ts // self.rebalance_interval_ms

        # 记录历史数据中最新K线所在的周期
        data_period = 0
        if self.symbol_periods:
            data_period = max(self.symbol_periods.values())

        # 将 last_rebalance_period 设为历史数据的周期，这样只有新周期的K线到达时才会触发调仓
        self.last_rebalance_period = data_period

        next_rebalance_ts = (data_period + 1) * self.rebalance_interval_ms
        next_ts_str = datetime.fromtimestamp(next_rebalance_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

        self.log_info(f"[启动检查] 账户和数据都已就绪")
        self.log_info(f"[启动检查] 当前时间: {ts_str} | 当前周期: {current_period} | 数据最新周期: {data_period}")
        self.log_info(f"[启动检查] 启动时不调仓，等待新8h K线到达后触发调仓")
        self.log_info(f"[启动检查] 下次调仓预计: {next_ts_str}")

    def _execute_rebalance(self):
        """执行调仓 - 基于Delta的精确调仓（支持连续持仓再平衡）"""
        target_positions = self._compute_target_positions()

        if not target_positions:
            self.log_info("[调仓] 无有效目标仓位，跳过")
            return

        self.target_positions = target_positions
        self.rebalance_count += 1

        self.current_batch_orders = {}
        self.current_batch_filled = []
        self.current_batch_rejected = []

        # 获取当前持仓
        current_positions = {}
        for pos in self.get_active_positions():
            if pos.symbol in self.symbols and pos.quantity != 0:
                current_positions[pos.symbol] = pos.quantity

        # 获取账户权益
        usdt_available = self.get_total_equity()
        equity = usdt_available * self.position_ratio

        # 计算目标持仓数
        target_n_long = sum(1 for w in target_positions.values() if w > 0)
        target_n_short = sum(1 for w in target_positions.values() if w < 0)
        target_total = target_n_long + target_n_short

        if target_total == 0:
            self.log_info("[调仓] 目标持仓数为0，跳过")
            return

        # 每个仓位分配等额资金
        per_position_value = equity / target_total

        self.log_info("=" * 50)
        self.log_info(f"[调仓#{self.rebalance_count}] 开始执行 (Delta调仓模式)")
        self.log_info(f"[账户] USDT余额: {usdt_available:.2f} | 每仓位资金: {per_position_value:.2f} USDT")
        self.log_info(f"[目标持仓] 多头 {target_n_long}个, 空头 {target_n_short}个")

        # 优化批次大小：Binance限速为10秒300单，使用50完全安全
        batch_size = 50 if self.exchange == "binance" else 20

        # 计算所有标的的目标数量和Delta
        all_symbols = set(list(current_positions.keys()) + list(target_positions.keys()))

        adjust_orders = []  # 所有调整订单（包括平仓、开仓、加减仓）

        for symbol in all_symbols:
            current_qty = current_positions.get(symbol, 0)
            target_weight = target_positions.get(symbol, 0)

            # 计算目标数量
            if target_weight == 0:
                target_qty = 0
            else:
                if symbol not in self.ticker_data or self.ticker_data[symbol].latest_close is None:
                    self.log_error(f"[跳过] {symbol} 无K线数据")
                    continue

                price = self.ticker_data[symbol].latest_close
                if price <= 0:
                    self.log_error(f"[跳过] {symbol} 价格异常: {price}")
                    continue

                multiplier = self._get_contract_multiplier(symbol)

                if self.exchange == "okx":
                    target_qty = int(per_position_value / (price * multiplier))
                    if target_qty < 1:
                        target_qty = 1
                    # OKX的多空用正负号表示
                    if target_weight < 0:
                        target_qty = -target_qty
                else:
                    target_qty = self.calculate_order_quantity(self.exchange, symbol, per_position_value, price)
                    if target_qty <= 0:
                        self.log_error(f"[跳过] {symbol} 计算下单数量失败")
                        continue
                    # Binance的多空用正负号表示
                    if target_weight < 0:
                        target_qty = -target_qty

            # 计算Delta
            delta_qty = target_qty - current_qty

            if delta_qty == 0:
                continue  # 无需调整

            # 判断操作类型和方向
            if target_qty == 0:
                # 完全平仓
                side = "SELL" if current_qty > 0 else "BUY"
                pos_side = "LONG" if current_qty > 0 else "SHORT"
                action_type = "平仓"
            elif current_qty == 0:
                # 新开仓
                side = "BUY" if target_qty > 0 else "SELL"
                pos_side = "LONG" if target_qty > 0 else "SHORT"
                action_type = "开仓"
            elif (current_qty > 0 and target_qty > 0) or (current_qty < 0 and target_qty < 0):
                # 同方向调整（加仓或减仓）
                if abs(target_qty) > abs(current_qty):
                    # 加仓
                    side = "BUY" if target_qty > 0 else "SELL"
                    pos_side = "LONG" if target_qty > 0 else "SHORT"
                    action_type = "加仓"
                else:
                    # 减仓
                    side = "SELL" if current_qty > 0 else "BUY"
                    pos_side = "LONG" if current_qty > 0 else "SHORT"
                    action_type = "减仓"
            else:
                # 反向调整（先平后开）- 需要分两步
                # 第一步：平掉当前仓位
                adjust_orders.append({
                    "symbol": symbol,
                    "side": "SELL" if current_qty > 0 else "BUY",
                    "quantity": abs(current_qty),
                    "pos_side": "LONG" if current_qty > 0 else "SHORT",
                    "type": "MARKET",
                    "action_type": "平仓(反向)"
                })
                # 第二步：开新仓位
                adjust_orders.append({
                    "symbol": symbol,
                    "side": "BUY" if target_qty > 0 else "SELL",
                    "quantity": abs(target_qty),
                    "pos_side": "LONG" if target_qty > 0 else "SHORT",
                    "type": "MARKET",
                    "action_type": "开仓(反向)",
                    "target_value": per_position_value,
                    "price": price,
                    "weight": target_weight
                })
                self.log_info(f"[反向调仓] {symbol} | {current_qty} -> {target_qty} (先平后开)")
                continue

            adjust_orders.append({
                "symbol": symbol,
                "side": side,
                "quantity": abs(delta_qty),
                "pos_side": pos_side,
                "type": "MARKET",
                "action_type": action_type,
                "target_value": per_position_value if target_qty != 0 else 0,
                "price": self.ticker_data[symbol].latest_close if symbol in self.ticker_data else 0,
                "weight": target_weight,
                "current_qty": current_qty,
                "target_qty": target_qty
            })

            direction = "多" if target_weight > 0 else ("空" if target_weight < 0 else "平")
            self.log_info(f"[{action_type}] {symbol} | {direction} {current_qty} -> {target_qty} (Delta: {delta_qty:+.0f})")

        # 执行所有调整订单 - 使用多线程并发发送
        if adjust_orders:
            self.log_info(f"[调仓] 共 {len(adjust_orders)} 个订单，并发发送...")

            def send_adjust_batch(batch_orders):
                batch_for_send = [{
                    "symbol": o["symbol"],
                    "side": o["side"],
                    "quantity": o["quantity"],
                    "pos_side": o["pos_side"],
                    "order_type": o["type"]
                } for o in batch_orders]
                self.send_batch_orders(batch_for_send, self.exchange)
                return len(batch_orders)

            # 多线程并发发送所有批次
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for i in range(0, len(adjust_orders), batch_size):
                    batch = adjust_orders[i:i+batch_size]
                    futures.append(executor.submit(send_adjust_batch, batch))

                for future in as_completed(futures):
                    count = future.result()
                    self.total_trades += count

            # 等待订单回报
            max_wait_time = 10.0
            check_interval = 0.5
            elapsed = 0.0

            while elapsed < max_wait_time:
                time.sleep(check_interval)
                elapsed += check_interval
                filled_count = len(self.current_batch_filled)
                rejected_count = len(self.current_batch_rejected)
                if filled_count + rejected_count >= len(adjust_orders):
                    break

            self.log_info(f"[调仓#{self.rebalance_count}] 完成: 总订单 {len(adjust_orders)} 个, 成交 {filled_count} 个, 拒绝 {rejected_count} 个")
        else:
            self.log_info(f"[调仓#{self.rebalance_count}] 无需调整，保持现有仓位")

    def _fetch_all_symbols(self) -> List[str]:
        """动态获取全市场USDT永续合约标的"""
        try:
            self.log_info(f"[币种池] 从 {self.exchange.upper()} 获取全市场永续合约...")
            all_symbols = self.get_available_historical_symbols(self.exchange)

            if all_symbols:
                if self.exchange == "okx":
                    symbols = [s for s in all_symbols if s.endswith("-USDT-SWAP")]
                else:
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
        print("  5动量因子截面策略 (Five Momentum Factor) - 初始化")
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

        # 3. 动态获取全市场标的
        if self.dynamic_symbols or not self.symbols:
            self.symbols = self._fetch_all_symbols()
            if not self.symbols:
                self.log_error("[初始化] 无法获取标的列表，程序终止")
                return

        # 4. 加载最小下单单位配置
        if self.exchange == "binance":
            self.log_info("[初始化] 加载 Binance 最小下单单位配置...")
            configs_dir = os.path.join(STRATEGIES_DIR, "configs")
            if not self.load_min_order_config("binance", configs_dir):
                self.log_error("[初始化] 加载 Binance 最小下单单位配置失败")

        # 5. 预设杠杆倍数
        #if self.exchange == "binance" and self.leverage > 0:
        #    self._preload_leverage()

        # 6. 订阅K线并初始化数据存储
        # 动态计算最大回看周期，确保deque足够大
        max_lookback = max(self.lookback_20, self.lookback_60, self.liq_period) + 20
        for symbol in self.symbols:
            self.subscribe_kline(symbol, self.interval)
            self.ticker_data[symbol] = TickerDataLive(min_bars=self.min_bars, lookback=max_lookback)

        self.log_info(f"[初始化] 已订阅 {len(self.symbols)} 个标的，K线周期: {self.interval}")

        # 7. 从 Redis 加载历史 K 线数据
        if redis_connected:
            self._load_historical_data()

        print("=" * 60)

    def _load_historical_data(self):
        """从 Redis 加载历史 K 线数据"""
        self.log_info(f"[历史数据] 开始从 Redis 加载历史 8h K 线...")
        loaded_count = 0
        ready_count = 0

        end_time = int(time.time() * 1000)
        start_time = end_time - self.history_bars * self.rebalance_interval_hours * 60 * 60 * 1000

        for symbol in self.symbols:
            try:
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
                        bar = KlineBar()
                        bar.open = float(kline.open)
                        bar.high = float(kline.high)
                        bar.low = float(kline.low)
                        bar.close = float(kline.close)
                        bar.volume = float(kline.volume)
                        bar.timestamp = int(kline.timestamp)
                        data.add_bar(bar)

                    # 记录最新K线时间戳和周期，避免on_tick重复处理
                    latest_ts = int(klines[-1].timestamp)
                    self.last_kline_timestamps[symbol] = latest_ts
                    self.symbol_periods[symbol] = latest_ts // self.rebalance_interval_ms

                    loaded_count += 1
                    if data.bar_count >= self.min_bars:
                        ready_count += 1

            except Exception as e:
                if loaded_count < 5:
                    self.log_error(f"[历史数据] {symbol} 加载失败: {e}")

        self.log_info(f"[历史数据] 加载完成: {loaded_count}/{len(self.symbols)} 个标的 | {ready_count} 个已就绪")

        if ready_count >= len(self.symbols) * 0.5:
            self.data_ready = True
            self.log_info(f"[历史数据] 数据就绪，等待账户余额回调后开始调仓")
        else:
            self.log_info(f"[历史数据] 数据不足，需要等待实时 8h K 线收集 (需要 {self.min_bars} 根8h K线)")

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] 5动量因子截面策略停止")
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
        self.log_info(f"[余额回调] 币种: {balance.currency}, 可用: {balance.available:.4f}")

        if balance.currency == "USDT" and not self.account_ready:
            self.account_ready = True
            self.log_info(f"[账户] 余额就绪, USDT可用: {balance.available:.2f}")

            if self.data_ready:
                self._check_initial_rebalance()

    def on_position_update(self, position):
        """持仓更新回调"""
        if position.symbol in self.symbols and position.quantity != 0:
            self.log_info(f"[持仓] {position.symbol} {position.quantity}张 盈亏: {position.unrealized_pnl:.2f}")

    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调 - IPC收到新K线时，检查Redis中8h数据是否齐全，齐全则触发调仓"""
        if symbol not in self.ticker_data:
            return

        if interval != self.interval:
            return

        data = self.ticker_data[symbol]
        data.add_bar(bar)

        # 记录该币种当前所在的8h周期
        current_period = bar.timestamp // self.rebalance_interval_ms
        self.symbol_periods[symbol] = current_period

        # 检查数据是否就绪
        if not self.data_ready:
            ready_count = sum(1 for s in self.symbols
                           if s in self.ticker_data and self.ticker_data[s].bar_count >= self.min_bars)
            total = len(self.symbols)

            total_bars = sum(self.ticker_data[s].bar_count for s in self.symbols if s in self.ticker_data)
            if total_bars % 100 == 0:
                avg_bars = total_bars / total if total > 0 else 0
                self.log_info(f"[数据收集] 进度: {ready_count}/{total} 标的就绪 | 平均K线数: {avg_bars:.0f}/{self.min_bars}")

            if ready_count >= total * 0.8:
                self.data_ready = True
                self.log_info(f"[数据] 就绪，{ready_count}/{total} 个标的已准备好")

        # 检查是否可以触发调仓
        if not self.account_ready or not self.data_ready:
            return

        if current_period <= self.last_rebalance_period:
            return

        # IPC收到新周期K线，触发Redis检查补全所有币种数据
        self._check_redis_and_rebalance(current_period)

    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        client_order_id = report.get("client_order_id", "")

        if status == "filled":
            filled_qty = report.get("filled_quantity", "0")
            filled_price = report.get("filled_price", "0")
            try:
                filled_qty = float(filled_qty) if filled_qty else 0
                filled_price = float(filled_price) if filled_price else 0
            except (ValueError, TypeError):
                filled_qty = 0
                filled_price = 0

            self.log_info(f"[成交] {symbol} {side} {filled_qty} @ {filled_price:.4f}")

            self.current_batch_filled.append({
                "symbol": symbol,
                "side": side,
                "quantity": filled_qty,
                "price": filled_price,
                "order_id": client_order_id
            })

        elif status == "rejected":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] {symbol} {side} | 原因: {error_msg}")

            self.current_batch_rejected.append({
                "symbol": symbol,
                "side": side,
                "error_msg": error_msg,
                "order_id": client_order_id
            })
        else:
            self.log_info(f"[订单] {symbol} {side} | 状态: {status}")

    def _check_redis_and_rebalance(self, current_period: int):
        """IPC触发：检查Redis中8h K线数据是否齐全，齐全则调仓"""
        current_ms = int(time.time() * 1000)

        # 毫秒级冷却，避免同一批IPC回调重复查Redis
        if current_ms - self.last_ipc_redis_check_ms < self.ipc_redis_cooldown_ms:
            return

        self.last_ipc_redis_check_ms = current_ms

        # 先看IPC已收到多少币种的当前周期数据
        total_symbols = len(self.symbols)
        ipc_arrived = sum(1 for s, p in self.symbol_periods.items() if p >= current_period)
        ipc_ratio = ipc_arrived / total_symbols if total_symbols > 0 else 0

        self.log_info(f"[IPC触发] 周期{current_period} | IPC已到达: {ipc_arrived}/{total_symbols} ({ipc_ratio*100:.1f}%) | 开始查Redis补全")

        # 查Redis补全未通过IPC到达的币种
        updated_symbols = 0
        query_errors = 0

        for symbol in self.symbols:
            # 已通过IPC到达当前周期的币种跳过
            if self.symbol_periods.get(symbol, 0) >= current_period:
                continue

            try:
                end_time = int(time.time() * 1000)
                start_time = end_time - 5 * self.rebalance_interval_hours * 60 * 60 * 1000

                klines = self.get_historical_klines(
                    symbol=symbol,
                    exchange=self.exchange,
                    interval=self.interval,
                    start_time=start_time,
                    end_time=end_time
                )

                if not klines or len(klines) == 0:
                    continue

                latest_kline = klines[-1]
                latest_ts = int(latest_kline.timestamp)

                last_known_ts = self.last_kline_timestamps.get(symbol, 0)
                if latest_ts > last_known_ts:
                    data = self.ticker_data.get(symbol)
                    if data:
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
                        updated_symbols += 1

                        redis_period = latest_ts // self.rebalance_interval_ms
                        self.symbol_periods[symbol] = redis_period

            except Exception as e:
                query_errors += 1
                if query_errors <= 3:
                    self.log_error(f"[Redis补全] {symbol} 查询异常: {e}")

        # 统计补全后的同步率
        arrived_count = sum(1 for s, p in self.symbol_periods.items() if p >= current_period)
        sync_ratio = arrived_count / total_symbols if total_symbols > 0 else 0

        self.log_info(f"[Redis补全] Redis补全 {updated_symbols} 个 | 错误 {query_errors} | 同步率: {arrived_count}/{total_symbols} ({sync_ratio*100:.1f}%)")

        if sync_ratio >= self.kline_sync_threshold:
            from datetime import datetime
            new_kline_ts = current_period * self.rebalance_interval_ms
            ts_str = datetime.fromtimestamp(new_kline_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            self.log_info(f"[调仓触发] 8h K线齐全 | 时间: {ts_str} | 触发调仓")
            self.last_rebalance_period = current_period
            self.last_rebalance_ts = new_kline_ts
            self._execute_rebalance()

    def on_tick(self):
        """定时回调 - C++ Pipeline批量查Redis检测新8h K线（<1ms）"""
        if not self.account_ready or not self.data_ready:
            return

        # C++ Lua脚本批量获取所有币种最新K线时间戳（单次EVALSHA，<0.5ms）
        try:
            latest_ts_map = self.lua_batch_get_latest_timestamps(
                self.symbols, self.exchange, self.interval
            )
        except Exception:
            return

        if not latest_ts_map:
            return

        # 检测哪些币种有新数据
        changed_symbols = []
        new_kline_ts = 0

        for symbol, latest_ts in latest_ts_map.items():
            last_known_ts = self.last_kline_timestamps.get(symbol, 0)
            if latest_ts > last_known_ts:
                changed_symbols.append(symbol)
                if latest_ts > new_kline_ts:
                    new_kline_ts = latest_ts

        if not changed_symbols:
            return

        # 只对有变化的币种拉取完整K线数据
        for symbol in changed_symbols:
            try:
                end_time = int(time.time() * 1000)
                start_time = end_time - 5 * self.rebalance_interval_hours * 60 * 60 * 1000

                klines = self.get_historical_klines(
                    symbol=symbol,
                    exchange=self.exchange,
                    interval=self.interval,
                    start_time=start_time,
                    end_time=end_time
                )

                if not klines or len(klines) == 0:
                    continue

                last_known_ts = self.last_kline_timestamps.get(symbol, 0)
                latest_ts = int(klines[-1].timestamp)

                data = self.ticker_data.get(symbol)
                if data:
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
                    self.symbol_periods[symbol] = latest_ts // self.rebalance_interval_ms

            except Exception:
                pass

        # 检查是否需要调仓
        if new_kline_ts > 0:
            current_period = new_kline_ts // self.rebalance_interval_ms

            if current_period <= self.last_rebalance_period:
                return

            total_symbols = len(self.symbols)
            arrived_count = sum(1 for s, p in self.symbol_periods.items() if p >= current_period)
            sync_ratio = arrived_count / total_symbols if total_symbols > 0 else 0

            if sync_ratio >= self.kline_sync_threshold:
                from datetime import datetime
                ts_str = datetime.fromtimestamp(new_kline_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                self.log_info(f"[Redis轮询] 发现新8h K线 | 时间: {ts_str} | 同步率: {arrived_count}/{total_symbols} ({sync_ratio*100:.1f}%) | 触发调仓")
                self.last_rebalance_period = current_period
                self.last_rebalance_ts = new_kline_ts
                self._execute_rebalance()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="5动量因子截面策略")
    parser.add_argument("--config", default="five_mom_factor_config.json", help="配置文件路径")
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
    strategy = FiveMomFactorLiveStrategy(config)

    # 打印信息
    print("=" * 60)
    print("  5动量因子截面策略 (Five Momentum Factor) - 实盘版本")
    print("=" * 60)
    print()
    print(f"交易所: {strategy.exchange.upper()} {'(测试网)' if strategy.is_testnet else '(主网)'}")
    print(f"标的数: {len(strategy.symbols)}")
    print(f"K线周期: {strategy.interval} | 调仓间隔: {strategy.rebalance_interval_hours}小时")
    print(f"仓位比例: {strategy.position_ratio * 100:.0f}%")
    print()
    print(f"因子参数: lookback_20={strategy.lookback_20}, lookback_60={strategy.lookback_60}")
    print(f"流动性过滤: liq_quantile={strategy.liq_quantile}, 多空比例: 1/{strategy.ls_ratio}")
    print()
    print("-" * 60)

    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()
