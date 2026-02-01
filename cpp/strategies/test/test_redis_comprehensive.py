#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口综合调用模式测试

覆盖所有可能的调用情况和组合：
1. 所有接口方法的调用
2. 所有参数组合
3. 所有交易所和币种组合
4. 所有时间周期组合
5. 策略典型使用模式

@author Test Suite
@date 2025-01
"""

import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')

import strategy_base


class CallPattern:
    """调用模式记录"""
    def __init__(self, name: str, method: str, params: Dict[str, Any]):
        self.name = name
        self.method = method
        self.params = params
        self.success = False
        self.result_count = 0
        self.latency = 0.0
        self.error = ""

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.name:<50} 结果:{self.result_count:<8} 耗时:{self.latency:.3f}s"


class RedisComprehensiveTest(strategy_base.StrategyBase):
    """综合调用模式测试"""

    def __init__(self):
        super().__init__("redis_comprehensive_test")
        self.patterns: List[CallPattern] = []
        self.connected = False

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("  Redis历史数据接口综合调用模式测试")
        print("=" * 80 + "\n")

        # 先连接
        if not self.connect_historical_data():
            print("✗ 无法连接Redis，测试终止")
            return
        self.connected = True
        print("✓ Redis连接成功\n")

        # 生成所有调用模式
        self.generate_all_patterns()

        # 执行所有调用
        print(f"共 {len(self.patterns)} 个调用模式待测试\n")
        print("-" * 80)

        for i, pattern in enumerate(self.patterns):
            self.execute_pattern(pattern)
            print(f"[{i+1:3d}/{len(self.patterns)}] {pattern}")

        # 打印摘要
        self.print_summary()

    def generate_all_patterns(self):
        """生成所有调用模式"""

        # ============================================================
        # 1. connect_historical_data() 调用模式
        # ============================================================
        self.patterns.append(CallPattern(
            "connect_historical_data()",
            "connect_historical_data",
            {}
        ))

        # ============================================================
        # 2. get_available_historical_symbols() 调用模式
        # ============================================================
        # 2.1 不指定交易所
        self.patterns.append(CallPattern(
            "get_available_historical_symbols()",
            "get_available_historical_symbols",
            {"exchange": ""}
        ))

        # 2.2 指定OKX
        self.patterns.append(CallPattern(
            "get_available_historical_symbols('okx')",
            "get_available_historical_symbols",
            {"exchange": "okx"}
        ))

        # 2.3 指定Binance
        self.patterns.append(CallPattern(
            "get_available_historical_symbols('binance')",
            "get_available_historical_symbols",
            {"exchange": "binance"}
        ))

        # ============================================================
        # 3. get_historical_kline_count() 调用模式
        # ============================================================
        # OKX 各币种
        okx_symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
                       "DOGE-USDT-SWAP", "XRP-USDT-SWAP", "LTC-USDT-SWAP",
                       "ADA-USDT-SWAP", "DOT-USDT-SWAP", "LINK-USDT-SWAP"]

        binance_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT",
                          "XRPUSDT", "LTCUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]

        intervals = ["1s", "1m", "5m", "15m", "30m", "1h", "4h", "1d"]

        # OKX K线数量查询
        for symbol in okx_symbols[:3]:  # 取前3个
            for interval in ["1m", "5m", "1h"]:
                self.patterns.append(CallPattern(
                    f"get_historical_kline_count('{symbol}', 'okx', '{interval}')",
                    "get_historical_kline_count",
                    {"symbol": symbol, "exchange": "okx", "interval": interval}
                ))

        # Binance K线数量查询
        for symbol in binance_symbols[:3]:
            for interval in ["1m", "5m", "1h"]:
                self.patterns.append(CallPattern(
                    f"get_historical_kline_count('{symbol}', 'binance', '{interval}')",
                    "get_historical_kline_count",
                    {"symbol": symbol, "exchange": "binance", "interval": interval}
                ))

        # ============================================================
        # 4. get_historical_data_time_range() 调用模式
        # ============================================================
        for symbol in okx_symbols[:3]:
            self.patterns.append(CallPattern(
                f"get_historical_data_time_range('{symbol}', 'okx', '1m')",
                "get_historical_data_time_range",
                {"symbol": symbol, "exchange": "okx", "interval": "1m"}
            ))

        for symbol in binance_symbols[:3]:
            self.patterns.append(CallPattern(
                f"get_historical_data_time_range('{symbol}', 'binance', '1m')",
                "get_historical_data_time_range",
                {"symbol": symbol, "exchange": "binance", "interval": "1m"}
            ))

        # ============================================================
        # 5. get_historical_klines() 时间范围查询
        # ============================================================
        now = int(time.time() * 1000)

        # 不同时间范围
        time_ranges = [
            ("1小时", now - 3600 * 1000, now),
            ("6小时", now - 6 * 3600 * 1000, now),
            ("24小时", now - 24 * 3600 * 1000, now),
            ("3天", now - 3 * 24 * 3600 * 1000, now),
            ("7天", now - 7 * 24 * 3600 * 1000, now),
        ]

        for name, start, end in time_ranges:
            self.patterns.append(CallPattern(
                f"get_historical_klines('BTC-USDT-SWAP', 'okx', '1m', {name})",
                "get_historical_klines",
                {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1m",
                 "start_time": start, "end_time": end}
            ))

        # ============================================================
        # 6. get_historical_klines_by_days() 按天数查询
        # ============================================================
        days_list = [1, 3, 7, 14, 30]

        for days in days_list:
            # OKX
            self.patterns.append(CallPattern(
                f"get_historical_klines_by_days('BTC-USDT-SWAP', 'okx', '1m', {days})",
                "get_historical_klines_by_days",
                {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1m", "days": days}
            ))
            # Binance
            self.patterns.append(CallPattern(
                f"get_historical_klines_by_days('BTCUSDT', 'binance', '1m', {days})",
                "get_historical_klines_by_days",
                {"symbol": "BTCUSDT", "exchange": "binance", "interval": "1m", "days": days}
            ))

        # ============================================================
        # 7. get_latest_historical_klines() 最近N根查询
        # ============================================================
        counts = [10, 50, 100, 500, 1000, 5000, 10000, 15000, 20000]

        # OKX 不同数量
        for count in counts:
            self.patterns.append(CallPattern(
                f"get_latest_historical_klines('BTC-USDT-SWAP', 'okx', '1m', {count})",
                "get_latest_historical_klines",
                {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1m", "count": count}
            ))

        # Binance 不同数量
        for count in counts[:5]:  # 取前5个
            self.patterns.append(CallPattern(
                f"get_latest_historical_klines('BTCUSDT', 'binance', '1m', {count})",
                "get_latest_historical_klines",
                {"symbol": "BTCUSDT", "exchange": "binance", "interval": "1m", "count": count}
            ))

        # 不同时间周期
        for interval in intervals:
            self.patterns.append(CallPattern(
                f"get_latest_historical_klines('BTC-USDT-SWAP', 'okx', '{interval}', 100)",
                "get_latest_historical_klines",
                {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": interval, "count": 100}
            ))

        # 不同币种 - OKX
        for symbol in okx_symbols:
            self.patterns.append(CallPattern(
                f"get_latest_historical_klines('{symbol}', 'okx', '1m', 1000)",
                "get_latest_historical_klines",
                {"symbol": symbol, "exchange": "okx", "interval": "1m", "count": 1000}
            ))

        # 不同币种 - Binance
        for symbol in binance_symbols:
            self.patterns.append(CallPattern(
                f"get_latest_historical_klines('{symbol}', 'binance', '1m', 1000)",
                "get_latest_historical_klines",
                {"symbol": symbol, "exchange": "binance", "interval": "1m", "count": 1000}
            ))

        # ============================================================
        # 8. get_okx_historical_klines() 便捷方法
        # ============================================================
        for symbol in okx_symbols[:5]:
            for days in [1, 7]:
                self.patterns.append(CallPattern(
                    f"get_okx_historical_klines('{symbol}', '1m', {days})",
                    "get_okx_historical_klines",
                    {"symbol": symbol, "interval": "1m", "days": days}
                ))

        # ============================================================
        # 9. get_binance_historical_klines() 便捷方法
        # ============================================================
        for symbol in binance_symbols[:5]:
            for days in [1, 7]:
                self.patterns.append(CallPattern(
                    f"get_binance_historical_klines('{symbol}', '1m', {days})",
                    "get_binance_historical_klines",
                    {"symbol": symbol, "interval": "1m", "days": days}
                ))

        # ============================================================
        # 10. get_historical_closes() 获取收盘价数组
        # ============================================================
        for symbol in okx_symbols[:3]:
            self.patterns.append(CallPattern(
                f"get_historical_closes('{symbol}', 'okx', '1m', 7)",
                "get_historical_closes",
                {"symbol": symbol, "exchange": "okx", "interval": "1m", "days": 7}
            ))

        for symbol in binance_symbols[:3]:
            self.patterns.append(CallPattern(
                f"get_historical_closes('{symbol}', 'binance', '1m', 7)",
                "get_historical_closes",
                {"symbol": symbol, "exchange": "binance", "interval": "1m", "days": 7}
            ))

        # ============================================================
        # 11. 策略典型使用模式
        # ============================================================
        # RetSkew策略模式
        self.patterns.append(CallPattern(
            "RetSkew策略: OKX BTC 15000根1m",
            "get_latest_historical_klines",
            {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1m", "count": 15000}
        ))

        self.patterns.append(CallPattern(
            "RetSkew策略: Binance BTC 15000根1m",
            "get_latest_historical_klines",
            {"symbol": "BTCUSDT", "exchange": "binance", "interval": "1m", "count": 15000}
        ))

        # 网格策略模式
        self.patterns.append(CallPattern(
            "网格策略: OKX BTC 1000根1m",
            "get_latest_historical_klines",
            {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1m", "count": 1000}
        ))

        # 趋势策略模式
        self.patterns.append(CallPattern(
            "趋势策略: OKX BTC 200根1h",
            "get_latest_historical_klines",
            {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1h", "count": 200}
        ))

        # 高频策略模式
        self.patterns.append(CallPattern(
            "高频策略: OKX BTC 3600根1s",
            "get_latest_historical_klines",
            {"symbol": "BTC-USDT-SWAP", "exchange": "okx", "interval": "1s", "count": 3600}
        ))

    def execute_pattern(self, pattern: CallPattern):
        """执行单个调用模式"""
        start_time = time.time()

        try:
            if pattern.method == "connect_historical_data":
                result = self.connect_historical_data()
                pattern.success = result
                pattern.result_count = 1 if result else 0

            elif pattern.method == "get_available_historical_symbols":
                exchange = pattern.params.get("exchange", "")
                if exchange:
                    result = self.get_available_historical_symbols(exchange)
                else:
                    result = self.get_available_historical_symbols()
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_historical_kline_count":
                result = self.get_historical_kline_count(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"]
                )
                pattern.success = True
                pattern.result_count = result

            elif pattern.method == "get_historical_data_time_range":
                earliest, latest = self.get_historical_data_time_range(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"]
                )
                pattern.success = earliest > 0 or latest > 0
                pattern.result_count = 2 if pattern.success else 0

            elif pattern.method == "get_historical_klines":
                result = self.get_historical_klines(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"],
                    pattern.params["start_time"],
                    pattern.params["end_time"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_historical_klines_by_days":
                result = self.get_historical_klines_by_days(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"],
                    pattern.params["days"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_latest_historical_klines":
                result = self.get_latest_historical_klines(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"],
                    pattern.params["count"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_okx_historical_klines":
                result = self.get_okx_historical_klines(
                    pattern.params["symbol"],
                    pattern.params["interval"],
                    pattern.params["days"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_binance_historical_klines":
                result = self.get_binance_historical_klines(
                    pattern.params["symbol"],
                    pattern.params["interval"],
                    pattern.params["days"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            elif pattern.method == "get_historical_closes":
                result = self.get_historical_closes(
                    pattern.params["symbol"],
                    pattern.params["exchange"],
                    pattern.params["interval"],
                    pattern.params["days"]
                )
                pattern.success = True
                pattern.result_count = len(result)

            else:
                pattern.success = False
                pattern.error = f"未知方法: {pattern.method}"

        except Exception as e:
            pattern.success = False
            pattern.error = str(e)

        pattern.latency = time.time() - start_time

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 80)
        print("  综合调用模式测试结果摘要")
        print("=" * 80 + "\n")

        # 按方法分组统计
        method_stats = {}
        for pattern in self.patterns:
            if pattern.method not in method_stats:
                method_stats[pattern.method] = {"success": 0, "fail": 0, "total_latency": 0}
            if pattern.success:
                method_stats[pattern.method]["success"] += 1
            else:
                method_stats[pattern.method]["fail"] += 1
            method_stats[pattern.method]["total_latency"] += pattern.latency

        print("按方法统计:")
        print("-" * 70)
        print(f"{'方法':<40} {'成功':<8} {'失败':<8} {'平均延迟':<12}")
        print("-" * 70)

        for method, stats in method_stats.items():
            total = stats["success"] + stats["fail"]
            avg_latency = stats["total_latency"] / total if total > 0 else 0
            print(f"{method:<40} {stats['success']:<8} {stats['fail']:<8} {avg_latency:<12.4f}")

        print("-" * 70)

        # 总体统计
        total_success = sum(1 for p in self.patterns if p.success)
        total_fail = sum(1 for p in self.patterns if not p.success)
        total_patterns = len(self.patterns)

        print(f"\n总计: {total_patterns} 个调用模式")
        print(f"  成功: {total_success}")
        print(f"  失败: {total_fail}")
        print(f"  成功率: {total_success / total_patterns * 100:.1f}%")

        # 打印失败的调用
        failed = [p for p in self.patterns if not p.success]
        if failed:
            print(f"\n失败的调用 ({len(failed)} 个):")
            for p in failed[:20]:  # 最多显示20个
                print(f"  - {p.name}: {p.error}")
            if len(failed) > 20:
                print(f"  ... 还有 {len(failed) - 20} 个失败")

        # 性能统计
        latencies = [p.latency for p in self.patterns]
        print(f"\n性能统计:")
        print(f"  总耗时: {sum(latencies):.2f}秒")
        print(f"  平均延迟: {sum(latencies)/len(latencies):.4f}秒")
        print(f"  最大延迟: {max(latencies):.4f}秒")
        print(f"  最小延迟: {min(latencies):.4f}秒")


def main():
    print("\n" + "=" * 80)
    print("  Redis历史数据接口综合调用模式测试程序")
    print("=" * 80)
    print()
    print("本程序将测试所有可能的调用情况和组合")
    print("包括: 所有接口方法、所有参数组合、所有交易所和币种")
    print()

    test = RedisComprehensiveTest()
    test.run_all_tests()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
