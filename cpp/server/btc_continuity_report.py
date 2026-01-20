#!/usr/bin/env python3
"""
BTC 1分钟K线数据连续性检查报告
"""

import redis
import json
from datetime import datetime

def format_timestamp(ts_ms):
    """将毫秒时间戳转换为可读格式"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def get_unique_timestamps(r, symbol, interval="1m"):
    """获取唯一的时间戳（去重）"""
    key = f"kline:{symbol}:{interval}"
    klines_raw = r.zrange(key, 0, -1)

    if not klines_raw:
        return []

    timestamps = set()
    for kline_raw in klines_raw:
        kline = json.loads(kline_raw)
        timestamps.add(kline['timestamp'])

    return sorted(list(timestamps))

def check_continuity(timestamps):
    """检查时间戳连续性"""
    if len(timestamps) < 2:
        return True, []

    interval_ms = 60 * 1000  # 1分钟
    gaps = []

    for i in range(len(timestamps) - 1):
        current_ts = timestamps[i]
        next_ts = timestamps[i + 1]
        expected_next = current_ts + interval_ms

        if next_ts != expected_next:
            gap_count = int((next_ts - expected_next) / interval_ms) + 1
            gaps.append({
                'start': expected_next,
                'end': next_ts - interval_ms,
                'count': gap_count
            })

    return len(gaps) == 0, gaps

def main():
    # 连接Redis
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

    print("=" * 80)
    print("BTC 1分钟K线数据连续性检查报告")
    print("=" * 80)
    print()

    # 检查的交易对
    symbols = [
        ("BTC-USDT", "OKX现货"),
        ("BTC-USDT-SWAP", "OKX永续合约"),
    ]

    for symbol, desc in symbols:
        print(f"【{symbol}】 ({desc})")
        print("-" * 80)

        timestamps = get_unique_timestamps(r, symbol)

        if not timestamps:
            print("  ❌ 没有数据")
            print()
            continue

        # 基本信息
        print(f"  数据量: {len(timestamps)} 根K线")
        print(f"  时间范围: {format_timestamp(timestamps[0])} ~ {format_timestamp(timestamps[-1])}")

        # 计算时间跨度
        time_span_ms = timestamps[-1] - timestamps[0]
        time_span_minutes = time_span_ms / (1000 * 60)
        expected_count = int(time_span_minutes) + 1

        print(f"  时间跨度: {time_span_minutes:.0f} 分钟")
        print(f"  期望数量: {expected_count} 根")

        # 检查连续性
        is_continuous, gaps = check_continuity(timestamps)

        if is_continuous:
            print(f"  ✅ 数据完全连续，无缺失")
        else:
            missing_total = sum(gap['count'] for gap in gaps)
            print(f"  ⚠️  发现 {len(gaps)} 个缺失段，共缺失 {missing_total} 根K线")
            print()
            print("  缺失详情:")
            for i, gap in enumerate(gaps[:5], 1):  # 只显示前5个
                print(f"    {i}. {format_timestamp(gap['start'])} ~ {format_timestamp(gap['end'])} (缺失 {gap['count']} 根)")
            if len(gaps) > 5:
                print(f"    ... 还有 {len(gaps) - 5} 个缺失段")

        print()

    print("=" * 80)
    print("检查完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
