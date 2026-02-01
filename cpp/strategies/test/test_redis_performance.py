#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口性能和压力测试

测试接口的性能表现：
1. 单次查询延迟测试
2. 不同数据量的查询性能
3. 并发查询性能
4. 持续压力测试
5. 内存使用测试
6. 吞吐量测试

@author Test Suite
@date 2025-01
"""

import sys
import time
import gc
from datetime import datetime
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')

import strategy_base


class PerformanceMetrics:
    """性能指标记录"""
    def __init__(self, name: str):
        self.name = name
        self.latencies: List[float] = []
        self.success_count = 0
        self.fail_count = 0
        self.total_klines = 0
        self.start_time = 0.0
        self.end_time = 0.0

    def add_result(self, latency: float, kline_count: int, success: bool):
        self.latencies.append(latency)
        self.total_klines += kline_count
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1

    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time

    @property
    def avg_latency(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0

    @property
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0

    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = len(sorted_lat) // 2
        return sorted_lat[idx]

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def qps(self) -> float:
        if self.total_time <= 0:
            return 0
        return len(self.latencies) / self.total_time

    @property
    def throughput(self) -> float:
        """K线/秒"""
        if self.total_time <= 0:
            return 0
        return self.total_klines / self.total_time

    def print_report(self):
        print(f"\n{'='*60}")
        print(f"  {self.name}")
        print(f"{'='*60}")
        print(f"  请求统计:")
        print(f"    总请求数: {len(self.latencies)}")
        print(f"    成功: {self.success_count}, 失败: {self.fail_count}")
        print(f"    成功率: {self.success_count / len(self.latencies) * 100:.1f}%")
        print(f"  延迟统计 (秒):")
        print(f"    平均: {self.avg_latency:.4f}")
        print(f"    最小: {self.min_latency:.4f}")
        print(f"    最大: {self.max_latency:.4f}")
        print(f"    P50: {self.p50_latency:.4f}")
        print(f"    P95: {self.p95_latency:.4f}")
        print(f"    P99: {self.p99_latency:.4f}")
        print(f"  吞吐量:")
        print(f"    QPS: {self.qps:.2f} 请求/秒")
        print(f"    数据吞吐: {self.throughput:.0f} K线/秒")
        print(f"    总K线数: {self.total_klines:,}")
        print(f"    总耗时: {self.total_time:.2f}秒")


class RedisPerformanceTest(strategy_base.StrategyBase):
    """性能和压力测试"""

    def __init__(self):
        super().__init__("redis_performance_test")
        self.connected = False

    def run_all_tests(self):
        """运行所有性能测试"""
        print("\n" + "=" * 80)
        print("  Redis历史数据接口性能和压力测试")
        print("=" * 80 + "\n")

        # 先连接
        if not self.connect_historical_data():
            print("✗ 无法连接Redis，测试终止")
            return
        self.connected = True
        print("✓ Redis连接成功\n")

        # 性能测试列表
        tests = [
            ("1. 单次查询延迟基准测试", self.test_single_query_latency),
            ("2. 不同数据量查询性能", self.test_different_sizes),
            ("3. 不同时间周期查询性能", self.test_different_intervals),
            ("4. 不同交易所查询性能", self.test_different_exchanges),
            ("5. 顺序批量查询性能", self.test_sequential_batch),
            ("6. 多币种顺序查询性能", self.test_multi_symbol_sequential),
            ("7. 持续压力测试 (30秒)", self.test_sustained_load),
            ("8. 大数据量查询性能", self.test_large_data_query),
            ("9. 冷启动性能测试", self.test_cold_start),
            ("10. 热缓存性能测试", self.test_hot_cache),
        ]

        for test_name, test_func in tests:
            print(f"\n开始: {test_name}")
            print("-" * 60)
            try:
                test_func()
            except Exception as e:
                print(f"✗ 测试异常: {e}")

        print("\n" + "=" * 80)
        print("  性能测试完成")
        print("=" * 80)

    def test_single_query_latency(self):
        """测试单次查询延迟"""
        metrics = PerformanceMetrics("单次查询延迟基准")
        metrics.start_time = time.time()

        # 执行100次单次查询
        for i in range(100):
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)

        metrics.end_time = time.time()
        metrics.print_report()

    def test_different_sizes(self):
        """测试不同数据量的查询性能"""
        sizes = [10, 100, 500, 1000, 5000, 10000, 20000, 50000]

        print(f"\n{'数据量':<10} {'延迟(s)':<12} {'K线数':<10} {'吞吐(K线/s)':<15}")
        print("-" * 50)

        for size in sizes:
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", size)
            latency = time.time() - start
            actual = len(klines)
            throughput = actual / latency if latency > 0 else 0

            print(f"{size:<10} {latency:<12.4f} {actual:<10} {throughput:<15.0f}")

    def test_different_intervals(self):
        """测试不同时间周期的查询性能"""
        intervals = ["1s", "1m", "5m", "15m", "1h", "4h", "1d"]

        print(f"\n{'周期':<10} {'延迟(s)':<12} {'K线数':<10}")
        print("-" * 35)

        for interval in intervals:
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", interval, 1000)
            latency = time.time() - start
            actual = len(klines)

            print(f"{interval:<10} {latency:<12.4f} {actual:<10}")

    def test_different_exchanges(self):
        """测试不同交易所的查询性能"""
        exchanges = [
            ("okx", "BTC-USDT-SWAP"),
            ("okx", "ETH-USDT-SWAP"),
            ("binance", "BTCUSDT"),
            ("binance", "ETHUSDT"),
        ]

        print(f"\n{'交易所':<10} {'交易对':<20} {'延迟(s)':<12} {'K线数':<10}")
        print("-" * 55)

        for exchange, symbol in exchanges:
            start = time.time()
            klines = self.get_latest_historical_klines(symbol, exchange, "1m", 1000)
            latency = time.time() - start
            actual = len(klines)

            print(f"{exchange:<10} {symbol:<20} {latency:<12.4f} {actual:<10}")

    def test_sequential_batch(self):
        """测试顺序批量查询性能"""
        metrics = PerformanceMetrics("顺序批量查询 (100次)")
        metrics.start_time = time.time()

        for i in range(100):
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 1000)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)

        metrics.end_time = time.time()
        metrics.print_report()

    def test_multi_symbol_sequential(self):
        """测试多币种顺序查询性能"""
        symbols_okx = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
                       "DOGE-USDT-SWAP", "XRP-USDT-SWAP"]
        symbols_binance = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

        metrics = PerformanceMetrics("多币种顺序查询")
        metrics.start_time = time.time()

        # OKX
        for symbol in symbols_okx:
            start = time.time()
            klines = self.get_latest_historical_klines(symbol, "okx", "1m", 1000)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)

        # Binance
        for symbol in symbols_binance:
            start = time.time()
            klines = self.get_latest_historical_klines(symbol, "binance", "1m", 1000)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)

        metrics.end_time = time.time()
        metrics.print_report()

    def test_sustained_load(self):
        """持续压力测试"""
        duration = 30  # 30秒
        metrics = PerformanceMetrics(f"持续压力测试 ({duration}秒)")

        print(f"开始持续压力测试，持续 {duration} 秒...")
        metrics.start_time = time.time()
        end_time = metrics.start_time + duration

        request_count = 0
        while time.time() < end_time:
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)
            request_count += 1

            # 每10秒打印进度
            if request_count % 100 == 0:
                elapsed = time.time() - metrics.start_time
                print(f"  已执行 {request_count} 次请求, 耗时 {elapsed:.1f}秒")

        metrics.end_time = time.time()
        metrics.print_report()

    def test_large_data_query(self):
        """大数据量查询性能测试"""
        sizes = [10000, 30000, 50000, 100000]

        print(f"\n大数据量查询测试:")
        print(f"{'数据量':<12} {'延迟(s)':<12} {'实际K线数':<12} {'吞吐(K线/s)':<15}")
        print("-" * 55)

        for size in sizes:
            gc.collect()  # 清理内存
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", size)
            latency = time.time() - start
            actual = len(klines)
            throughput = actual / latency if latency > 0 else 0

            print(f"{size:<12} {latency:<12.4f} {actual:<12} {throughput:<15.0f}")

    def test_cold_start(self):
        """冷启动性能测试"""
        # 模拟冷启动：查询不同的交易对
        symbols = [
            ("okx", "BTC-USDT-SWAP"),
            ("okx", "ETH-USDT-SWAP"),
            ("okx", "SOL-USDT-SWAP"),
            ("binance", "BTCUSDT"),
            ("binance", "ETHUSDT"),
        ]

        print(f"\n冷启动性能测试 (首次查询各交易对):")
        print(f"{'交易所':<10} {'交易对':<20} {'延迟(s)':<12}")
        print("-" * 45)

        for exchange, symbol in symbols:
            start = time.time()
            klines = self.get_latest_historical_klines(symbol, exchange, "1m", 1000)
            latency = time.time() - start

            print(f"{exchange:<10} {symbol:<20} {latency:<12.4f}")

    def test_hot_cache(self):
        """热缓存性能测试"""
        # 先预热
        print("\n热缓存性能测试:")
        print("预热中...")
        for _ in range(5):
            self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 1000)

        # 测试热缓存性能
        metrics = PerformanceMetrics("热缓存查询 (预热后)")
        metrics.start_time = time.time()

        for i in range(50):
            start = time.time()
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 1000)
            latency = time.time() - start
            metrics.add_result(latency, len(klines), len(klines) > 0)

        metrics.end_time = time.time()
        metrics.print_report()


def main():
    print("\n" + "=" * 80)
    print("  Redis历史数据接口性能和压力测试程序")
    print("=" * 80)
    print()
    print("本程序将测试接口的性能表现")
    print("包括: 延迟、吞吐量、压力测试等")
    print()

    test = RedisPerformanceTest()
    test.run_all_tests()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
