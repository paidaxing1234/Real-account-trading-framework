#!/usr/bin/env python3
"""
K线聚合功能测试脚本

测试 data_recorder 的K线聚合功能是否正常工作
"""

import redis
import json
import time
from datetime import datetime

def test_kline_aggregation():
    """测试K线聚合功能"""

    # 连接Redis
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)

    print("=" * 60)
    print("K线聚合功能测试")
    print("=" * 60)

    # 测试币种
    test_symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]

    # 原始周期
    base_intervals = ["1s", "1m", "5m", "1H"]

    # 聚合周期
    aggregated_intervals = ["15m", "30m", "4H", "1D"]

    print("\n1. 检查原始K线数据")
    print("-" * 60)

    for symbol in test_symbols:
        print(f"\n币种: {symbol}")
        for interval in base_intervals:
            key = f"kline:{symbol}:{interval}"
            count = r.zcard(key)

            if count > 0:
                # 获取最新一根K线
                latest = r.zrange(key, -1, -1)
                if latest:
                    kline = json.loads(latest[0])
                    ts = datetime.fromtimestamp(kline['timestamp'] / 1000)
                    print(f"  [{interval:>4}] {count:>5} 根 | 最新: {ts.strftime('%Y-%m-%d %H:%M:%S')} | "
                          f"O:{kline['open']:.2f} H:{kline['high']:.2f} L:{kline['low']:.2f} C:{kline['close']:.2f}")
            else:
                print(f"  [{interval:>4}] 无数据")

    print("\n\n2. 检查聚合K线数据")
    print("-" * 60)

    for symbol in test_symbols:
        print(f"\n币种: {symbol}")
        for interval in aggregated_intervals:
            key = f"kline:{symbol}:{interval}"
            count = r.zcard(key)

            if count > 0:
                # 获取最新一根K线
                latest = r.zrange(key, -1, -1)
                if latest:
                    kline = json.loads(latest[0])
                    ts = datetime.fromtimestamp(kline['timestamp'] / 1000)
                    print(f"  [{interval:>4}] {count:>5} 根 | 最新: {ts.strftime('%Y-%m-%d %H:%M:%S')} | "
                          f"O:{kline['open']:.2f} H:{kline['high']:.2f} L:{kline['low']:.2f} C:{kline['close']:.2f}")
            else:
                print(f"  [{interval:>4}] 无数据 (可能需要等待聚合)")

    print("\n\n3. 验证聚合逻辑")
    print("-" * 60)

    # 验证15分钟K线是否由3根5分钟K线正确聚合
    symbol = "BTC-USDT-SWAP"

    # 获取最新的15分钟K线
    key_15m = f"kline:{symbol}:15m"
    latest_15m = r.zrange(key_15m, -1, -1)

    if latest_15m:
        kline_15m = json.loads(latest_15m[0])
        ts_15m = kline_15m['timestamp']

        print(f"\n最新15分钟K线 ({symbol}):")
        print(f"  时间: {datetime.fromtimestamp(ts_15m / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  OHLC: O={kline_15m['open']:.2f}, H={kline_15m['high']:.2f}, "
              f"L={kline_15m['low']:.2f}, C={kline_15m['close']:.2f}")
        print(f"  成交量: {kline_15m['volume']:.2f}")

        # 获取对应的3根5分钟K线
        key_5m = f"kline:{symbol}:5m"
        # 15分钟K线的时间戳应该对应3根5分钟K线：ts_15m, ts_15m+5min, ts_15m+10min
        klines_5m = []
        for offset in [0, 5*60*1000, 10*60*1000]:
            target_ts = ts_15m + offset
            # 使用ZRANGEBYSCORE获取特定时间戳的K线
            result = r.zrangebyscore(key_5m, target_ts, target_ts)
            if result:
                klines_5m.append(json.loads(result[0]))

        if len(klines_5m) == 3:
            print(f"\n对应的3根5分钟K线:")
            total_volume = 0
            max_high = 0
            min_low = float('inf')

            for i, k in enumerate(klines_5m):
                ts = datetime.fromtimestamp(k['timestamp'] / 1000).strftime('%H:%M:%S')
                print(f"  K{i+1} [{ts}]: O={k['open']:.2f}, H={k['high']:.2f}, "
                      f"L={k['low']:.2f}, C={k['close']:.2f}, V={k['volume']:.2f}")
                total_volume += k['volume']
                max_high = max(max_high, k['high'])
                min_low = min(min_low, k['low'])

            print(f"\n验证聚合逻辑:")
            print(f"  Open应该等于K1的open: {kline_15m['open']:.2f} == {klines_5m[0]['open']:.2f} "
                  f"{'✓' if abs(kline_15m['open'] - klines_5m[0]['open']) < 0.01 else '✗'}")
            print(f"  Close应该等于K3的close: {kline_15m['close']:.2f} == {klines_5m[2]['close']:.2f} "
                  f"{'✓' if abs(kline_15m['close'] - klines_5m[2]['close']) < 0.01 else '✗'}")
            print(f"  High应该等于max(K1,K2,K3的high): {kline_15m['high']:.2f} == {max_high:.2f} "
                  f"{'✓' if abs(kline_15m['high'] - max_high) < 0.01 else '✗'}")
            print(f"  Low应该等于min(K1,K2,K3的low): {kline_15m['low']:.2f} == {min_low:.2f} "
                  f"{'✓' if abs(kline_15m['low'] - min_low) < 0.01 else '✗'}")
            print(f"  Volume应该等于sum(K1,K2,K3的volume): {kline_15m['volume']:.2f} == {total_volume:.2f} "
                  f"{'✓' if abs(kline_15m['volume'] - total_volume) < 0.01 else '✗'}")
        else:
            print(f"\n⚠ 无法找到对应的3根5分钟K线（找到{len(klines_5m)}根）")
    else:
        print(f"\n⚠ 还没有15分钟K线数据，请等待聚合完成")

    print("\n\n4. 数据统计")
    print("-" * 60)

    total_keys = 0
    total_klines = 0

    for symbol in test_symbols:
        for interval in base_intervals + aggregated_intervals:
            key = f"kline:{symbol}:{interval}"
            count = r.zcard(key)
            if count > 0:
                total_keys += 1
                total_klines += count

    print(f"  总Key数: {total_keys}")
    print(f"  总K线数: {total_klines}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_kline_aggregation()
    except redis.ConnectionError:
        print("❌ 无法连接到Redis，请确保Redis服务正在运行")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
