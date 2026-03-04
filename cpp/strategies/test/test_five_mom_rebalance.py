#!/usr/bin/env python3
"""
5动量因子策略 - 调仓逻辑单元测试

测试内容:
1. _check_initial_rebalance: 启动时同步率>=80%应立即调仓
2. tracked_positions: 本地持仓跟踪的正确性
3. Delta调仓: 平仓/开仓/加仓/减仓/反向调仓的分类
4. _wait_for_orders: 返回值和清空逻辑

运行方式:
    cd cpp/strategies && python test/test_five_mom_rebalance.py
"""

import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from collections import deque
from typing import Dict, List, Any, Optional

# 路径设置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, STRATEGIES_DIR)


# ============================================================
# Mock StrategyBase - 模拟C++基类，不需要真实连接
# ============================================================
class MockPositionInfo:
    def __init__(self, symbol, quantity, unrealized_pnl=0):
        self.symbol = symbol
        self.quantity = quantity
        self.unrealized_pnl = unrealized_pnl


class MockBalanceInfo:
    def __init__(self, currency="USDT", available=10000):
        self.currency = currency
        self.available = available


class MockStrategyBase:
    """模拟C++策略基类"""
    def __init__(self, strategy_id, max_kline_bars=300, log_file_path=""):
        self.strategy_id = strategy_id
        self._active_positions = []
        self._total_equity = 10000.0
        self._sent_batches = []
        self._log_messages = []

    def log_info(self, msg):
        self._log_messages.append(("INFO", msg))

    def log_error(self, msg):
        self._log_messages.append(("ERROR", msg))

    def get_active_positions(self):
        return self._active_positions

    def get_total_equity(self):
        return self._total_equity

    def send_batch_orders(self, orders, exchange):
        self._sent_batches.append(orders)

    def calculate_order_quantity(self, exchange, symbol, value, price):
        # 简化: 直接算
        qty = int(value / price)
        return max(qty, 1)

    def get_available_historical_symbols(self, exchange):
        return []

    def load_min_order_config(self, exchange, path):
        return True

    def connect_historical_data(self):
        return True

    def get_historical_klines(self, **kwargs):
        return []

    def lua_batch_get_latest_timestamps(self, symbols, exchange, interval):
        return {}

    def register_binance_account(self, **kwargs):
        pass

    def refresh_account(self):
        pass

    def change_leverage(self, symbol, leverage, exchange):
        return True

    def run(self):
        pass

    def stop(self):
        pass


# ============================================================
# Patch strategy_base 模块，让 import 不依赖 C++ .so
# ============================================================
class MockKlineBar:
    def __init__(self):
        self.open = 0
        self.high = 0
        self.low = 0
        self.close = 0
        self.volume = 0
        self.timestamp = 0


# 创建 mock 模块
mock_strategy_base = MagicMock()
mock_strategy_base.StrategyBase = MockStrategyBase
mock_strategy_base.KlineBar = MockKlineBar
sys.modules['strategy_base'] = mock_strategy_base

# 现在可以安全导入策略（目录名以数字开头，用 importlib）
import importlib.util
_mod_path = os.path.join(STRATEGIES_DIR, "implementations", "5_mom_factor_cs", "live", "five_mom_factor_live.py")
_spec = importlib.util.spec_from_file_location("five_mom_factor_live", _mod_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FiveMomFactorLiveStrategy = _mod.FiveMomFactorLiveStrategy
TickerDataLive = _mod.TickerDataLive


# ============================================================
# 测试用例
# ============================================================
def make_config(**overrides):
    """生成测试配置"""
    config = {
        "strategy_id": "test_five_mom",
        "exchange": "binance",
        "api_key": "test",
        "secret_key": "test",
        "is_testnet": True,
        "dynamic_symbols": False,
        "symbols": [f"SYM{i}USDT" for i in range(20)],
        "factor_params": {
            "lookback_window_20": 5,
            "lookback_window_60": 10,
            "liquidity_period": 5,
            "liq_quantile": 0.5,
            "long_short_ratio": 5,
            "direction": "descending"
        },
        "trading_params": {
            "interval": "8h",
            "rebalance_interval_hours": 8,
            "position_ratio": 0.8,
            "min_bars": 3,
            "history_bars": 20
        },
        "logging": {"log_file": "/dev/null"}
    }
    config.update(overrides)
    return config


def make_strategy(symbols=None, equity=10000.0):
    """创建测试策略实例"""
    if symbols is None:
        symbols = [f"SYM{i}USDT" for i in range(20)]
    config = make_config(symbols=symbols)
    s = FiveMomFactorLiveStrategy(config)
    s._total_equity = equity
    s.account_ready = True
    s.data_ready = True
    return s


class TestCheckInitialRebalance(unittest.TestCase):
    """测试启动时调仓检查"""

    def test_no_rebalance_on_startup_even_sync_ready(self):
        """启动时即使同步率>=80%也不应立即调仓（无法确定是否已调仓过）"""
        symbols = [f"SYM{i}USDT" for i in range(10)]
        s = make_strategy(symbols=symbols)

        # 模拟所有币种都在同一个周期
        for sym in symbols:
            s.symbol_periods[sym] = 61544

        # mock _execute_rebalance 防止真正执行
        s._execute_rebalance = MagicMock()

        s._check_initial_rebalance()

        # 不应该调仓
        s._execute_rebalance.assert_not_called()
        # last_rebalance_period 应该设为当前周期（标记已处理）
        self.assertEqual(s.last_rebalance_period, 61544)

        # 检查日志中有"跳过当前周期"
        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("跳过当前周期" in m for m in log_texts),
                        f"日志中应包含'跳过当前周期': {log_texts}")

    def test_no_rebalance_when_sync_not_ready(self):
        """同步率<80%时也不应调仓，同样标记当前周期"""
        symbols = [f"SYM{i}USDT" for i in range(10)]
        s = make_strategy(symbols=symbols)

        # 只有3个币种到达最新周期 (30% < 80%)
        for i, sym in enumerate(symbols):
            s.symbol_periods[sym] = 61544 if i < 3 else 61543

        s._execute_rebalance = MagicMock()

        s._check_initial_rebalance()

        # 不应该调仓
        s._execute_rebalance.assert_not_called()
        # last_rebalance_period 应该设为 data_period（最大周期）
        self.assertEqual(s.last_rebalance_period, 61544)

        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("跳过当前周期" in m for m in log_texts))


class TestTrackedPositions(unittest.TestCase):
    """测试本地持仓跟踪"""

    def test_fallback_to_tracked_when_exchange_empty(self):
        """交易所无持仓数据时应使用本地跟踪"""
        s = make_strategy(symbols=["BTCUSDT", "ETHUSDT"])
        s._active_positions = []  # 交易所返回空
        s.tracked_positions = {"BTCUSDT": 0.1, "ETHUSDT": -5.0}

        # 准备 ticker_data
        for sym in ["BTCUSDT", "ETHUSDT"]:
            td = TickerDataLive(min_bars=1, lookback=10)
            bar = MockKlineBar()
            bar.close = 50000 if sym == "BTCUSDT" else 3000
            bar.high = bar.close * 1.01
            bar.low = bar.close * 0.99
            bar.open = bar.close
            bar.volume = 100
            bar.timestamp = 1000
            for _ in range(5):
                td.add_bar(bar)
            s.ticker_data[sym] = td

        # mock send_batch_orders 和 _compute_target_positions
        s.send_batch_orders = MagicMock()
        s._compute_target_positions = MagicMock(return_value={
            "BTCUSDT": 0.5,  # 多
            "ETHUSDT": -0.5   # 空
        })

        s._execute_rebalance()

        # 检查日志中有"使用本地跟踪持仓"
        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("使用本地跟踪持仓" in m for m in log_texts),
                        f"应使用本地跟踪: {log_texts}")

    def test_on_position_update_syncs_tracked(self):
        """on_position_update 应同步更新 tracked_positions"""
        s = make_strategy(symbols=["BTCUSDT", "ETHUSDT"])

        pos = MockPositionInfo("BTCUSDT", 0.5, 100.0)
        s.on_position_update(pos)
        self.assertEqual(s.tracked_positions["BTCUSDT"], 0.5)

        # 平仓时应移除
        pos2 = MockPositionInfo("BTCUSDT", 0, 0)
        s.on_position_update(pos2)
        self.assertNotIn("BTCUSDT", s.tracked_positions)

    def test_tracked_positions_updated_after_rebalance(self):
        """调仓完成后 tracked_positions 应更新"""
        s = make_strategy(symbols=["AAAUSDT", "BBBUSDT"])
        s.send_batch_orders = MagicMock()

        # 准备 ticker_data
        for sym in ["AAAUSDT", "BBBUSDT"]:
            td = TickerDataLive(min_bars=1, lookback=10)
            bar = MockKlineBar()
            bar.close = 100
            bar.high = 101
            bar.low = 99
            bar.open = 100
            bar.volume = 1000
            bar.timestamp = 1000
            for _ in range(5):
                td.add_bar(bar)
            s.ticker_data[sym] = td

        s._compute_target_positions = MagicMock(return_value={
            "AAAUSDT": 0.5,
            "BBBUSDT": -0.5
        })

        s._execute_rebalance()

        # tracked_positions 应该有2个持仓
        self.assertEqual(len(s.tracked_positions), 2)
        self.assertIn("AAAUSDT", s.tracked_positions)
        self.assertIn("BBBUSDT", s.tracked_positions)
        # AAAUSDT 应该是正数（多头）
        self.assertGreater(s.tracked_positions["AAAUSDT"], 0)
        # BBBUSDT 应该是负数（空头）
        self.assertLess(s.tracked_positions["BBBUSDT"], 0)


class TestWaitForOrders(unittest.TestCase):
    """测试 _wait_for_orders 返回值"""

    def test_returns_filled_and_rejected(self):
        """应返回 filled 和 rejected 列表"""
        s = make_strategy()

        # 模拟已有回报
        s.current_batch_filled = [
            {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1, "price": 50000}
        ]
        s.current_batch_rejected = [
            {"symbol": "ETHUSDT", "side": "SELL", "error_msg": "Margin insufficient"}
        ]

        filled, rejected = s._wait_for_orders(2, "测试")

        self.assertEqual(len(filled), 1)
        self.assertEqual(filled[0]["symbol"], "BTCUSDT")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["symbol"], "ETHUSDT")

        # 调用后应清空
        self.assertEqual(len(s.current_batch_filled), 0)
        self.assertEqual(len(s.current_batch_rejected), 0)

    def test_timeout_returns_whatever_received(self):
        """超时后应返回已收到的回报"""
        s = make_strategy()
        s.current_batch_filled = []
        s.current_batch_rejected = []

        # 期望10个回报但一个都没有，会超时
        # 用很短的超时避免测试太慢
        original_wait = s._wait_for_orders

        # patch time.sleep 加速
        with patch('time.sleep'):
            filled, rejected = s._wait_for_orders(10, "超时测试")

        self.assertEqual(len(filled), 0)
        self.assertEqual(len(rejected), 0)


class TestDeltaRebalance(unittest.TestCase):
    """测试 Delta 调仓分类逻辑"""

    def _setup_strategy_with_positions(self, current_pos, target_weights):
        """辅助: 创建带持仓和目标的策略"""
        all_syms = list(set(list(current_pos.keys()) + list(target_weights.keys())))
        s = make_strategy(symbols=all_syms, equity=10000)
        s.tracked_positions = dict(current_pos)
        s._active_positions = []  # 交易所返回空，走 fallback
        s.send_batch_orders = MagicMock()

        # 准备 ticker_data
        for sym in all_syms:
            td = TickerDataLive(min_bars=1, lookback=10)
            bar = MockKlineBar()
            bar.close = 100
            bar.high = 101
            bar.low = 99
            bar.open = 100
            bar.volume = 1000
            bar.timestamp = 1000
            for _ in range(5):
                td.add_bar(bar)
            s.ticker_data[sym] = td

        s._compute_target_positions = MagicMock(return_value=target_weights)
        return s

    def test_close_position(self):
        """持有但目标为0 -> 平仓"""
        s = self._setup_strategy_with_positions(
            current_pos={"AAAUSDT": 100},
            target_weights={"BBBUSDT": 0.5}  # AAA不在目标中
        )
        s._execute_rebalance()

        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("[平仓] AAAUSDT" in m for m in log_texts),
                        f"应有AAAUSDT平仓日志: {log_texts}")

    def test_open_position(self):
        """不持有但目标有 -> 开仓"""
        s = self._setup_strategy_with_positions(
            current_pos={},
            target_weights={"AAAUSDT": 0.5}
        )
        s._execute_rebalance()

        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("[开仓] AAAUSDT" in m for m in log_texts),
                        f"应有AAAUSDT开仓日志: {log_texts}")

    def test_reverse_position(self):
        """多头变空头 -> 反向调仓(先平后开)"""
        s = self._setup_strategy_with_positions(
            current_pos={"AAAUSDT": 100},  # 当前多头
            target_weights={"AAAUSDT": -0.5}  # 目标空头
        )
        s._execute_rebalance()

        log_texts = [msg for _, msg in s._log_messages]
        self.assertTrue(any("[反向调仓] AAAUSDT" in m for m in log_texts),
                        f"应有AAAUSDT反向调仓日志: {log_texts}")


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  5动量因子策略 - 调仓逻辑单元测试")
    print("=" * 60)
    print()

    # 使用 verbosity=2 显示每个测试的结果
    unittest.main(verbosity=2)
