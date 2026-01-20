#!/usr/bin/env python3
"""
检查BTC 1分钟K线数据的连续性
"""

import redis
import json
from datetime import datetime

def format_timestamp(ts_ms):
    """将毫秒时间戳转换为可读格式"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def check_btc_1m_continuity():
    # 连接Redis
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

    symbol = "BTC-USDT"
    interval = "1m"
    key = f"kline:{symbol}:{interval}"

    print(f"检查 {symbol} {interval} K线数据连续性")
    print("=" * 80)

    # 获取所有K线
    klines_raw = r.zrange(key, 0, -1)

    if not klines_raw:
        print(f"❌ 没有找到任何 {symbol} {interval} 数据")
        return

    print(f"✓ 找到 {len(klines_raw)} 根K线")

    # 解析时间戳
    timestamps = []
    for kline_raw in klines_raw:
        kline = json.loads(kline_raw)
        timestamps.append(kline['timestamp'])

    timestamps.sort()

    # 显示时间范围
    print(f"\n时间范围:")
    print(f"  开始: {format_timestamp(timestamps[0])}")
    print(f"  结束: {format_timestamp(timestamps[-1])}")

    # 计算时间跨度
    time_span_ms = timestamps[-1] - timestamps[0]
    time_span_minutes = time_span_ms / (1000 * 60)
    expected_count = int(time_span_minutes) + 1

    print(f"\n统计:")
    print(f"  时间跨度: {time_span_minutes:.0f} 分钟")
    print(f"  实际K线数: {len(timestamps)}")
    print(f"  期望K线数: {expected_count}")
    print(f"  缺失K线数: {expected_count - len(timestamps)}")

    # 检查连续性
    interval_ms = 60 * 1000  # 1分钟
    gaps = []

    for i in range(len(timestamps) - 1):
        current_ts = timestamps[i]
        next_ts = timestamps[i + 1]
        expected_next = current_ts + interval_ms

        # 检查是否有缺失
        if next_ts != expected_next:
            gap_count = int((next_ts - expected_next) / interval_ms) + 1
            gaps.append({
                'start': expected_next,
                'end': next_ts - interval_ms,
                'count': gap_count
            })

    # 显示缺失情况
    if not gaps:
        print(f"\n✅ 数据完全连续，无缺失！")
    else:
        print(f"\n⚠️  发现 {len(gaps)} 个缺失段:")
        print()

        total_missing = 0
        for i, gap in enumerate(gaps, 1):
            missing_count = gap['count']
            total_missing += missing_count
            print(f"  缺失段 {i}:")
            print(f"    开始: {format_timestamp(gap['start'])}")
            print(f"    结束: {format_timestamp(gap['end'])}")
            print(f"    缺失: {missing_count} 根K线")

            # 如果缺失不多，列出具体时间
            if missing_count <= 10:
                print(f"    详细:")
                ts = gap['start']
                while ts <= gap['end']:
                    print(f"      - {format_timestamp(ts)}")
                    ts += interval_ms
            print()

        print(f"  总计缺失: {total_missing} 根K线")

    # 检查最近的数据
    print(f"\n最近10根K线:")
    for ts in timestamps[-10:]:
        print(f"  {format_timestamp(ts)}")

if __name__ == "__main__":
    check_btc_1m_continuity()
