#!/usr/bin/env python3
"""
检查Redis中K线数据的统计信息和连续性

功能：
1. 统计每个交易对每个周期的K线数量
2. 显示起止时间
3. 检测时间连续性（是否有缺失）
"""

import redis
import json
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple

# Redis连接配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# 要检查的周期
INTERVALS = ["1m", "5m", "15m", "30m", "1h"]

# 周期对应的秒数
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


def connect_redis():
    """连接Redis"""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")
        return None


def get_all_kline_keys(r: redis.Redis, exchange: str) -> Dict[str, List[str]]:
    """
    获取所有K线数据的key

    返回: {symbol: [intervals]}
    """
    pattern = f"kline:{exchange}:*"
    keys = r.keys(pattern)

    # 按交易对和周期分组
    symbol_intervals = defaultdict(set)

    for key in keys:
        # key格式: kline:okx:BTC-USDT-SWAP:1m
        parts = key.split(":")
        if len(parts) == 4:
            symbol = parts[2]
            interval = parts[3]
            if interval in INTERVALS:
                symbol_intervals[symbol].add(interval)

    # 转换为字典
    result = {}
    for symbol, intervals in symbol_intervals.items():
        result[symbol] = sorted(list(intervals))

    return result


def get_kline_stats(r: redis.Redis, exchange: str, symbol: str, interval: str) -> Dict:
    """
    获取K线统计信息

    返回: {
        'count': 数量,
        'start_time': 开始时间,
        'end_time': 结束时间,
        'gaps': 缺失数量,
        'gap_details': 缺失详情
    }
    """
    key = f"kline:{exchange}:{symbol}:{interval}"

    # 获取所有K线数据（从sorted set中获取）
    # zrange返回的是成员列表，score是时间戳
    klines_data = r.zrange(key, 0, -1, withscores=True)

    if not klines_data:
        return {
            'count': 0,
            'start_time': None,
            'end_time': None,
            'gaps': 0,
            'gap_details': []
        }

    # 解析K线数据
    # klines_data格式: [(json_string, timestamp), ...]
    klines = []
    for kline_json, score in klines_data:
        try:
            # score就是时间戳（毫秒）
            timestamp = int(score)
            if timestamp > 0:
                klines.append(timestamp)
        except:
            continue

    if not klines:
        return {
            'count': 0,
            'start_time': None,
            'end_time': None,
            'gaps': 0,
            'gap_details': []
        }

    # 排序（应该已经是排序的，但为了保险）
    klines.sort()

    # 统计信息
    count = len(klines)
    start_time = datetime.fromtimestamp(klines[0] / 1000)
    end_time = datetime.fromtimestamp(klines[-1] / 1000)

    # 检测连续性
    interval_ms = INTERVAL_SECONDS[interval] * 1000
    gaps = 0
    gap_details = []

    for i in range(1, len(klines)):
        expected_time = klines[i-1] + interval_ms
        actual_time = klines[i]

        if actual_time > expected_time:
            # 有缺失
            gap_count = int((actual_time - expected_time) / interval_ms)
            gaps += gap_count

            # 只记录前5个缺失详情
            if len(gap_details) < 5:
                gap_start = datetime.fromtimestamp(expected_time / 1000)
                gap_end = datetime.fromtimestamp(actual_time / 1000)
                gap_details.append({
                    'start': gap_start.strftime('%Y-%m-%d %H:%M:%S'),
                    'end': gap_end.strftime('%Y-%m-%d %H:%M:%S'),
                    'count': gap_count
                })

    return {
        'count': count,
        'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'gaps': gaps,
        'gap_details': gap_details
    }


def print_stats_table(exchange: str, stats: Dict):
    """打印统计表格"""
    print()
    print("=" * 120)
    print(f"  {exchange.upper()} K线数据统计")
    print("=" * 120)
    print()

    if not stats:
        print(f"  ❌ 没有找到 {exchange.upper()} 的K线数据")
        print()
        return

    # 按交易对排序
    sorted_symbols = sorted(stats.keys())

    for symbol in sorted_symbols:
        print(f"📊 {symbol}")
        print("-" * 120)

        intervals_data = stats[symbol]

        # 表头
        print(f"{'周期':<8} {'数量':<10} {'起始时间':<22} {'结束时间':<22} {'缺失':<8} {'连续性':<10}")
        print("-" * 120)

        for interval in INTERVALS:
            if interval in intervals_data:
                data = intervals_data[interval]
                count = data['count']
                start = data['start_time'] or 'N/A'
                end = data['end_time'] or 'N/A'
                gaps = data['gaps']

                # 计算连续性百分比
                if count > 0 and gaps >= 0:
                    total_expected = count + gaps
                    continuity = (count / total_expected) * 100 if total_expected > 0 else 0
                    continuity_str = f"{continuity:.2f}%"
                else:
                    continuity_str = "N/A"

                # 状态标记
                if gaps == 0:
                    status = "✓"
                elif gaps < 10:
                    status = "⚠"
                else:
                    status = "✗"

                print(f"{interval:<8} {count:<10} {start:<22} {end:<22} {gaps:<8} {continuity_str:<10} {status}")

                # 显示缺失详情
                if data['gap_details']:
                    for gap in data['gap_details']:
                        print(f"         └─ 缺失 {gap['count']} 根: {gap['start']} ~ {gap['end']}")
            else:
                print(f"{interval:<8} {'0':<10} {'N/A':<22} {'N/A':<22} {'N/A':<8} {'N/A':<10} ✗")

        print()


def main():
    print()
    print("╔" + "═" * 118 + "╗")
    print("║" + "  Redis K线数据统计与连续性检测".center(116) + "║")
    print("╚" + "═" * 118 + "╝")

    # 连接Redis
    r = connect_redis()
    if not r:
        return

    print(f"\n✓ 已连接到 Redis ({REDIS_HOST}:{REDIS_PORT})")
    print(f"✓ 检查周期: {', '.join(INTERVALS)}")

    # 检查OKX
    print("\n正在扫描 OKX 数据...")
    okx_keys = get_all_kline_keys(r, "okx")
    print(f"  找到 {len(okx_keys)} 个交易对")

    okx_stats = {}
    for symbol in sorted(okx_keys.keys()):
        okx_stats[symbol] = {}
        for interval in okx_keys[symbol]:
            stats = get_kline_stats(r, "okx", symbol, interval)
            okx_stats[symbol][interval] = stats

    print_stats_table("okx", okx_stats)

    # 检查Binance
    print("\n正在扫描 Binance 数据...")
    binance_keys = get_all_kline_keys(r, "binance")
    print(f"  找到 {len(binance_keys)} 个交易对")

    binance_stats = {}
    for symbol in sorted(binance_keys.keys()):
        binance_stats[symbol] = {}
        for interval in binance_keys[symbol]:
            stats = get_kline_stats(r, "binance", symbol, interval)
            binance_stats[symbol][interval] = stats

    print_stats_table("binance", binance_stats)

    # 总结
    print("=" * 120)
    print("  统计总结")
    print("=" * 120)
    print(f"  OKX 交易对数量:     {len(okx_stats)}")
    print(f"  Binance 交易对数量: {len(binance_stats)}")

    # 计算总K线数量
    okx_total = sum(
        data['count']
        for symbol_data in okx_stats.values()
        for data in symbol_data.values()
    )
    binance_total = sum(
        data['count']
        for symbol_data in binance_stats.values()
        for data in symbol_data.values()
    )

    print(f"  OKX K线总数:        {okx_total:,}")
    print(f"  Binance K线总数:    {binance_total:,}")
    print(f"  总计:               {okx_total + binance_total:,}")
    print("=" * 120)
    print()

    # 图例
    print("图例:")
    print("  ✓ = 完全连续（无缺失）")
    print("  ⚠ = 少量缺失（< 10根）")
    print("  ✗ = 较多缺失或无数据")
    print()


if __name__ == "__main__":
    main()
