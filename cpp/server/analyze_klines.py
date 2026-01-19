#!/usr/bin/env python3
"""
K线数据分析工具
分析Redis中K线的连续性和缺失情况
"""

import redis
import json
from datetime import datetime, timedelta

def format_timestamp(ts_ms):
    """格式化时间戳（毫秒）为可读格式"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def analyze_klines(symbol, interval):
    """分析指定symbol和interval的K线数据"""
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

    key = f"kline:{symbol}:{interval}"

    # 获取所有K线数据（带score）
    klines = r.zrange(key, 0, -1, withscores=True)

    if not klines:
        print(f"❌ {symbol}:{interval} 没有K线数据")
        return

    print(f"\n{'='*60}")
    print(f"分析 {symbol}:{interval}")
    print(f"{'='*60}")
    print(f"总数: {len(klines)} 根K线\n")

    # 解析时间戳
    timestamps = []
    for kline_data, score in klines:
        try:
            kline_json = json.loads(kline_data)
            ts = kline_json.get('timestamp', int(score))
            timestamps.append(ts)
        except:
            timestamps.append(int(score))

    timestamps.sort()

    # 显示时间范围
    print(f"时间范围:")
    print(f"  最早: {format_timestamp(timestamps[0])} ({timestamps[0]})")
    print(f"  最新: {format_timestamp(timestamps[-1])} ({timestamps[-1]})")

    # 计算周期（毫秒）
    interval_map = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1H': 60 * 60 * 1000
    }
    interval_ms = interval_map.get(interval, 60 * 1000)

    # 检查连续性
    print(f"\n连续性检查 (周期: {interval}):")
    gaps = []
    for i in range(len(timestamps) - 1):
        expected_next = timestamps[i] + interval_ms
        actual_next = timestamps[i + 1]

        if actual_next > expected_next:
            gap_count = (actual_next - expected_next) // interval_ms
            gaps.append({
                'start': expected_next,
                'end': actual_next - interval_ms,
                'count': gap_count
            })

    if gaps:
        print(f"  ⚠ 发现 {len(gaps)} 个缺失段:")
        for i, gap in enumerate(gaps[:10], 1):  # 只显示前10个
            print(f"    {i}. {format_timestamp(gap['start'])} ~ {format_timestamp(gap['end'])} (缺失 {gap['count']} 根)")
        if len(gaps) > 10:
            print(f"    ... 还有 {len(gaps) - 10} 个缺失段")
    else:
        print(f"  ✓ K线连续，无缺失")

    # 显示前5根和后5根K线
    print(f"\n前5根K线:")
    for i in range(min(5, len(timestamps))):
        print(f"  {i+1}. {format_timestamp(timestamps[i])}")

    print(f"\n后5根K线:")
    for i in range(max(0, len(timestamps) - 5), len(timestamps)):
        print(f"  {i+1}. {format_timestamp(timestamps[i])}")

if __name__ == '__main__':
    # 分析BTC-USDT-SWAP的各个周期
    symbol = 'BTC-USDT-SWAP'

    for interval in ['1m', '5m', '15m', '30m', '1H']:
        analyze_klines(symbol, interval)
