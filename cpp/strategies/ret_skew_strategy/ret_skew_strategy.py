#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RetSkew 因子策略 - 实盘版本

基于收益率偏度因子的交易策略
公式: ts_ema(clip(ts_zscore(ts_skew(returns(close, 1), 600), 14400), -3, 3), 2)

数据来源: Redis (由 data_recorder 实时录入)
交易接口: C++ StrategyBase (支持 OKX / Binance)

运行方式:
    # 使用配置文件
    python ret_skew_strategy.py --config config.json

    # 命令行参数 (覆盖配置文件)
    python ret_skew_strategy.py --config config.json --symbol ETH-USDT-SWAP

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
from typing import Optional, Dict, Any

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, STRATEGIES_DIR)

# 导入 C++ 策略基类 (已封装 HistoricalDataModule，提供 Redis 历史数据接口)
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
        "strategy_id": "ret_skew_strategy",
        "exchange": "okx",
        "api_key": "",
        "secret_key": "",
        "passphrase": "",
        "is_testnet": True,
        "symbols": ["BTC-USDT-SWAP"],
        "factor_params": {
            "skew_window": 600,
            "zscore_window": 14400,
            "ema_alpha": 2.0,
            "signal_threshold": 2.0
        },
        "trading_params": {
            "position_size_usdt": 100,
            "interval": "1m",
            "history_bars": 15000
        },
        "redis": {
            "host": "127.0.0.1",
            "port": 6379,
            "password": ""
        },
        "risk_control": {
            "enabled": False,
            "max_position_value": 10000,
            "max_daily_loss": 1000
        }
    }


# ======================
# 因子计算类
# ======================
class RetSkewCalculator:
    """
    收益率偏度因子计算器 (增量计算)

    公式: ts_ema(clip(ts_zscore(ts_skew(returns(close, 1), 600), 14400), -3, 3), 2)
    """

    def __init__(
        self,
        skew_window: int = 600,
        zscore_window: int = 14400,
        ema_alpha: float = 2.0,
        signal_threshold: float = 2.0
    ):
        self.skew_window = skew_window
        self.zscore_window = zscore_window
        self.ema_alpha = ema_alpha
        self.signal_threshold = signal_threshold

        # 数据缓存
        self.closes: deque = deque(maxlen=zscore_window + skew_window + 100)
        self.returns: deque = deque(maxlen=zscore_window + skew_window + 100)
        self.skews: deque = deque(maxlen=zscore_window + 100)

        # EMA 状态
        self.ema_value: Optional[float] = None
        self.last_factor_value: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        """更新因子值 (增量计算)"""
        self.closes.append(close)

        # 计算收益率
        if len(self.closes) >= 2:
            ret = (self.closes[-1] / self.closes[-2]) - 1
            self.returns.append(ret)
        else:
            return None

        # 计算滚动偏度
        if len(self.returns) >= self.skew_window:
            returns_arr = np.array(list(self.returns)[-self.skew_window:])
            skew = self._calc_skewness(returns_arr)
            self.skews.append(skew)
        else:
            return None

        # 计算 Z-score (必须有足够的 zscore_window 数据)
        if len(self.skews) >= self.zscore_window:
            skews_arr = np.array(list(self.skews)[-self.zscore_window:])
            zscore = self._calc_zscore(self.skews[-1], skews_arr)
        else:
            return None

        # Clip 到 [-3, 3]
        clipped = np.clip(zscore, -3, 3)

        # EMA 平滑
        if self.ema_value is None:
            self.ema_value = clipped
        else:
            alpha = 2.0 / (self.ema_alpha + 1)
            self.ema_value = alpha * clipped + (1 - alpha) * self.ema_value

        self.last_factor_value = self.ema_value
        return self.ema_value

    def get_signal(self) -> int:
        """获取交易信号: 1=做多, -1=做空, 0=无信号"""
        if self.last_factor_value is None:
            return 0

        if self.last_factor_value > self.signal_threshold:
            return 1
        elif self.last_factor_value < -self.signal_threshold:
            return -1
        else:
            return 0

    def _calc_skewness(self, arr: np.ndarray) -> float:
        """计算偏度"""
        n = len(arr)
        if n < 3:
            return 0.0
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        if std == 0:
            return 0.0
        return np.mean(((arr - mean) / std) ** 3)

    def _calc_zscore(self, value: float, arr: np.ndarray) -> float:
        """计算 Z-score"""
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        if std == 0:
            return 0.0
        return (value - mean) / std


# ======================
# 策略类
# ======================
class RetSkewStrategy(StrategyBase):
    """RetSkew 因子交易策略 - 使用 Redis 数据源和 C++ 交易接口"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化策略

        Args:
            config: 配置字典
        """
        # 提取配置
        strategy_id = config.get("strategy_id", "ret_skew_strategy")
        trading_params = config.get("trading_params", {})
        history_bars = trading_params.get("history_bars", 15000)
        log_file = config.get("logging", {}).get("log_file", "")

        super().__init__(
            strategy_id,
            max_kline_bars=history_bars + 100,
            log_file_path=log_file
        )
        # self._set_python_self(self)  # 注释掉，可能导致问题

        # 保存配置
        self.config = config

        # 交易所配置
        self.exchange = config.get("exchange", "okx").lower()
        self.api_key = config.get("api_key", "")
        self.secret_key = config.get("secret_key", "")
        self.passphrase = config.get("passphrase", "")
        self.is_testnet = config.get("is_testnet", True)

        # 交易对
        symbols = config.get("symbols", ["BTC-USDT-SWAP"])
        self.symbol = symbols[0] if symbols else "BTC-USDT-SWAP"

        # 交易参数
        self.position_size_usdt = trading_params.get("position_size_usdt", 100)
        self.position_ratio = trading_params.get("position_ratio", 0.3)  # 仓位比例，默认30%
        self.interval = trading_params.get("interval", "1m")
        self.history_bars = history_bars

        # 因子参数
        factor_params = config.get("factor_params", {})
        self.skew_window = factor_params.get("skew_window", 600)
        self.zscore_window = factor_params.get("zscore_window", 14400)
        self.ema_alpha = factor_params.get("ema_alpha", 2.0)
        self.signal_threshold = factor_params.get("signal_threshold", 2.0)

        # 风控配置
        self.risk_control = config.get("risk_control", {})

        # 因子计算器
        self.factor_calc = RetSkewCalculator(
            skew_window=self.skew_window,
            zscore_window=self.zscore_window,
            ema_alpha=self.ema_alpha,
            signal_threshold=self.signal_threshold
        )

        # 状态
        self.account_ready = False
        self.data_ready = False
        self.current_position = 0
        self.current_price = 0.0

        # 订单状态跟踪
        self.pending_position = None  # 待确认的持仓方向 (1=多, -1=空, 0=平仓)
        self.last_order_error = ""    # 最近一次订单失败原因
        self.last_order_error_time = 0  # 最近一次订单失败时间戳

        # 统计
        self.total_trades = 0
        self.long_trades = 0
        self.short_trades = 0

        self.log_info(f"策略参数: {self.exchange.upper()} | {self.symbol} | 阈值:{self.signal_threshold} | 仓位比例:{self.position_ratio*100:.0f}%")

    def _warmup_factor(self) -> bool:
        """预热因子计算器 - 使用基类的历史数据接口"""
        self.log_info("[预热] 从 Redis 获取历史数据...")

        # 使用基类提供的 get_latest_historical_klines 接口
        klines = self.get_latest_historical_klines(
            symbol=self.symbol,
            exchange=self.exchange,
            interval=self.interval,
            count=self.history_bars
        )

        if not klines:
            self.log_error(f"[Redis] 未获取到 {self.exchange}:{self.symbol} 的历史数据")
            return False

        # 提取收盘价
        closes = [kline.close for kline in klines]
        self.log_info(f"[Redis] 获取到 {len(closes)} 条历史数据，开始预热因子...")

        for close in closes:
            self.factor_calc.update(close)

        self.data_ready = True
        factor_val = self.factor_calc.last_factor_value
        if factor_val is not None:
            self.log_info(f"[预热] 完成, 当前因子值: {factor_val:.4f}")
        else:
            self.log_info("[预热] 完成, 因子值尚未计算出")

        return True

    def on_init(self):
        """策略初始化（在主循环中调用）"""
        print("=" * 60)
        print("       RetSkew 因子策略 - 初始化")
        print("=" * 60)

        # 1. 连接 Redis 历史数据服务 (使用基类接口)
        self.log_info("[初始化] 连接 Redis 历史数据服务...")
        if not self.connect_historical_data():
            self.log_error("[初始化] Redis 连接失败")
            return

        # 2. 预热因子
        if not self._warmup_factor():
            self.log_error("[初始化] 因子预热失败")
            return

        # 3. 注册账户
        if self.api_key and self.secret_key:
            self.log_info(f"[初始化] 注册 {self.exchange.upper()} 账户...")
            if self.exchange == "okx":
                self.register_account(
                    self.api_key,
                    self.secret_key,
                    self.passphrase,
                    self.is_testnet
                )
            else:  # binance
                self.register_binance_account(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    is_testnet=self.is_testnet
                )
        else:
            self.log_error("[初始化] 请在配置文件中设置 API 密钥")
            return

        # 4. 订阅 K 线
        self.subscribe_kline(self.symbol, self.interval)
        self.log_info("[初始化] 已订阅K线，等待行情数据...")
        print("=" * 60)

    def on_register_report(self, success: bool, error_msg: str):
        """账户注册回报"""
        if success:
            self.log_info("[账户] ✓ 注册成功")
            # 主动刷新账户余额（重要！）
            self.refresh_account()
            # 不在这里设置 account_ready，而是在 on_balance_update 回调中处理
        else:
            self.log_error(f"[账户] ✗ 注册失败: {error_msg}")

    def on_balance_update(self, balance):
        """余额更新回调"""
        if balance.currency == "USDT" and not self.account_ready:
            self.account_ready = True
            self.log_info(f"[账户] ✓ 余额数据已就绪")
            self.log_info(f"  USDT可用: {balance.available:.2f}")
            self.log_info(f"  USDT冻结: {balance.frozen:.2f}")
            self.log_info(f"  USDT总计: {balance.total:.2f}")

    def on_position_update(self, position):
        """持仓更新回调"""
        if position.symbol == self.symbol and position.quantity != 0:
            self.log_info(f"[持仓更新] {position.symbol} {position.pos_side}: "
                         f"{position.quantity}张 @ {position.avg_price:.2f} "
                         f"盈亏: {position.unrealized_pnl:.2f}")

    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K线回调"""
        if symbol != self.symbol:
            return

        self.current_price = bar.close

        # 更新因子
        factor_value = self.factor_calc.update(bar.close)

        if factor_value is None:
            self.log_info(f"[K线] 收到 {symbol} | 价格:{bar.close:.2f} | 因子预热中...")
            return

        # 获取信号
        sig = self.factor_calc.get_signal()

        # 打印详细状态
        signal_text = {1: "做多", -1: "做空", 0: "观望"}[sig]

        # 构建持仓显示文本
        if self.pending_position is not None:
            # 有待确认的订单
            pending_text = {1: "多头", -1: "空头", 0: "平仓"}[self.pending_position]
            position_display = f"待确认({pending_text})"
        else:
            # 没有待确认订单，显示当前持仓
            position_text = {1: "多头", -1: "空头", 0: "空仓"}[self.current_position]
            position_display = f"{position_text}({self.current_position})"
            if self.last_order_error and (time.time() - self.last_order_error_time < 300):  # 5分钟内的错误
                position_display += f" [上次开仓失败: {self.last_order_error}]"

        self.log_info(f"[K线] 价格:{bar.close:.2f} | 因子:{factor_value:.4f} | 信号:{signal_text}({sig}) | 持仓:{position_display}")

        # 信号变化时额外提示（只在没有待确认订单时提示）
        if sig != self.current_position and self.pending_position is None:
            position_text = {1: "多头", -1: "空头", 0: "空仓"}[self.current_position]
            self.log_info(f"[信号变化] {position_text} -> {signal_text}，准备执行交易...")

        # 执行交易
        self._execute_signal(sig)

    def _execute_signal(self, sig: int):
        """执行交易信号"""
        if not self.account_ready:
            return

        # 防止重复下单：如果有待确认的订单，不再发送新订单
        if self.pending_position is not None:
            pending_text = {1: "多头", -1: "空头", 0: "平仓"}[self.pending_position]
            self.log_info(f"[跳过] 已有待确认订单({pending_text})，等待订单确认后再操作")
            return

        # 信号与当前持仓相同，不操作
        if sig == self.current_position:
            return

        # 计算下单数量（基于可用资金的百分比）
        if self.current_price <= 0:
            return

        # 获取可用资金
        available_usdt = self.get_usdt_available()
        if available_usdt <= 0:
            self.log_error(f"[下单] 可用资金不足: {available_usdt:.2f} USDT")
            return

        # 根据仓位比例计算下单金额
        position_value = available_usdt * self.position_ratio

        if self.exchange == "okx":
            # OKX合约：1张 = 0.01 BTC/ETH
            contracts = round(position_value / self.current_price / 0.01)
            if contracts < 1:
                contracts = 1
            order_qty = contracts
            actual_value = contracts * self.current_price * 0.01
        else:
            # Binance：使用类似"张数"的概念，1单位 = 0.001 BTC
            units = round(position_value / self.current_price / 0.001)
            if units < 1:
                units = 1
            order_qty = round(units * 0.001, 3)  # 转换为实际数量，保留3位小数
            actual_value = order_qty * self.current_price

        self.log_info(f"[仓位计算] 可用:{available_usdt:.2f}U | 比例:{self.position_ratio*100:.0f}% | 目标:{position_value:.2f}U | 实际:{actual_value:.2f}U")

        # 平仓
        if self.current_position != 0:
            close_side = "sell" if self.current_position > 0 else "buy"

            if self.exchange == "okx":
                pos_side = "long" if self.current_position > 0 else "short"
                self.log_info(f"[平仓] {close_side} {order_qty}张 @ {self.current_price:.2f}")
                order_id = self.send_swap_market_order(self.symbol, close_side, order_qty, pos_side)
            else:
                # Binance：使用双向持仓模式（与OKX保持一致）
                pos_side = "LONG" if self.current_position > 0 else "SHORT"
                self.log_info(f"[平仓] {close_side} {order_qty} @ {self.current_price:.2f}")
                order_id = self.send_binance_futures_market_order(
                    symbol=self.symbol,
                    side=close_side,
                    quantity=order_qty,
                    pos_side=pos_side
                )

            if order_id:
                self.log_info(f"[平仓] 订单已发送: {order_id}")
                self.pending_position = 0  # 标记待确认的平仓
            else:
                self.log_error(f"[平仓] 订单发送失败")
                return  # 平仓失败，不继续开仓

        # 开仓
        if sig != 0:
            open_side = "buy" if sig > 0 else "sell"

            if self.exchange == "okx":
                pos_side = "long" if sig > 0 else "short"
                self.log_info(f"[开仓] {open_side} {order_qty}张 @ {self.current_price:.2f}")
                order_id = self.send_swap_market_order(self.symbol, open_side, order_qty, pos_side)
            else:
                # Binance：使用双向持仓模式（与OKX保持一致）
                pos_side = "LONG" if sig > 0 else "SHORT"
                self.log_info(f"[开仓] {open_side} {order_qty} @ {self.current_price:.2f}")
                order_id = self.send_binance_futures_market_order(
                    symbol=self.symbol,
                    side=open_side,
                    quantity=order_qty,
                    pos_side=pos_side
                )

            if order_id:
                self.log_info(f"[开仓] 订单已发送: {order_id}")
                self.pending_position = sig  # 标记待确认的持仓方向
            else:
                self.log_error(f"[开仓] 订单发送失败")
                # 如果已经平仓成功，需要更新持仓为0
                if self.pending_position == 0:
                    self.current_position = 0

    def on_order_report(self, report: dict):
        """订单回报"""
        status = report.get("status", "")
        symbol = report.get("symbol", "")
        side = report.get("side", "")
        exchange = report.get("exchange", self.exchange)

        # OKX使用"accepted"，Binance使用"live"/"pending"/"submitted"，统一处理为订单已接受
        if status in ["accepted", "NEW", "live", "pending", "submitted"]:
            self.log_info(f"[接受] {exchange}|{symbol} {side}")

            # 订单被接受后，立即更新持仓状态（市价单很快就会成交）
            if self.pending_position is not None:
                old_position = self.current_position
                self.current_position = self.pending_position
                self.pending_position = None

                # 清除错误信息
                self.last_order_error = ""
                self.last_order_error_time = 0

                # 统计交易次数（仅在开仓时统计）
                if self.current_position != 0 and old_position == 0:
                    self.total_trades += 1
                    if self.current_position > 0:
                        self.long_trades += 1
                    else:
                        self.short_trades += 1

                self.log_info(f"[持仓更新] 持仓已更新: {old_position} -> {self.current_position}")

        elif status == "filled" or status == "FILLED":
            filled_qty = report.get("filled_quantity", 0)
            filled_price = report.get("filled_price", 0)
            self.log_info(f"[成交] {exchange}|{symbol} {side} {filled_qty} @ {filled_price:.2f}")

        elif status == "rejected" or status == "REJECTED":
            error_msg = report.get("error_msg", "")
            self.log_error(f"[拒绝] {exchange}|{symbol} {side} | {error_msg}")

            # 记录订单失败原因
            self.last_order_error = error_msg
            self.last_order_error_time = time.time()

            # 订单被拒绝，需要回滚持仓状态
            if self.pending_position is not None:
                # 清除待确认状态
                self.pending_position = None

                if error_msg:
                    self.log_error(f"[订单失败] ✗ {symbol} | 原因: {error_msg}")

    def on_stop(self):
        """策略停止"""
        print()
        print("=" * 60)
        print("[策略] RetSkew 因子策略停止")
        print(f"[统计] 总交易: {self.total_trades} | 多: {self.long_trades} | 空: {self.short_trades}")

        if self.factor_calc.last_factor_value is not None:
            print(f"[统计] 最终因子值: {self.factor_calc.last_factor_value:.4f}")

        self.unsubscribe_kline(self.symbol, self.interval)
        print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RetSkew 因子策略")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--symbol", default="", help="交易对 (覆盖配置文件)")
    parser.add_argument("--position-size", type=float, default=0, help="下单金额 (覆盖配置文件)")
    parser.add_argument("--threshold", type=float, default=0, help="信号阈值 (覆盖配置文件)")

    args = parser.parse_args()

    # 加载配置
    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(SCRIPT_DIR, config_path)

    try:
        config = load_config(config_path)
        print(f"[配置] 已加载: {config_path}")
    except FileNotFoundError:
        print(f"[配置] 文件不存在: {config_path}，使用默认配置")
        config = get_default_config()

    # 命令行参数覆盖配置文件
    if args.symbol:
        config["symbols"] = [args.symbol]
    if args.position_size > 0:
        config.setdefault("trading_params", {})["position_size_usdt"] = args.position_size
    if args.threshold > 0:
        config.setdefault("factor_params", {})["signal_threshold"] = args.threshold

    # 创建策略
    strategy = RetSkewStrategy(config)

    # 打印策略信息
    print("=" * 60)
    print("       RetSkew 因子策略 - 实盘版本")
    print("=" * 60)
    print()
    print(f"交易所: {strategy.exchange.upper()} {'(测试网)' if strategy.is_testnet else '(主网)'}")
    print(f"交易对: {strategy.symbol}")
    print(f"信号阈值: {strategy.signal_threshold}")
    print(f"仓位比例: {strategy.position_ratio * 100:.0f}% (可用资金)")
    print(f"历史数据: Redis (通过基类接口)")
    print()
    print(f"因子参数: skew_window={strategy.skew_window}, zscore_window={strategy.zscore_window}, ema_alpha={strategy.ema_alpha}")
    print()
    print("因子公式: ts_ema(clip(ts_zscore(ts_skew(returns(close, 1), skew_window), zscore_window), -3, 3), ema_alpha)")
    print()
    print("-" * 60)
    print("准备启动策略...")
    print("=" * 60)

    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())

    # 运行策略（run() 内部会自动调用 connect()）
    strategy.run()


if __name__ == "__main__":
    main()
