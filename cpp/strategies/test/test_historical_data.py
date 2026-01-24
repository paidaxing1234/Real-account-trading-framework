#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试历史数据查询接口的功能

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
10. 批量并行查询
"""

import sys
import time
from datetime import datetime, timedelta

# 添加策略路径
sys.path.append('/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies')

import strategy_base

class HistoricalDataTestStrategy(strategy_base.StrategyBase):
    def __init__(self):
        super().__init__("historical_data_test")
        self.test_results = {}

    def on_init(self):
        print("\n" + "="*80)
        print("  历史数据查询接口测试")
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

        # 测试11: 批量并行查询K线
        self.test_batch_klines()

        # 测试12: 批量获取收盘价
        self.test_batch_closes()

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

            if len(okx_symbols) > 0 and len(binance_symbols) > 0:
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

            if count_okx > 0 and count_binance > 0:
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
            earliest_dt = datetime.fromtimestamp(earliest / 1000)
            latest_dt = datetime.fromtimestamp(latest / 1000)
            print(f"OKX BTC-USDT-SWAP 1m:")
            print(f"  最早: {earliest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  最新: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            # Binance BTC 1m
            earliest, latest = self.get_historical_data_time_range("BTCUSDT", "binance", "1m")
            earliest_dt = datetime.fromtimestamp(earliest / 1000)
            latest_dt = datetime.fromtimestamp(latest / 1000)
            print(f"Binance BTCUSDT 1m:")
            print(f"  最早: {earliest_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  最新: {latest_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            if earliest > 0 and latest > 0:
                print(f"✓ 成功获取时间范围")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 时间范围无效")
                self.test_results[test_name] = "FAIL"
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

    def test_batch_klines(self):
        """测试11: 批量并行查询K线"""
        test_name = "批量并行查询K线"
        print(f"\n{'='*80}")
        print(f"测试11: {test_name}")
        print(f"{'='*80}")

        try:
            # 批量查询多个币种
            symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]

            start_time = time.time()
            klines_map = self.get_batch_historical_klines(symbols, "okx", "1m", 1, 4)
            elapsed = time.time() - start_time

            print(f"批量查询{len(symbols)}个币种的1m K线（最近1天）")
            print(f"  耗时: {elapsed:.2f}秒")
            print(f"  返回币种数: {len(klines_map)}")

            for symbol, klines in klines_map.items():
                print(f"  {symbol}: {len(klines)} 根K线")

            if len(klines_map) == len(symbols):
                print(f"✓ 批量查询成功")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 部分币种查询失败")
                self.test_results[test_name] = "PARTIAL"
        except Exception as e:
            print(f"✗ 异常: {e}")
            self.test_results[test_name] = "ERROR"

    def test_batch_closes(self):
        """测试12: 批量获取收盘价"""
        test_name = "批量获取收盘价"
        print(f"\n{'='*80}")
        print(f"测试12: {test_name}")
        print(f"{'='*80}")

        try:
            # 批量获取多个币种的收盘价
            symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]

            start_time = time.time()
            closes_map = self.get_batch_historical_closes(symbols, "okx", "1m", 1, 4)
            elapsed = time.time() - start_time

            print(f"批量获取{len(symbols)}个币种的收盘价（最近1天）")
            print(f"  耗时: {elapsed:.2f}秒")
            print(f"  返回币种数: {len(closes_map)}")

            for symbol, closes in closes_map.items():
                if len(closes) > 0:
                    print(f"  {symbol}: {len(closes)} 个价格, 最新={closes[-1]:.2f}")

            if len(closes_map) == len(symbols):
                print(f"✓ 批量获取成功")
                self.test_results[test_name] = "PASS"
            else:
                print(f"✗ 部分币种获取失败")
                self.test_results[test_name] = "PARTIAL"
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
            print("🎉 所有测试通过！历史数据查询接口工作正常。")
        elif pass_count + partial_count == total_count:
            print("⚠️  大部分测试通过，部分功能可能受限。")
        else:
            print("❌ 部分测试失败，请检查配置和数据。")

def main():
    print("\n" + "="*80)
    print("  历史数据查询接口测试程序")
    print("="*80)
    print()
    print("本程序将测试所有历史K线数据查询接口的功能")
    print("包括: 连接、查询、批量查询等12个测试项")
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
