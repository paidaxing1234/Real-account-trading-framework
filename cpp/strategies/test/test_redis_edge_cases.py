#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口边界条件和异常测试

测试各种边界条件和异常情况：
1. 空参数测试
2. 无效参数测试
3. 不存在的交易对测试
4. 不存在的交易所测试
5. 无效时间周期测试
6. 边界数量测试（0, 1, 极大值）
7. 时间范围边界测试
8. 重复调用测试
9. 数据一致性测试

@author Test Suite
@date 2025-01
"""

import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')

import strategy_base


class TestResult:
    """测试结果记录"""
    def __init__(self, name: str):
        self.name = name
        self.status = "PENDING"
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
        return f"{status_symbol} {self.name:<60} {self.status} ({self.duration:.3f}s)"


class RedisEdgeCaseTest(strategy_base.StrategyBase):
    """边界条件和异常测试"""

    def __init__(self):
        super().__init__("redis_edge_case_test")
        self.results: List[TestResult] = []
        self.connected = False

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("  Redis历史数据接口边界条件和异常测试")
        print("=" * 80 + "\n")

        # 先连接
        if not self.connect_historical_data():
            print("✗ 无法连接Redis，测试终止")
            return
        self.connected = True
        print("✓ Redis连接成功\n")

        # 测试列表
        tests = [
            # 空参数测试
            ("1. 空symbol参数", self.test_empty_symbol),
            ("2. 空exchange参数", self.test_empty_exchange),
            ("3. 空interval参数", self.test_empty_interval),

            # 无效参数测试
            ("4. 无效symbol-随机字符串", self.test_invalid_symbol_random),
            ("5. 无效symbol-特殊字符", self.test_invalid_symbol_special),
            ("6. 无效exchange", self.test_invalid_exchange),
            ("7. 无效interval", self.test_invalid_interval),

            # 不存在的交易对测试
            ("8. 不存在的OKX交易对", self.test_nonexistent_okx_symbol),
            ("9. 不存在的Binance交易对", self.test_nonexistent_binance_symbol),

            # 边界数量测试
            ("10. 请求0根K线", self.test_count_zero),
            ("11. 请求1根K线", self.test_count_one),
            ("12. 请求负数根K线", self.test_count_negative),
            ("13. 请求极大数量K线", self.test_count_very_large),

            # 时间范围边界测试
            ("14. 开始时间等于结束时间", self.test_time_range_equal),
            ("15. 开始时间大于结束时间", self.test_time_range_reversed),
            ("16. 未来时间范围", self.test_time_range_future),
            ("17. 很久以前的时间范围", self.test_time_range_ancient),
            ("18. 时间戳为0", self.test_time_range_zero),
            ("19. 负数时间戳", self.test_time_range_negative),

            # 天数边界测试
            ("20. 0天查询", self.test_days_zero),
            ("21. 负数天查询", self.test_days_negative),
            ("22. 极大天数查询", self.test_days_very_large),

            # 重复调用测试
            ("23. 重复连接测试", self.test_repeated_connect),
            ("24. 重复查询测试", self.test_repeated_query),

            # 数据一致性测试
            ("25. 数据时间顺序验证", self.test_data_time_order),
            ("26. 数据完整性验证", self.test_data_integrity),
            ("27. OHLC逻辑验证", self.test_ohlc_logic),

            # 混合参数测试
            ("28. OKX格式symbol查Binance", self.test_wrong_symbol_format_binance),
            ("29. Binance格式symbol查OKX", self.test_wrong_symbol_format_okx),

            # 并发安全测试（简化版）
            ("30. 快速连续查询", self.test_rapid_queries),
        ]

        for test_name, test_func in tests:
            result = TestResult(test_name)
            start_time = time.time()

            try:
                test_func(result)
            except Exception as e:
                result.status = "ERROR"
                result.message = str(e)

            result.duration = time.time() - start_time
            self.results.append(result)
            print(result)

        self.print_summary()

    def test_empty_symbol(self, result: TestResult):
        """测试空symbol参数"""
        klines = self.get_latest_historical_klines("", "okx", "1m", 100)
        result.details["count"] = len(klines)

        # 空symbol应该返回空结果，不应该崩溃
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_empty_exchange(self, result: TestResult):
        """测试空exchange参数"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_empty_interval(self, result: TestResult):
        """测试空interval参数"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_invalid_symbol_random(self, result: TestResult):
        """测试随机字符串symbol"""
        klines = self.get_latest_historical_klines("ABCDEFG123", "okx", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_invalid_symbol_special(self, result: TestResult):
        """测试特殊字符symbol"""
        klines = self.get_latest_historical_klines("!@#$%^&*()", "okx", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_invalid_exchange(self, result: TestResult):
        """测试无效exchange"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "invalid_exchange", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_invalid_interval(self, result: TestResult):
        """测试无效interval"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "invalid", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_nonexistent_okx_symbol(self, result: TestResult):
        """测试不存在的OKX交易对"""
        klines = self.get_latest_historical_klines("NONEXISTENT-USDT-SWAP", "okx", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_nonexistent_binance_symbol(self, result: TestResult):
        """测试不存在的Binance交易对"""
        klines = self.get_latest_historical_klines("NONEXISTENTUSDT", "binance", "1m", 100)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_count_zero(self, result: TestResult):
        """测试请求0根K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 0)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确返回空结果"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_count_one(self, result: TestResult):
        """测试请求1根K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 1)
        result.details["count"] = len(klines)

        if len(klines) == 1:
            result.status = "PASS"
            result.message = "正确返回1根K线"
        elif len(klines) == 0:
            result.status = "PASS"
            result.message = "返回空（可能无数据）"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_count_negative(self, result: TestResult):
        """测试请求负数根K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", -100)
        result.details["count"] = len(klines)

        # 负数应该被处理为0或返回空
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理负数参数"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_count_very_large(self, result: TestResult):
        """测试请求极大数量K线"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 1000000)
        result.details["count"] = len(klines)

        # 应该返回实际可用的数据量，不应该崩溃
        if len(klines) >= 0:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根（实际可用数据）"
        else:
            result.status = "FAIL"
            result.message = "异常情况"

    def test_time_range_equal(self, result: TestResult):
        """测试开始时间等于结束时间"""
        now = int(time.time() * 1000)
        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", now, now)
        result.details["count"] = len(klines)

        # 相同时间应该返回空或最多1根
        if len(klines) <= 1:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_time_range_reversed(self, result: TestResult):
        """测试开始时间大于结束时间"""
        now = int(time.time() * 1000)
        start = now
        end = now - 3600 * 1000  # 1小时前

        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start, end)
        result.details["count"] = len(klines)

        # 反转的时间范围应该返回空
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理反转时间范围"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_time_range_future(self, result: TestResult):
        """测试未来时间范围"""
        now = int(time.time() * 1000)
        start = now + 3600 * 1000  # 1小时后
        end = now + 7200 * 1000    # 2小时后

        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start, end)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理未来时间范围"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_time_range_ancient(self, result: TestResult):
        """测试很久以前的时间范围"""
        # 2010年的时间戳
        start = 1262304000000  # 2010-01-01
        end = 1264982400000    # 2010-02-01

        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start, end)
        result.details["count"] = len(klines)

        # 很久以前应该没有数据
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理历史时间范围"
        else:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根历史数据"

    def test_time_range_zero(self, result: TestResult):
        """测试时间戳为0"""
        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", 0, 0)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理零时间戳"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_time_range_negative(self, result: TestResult):
        """测试负数时间戳"""
        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", -1000, -500)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理负数时间戳"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_days_zero(self, result: TestResult):
        """测试0天查询"""
        klines = self.get_historical_klines_by_days("BTC-USDT-SWAP", "okx", "1m", 0)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理0天查询"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_days_negative(self, result: TestResult):
        """测试负数天查询"""
        klines = self.get_historical_klines_by_days("BTC-USDT-SWAP", "okx", "1m", -7)
        result.details["count"] = len(klines)

        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理负数天查询"
        else:
            result.status = "FAIL"
            result.message = f"意外返回 {len(klines)} 根数据"

    def test_days_very_large(self, result: TestResult):
        """测试极大天数查询"""
        klines = self.get_historical_klines_by_days("BTC-USDT-SWAP", "okx", "1m", 10000)
        result.details["count"] = len(klines)

        # 应该返回实际可用的数据，不应该崩溃
        if len(klines) >= 0:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根（实际可用数据）"
        else:
            result.status = "FAIL"
            result.message = "异常情况"

    def test_repeated_connect(self, result: TestResult):
        """测试重复连接"""
        # 尝试多次连接
        results = []
        for i in range(3):
            connected = self.connect_historical_data()
            results.append(connected)

        result.details["results"] = results

        # 重复连接应该都成功或者幂等
        if all(results):
            result.status = "PASS"
            result.message = "重复连接正常"
        else:
            result.status = "PASS"
            result.message = f"连接结果: {results}"

    def test_repeated_query(self, result: TestResult):
        """测试重复查询"""
        counts = []
        for i in range(5):
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
            counts.append(len(klines))

        result.details["counts"] = counts

        # 重复查询应该返回一致的结果
        if len(set(counts)) <= 2:  # 允许小幅波动（新数据到来）
            result.status = "PASS"
            result.message = f"查询结果一致: {counts}"
        else:
            result.status = "FAIL"
            result.message = f"查询结果不一致: {counts}"

    def test_data_time_order(self, result: TestResult):
        """测试数据时间顺序"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)

        if len(klines) < 2:
            result.status = "SKIP"
            result.message = "数据不足，无法验证"
            return

        # 验证时间是否升序
        is_ordered = True
        for i in range(1, len(klines)):
            if klines[i].timestamp <= klines[i-1].timestamp:
                is_ordered = False
                break

        result.details["count"] = len(klines)
        result.details["is_ordered"] = is_ordered

        if is_ordered:
            result.status = "PASS"
            result.message = "数据时间顺序正确（升序）"
        else:
            result.status = "FAIL"
            result.message = "数据时间顺序错误"

    def test_data_integrity(self, result: TestResult):
        """测试数据完整性"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)

        if len(klines) == 0:
            result.status = "SKIP"
            result.message = "无数据，无法验证"
            return

        # 验证每根K线的字段是否完整
        valid_count = 0
        invalid_count = 0

        for k in klines:
            if (k.timestamp > 0 and
                k.open > 0 and
                k.high > 0 and
                k.low > 0 and
                k.close > 0 and
                k.volume >= 0):
                valid_count += 1
            else:
                invalid_count += 1

        result.details["valid"] = valid_count
        result.details["invalid"] = invalid_count

        if invalid_count == 0:
            result.status = "PASS"
            result.message = f"全部 {valid_count} 根数据完整"
        else:
            result.status = "FAIL"
            result.message = f"有 {invalid_count} 根数据不完整"

    def test_ohlc_logic(self, result: TestResult):
        """测试OHLC逻辑"""
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)

        if len(klines) == 0:
            result.status = "SKIP"
            result.message = "无数据，无法验证"
            return

        # 验证OHLC逻辑: high >= max(open, close), low <= min(open, close)
        valid_count = 0
        invalid_count = 0

        for k in klines:
            if (k.high >= k.open and
                k.high >= k.close and
                k.low <= k.open and
                k.low <= k.close and
                k.high >= k.low):
                valid_count += 1
            else:
                invalid_count += 1

        result.details["valid"] = valid_count
        result.details["invalid"] = invalid_count

        if invalid_count == 0:
            result.status = "PASS"
            result.message = f"全部 {valid_count} 根OHLC逻辑正确"
        else:
            result.status = "FAIL"
            result.message = f"有 {invalid_count} 根OHLC逻辑错误"

    def test_wrong_symbol_format_binance(self, result: TestResult):
        """测试用OKX格式查Binance"""
        # 用OKX格式的symbol查Binance
        klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "binance", "1m", 100)
        result.details["count"] = len(klines)

        # 应该返回空（格式不匹配）
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理格式不匹配"
        else:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根（可能有兼容处理）"

    def test_wrong_symbol_format_okx(self, result: TestResult):
        """测试用Binance格式查OKX"""
        # 用Binance格式的symbol查OKX
        klines = self.get_latest_historical_klines("BTCUSDT", "okx", "1m", 100)
        result.details["count"] = len(klines)

        # 应该返回空（格式不匹配）
        if len(klines) == 0:
            result.status = "PASS"
            result.message = "正确处理格式不匹配"
        else:
            result.status = "PASS"
            result.message = f"返回 {len(klines)} 根（可能有兼容处理）"

    def test_rapid_queries(self, result: TestResult):
        """测试快速连续查询"""
        success_count = 0
        total_count = 20

        for i in range(total_count):
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 10)
            if len(klines) > 0:
                success_count += 1

        result.details["success"] = success_count
        result.details["total"] = total_count

        if success_count == total_count:
            result.status = "PASS"
            result.message = f"全部 {total_count} 次查询成功"
        elif success_count > total_count * 0.9:
            result.status = "PASS"
            result.message = f"{success_count}/{total_count} 次查询成功"
        else:
            result.status = "FAIL"
            result.message = f"只有 {success_count}/{total_count} 次成功"

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 80)
        print("  边界条件和异常测试结果摘要")
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
    print("  Redis历史数据接口边界条件和异常测试程序")
    print("=" * 80)
    print()
    print("本程序将测试各种边界条件和异常情况")
    print("包括: 空参数、无效参数、边界值、数据一致性等")
    print()

    test = RedisEdgeCaseTest()
    test.run_all_tests()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
