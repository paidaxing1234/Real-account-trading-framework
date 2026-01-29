#!/usr/bin/env python3
"""
K线连续性检查工具
检测K线数据中的缺失，并显示哪些K线缺失导致无法聚合
"""

import redis
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

def format_timestamp(ts_ms: int) -> str:
    """将毫秒时间戳转换为可读格式"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def get_interval_seconds(interval: str) -> int:
    """获取K线周期的秒数"""
    if interval == "1s": return 1
    if interval == "1m": return 60
    if interval == "5m": return 5 * 60
    if interval == "15m": return 15 * 60
    if interval == "30m": return 30 * 60
    if interval == "1H": return 60 * 60
    if interval == "4H": return 4 * 60 * 60
    if interval == "1D": return 24 * 60 * 60
    return 60

def check_continuity(r: redis.Redis, exchange: str, symbol: str, interval: str,
                     required_count: int) -> Tuple[int, List[str], bool]:
    """
    检查K线连续性

    返回: (实际K线数, 缺失的K线时间列表, 是否连续)
    """
    key = f"kline:{exchange}:{symbol}:{interval}"

    # 获取所有K线
    klines_raw = r.zrange(key, 0, -1)

    if not klines_raw:
        return 0, [], False

    # 解析时间戳
    timestamps = []
    for kline_raw in klines_raw:
        kline = json.loads(kline_raw)
        timestamps.append(kline['timestamp'])

    timestamps.sort()

    # 检查连续性
    interval_ms = get_interval_seconds(interval) * 1000
    missing = []

    for i in range(len(timestamps) - 1):
        current_ts = timestamps[i]
        next_ts = timestamps[i + 1]
        expected_next = current_ts + interval_ms

        # 检查是否有缺失
        while expected_next < next_ts:
            missing.append(format_timestamp(expected_next))
            expected_next += interval_ms

    # 检查最近的K线是否能形成完整周期
    if len(timestamps) >= required_count:
        # 检查最后N根是否连续
        last_n = timestamps[-required_count:]
        is_continuous = True
        for i in range(len(last_n) - 1):
            if last_n[i + 1] - last_n[i] != interval_ms:
                is_continuous = False
                break
    else:
        is_continuous = False

    return len(timestamps), missing, is_continuous

def check_aggregation_readiness(r: redis.Redis, exchange: str, symbol: str,
                                base_interval: str, target_interval: str,
                                multiplier: int) -> Dict:
    """
    检查聚合准备情况

    返回包含详细信息的字典
    """
    base_key = f"kline:{exchange}:{symbol}:{base_interval}"
    target_key = f"kline:{exchange}:{symbol}:{target_interval}"

    # 获取基础K线
    base_klines_raw = r.zrange(base_key, 0, -1)
    base_count = len(base_klines_raw)

    # 获取聚合K线数量
    target_count = r.zcard(target_key)

    # 检查连续性
    _, missing, is_continuous = check_continuity(r, exchange, symbol, base_interval, multiplier)

    # 计算对齐到目标周期的最近N根K线
    if base_klines_raw:
        # 获取最后N根K线的时间戳
        recent_timestamps = []
        for kline_raw in base_klines_raw[-multiplier:]:
            kline = json.loads(kline_raw)
            recent_timestamps.append(kline['timestamp'])

        # 检查这N根是否连续
        interval_ms = get_interval_seconds(base_interval) * 1000
        recent_continuous = True
        recent_missing = []

        if len(recent_timestamps) >= 2:
            for i in range(len(recent_timestamps) - 1):
                if recent_timestamps[i + 1] - recent_timestamps[i] != interval_ms:
                    recent_continuous = False
                    # 找出缺失的时间点
                    expected = recent_timestamps[i] + interval_ms
                    while expected < recent_timestamps[i + 1]:
                        recent_missing.append(format_timestamp(expected))
                        expected += interval_ms

        # 检查是否对齐到目标周期边界
        target_period_ms = interval_ms * multiplier
        if recent_timestamps:
            first_ts = recent_timestamps[0]
            aligned_ts = (first_ts // target_period_ms) * target_period_ms
            is_aligned = (first_ts == aligned_ts)
        else:
            is_aligned = False
    else:
        recent_continuous = False
        recent_missing = []
        is_aligned = False

    return {
        'base_count': base_count,
        'target_count': target_count,
        'required': multiplier,
        'missing_all': missing,
        'missing_recent': recent_missing,
        'is_continuous': recent_continuous,
        'is_aligned': is_aligned,
        'can_aggregate': base_count >= multiplier and recent_continuous and is_aligned
    }

def print_aggregation_status(symbol: str, target_interval: str,
                            base_interval: str, info: Dict):
    """打印聚合状态"""

    if info['target_count'] > 0:
        print(f"  \033[0;32m{target_interval}:\033[0m ✓ 已生成 {info['target_count']} 根")
        return

    # 未生成聚合K线
    base_count = info['base_count']
    required = info['required']

    if base_count == 0:
        print(f"  \033[1;33m{target_interval}:\033[0m 0/{required} 根{base_interval} K线 (还需 {required} 根)")
        return

    # 有基础K线但未聚合
    if base_count < required:
        print(f"  \033[1;33m{target_interval}:\033[0m {base_count}/{required} 根{base_interval} K线 (还需 {required - base_count} 根)")
    else:
        # 数量足够但无法聚合
        print(f"  \033[1;31m{target_interval}:\033[0m {base_count}/{required} 根{base_interval} K线")

        if not info['is_continuous']:
            print(f"    \033[1;31m⚠️  K线不连续，无法聚合\033[0m")

            if info['missing_recent']:
                print(f"    \033[1;31m   缺失的K线:\033[0m")
                for missing_time in info['missing_recent'][:5]:  # 最多显示5个
                    print(f"      - {missing_time}")
                if len(info['missing_recent']) > 5:
                    print(f"      ... 还有 {len(info['missing_recent']) - 5} 个缺失")

        if not info['is_aligned']:
            print(f"    \033[1;33m⚠️  K线未对齐到{target_interval}周期边界\033[0m")

        # 显示所有缺失的K线（如果有）
        if info['missing_all'] and len(info['missing_all']) <= 10:
            print(f"    \033[0;36m   历史缺失的K线:\033[0m")
            for missing_time in info['missing_all']:
                print(f"      - {missing_time}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 check_kline_continuity.py <symbol> [exchange]")
        sys.exit(1)

    symbol = sys.argv[1]
    exchange = sys.argv[2] if len(sys.argv) > 2 else "okx"  # 默认使用 okx

    # 连接Redis
    r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=False)

    # 检查各个聚合周期
    aggregations = [
        ("5m", "1m", 5),
        ("15m", "1m", 15),
        ("30m", "1m", 30),
        ("1h", "1m", 60),  # 修改为小写 1h
    ]

    for target_interval, base_interval, multiplier in aggregations:
        info = check_aggregation_readiness(r, exchange, symbol, base_interval, target_interval, multiplier)
        print_aggregation_status(symbol, target_interval, base_interval, info)

if __name__ == "__main__":
    main()
