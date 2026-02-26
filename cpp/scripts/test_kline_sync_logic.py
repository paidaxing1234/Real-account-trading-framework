#!/usr/bin/env python3
"""
测试 K线同步触发逻辑

使用1分钟K线来验证：
1. symbol_periods 记录是否正确
2. 同步率计算是否正确
3. 调仓触发条件是否正确
"""

import redis
import time
from datetime import datetime
from typing import Dict, List

# Redis连接配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# 测试配置
EXCHANGE = "binance"
INTERVAL = "1m"  # 用1分钟K线测试
TOP_N = 20  # 测试前20个币种
SYNC_THRESHOLD = 0.8  # 80%同步阈值

# 1分钟周期（毫秒）
PERIOD_MS = 1 * 60 * 1000


def connect_redis():
    """连接Redis"""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"Redis连接失败: {e}")
        return None


def get_symbols(r: redis.Redis, exchange: str, interval: str, top_n: int) -> List[str]:
    """获取币种列表"""
    priority = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
                'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT',
                'LTCUSDT', 'ATOMUSDT', 'UNIUSDT', 'APTUSDT', 'ARBUSDT',
                'OPUSDT', 'NEARUSDT', 'FILUSDT', 'INJUSDT', 'SEIUSDT']

    # 验证这些币种有数据
    valid_symbols = []
    for symbol in priority:
        key = f"kline:{exchange}:{symbol}:{interval}"
        if r.exists(key):
            valid_symbols.append(symbol)
        if len(valid_symbols) >= top_n:
            break

    return valid_symbols


def get_latest_kline_ts(r: redis.Redis, exchange: str, symbol: str, interval: str) -> int:
    """获取最新K线时间戳"""
    key = f"kline:{exchange}:{symbol}:{interval}"
    latest = r.zrange(key, -1, -1, withscores=True)
    if latest:
        _, ts = latest[0]
        return int(ts)
    return 0


def ts_to_str(ts_ms: int) -> str:
    """时间戳转字符串"""
    if ts_ms == 0:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')


class KlineSyncTester:
    """K线同步逻辑测试器"""

    def __init__(self, symbols: List[str], sync_threshold: float = 0.8):
        self.symbols = symbols
        self.sync_threshold = sync_threshold

        # 模拟实盘策略中的状态变量
        self.symbol_periods: Dict[str, int] = {}  # 每个币种当前所在的周期编号
        self.last_rebalance_period = 0  # 上次调仓的周期编号
        self.rebalance_count = 0  # 调仓次数

    def update_symbol_period(self, symbol: str, timestamp: int):
        """更新币种的周期编号（模拟 on_kline 中的逻辑）"""
        current_period = timestamp // PERIOD_MS
        old_period = self.symbol_periods.get(symbol, 0)
        self.symbol_periods[symbol] = current_period

        return current_period, old_period

    def check_sync_and_trigger(self, current_period: int) -> bool:
        """
        检查同步率并判断是否触发调仓
        （模拟 on_kline 和 on_tick 中的逻辑）
        """
        # 检查是否已经在当前周期调仓过
        if current_period <= self.last_rebalance_period:
            return False

        # 统计有多少币种已到达当前周期
        total_symbols = len(self.symbols)
        arrived_count = sum(1 for s, p in self.symbol_periods.items() if p >= current_period)

        # 计算同步率
        sync_ratio = arrived_count / total_symbols if total_symbols > 0 else 0

        print(f"  [同步检查] 周期 {current_period} | 已到达: {arrived_count}/{total_symbols} ({sync_ratio*100:.1f}%)")

        # 判断是否达到阈值
        if sync_ratio >= self.sync_threshold:
            self.last_rebalance_period = current_period
            self.rebalance_count += 1
            return True

        return False


def main():
    print("=" * 80)
    print("  K线同步触发逻辑测试")
    print("=" * 80)
    print()

    # 连接Redis
    r = connect_redis()
    if not r:
        return

    print(f"已连接 Redis ({REDIS_HOST}:{REDIS_PORT})")
    print(f"测试周期: {INTERVAL} | 同步阈值: {SYNC_THRESHOLD*100:.0f}%")
    print()

    # 获取测试币种
    symbols = get_symbols(r, EXCHANGE, INTERVAL, TOP_N)
    print(f"测试币种 ({len(symbols)}个): {symbols}")
    print()

    # 创建测试器
    tester = KlineSyncTester(symbols, SYNC_THRESHOLD)

    # 初始化：获取当前所有币种的最新K线时间戳
    print("=" * 80)
    print("  初始化：获取当前K线状态")
    print("=" * 80)
    print()

    initial_periods = {}
    for symbol in symbols:
        ts = get_latest_kline_ts(r, EXCHANGE, symbol, INTERVAL)
        period, _ = tester.update_symbol_period(symbol, ts)
        initial_periods[symbol] = period
        print(f"  {symbol:<12} | 时间戳: {ts_to_str(ts)} | 周期: {period}")

    # 统计初始周期分布
    period_counts = {}
    for symbol, period in initial_periods.items():
        if period not in period_counts:
            period_counts[period] = 0
        period_counts[period] += 1

    print()
    print(f"初始周期分布: {period_counts}")

    # 找出最大周期
    max_period = max(initial_periods.values()) if initial_periods else 0
    print(f"最大周期: {max_period}")
    print()

    # 模拟调仓检查
    print("=" * 80)
    print("  模拟调仓触发检查")
    print("=" * 80)
    print()

    # 假设我们刚启动，last_rebalance_period = 0
    print(f"当前 last_rebalance_period = {tester.last_rebalance_period}")
    print()

    # 检查是否应该触发调仓
    should_trigger = tester.check_sync_and_trigger(max_period)
    print()
    if should_trigger:
        print(f"  >>> 触发调仓! (第 {tester.rebalance_count} 次)")
    else:
        print(f"  >>> 未触发调仓")

    print()
    print("=" * 80)
    print("  实时监控模式 (等待新K线)")
    print("=" * 80)
    print()
    print("每10秒检查一次Redis，观察K线更新和同步触发...")
    print("按 Ctrl+C 退出")
    print()

    # 记录上次检查的时间戳
    last_timestamps = {symbol: get_latest_kline_ts(r, EXCHANGE, symbol, INTERVAL) for symbol in symbols}

    try:
        check_count = 0
        while True:
            time.sleep(10)
            check_count += 1

            now = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{now}] 第 {check_count} 次检查...")

            # 检查每个币种是否有新K线
            new_klines = []
            for symbol in symbols:
                ts = get_latest_kline_ts(r, EXCHANGE, symbol, INTERVAL)
                if ts > last_timestamps.get(symbol, 0):
                    new_klines.append((symbol, ts))
                    last_timestamps[symbol] = ts

                    # 更新周期
                    period, old_period = tester.update_symbol_period(symbol, ts)
                    if period > old_period:
                        print(f"  [新K线] {symbol} | {ts_to_str(ts)} | 周期 {old_period} -> {period}")

            if new_klines:
                # 找出最新的周期
                max_new_period = max(ts // PERIOD_MS for _, ts in new_klines)

                # 检查是否触发调仓
                should_trigger = tester.check_sync_and_trigger(max_new_period)
                if should_trigger:
                    print(f"\n  >>> 触发调仓! (第 {tester.rebalance_count} 次) <<<")
                    print(f"  >>> 周期: {max_new_period} | 时间: {ts_to_str(max_new_period * PERIOD_MS)}")
            else:
                print(f"  无新K线")

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 80)
        print("  测试结束")
        print("=" * 80)
        print(f"  总调仓次数: {tester.rebalance_count}")
        print(f"  最后调仓周期: {tester.last_rebalance_period}")
        print()


if __name__ == "__main__":
    main()
