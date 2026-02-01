#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口基础测试

测试所有基础的历史数据查询接口：
1. connect_historical_data() - 连接Redis
2. get_available_historical_symbols() - 获取可用交易对
3. get_historical_kline_count() - 获取K线数量
4. get_historical_data_time_range() - 获取时间范围
5. get_historical_klines() - 时间范围查询
6. get_historical_klines_by_days() - 按天数查询
7. get_latest_historical_klines() - 最近N根查询
8. get_okx_historical_klines() - OKX便捷方法
9. get_binance_historical_klines() - Binance便捷方法
10. get_historical_closes() - 获取收盘价数组

@author Test Suite
@date 2025-01
"""

import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')

import strategy_base


class TestResult:
    """测试结果记录"""
    def __init__(self, name: str):
        self.name = name
        self.status = "PENDING"  # PASS, FAIL, ERROR, SKIP
        self.message = ""
        self.duration = 0.0
        self.details = {}

    def __str__(self):
        status_symbol = {
            "PASS": "✓",
            "FAIL": "✗",
            "ERROR": "✗",
            "SKIP": "○",
            "PENDING": "?"
        }.get(self.status, "?")
        return f"{status_symbol} {self.name:<50} {self.status} ({self.duration:.3f}s)"


class RedisHistoricalBasicTest(strategy_base.StrategyBase):
    """Redis历史数据基础接口测试"""

    def __init__(self):
        super().__init__("redis_historical_basic_test")
        self.results: List[TestResult] = []
        self.connected = False

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("  Redis历史数据接口基础测试")
        print("=" * 80 + "\n")

        # 测试列表
        tests = [
            ("1. 连接Redis历史数据服务", self.test_connect),
            ("2. 获取OKX可用交易对", self.test_get_okx_symbols),
            ("3. 获取Binance可用交易对", self.test_get_binance_symbols),
            ("4. 获取所有可用交易对", self.test_get_all_symbols),
            ("5. 获取OKX K线数量", self.test_get_okx_kline_count),
            ("6. 获取Binance K线数量", self.test_get_binance_kline_count),
            ("7. 获取OKX数据时间范围", self.test_get_okx_time_range),
            ("8. 获取Binance数据时间范围", self.test_get_binance_time_range),
            ("9. 时间范围查询-OKX", self.test_time_range_query_okx),
            ("10. 时间范围查询-Binance", self.test_time_range_query_binance),
            ("11. 按天数查询-OKX", self.test_days_query_okx),
            ("12. 按天数查询-Binance", self.test_days_query_binance),
            ("13. 最近N根查询-OKX", self.test_latest_n_query_okx),
            ("14. 最近N根查询-Binance", self.test_latest_n_query_binance),
            ("15. OKX便捷方法", self.test_okx_convenience),
            ("16. Binance便捷方法", self.test_binance_convenience),
            ("17. 获取收盘价数组-OKX", self.test_get_closes_okx),
            ("18. 获取收盘价数组-Binance", self.test_get_closes_binance),
            ("19. 不同时间周期测试-1s", self.test_interval_1s),
            ("20. 不同时间周期测试-1m", self.test_interval_1m),
            ("21. 不同时间周期测试-5m", self.test_interval_5m),
            ("22. 不同时间周期测试-15m", self.test_interval_15m),
            ("23. 不同时间周期测试-1h", self.test_interval_1h),
            ("24. 不同时间周期测试-4h", self.test_interval_4h),
            ("25. 不同时间周期测试-1d", self.test_interval_1d),
        ]

        for test_name, test_func in tests:
            result = TestResult(test_name)
            start_time = time.time()

            try:
                # 如果未连接且不是连接测试，跳过
                if not self.connected and test_func != self.test_connect:
                    result.status = "SKIP"
                    result.message = "Redis未连接"
                else:
                    test_func(result)
            except Exception as e:
                result.status = "ERROR"
                result.message = str(e)

            result.duration = time.time() - start_time
            self.results.append(result)
            print(result)

        self.print_summary()

    def test_connect(self, result: TestResult):
        """测试1: 连接Redis"""
        connected = self.connect_historical_data()
        if connected:
            result.status = "PASS"
            result.message = "连接成功"
            self.connected = True
        else:
            result.status = "FAIL"
            result.message = "连接失败"

    def test_get_okx_symbols(self, result: TestResult):
        """测试2: 获取OKX可用交易对"""
        symbols = self.get_available_historical_symbols("okx")
        result.details["count"] = len(symbols)
        result.details["samples"] = symbols[:5] if len(symbols) > 5 else symbols

        if len(symbols) > 0:
            result.status = "PASS"
            result.message = f"获取到 {len(symbols)} 个交易对"
        else:
            result.status = "FAIL"
            result.message = "未获取到任何交易对"

    def test_get_binance_symbols(self, result: TestResult):
        """测试3: 获取Binance可用交易对"""
        symbols = self.get_available_historical_symbols("binance")
        result.details["count"] = len(symbols)
        result.details["samples"] = symbols[:5] if len(symbols) > 5 else symbols

        if len(symbols) > 0:
            result.status = "PASS"
            result.message = f"获取到 {len(symbols)} 个交易对"
        else:
            result.status = "FAIL"
            result.message = "未获取到任何交易对"

    def test_get_all_symbols(self, result: TestResult):
        """测试4: 获取所有可用交易对"""
        symbols = self.get_available_historical_symbols()
        result.details["count"] = len(symbols)

        if len(symbols) > 0:
            result.status = "PASS"
            result.message = f"获取到 {len(symbols)} 个交易对"
        else:
            result.status = "FAIL"
            result.message = "未获取到任何交易对"

    def test_get_okx_kline_count(self, result: TestResult):
        """测试5: 获取OKX K线数量"""
        count = self.get_historical_kline_count("BTC-USDT-SWAP", "okx", "1m")
        result.details["count"] = count

        if count > 0:
            result.status = "PASS"
            result.message = f"BTC-USDT-SWAP 1m: {count:,} 根"
        else:
            result.status = "FAIL"
            result.message = "K线数量为0"

    def test_get_binance_kline_count(self, result: TestResult):
        """测试6: 获取Binance K线数量"""
        count = self.get_historical_kline_count("BTCUSDT", "binance", "1m")
        result.details["count"] = count

        if count > 0:
            result.status = "PASS"
            result.message = f"BTCUSDT 1m: {count:,} 根"
        else:
            result.status = "FAIL"
            result.message = "K线数量为0"

    def test_get_okx_time_range(self, result: TestResult):
        """测试7: 获取OKX数据时间范围"""
        earliest, latest = self.get_historical_data_time_range("BTC-USDT-SWAP", "okx", "1m")
        result.details["earliest"] = earliest
        result.details["latest"] = latest

        if earliest > 0 and latest > 0:
            earliest_dt = datetime.fromtimestamp(earliest / 1000)
            latest_dt = datetime.fromtimestamp(latest / 1000)
            result.status = "PASS"
            result.message = f"{earliest_dt.strftime('%Y-%m-%d')} ~ {latest_dt.strftime('%Y-%m-%d')}"
        else:
            result.status = "FAIL"
            result.message = "时间范围无效"

    def test_get_binance_time_range(self, result: TestResult):
        """测试8: 获取Binance数据时间范围"""
        earliest, latest = self.get_historical_data_time_range("BTCUSDT", "binance", "1m")
        result.details["earliest"] = earliest
        result.details["latest"] = latest

        if earliest > 0 and latest > 0:
            earliest_dt = datetime.fromtimestamp(earliest / 1000)
            latest_dt = datetime.fromtimestamp(latest / 1000)
            result.status = "PASS"
            result.message = f"{earliest_dt.strftime('%Y-%m-%d')} ~ {latest_dt.strftime('%Y-%m-%d')}"
        else:
            result.status = "FAIL"
            result.message = "时间范围无效"

    def test_time_range_query_okx(self, result: TestResult):
        """测试9: 时间范围查询-OKX"""
        end_time = int(time.time() * 1000)
        start_time = end_time - 3600 * 1000  # 1小时前

        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start_time, end_time)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            first = klines[0]
            last = klines[-1]
            result.details["first_close"] = first.close
            result.details["last_close"] = last.close
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_time_range_query_binance(self, result: TestResult):
        """测试10: 时间范围查询-Binance"""
        end_time = int(time.time() * 1000)
        start_time = end_time - 3600 * 1000

        klines = self.get_historical_klines("BTCUSDT", "binance", "1m", start_time, end_time)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_days_query_okx(self, result: TestResult):
        """测试11: 按天数查询-OKX"""
        klines = self.get_historical_klines_by_days("BTC-USDT-SWAP", "okx", "1m", 1)
        result.details["count"] = len(klines)

        # 1天应该有约1440根1分钟K线
        if len(klines) > 1000:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线 (预期~1440)"
        elif len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线 (数据可能不完整)"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_days_query_binance(self, result: TestResult):
        """测试12: 按天数查询-Binance"""
        klines = self.get_historical_klines_by_days("BTCUSDT", "binance", "1m", 1)
        result.details["count"] = len(klines)

        if len(klines) > 1000:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线 (预期~1440)"
        elif len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线 (数据可能不完整)"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_latest_n_query_okx(self, result: TestResult):
        """测试13: 最近N根查询-OKX"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
        result.details["requested"] = 100
        result.details["received"] = len(klines)

        if len(klines) == 100:
            result.status = "PASS"
            result.message = f"精确获取 {len(klines)} 根K线"
        elif len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)}/100 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_latest_n_query_binance(self, result: TestResult):
        """测试14: 最近N根查询-Binance"""
        klines = self.get_latest_historical_klines("BTCUSDT", "binance", "1m", 100)
        result.details["requested"] = 100
        result.details["received"] = len(klines)

        if len(klines) == 100:
            result.status = "PASS"
            result.message = f"精确获取 {len(klines)} 根K线"
        elif len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)}/100 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_okx_convenience(self, result: TestResult):
        """测试15: OKX便捷方法"""
        klines = self.get_okx_historical_klines("BTC-USDT-SWAP", "1m", 1)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_binance_convenience(self, result: TestResult):
        """测试16: Binance便捷方法"""
        klines = self.get_binance_historical_klines("BTCUSDT", "1m", 1)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_get_closes_okx(self, result: TestResult):
        """测试17: 获取收盘价数组-OKX"""
        closes = self.get_historical_closes("BTC-USDT-SWAP", "okx", "1m", 1)
        result.details["count"] = len(closes)

        if len(closes) > 0:
            result.details["min"] = min(closes)
            result.details["max"] = max(closes)
            result.details["avg"] = sum(closes) / len(closes)
            result.status = "PASS"
            result.message = f"获取 {len(closes)} 个收盘价"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_get_closes_binance(self, result: TestResult):
        """测试18: 获取收盘价数组-Binance"""
        closes = self.get_historical_closes("BTCUSDT", "binance", "1m", 1)
        result.details["count"] = len(closes)

        if len(closes) > 0:
            result.details["min"] = min(closes)
            result.details["max"] = max(closes)
            result.status = "PASS"
            result.message = f"获取 {len(closes)} 个收盘价"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_interval_1s(self, result: TestResult):
        """测试19: 1秒K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1s", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根1s K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到1s数据（可能不支持）"

    def test_interval_1m(self, result: TestResult):
        """测试20: 1分钟K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根1m K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到1m数据"

    def test_interval_5m(self, result: TestResult):
        """测试21: 5分钟K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "5m", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根5m K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到5m数据"

    def test_interval_15m(self, result: TestResult):
        """测试22: 15分钟K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "15m", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根15m K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到15m数据"

    def test_interval_1h(self, result: TestResult):
        """测试23: 1小时K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1h", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根1h K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到1h数据"

    def test_interval_4h(self, result: TestResult):
        """测试24: 4小时K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "4h", 100)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根4h K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到4h数据"

    def test_interval_1d(self, result: TestResult):
        """测试25: 日K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1d", 30)
        result.details["count"] = len(klines)

        if len(klines) > 0:
            result.status = "PASS"
            result.message = f"获取 {len(klines)} 根日K线"
        else:
            result.status = "FAIL"
            result.message = "未获取到日K数据"

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 80)
        print("  测试结果摘要")
        print("=" * 80 + "\n")

        pass_count = sum(1 for r in self.results if r.status == "PASS")
        fail_count = sum(1 for r in self.results if r.status == "FAIL")
        error_count = sum(1 for r in self.results if r.status == "ERROR")
        skip_count = sum(1 for r in self.results if r.status == "SKIP")
        total = len(self.results)

        print(f"总计: {total} 个测试")
        print(f"  通过: {pass_count}")
        print(f"  失败: {fail_count}")
        print(f"  错误: {error_count}")
        print(f"  跳过: {skip_count}")
        print(f"\n通过率: {pass_count / total * 100:.1f}%")

        # 打印失败的测试详情
        failed = [r for r in self.results if r.status in ("FAIL", "ERROR")]
        if failed:
            print("\n失败的测试:")
            for r in failed:
                print(f"  - {r.name}: {r.message}")


def main():
    print("\n" + "=" * 80)
    print("  Redis历史数据接口基础测试程序")
    print("=" * 80)
    print()
    print("本程序将测试所有基础的历史数据查询接口")
    print()

    test = RedisHistoricalBasicTest()
    test.run_all_tests()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
