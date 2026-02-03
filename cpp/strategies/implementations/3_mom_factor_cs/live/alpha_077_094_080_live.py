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
            "interval": "1m",
            "position_ratio": 1,  # 仓位比例，占账户余额的比例
            "min_bars": 120,
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
        self.interval = trading_params.get("interval", "1m")
        self.position_ratio = trading_params.get("position_ratio", 0.8)  # 仓位比例，占账户余额的比例
        self.min_bars = trading_params.get("min_bars", 120)
        self.history_bars = history_bars

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

        self.log_info(f"策略参数: {self.exchange.upper()} | {len(self.symbols)}个标的 | K线周期:{self.interval}")

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

    def _execute_rebalance(self):
        """执行调仓"""
        target_positions = self._compute_target_positions()

        if not target_positions:
            return

        self.target_positions = target_positions
        self.rebalance_count += 1

        # 获取账户余额
        usdt_available = self.get_usdt_available()
        total_position_value = usdt_available * self.position_ratio

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
        self.log_info(f"[账户] USDT余额: {usdt_available:.2f} | 总仓位: {total_position_value:.2f} USDT")
        self.log_info(f"[多头] {len(long_symbols)}个: {[s for s, _ in long_symbols]}")
        self.log_info(f"[空头] {len(short_symbols)}个: {[s for s, _ in short_symbols]}")

        # 执行调仓
        for symbol, weight in target_positions.items():
            last_kline = self.get_last_kline(symbol, self.interval)
            if last_kline is None:
                self.log_error(f"[跳过] {symbol} 无K线数据")
                continue

            price = last_kline.close
            if price <= 0:
                self.log_error(f"[跳过] {symbol} 价格异常: {price}")
                continue

            # 计算目标仓位: 总仓位 × 权重
            target_value = total_position_value * abs(weight)
            multiplier = self._get_contract_multiplier(symbol)

            if self.exchange == "okx":
                target_qty = int(target_value / (price * multiplier))
                if target_qty < 1:
                    target_qty = 1
            else:
                target_qty = round(target_value / price, 4)
                if target_qty < 0.001:
                    target_qty = 0.001

            # 当前持仓
            current_qty = current_positions.get(symbol, 0)

            # 先平仓
            if current_qty != 0:
                close_side = "sell" if current_qty > 0 else "buy"
                close_qty = abs(current_qty)

                if self.exchange == "okx":
                    pos_side = "long" if current_qty > 0 else "short"
                    order_id = self.send_swap_market_order(symbol, close_side, int(close_qty), pos_side)
                else:
                    order_id = self.send_binance_futures_market_order(
                        symbol=symbol,
                        side=close_side,
                        quantity=close_qty,
                        pos_side="BOTH"
                    )
                self.log_info(f"[平仓] {symbol} | {close_side} {close_qty}张 | 订单ID: {order_id}")

            # 再开仓
            if weight != 0:
                open_side = "buy" if weight > 0 else "sell"
                direction = "多" if weight > 0 else "空"

                if self.exchange == "okx":
                    pos_side = "long" if weight > 0 else "short"
                    order_id = self.send_swap_market_order(symbol, open_side, target_qty, pos_side)
                else:
                    order_id = self.send_binance_futures_market_order(
                        symbol=symbol,
                        side=open_side,
                        quantity=target_qty,
                        pos_side="BOTH"
                    )
                self.log_info(f"[开仓] {symbol} | {direction} {target_qty}张 @ {price:.4f} | 价值: {target_value:.2f} USDT | 权重: {weight:.4f} | 订单ID: {order_id}")
                self.total_trades += 1

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

        # 4. 订阅K线并初始化数据存储
        for symbol in self.symbols:
            self.subscribe_kline(symbol, self.interval)
            self.ticker_data[symbol] = TickerDataLive(min_bars=self.min_bars)

        self.log_info(f"[初始化] 已订阅 {len(self.symbols)} 个标的，K线周期: {self.interval}")

        # 5. 从 Redis 加载历史 K 线数据
        if redis_connected:
            self._load_historical_data()

        print("=" * 60)

    def _load_historical_data(self):
        """从 Redis 加载历史 K 线数据"""
        self.log_info(f"[历史数据] 开始从 Redis 加载历史 K 线...")
        loaded_count = 0
        ready_count = 0

        for symbol in self.symbols:
            try:
                # 获取历史 K 线 (最近 history_bars 根)
                klines = self.get_historical_klines(
                    symbol=symbol,
                    exchange=self.exchange,
                    interval=self.interval,
                    limit=self.history_bars
                )

                if klines and len(klines) > 0:
                    data = self.ticker_data[symbol]
                    for kline in klines:
                        # 创建 KlineBar 对象
                        bar = KlineBar()
                        bar.open = float(kline.get("open", 0))
                        bar.high = float(kline.get("high", 0))
                        bar.low = float(kline.get("low", 0))
                        bar.close = float(kline.get("close", 0))
                        bar.volume = float(kline.get("volume", 0))
                        bar.timestamp = int(kline.get("timestamp", 0))
                        data.add_bar(bar)

                    loaded_count += 1
                    if data.bar_count >= self.min_bars:
                        ready_count += 1

            except Exception as e:
                self.log_error(f"[历史数据] {symbol} 加载失败: {e}")

        self.log_info(f"[历史数据] 加载完成: {loaded_count}/{len(self.symbols)} 个标的 | {ready_count} 个已就绪")

        # 检查是否有足够的数据
        if ready_count >= len(self.symbols) * 0.5:
            self.data_ready = True
            self.log_info(f"[历史数据] 数据就绪，可以开始调仓")
        else:
            self.log_info(f"[历史数据] 数据不足，需要等待实时 K 线收集 (需要 {self.min_bars} 根)")

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

    def on_position_update(self, position):
        """持仓更新回调"""
        if position.symbol in self.symbols and position.quantity != 0:
            self.log_info(f"[持仓] {position.symbol} {position.quantity}张 盈亏: {position.unrealized_pnl:.2f}")

    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调 - 每根K线到来时触发调仓（与源码on_time_event一致）"""
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
            if total_bars % 500 == 0:  # 每500根K线打印一次
                avg_bars = total_bars / total if total > 0 else 0
                self.log_info(f"[数据收集] 进度: {ready_count}/{total} 标的就绪 | 平均K线数: {avg_bars:.0f}/{self.min_bars}")

            if ready_count >= total * 0.8:
                self.data_ready = True
                self.log_info(f"[数据] 就绪，{ready_count}/{total} 个标的已准备好，开始调仓")

        # 每根K线到来时执行调仓（与源码on_time_event一致）
        if self.account_ready and self.data_ready:
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
    print(f"K线周期: {strategy.interval} (每根K线触发调仓)")
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
