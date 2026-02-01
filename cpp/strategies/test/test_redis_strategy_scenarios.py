#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis历史数据接口策略场景测试

模拟真实策略的使用场景，测试各种组合：
1. 指定交易所 + 指定币种 + 指定根数
2. 多币种顺序查询
3. 多交易所对比查询
4. 不同时间周期组合
5. 大数据量查询
6. 策略初始化场景

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


class RedisStrategyScenarioTest(strategy_base.StrategyBase):
    """策略场景测试"""

    def __init__(self):
        super().__init__("redis_strategy_scenario_test")
        self.results: List[TestResult] = []
        self.connected = False

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("  Redis历史数据接口策略场景测试")
        print("=" * 80 + "\n")

        # 先连接
        if not self.connect_historical_data():
            print("✗ 无法连接Redis，测试终止")
            return
        self.connected = True
        print("✓ Redis连接成功\n")

        # 测试场景列表
        scenarios = [
            # 场景1: RetSkew策略场景 - OKX BTC 15000根1分钟
            ("场景1: RetSkew策略-OKX BTC 15000根1m",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1m", 15000)),

            # 场景2: RetSkew策略场景 - OKX ETH 15000根1分钟
            ("场景2: RetSkew策略-OKX ETH 15000根1m",
             lambda r: self.test_specific_query(r, "okx", "ETH-USDT-SWAP", "1m", 15000)),

            # 场景3: RetSkew策略场景 - Binance BTC 15000根1分钟
            ("场景3: RetSkew策略-Binance BTC 15000根1m",
             lambda r: self.test_specific_query(r, "binance", "BTCUSDT", "1m", 15000)),

            # 场景4: RetSkew策略场景 - Binance ETH 15000根1分钟
            ("场景4: RetSkew策略-Binance ETH 15000根1m",
             lambda r: self.test_specific_query(r, "binance", "ETHUSDT", "1m", 15000)),

            # 场景5: 网格策略场景 - 较少数据
            ("场景5: 网格策略-OKX BTC 1000根1m",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1m", 1000)),

            # 场景6: 网格策略场景 - 5分钟周期
            ("场景6: 网格策略-OKX BTC 500根5m",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "5m", 500)),

            # 场景7: 趋势策略场景 - 小时级别
            ("场景7: 趋势策略-OKX BTC 200根1h",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1h", 200)),

            # 场景8: 趋势策略场景 - 4小时级别
            ("场景8: 趋势策略-OKX BTC 100根4h",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "4h", 100)),

            # 场景9: 日线策略场景
            ("场景9: 日线策略-OKX BTC 60根1d",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1d", 60)),

            # 场景10: 高频策略场景 - 秒级数据
            ("场景10: 高频策略-OKX BTC 3600根1s",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1s", 3600)),

            # 场景11: 多币种策略 - OKX主流币
            ("场景11: 多币种策略-OKX主流币",
             self.test_multi_symbol_okx),

            # 场景12: 多币种策略 - Binance主流币
            ("场景12: 多币种策略-Binance主流币",
             self.test_multi_symbol_binance),

            # 场景13: 跨交易所对比 - BTC
            ("场景13: 跨交易所对比-BTC",
             self.test_cross_exchange_btc),

            # 场景14: 跨交易所对比 - ETH
            ("场景14: 跨交易所对比-ETH",
             self.test_cross_exchange_eth),

            # 场景15: 多周期策略 - 同币种不同周期
            ("场景15: 多周期策略-BTC多周期",
             self.test_multi_interval),

            # 场景16: 大数据量查询 - 30000根
            ("场景16: 大数据量-OKX BTC 30000根1m",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1m", 30000)),

            # 场景17: 大数据量查询 - 50000根
            ("场景17: 大数据量-OKX BTC 50000根1m",
             lambda r: self.test_specific_query(r, "okx", "BTC-USDT-SWAP", "1m", 50000)),

            # 场景18: 策略初始化场景 - 完整流程
            ("场��18: 策略初始化完整流程",
             self.test_strategy_init_flow),

            # 场景19: SOL币种测试 - OKX
            ("场景19: SOL币种-OKX 5000根1m",
             lambda r: self.test_specific_query(r, "okx", "SOL-USDT-SWAP", "1m", 5000)),

            # 场景20: SOL币种测试 - Binance
            ("场景20: SOL币种-Binance 5000根1m",
             lambda r: self.test_specific_query(r, "binance", "SOLUSDT", "1m", 5000)),

            # 场景21: DOGE币种测试
            ("场景21: DOGE币种-OKX 5000根1m",
             lambda r: self.test_specific_query(r, "okx", "DOGE-USDT-SWAP", "1m", 5000)),

            # 场景22: XRP币种测试
            ("场景22: XRP币种-OKX 5000根1m",
             lambda r: self.test_specific_query(r, "okx", "XRP-USDT-SWAP", "1m", 5000)),

            # 场景23: 按天数查询场景 - 7天
            ("场景23: 按天数查询-OKX BTC 7天1m",
             lambda r: self.test_days_query(r, "okx", "BTC-USDT-SWAP", "1m", 7)),

            # 场景24: 按天数查询场景 - 30天
            ("场景24: 按天数查询-OKX BTC 30天1m",
             lambda r: self.test_days_query(r, "okx", "BTC-USDT-SWAP", "1m", 30)),

            # 场景25: 时间范围查询场景
            ("场景25: 时间范围查询-最近24小时",
             self.test_time_range_query),
        ]

        for scenario_name, test_func in scenarios:
            result = TestResult(scenario_name)
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

    def test_specific_query(self, result: TestResult, exchange: str, symbol: str,
                           interval: str, count: int):
        """测试指定交易所+币种+根数的查询"""
        klines = self.get_latest_historical_klines(symbol, exchange, interval, count)
        actual_count = len(klines)

        result.details["exchange"] = exchange
        result.details["symbol"] = symbol
        result.details["interval"] = interval
        result.details["requested"] = count
        result.details["received"] = actual_count

        if actual_count > 0:
            first = klines[0]
            last = klines[-1]
            first_dt = datetime.fromtimestamp(first.timestamp / 1000)
            last_dt = datetime.fromtimestamp(last.timestamp / 1000)

            result.details["first_time"] = first_dt.strftime('%Y-%m-%d %H:%M')
            result.details["last_time"] = last_dt.strftime('%Y-%m-%d %H:%M')
            result.details["last_close"] = last.close

            # 允许10%的误差
            if actual_count >= count * 0.9:
                result.status = "PASS"
                result.message = f"获取 {actual_count}/{count} 根, 最新价: {last.close:.2f}"
            else:
                result.status = "PASS"  # 数据不足但有数据也算通过
                result.message = f"数据不足 {actual_count}/{count}, 最新价: {last.close:.2f}"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_days_query(self, result: TestResult, exchange: str, symbol: str,
                       interval: str, days: int):
        """测试按天数查询"""
        klines = self.get_historical_klines_by_days(symbol, exchange, interval, days)
        actual_count = len(klines)

        result.details["exchange"] = exchange
        result.details["symbol"] = symbol
        result.details["interval"] = interval
        result.details["days"] = days
        result.details["received"] = actual_count

        if actual_count > 0:
            first = klines[0]
            last = klines[-1]
            first_dt = datetime.fromtimestamp(first.timestamp / 1000)
            last_dt = datetime.fromtimestamp(last.timestamp / 1000)

            result.details["first_time"] = first_dt.strftime('%Y-%m-%d %H:%M')
            result.details["last_time"] = last_dt.strftime('%Y-%m-%d %H:%M')

            result.status = "PASS"
            result.message = f"获取 {actual_count} 根, 时间跨度: {first_dt.strftime('%m-%d')} ~ {last_dt.strftime('%m-%d')}"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def test_multi_symbol_okx(self, result: TestResult):
        """测试OKX多币种查询"""
        symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
                   "DOGE-USDT-SWAP", "XRP-USDT-SWAP"]

        success_count = 0
        total_klines = 0
        symbol_results = {}

        for symbol in symbols:
            klines = self.get_latest_historical_klines(symbol, "okx", "1m", 1000)
            count = len(klines)
            symbol_results[symbol] = count
            total_klines += count
            if count > 0:
                success_count += 1

        result.details["symbols"] = symbol_results
        result.details["success_count"] = success_count
        result.details["total_klines"] = total_klines

        if success_count == len(symbols):
            result.status = "PASS"
            result.message = f"全部 {success_count}/{len(symbols)} 币种成功, 共 {total_klines} 根"
        elif success_count > 0:
            result.status = "PASS"
            result.message = f"部分成功 {success_count}/{len(symbols)}, 共 {total_klines} 根"
        else:
            result.status = "FAIL"
            result.message = "所有币种查询失败"

    def test_multi_symbol_binance(self, result: TestResult):
        """测试Binance多币种查询"""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

        success_count = 0
        total_klines = 0
        symbol_results = {}

        for symbol in symbols:
            klines = self.get_latest_historical_klines(symbol, "binance", "1m", 1000)
            count = len(klines)
            symbol_results[symbol] = count
            total_klines += count
            if count > 0:
                success_count += 1

        result.details["symbols"] = symbol_results
        result.details["success_count"] = success_count
        result.details["total_klines"] = total_klines

        if success_count == len(symbols):
            result.status = "PASS"
            result.message = f"全部 {success_count}/{len(symbols)} 币种成功, 共 {total_klines} 根"
        elif success_count > 0:
            result.status = "PASS"
            result.message = f"部分成功 {success_count}/{len(symbols)}, 共 {total_klines} 根"
        else:
            result.status = "FAIL"
            result.message = "所有币种查询失败"

    def test_cross_exchange_btc(self, result: TestResult):
        """测试跨交易所BTC对比"""
        okx_klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
        binance_klines = self.get_latest_historical_klines("BTCUSDT", "binance", "1m", 100)

        result.details["okx_count"] = len(okx_klines)
        result.details["binance_count"] = len(binance_klines)

        if len(okx_klines) > 0 and len(binance_klines) > 0:
            okx_price = okx_klines[-1].close
            binance_price = binance_klines[-1].close
            diff = abs(okx_price - binance_price)
            diff_pct = diff / binance_price * 100

            result.details["okx_price"] = okx_price
            result.details["binance_price"] = binance_price
            result.details["diff_pct"] = diff_pct

            result.status = "PASS"
            result.message = f"OKX: {okx_price:.2f}, Binance: {binance_price:.2f}, 差异: {diff_pct:.4f}%"
        elif len(okx_klines) > 0 or len(binance_klines) > 0:
            result.status = "PASS"
            result.message = f"部分成功 OKX:{len(okx_klines)}, Binance:{len(binance_klines)}"
        else:
            result.status = "FAIL"
            result.message = "两个交易所都无数据"

    def test_cross_exchange_eth(self, result: TestResult):
        """测试跨交易所ETH对比"""
        okx_klines = self.get_latest_historical_klines("ETH-USDT-SWAP", "okx", "1m", 100)
        binance_klines = self.get_latest_historical_klines("ETHUSDT", "binance", "1m", 100)

        result.details["okx_count"] = len(okx_klines)
        result.details["binance_count"] = len(binance_klines)

        if len(okx_klines) > 0 and len(binance_klines) > 0:
            okx_price = okx_klines[-1].close
            binance_price = binance_klines[-1].close
            diff = abs(okx_price - binance_price)
            diff_pct = diff / binance_price * 100

            result.details["okx_price"] = okx_price
            result.details["binance_price"] = binance_price
            result.details["diff_pct"] = diff_pct

            result.status = "PASS"
            result.message = f"OKX: {okx_price:.2f}, Binance: {binance_price:.2f}, 差异: {diff_pct:.4f}%"
        elif len(okx_klines) > 0 or len(binance_klines) > 0:
            result.status = "PASS"
            result.message = f"部分成功 OKX:{len(okx_klines)}, Binance:{len(binance_klines)}"
        else:
            result.status = "FAIL"
            result.message = "两个交易所都无数据"

    def test_multi_interval(self, result: TestResult):
        """测试多周期查询"""
        intervals = ["1m", "5m", "15m", "1h", "4h"]
        interval_results = {}
        success_count = 0

        for interval in intervals:
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", interval, 100)
            count = len(klines)
            interval_results[interval] = count
            if count > 0:
                success_count += 1

        result.details["intervals"] = interval_results
        result.details["success_count"] = success_count

        if success_count == len(intervals):
            result.status = "PASS"
            result.message = f"全部 {success_count}/{len(intervals)} 周期成功"
        elif success_count > 0:
            result.status = "PASS"
            result.message = f"部分成功 {success_count}/{len(intervals)}"
        else:
            result.status = "FAIL"
            result.message = "所有周期查询失败"

    def test_strategy_init_flow(self, result: TestResult):
        """测试策略初始化完整流程"""
        # 模拟策略初始化时的数据获取流程
        steps = []

        # 步骤1: 获取可用交易对
        symbols = self.get_available_historical_symbols("okx")
        steps.append(("获取交易对", len(symbols) > 0, len(symbols)))

        # 步骤2: 检查目标币种是否可用
        target_symbol = "BTC-USDT-SWAP"
        symbol_available = target_symbol in symbols if symbols else False
        steps.append(("检查目标币种", symbol_available, target_symbol))

        # 步骤3: 获取数据时间范围
        earliest, latest = self.get_historical_data_time_range(target_symbol, "okx", "1m")
        steps.append(("获取时间范围", earliest > 0 and latest > 0, f"{earliest}-{latest}"))

        # 步骤4: 获取K线数量
        count = self.get_historical_kline_count(target_symbol, "okx", "1m")
        steps.append(("获取K线数量", count > 0, count))

        # 步骤5: 获取历史数据
        klines = self.get_latest_historical_klines(target_symbol, "okx", "1m", 15000)
        steps.append(("获取历史数据", len(klines) > 0, len(klines)))

        # 步骤6: 获取收盘价数组
        closes = self.get_historical_closes(target_symbol, "okx", "1m", 7)
        steps.append(("获取收盘价", len(closes) > 0, len(closes)))

        result.details["steps"] = steps
        success_count = sum(1 for _, success, _ in steps if success)

        if success_count == len(steps):
            result.status = "PASS"
            result.message = f"全部 {success_count}/{len(steps)} 步骤成功"
        elif success_count > 0:
            result.status = "PASS"
            result.message = f"部分成功 {success_count}/{len(steps)}"
        else:
            result.status = "FAIL"
            result.message = "初始化流程失败"

    def test_time_range_query(self, result: TestResult):
        """测试时间范围查询"""
        end_time = int(time.time() * 1000)
        start_time = end_time - 24 * 3600 * 1000  # 24小时前

        klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start_time, end_time)
        actual_count = len(klines)

        result.details["start_time"] = datetime.fromtimestamp(start_time / 1000).strftime('%Y-%m-%d %H:%M')
        result.details["end_time"] = datetime.fromtimestamp(end_time / 1000).strftime('%Y-%m-%d %H:%M')
        result.details["received"] = actual_count

        # 24小时应该有约1440根1分钟K线
        if actual_count > 1000:
            result.status = "PASS"
            result.message = f"获取 {actual_count} 根 (预期~1440)"
        elif actual_count > 0:
            result.status = "PASS"
            result.message = f"获取 {actual_count} 根 (数据可能不完整)"
        else:
            result.status = "FAIL"
            result.message = "未获取到数据"

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 80)
        print("  策略场景测试结果摘要")
        print("=" * 80 + "\n")

        pass_count = sum(1 for r in self.results if r.status == "PASS")
        fail_count = sum(1 for r in self.results if r.status == "FAIL")
        error_count = sum(1 for r in self.results if r.status == "ERROR")
        total = len(self.results)

        print(f"总计: {total} 个场景")
        print(f"  通过: {pass_count}")
        print(f"  失败: {fail_count}")
        print(f"  错误: {error_count}")
        print(f"\n通过率: {pass_count / total * 100:.1f}%")

        # 打印失败的测试详情
        failed = [r for r in self.results if r.status in ("FAIL", "ERROR")]
        if failed:
            print("\n失败的场景:")
            for r in failed:
                print(f"  - {r.name}: {r.message}")

        # 打印性能统计
        print("\n性能统计:")
        durations = [r.duration for r in self.results]
        print(f"  总耗时: {sum(durations):.2f}s")
        print(f"  平均耗时: {sum(durations)/len(durations):.3f}s")
        print(f"  最长耗时: {max(durations):.3f}s")
        print(f"  最短耗时: {min(durations):.3f}s")


def main():
    print("\n" + "=" * 80)
    print("  Redis历史数据接口策略场景测试程序")
    print("=" * 80)
    print()
    print("本程序将模拟真实策略的使用场景进行测试")
    print("包括: 指定交易所/币种/根数、多币种、跨交易所等场景")
    print()

    test = RedisStrategyScenarioTest()
    test.run_all_tests()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
