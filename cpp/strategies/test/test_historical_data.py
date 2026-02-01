#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试历史数据查询接口的功能（基于 server 端 RedisDataProvider）

测试所有历史K线数据查询接口，包括：
1. 连接历史数据服务
2. 时间范围查询
3. 按天数查询
4. 最近N根查询
5. 便捷方法（OKX/Binance）
6. 获取收盘价数组
7. 获取可用交易对
8. 获取时间范围
9. 获取K线数量
10. 策略实际使用场景测试

注意：批量查询接口已移除，使用 server 端的 RedisDataProvider 实现
"""

import sys
import time
from datetime import datetime, timedelta

# 添加策略路径
sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')

import strategy_base


class HistoricalDataTestStrategy(strategy_base.StrategyBase):
    """历史数据接口测试策略"""

    def __init__(self):
        super().__init__("historical_data_test")
        self.test_results = {}

    def on_init(self):
        print("\n" + "="*80)
        print("  历史数据查询接口测试 (RedisDataProvider)")
        print("="*80 + "\n")

        # 测试1: 连接历史数据服务
        self.test_connect_historical_data()

        # 测试2: 获取可用交易对
        self.test_get_available_symbols()

        # 测试3: 获取K线数量
        self.test_get_kline_count()

        # 测试4: 获取时间范围
        self.test_get_time_range()

        # 测试5: 按天数查询
        self.test_get_klines_by_days()

        # 测试6: 时间范围查询
        self.test_get_klines_by_time_range()

        # 测试7: 最近N根查询
        self.test_get_latest_klines()

        # 测试8: OKX便捷方法
        self.test_okx_convenience_method()

        # 测试9: Binance便捷方法
        self.test_binance_convenience_method()

        # 测试10: 获取收盘价数组
        self.test_get_closes()

        # 测试11: 策略实际使用场景 - 指定交易所、币种、根数
        self.test_strategy_use_case()

        # 测试12: 多币种顺序查询
        self.test_multi_symbol_query()

        # 打印测试结果摘要
        self.print_test_summary()

    def on_start(self):
        print("\n[测试完成] 策略启动")

    def on_stop(self):
        print("\n[测试完成] 策略停止")

    def test_connect_historical_data(self):
        """测试1: 连接历史数据服务"""
        test_name = "连接历史数据服务"
        print(f"\n{'='*80}")
        print(f"测试1: {test_name}")
        print(f"{'='*80}")

        try:
            result = self.connect_historical_data()
            if result:
                print(f"✓ 连接成功")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 连接失败")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_available_symbols(self):
        """测试2: 获取可用交易对"""
        test_name = "获取可用交易对"
        print(f"\n{'='*80}")
        print(f"测试2: {test_name}")
        print(f"{'='*80}")

        try:
            # 获取OKX交易对
            okx_symbols = self.get_available_historical_symbols("okx")
            print(f"OKX 交易对数量: {len(okx_symbols)}")
            if len(okx_symbols) > 0:
                print(f"前5个: {okx_symbols[:5]}")

            # 获取Binance交易对
            binance_symbols = self.get_available_historical_symbols("binance")
            print(f"Binance 交易对数量: {len(binance_symbols)}")
            if len(binance_symbols) > 0:
                print(f"前5个: {binance_symbols[:5]}")

            # 获取所有交易对
            all_symbols = self.get_available_historical_symbols()
            print(f"总交易对数量: {len(all_symbols)}")

            if len(okx_symbols) > 0 or len(binance_symbols) > 0:
                print(f"✓ 成功获取交易对列表")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 交易对列表为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_kline_count(self):
        """测试3: 获取K线数量"""
        test_name = "获取K线数量"
        print(f"\n{'='*80}")
        print(f"测试3: {test_name}")
        print(f"{'='*80}")

        try:
            # OKX BTC 1m
            count_okx = self.get_historical_kline_count("BTC-USDT-SWAP", "okx", "1m")
            print(f"OKX BTC-USDT-SWAP 1m K线数量: {count_okx:,}")

            # Binance BTC 1m
            count_binance = self.get_historical_kline_count("BTCUSDT", "binance", "1m")
            print(f"Binance BTCUSDT 1m K线数量: {count_binance:,}")

            if count_okx > 0 or count_binance > 0:
                print(f"✓ 成功获取K线数量")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ K线数量为0")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_time_range(self):
        """测试4: 获取时间范围"""
        test_name = "获取时间范围"
        print(f"\n{'='*80}")
        print(f"测试4: {test_name}")
        print(f"{'='*80}")

        try:
            # OKX BTC 1m
            earliest, latest = self.get_historical_data_time_range("BTC-USDT-SWAP", "okx", "1m")
            if earliest > 0 and latest > 0:
                earliest_dt = datetime.fromtimestamp(earliest / 1000)
                latest_dt = datetime.fromtimestamp(latest / 1000)
                print(f"OKX BTC-USDT-SWAP 1m:")
                print(f"  最早: {earliest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  最新: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            # Binance BTC 1m
            earliest, latest = self.get_historical_data_time_range("BTCUSDT", "binance", "1m")
            if earliest > 0 and latest > 0:
                earliest_dt = datetime.fromtimestamp(earliest / 1000)
                latest_dt = datetime.fromtimestamp(latest / 1000)
                print(f"Binance BTCUSDT 1m:")
                print(f"  最早: {earliest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  最新: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            if earliest > 0 and latest > 0:
                print(f"✓ 成功获取时间范围")
                self.test_results[test_name] = "PASS"
            else:
                print(f"⚠ 时间范围为空（可能没有数据）")
                self.test_results[test_name] = "PARTIAL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_klines_by_days(self):
        """测试5: 按天数查询"""
        test_name = "按天数查询"
        print(f"\n{'='*80}")
        print(f"测试5: {test_name}")
        print(f"{'='*80}")

        try:
            # 查询最近7天的1m K线
            klines = self.get_historical_klines_by_days("BTC-USDT-SWAP", "okx", "1m", 7)
            print(f"查询最近7天的OKX BTC 1m K线")
            print(f"  返回数量: {len(klines)}")

            if len(klines) > 0:
                first = klines[0]
                last = klines[-1]
                first_dt = datetime.fromtimestamp(first.timestamp / 1000)
                last_dt = datetime.fromtimestamp(last.timestamp / 1000)
                print(f"  时间范围: {first_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {last_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  第一根: open={first.open}, close={first.close}, volume={first.volume}")
                print(f"  最后根: open={last.open}, close={last.close}, volume={last.volume}")
                print(f"✓ 成功查询K线数据")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_klines_by_time_range(self):
        """测试6: 时间范围查询"""
        test_name = "时间范围查询"
        print(f"\n{'='*80}")
        print(f"测试6: {test_name}")
        print(f"{'='*80}")

        try:
            # 查询最近1小时的1m K线
            end_time = int(time.time() * 1000)
            start_time = end_time - 3600 * 1000  # 1小时前

            klines = self.get_historical_klines("BTC-USDT-SWAP", "okx", "1m", start_time, end_time)
            print(f"查询最近1小时的OKX BTC 1m K线")
            print(f"  返回数量: {len(klines)}")

            if len(klines) > 0:
                first = klines[0]
                last = klines[-1]
                first_dt = datetime.fromtimestamp(first.timestamp / 1000)
                last_dt = datetime.fromtimestamp(last.timestamp / 1000)
                print(f"  时间范围: {first_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {last_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  第一根: open={first.open}, close={first.close}")
                print(f"  最后根: open={last.open}, close={last.close}")
                print(f"✓ 成功查询K线数据")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_latest_klines(self):
        """测试7: 最近N根查询"""
        test_name = "最近N根查询"
        print(f"\n{'='*80}")
        print(f"测试7: {test_name}")
        print(f"{'='*80}")

        try:
            # 查询最近100根1m K线
            klines = self.get_latest_historical_klines("BTC-USDT-SWAP", "okx", "1m", 100)
            print(f"查询最近100根OKX BTC 1m K线")
            print(f"  返回数量: {len(klines)}")

            if len(klines) > 0:
                first = klines[0]
                last = klines[-1]
                first_dt = datetime.fromtimestamp(first.timestamp / 1000)
                last_dt = datetime.fromtimestamp(last.timestamp / 1000)
                print(f"  时间范围: {first_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {last_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  最后根: open={last.open}, close={last.close}")

                if len(klines) == 100:
                    print(f"✓ 成功查询100根K线")
                    self.test_results[test_name] = "PASS"
                else:
                    print(f"⚠ 返回{len(klines)}根，不足100根")
                    self.test_results[test_name] = "PARTIAL"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_okx_convenience_method(self):
        """测试8: OKX便捷方法"""
        test_name = "OKX便捷方法"
        print(f"\n{'='*80}")
        print(f"测试8: {test_name}")
        print(f"{'='*80}")

        try:
            # 使用便捷方法查询
            klines = self.get_okx_historical_klines("BTC-USDT-SWAP", "1m", 1)
            print(f"使用便捷方法查询OKX BTC 1m K线（最近1天）")
            print(f"  返回数量: {len(klines)}")

            if len(klines) > 0:
                last = klines[-1]
                last_dt = datetime.fromtimestamp(last.timestamp / 1000)
                print(f"  最新K线: {last_dt.strftime('%Y-%m-%d %H:%M:%S')}, close={last.close}")
                print(f"✓ 便捷方法工作正常")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_binance_convenience_method(self):
        """测试9: Binance便捷方法"""
        test_name = "Binance便捷方法"
        print(f"\n{'='*80}")
        print(f"测试9: {test_name}")
        print(f"{'='*80}")

        try:
            # 使用便捷方法查询
            klines = self.get_binance_historical_klines("BTCUSDT", "1m", 1)
            print(f"使用便捷方法查询Binance BTC 1m K线（最近1天）")
            print(f"  返回数量: {len(klines)}")

            if len(klines) > 0:
                last = klines[-1]
                last_dt = datetime.fromtimestamp(last.timestamp / 1000)
                print(f"  最新K线: {last_dt.strftime('%Y-%m-%d %H:%M:%S')}, close={last.close}")
                print(f"✓ 便捷方法工作正常")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_get_closes(self):
        """测试10: 获取收盘价数组"""
        test_name = "获取收盘价数组"
        print(f"\n{'='*80}")
        print(f"测试10: {test_name}")
        print(f"{'='*80}")

        try:
            # 获取最近7天的收盘价
            closes = self.get_historical_closes("BTC-USDT-SWAP", "okx", "1m", 7)
            print(f"获取最近7天的OKX BTC 1m收盘价")
            print(f"  返回数量: {len(closes)}")

            if len(closes) > 0:
                print(f"  最近5个收盘价: {closes[-5:]}")
                print(f"  最高价: {max(closes):.2f}")
                print(f"  最低价: {min(closes):.2f}")
                print(f"  平均价: {sum(closes)/len(closes):.2f}")
                print(f"✓ 成功获取收盘价数组")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 返回数据为空")
                self.test_results[test_name] = "FAIL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_strategy_use_case(self):
        """测试11: 策略实际使用场景 - 指定交易所、币种、根数"""
        test_name = "策略实际使用场景"
        print(f"\n{'='*80}")
        print(f"测试11: {test_name}")
        print(f"{'='*80}")

        try:
            # 模拟 RetSkew 策略的使用场景
            # 策略需要获取指定交易所、指定币种、指定根数的历史数据

            test_cases = [
                # (exchange, symbol, interval, count, description)
                ("okx", "BTC-USDT-SWAP", "1m", 15000, "OKX BTC 15000根1分钟K线"),
                ("okx", "ETH-USDT-SWAP", "1m", 10000, "OKX ETH 10000根1分钟K线"),
                ("binance", "BTCUSDT", "1m", 15000, "Binance BTC 15000根1分钟K线"),
                ("binance", "ETHUSDT", "1m", 10000, "Binance ETH 10000根1分钟K线"),
                ("okx", "BTC-USDT-SWAP", "5m", 2000, "OKX BTC 2000根5分钟K线"),
                ("binance", "BTCUSDT", "1h", 500, "Binance BTC 500根1小时K线"),
            ]

            all_passed = True
            for exchange, symbol, interval, count, desc in test_cases:
                print(f"\n  测试: {desc}")
                start_time = time.time()

                klines = self.get_latest_historical_klines(symbol, exchange, interval, count)

                elapsed = time.time() - start_time
                actual_count = len(klines)

                if actual_count > 0:
                    # 验证数据完整性
                    first = klines[0]
                    last = klines[-1]
                    first_dt = datetime.fromtimestamp(first.timestamp / 1000)
                    last_dt = datetime.fromtimestamp(last.timestamp / 1000)

                    print(f"    请求: {count} 根, 实际: {actual_count} 根")
                    print(f"    时间范围: {first_dt.strftime('%Y-%m-%d %H:%M')} ~ {last_dt.strftime('%Y-%m-%d %H:%M')}")
                    print(f"    最新价格: {last.close:.2f}")
                    print(f"    查询耗时: {elapsed:.3f}秒")

                    if actual_count >= count * 0.9:  # 允许10%的误差
                        print(f"    ✓ 通过")
                    else:
                        print(f"    ⚠ 数据不足 ({actual_count}/{count})")
                        all_passed = False
                else:
                    print(f"    ✗ 无数据")
                    all_passed = False

            if all_passed:
                print(f"\n✓ 所有策略使用场景测试通过")
                self.test_results[test_name] = "PASS"
            else:
                print(f"\n⚠ 部分测试未通过")
                self.test_results[test_name] = "PARTIAL"

        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_multi_symbol_query(self):
        """测试12: 多币种顺序查询"""
        test_name = "多币种顺序查询"
        print(f"\n{'='*80}")
        print(f"测试12: {test_name}")
        print(f"{'='*80}")

        try:
            # 模拟多币种策略的使用场景
            symbols_okx = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
            symbols_binance = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

            print("\n  OKX 多币种查询:")
            start_time = time.time()
            okx_results = {}
            for symbol in symbols_okx:
                klines = self.get_latest_historical_klines(symbol, "okx", "1m", 1000)
                okx_results[symbol] = len(klines)
                if len(klines) > 0:
                    print(f"    {symbol}: {len(klines)} 根, 最新价: {klines[-1].close:.2f}")
                else:
                    print(f"    {symbol}: 无数据")
            okx_elapsed = time.time() - start_time
            print(f"  OKX 总耗时: {okx_elapsed:.3f}秒")

            print("\n  Binance 多���种查询:")
            start_time = time.time()
            binance_results = {}
            for symbol in symbols_binance:
                klines = self.get_latest_historical_klines(symbol, "binance", "1m", 1000)
                binance_results[symbol] = len(klines)
                if len(klines) > 0:
                    print(f"    {symbol}: {len(klines)} 根, 最新价: {klines[-1].close:.2f}")
                else:
                    print(f"    {symbol}: 无数据")
            binance_elapsed = time.time() - start_time
            print(f"  Binance 总耗时: {binance_elapsed:.3f}秒")

            # 检查结果
            okx_success = sum(1 for v in okx_results.values() if v > 0)
            binance_success = sum(1 for v in binance_results.values() if v > 0)

            if okx_success == len(symbols_okx) and binance_success == len(symbols_binance):
                print(f"\n✓ 多币种查询成功")
                self.test_results[test_name] = "PASS"
            elif okx_success > 0 or binance_success > 0:
                print(f"\n⚠ 部分币种查询成功 (OKX: {okx_success}/{len(symbols_okx)}, Binance: {binance_success}/{len(symbols_binance)})")
                self.test_results[test_name] = "PARTIAL"
            else:
                print(f"\n✗ 多币种查询失败")
                self.test_results[test_name] = "FAIL"

        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def print_test_summary(self):
        """打印测试结果摘要"""
        print(f"\n{'='*80}")
        print("  测试结果摘要")
        print(f"{'='*80}\n")

        pass_count = sum(1 for r in self.test_results.values() if r == "PASS")
        partial_count = sum(1 for r in self.test_results.values() if r == "PARTIAL")
        fail_count = sum(1 for r in self.test_results.values() if r == "FAIL")
        error_count = sum(1 for r in self.test_results.values() if r == "ERROR")
        total_count = len(self.test_results)

        for test_name, result in self.test_results.items():
            status_symbol = {
                "PASS": "✓",
                "PARTIAL": "⚠",
                "FAIL": "✗",
                "ERROR": "✗"
            }.get(result, "?")

            print(f"{status_symbol} {test_name:<30} {result}")

        print(f"\n{'='*80}")
        print(f"总计: {total_count} 个测试")
        print(f"  通过: {pass_count}")
        print(f"  部分通过: {partial_count}")
        print(f"  失败: {fail_count}")
        print(f"  错误: {error_count}")
        print(f"{'='*80}\n")

        if pass_count == total_count:
            print("所有测试通过！历史数据查询接口工作正常。")
        elif pass_count + partial_count == total_count:
            print("大部分测试通过，部分功能可能受限。")
        else:
            print("部分测试失败，请检查配置和数据。")


def main():
    print("\n" + "="*80)
    print("  历史数据查询接口测试程序")
    print("="*80)
    print()
    print("本程序将测试所有历史K线数据查询接口的功能")
    print("包括: 连接、查询、策略使用场景等12个测试项")
    print()

    # 创建测试策略
    strategy = HistoricalDataTestStrategy()

    # 初始化（会自动运行所有测试）
    strategy.on_init()

    # 启动
    strategy.on_start()

    # 等待一下
    time.sleep(1)

    # 停止
    strategy.on_stop()

    print("\n测试完成！")


if __name__ == "__main__":
    main()
