#!/usr/bin/env python3
"""
实时监控 Redis 中币安前20个币种的8小时K线时间戳

功能：
1. 每隔几秒刷新一次
2. 显示每个币种最新8h K线的时间戳
3. 检测时间戳是否一致（高亮不一致的）
"""

import redis
import time
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Redis连接配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# 监控配置
EXCHANGE = "binance"
INTERVAL = "8h"
TOP_N = 20  # 监控前N个币种
REFRESH_INTERVAL = 5  # 刷新间隔（秒）

# 8小时周期（毫秒）
PERIOD_MS = 8 * 60 * 60 * 1000


def connect_redis():
    """连接Redis"""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        print(f"Redis连接失败: {e}")
        return None


def get_all_symbols(r: redis.Redis, exchange: str, interval: str) -> List[str]:
    """获取所有有8h K线数据的币种"""
    pattern = f"kline:{exchange}:*:{interval}"
    keys = r.keys(pattern)

    symbols = []
    for key in keys:
        # key格式: kline:binance:BTCUSDT:8h
        parts = key.split(":")
        if len(parts) == 4:
            symbol = parts[2]
            symbols.append(symbol)

    return sorted(symbols)


def get_latest_kline_timestamp(r: redis.Redis, exchange: str, symbol: str, interval: str) -> Tuple[int, int]:
    """
    获取最新K线的时间戳和K线数量

    返回: (timestamp_ms, count)
    """
    key = f"kline:{exchange}:{symbol}:{interval}"

    # 获取最新的一根K线（sorted set按score排序，-1是最后一个）
    latest = r.zrange(key, -1, -1, withscores=True)

    if not latest:
        return 0, 0

    # 获取总数量
    count = r.zcard(key)

    # latest格式: [(json_string, timestamp)]
    _, timestamp = latest[0]
    return int(timestamp), count


def ts_to_str(ts_ms: int) -> str:
    """时间戳转字符串"""
    if ts_ms == 0:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')


def get_period_number(ts_ms: int) -> int:
    """计算8h周期编号"""
    return ts_ms // PERIOD_MS


def clear_screen():
    """清屏"""
    os.system('clear' if os.name == 'posix' else 'cls')


def main():
    print("正在连接 Redis...")
    r = connect_redis()
    if not r:
        return

    print(f"已连接到 Redis ({REDIS_HOST}:{REDIS_PORT})")
    print(f"监控交易所: {EXCHANGE.upper()} | K线周期: {INTERVAL}")
    print()

    # 获取所有币种
    all_symbols = get_all_symbols(r, EXCHANGE, INTERVAL)
    if not all_symbols:
        print(f"未找到 {EXCHANGE} 的 {INTERVAL} K线数据")
        return

    print(f"找到 {len(all_symbols)} 个币种，监控前 {TOP_N} 个")
    print()

    # 选择前N个币种（按字母排序）
    # 优先选择主流币种
    priority_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                       "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
                       "MATICUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT", "APTUSDT",
                       "ARBUSDT", "OPUSDT", "NEARUSDT", "FILUSDT", "INJUSDT"]

    # 从可用币种中选择
    monitor_symbols = []
    for s in priority_symbols:
        if s in all_symbols and len(monitor_symbols) < TOP_N:
            monitor_symbols.append(s)

    # 如果不够，从剩余币种中补充
    for s in all_symbols:
        if s not in monitor_symbols and len(monitor_symbols) < TOP_N:
            monitor_symbols.append(s)

    print(f"监控币种: {monitor_symbols}")
    print()
    print(f"每 {REFRESH_INTERVAL} 秒刷新一次，按 Ctrl+C 退出")
    print()
    time.sleep(2)

    try:
        while True:
            clear_screen()

            # 当前时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            current_ts = int(time.time() * 1000)
            current_period = get_period_number(current_ts)

            print("=" * 90)
            print(f"  币安 8h K线时间戳监控 | 刷新时间: {now}")
            print(f"  当前周期编号: {current_period}")
            print("=" * 90)
            print()

            # 收集所有币种的时间戳
            timestamps = {}
            counts = {}

            for symbol in monitor_symbols:
                ts, count = get_latest_kline_timestamp(r, EXCHANGE, symbol, INTERVAL)
                timestamps[symbol] = ts
                counts[symbol] = count

            # 统计时间戳分布
            ts_distribution = {}
            for symbol, ts in timestamps.items():
                if ts > 0:
                    if ts not in ts_distribution:
                        ts_distribution[ts] = []
                    ts_distribution[ts].append(symbol)

            # 找出最常见的时间戳（众数）
            most_common_ts = 0
            max_count = 0
            for ts, symbols in ts_distribution.items():
                if len(symbols) > max_count:
                    max_count = len(symbols)
                    most_common_ts = ts

            # 打印表头
            print(f"{'序号':<4} {'币种':<12} {'最新K线时间戳':<22} {'周期编号':<12} {'K线数量':<10} {'状态':<6}")
            print("-" * 90)

            # 打印每个币种的信息
            consistent_count = 0
            for i, symbol in enumerate(monitor_symbols, 1):
                ts = timestamps[symbol]
                count = counts[symbol]
                ts_str = ts_to_str(ts)
                period = get_period_number(ts) if ts > 0 else 0

                # 判断是否与众数一致
                if ts == most_common_ts and ts > 0:
                    status = "OK"
                    consistent_count += 1
                elif ts == 0:
                    status = "无数据"
                else:
                    status = "不一致"

                # 高亮不一致的行
                if status == "不一致":
                    print(f"\033[91m{i:<4} {symbol:<12} {ts_str:<22} {period:<12} {count:<10} {status:<6}\033[0m")
                elif status == "无数据":
                    print(f"\033[93m{i:<4} {symbol:<12} {ts_str:<22} {period:<12} {count:<10} {status:<6}\033[0m")
                else:
                    print(f"\033[92m{i:<4} {symbol:<12} {ts_str:<22} {period:<12} {count:<10} {status:<6}\033[0m")

            print("-" * 90)

            # 统计信息
            print()
            print(f"统计:")
            print(f"  - 一致数量: {consistent_count}/{len(monitor_symbols)} ({consistent_count/len(monitor_symbols)*100:.1f}%)")
            print(f"  - 众数时间戳: {ts_to_str(most_common_ts)} (周期 {get_period_number(most_common_ts)})")

            # 显示时间戳分布
            if len(ts_distribution) > 1:
                print()
                print(f"时间戳分布 ({len(ts_distribution)} 个不同时间戳):")
                for ts in sorted(ts_distribution.keys(), reverse=True):
                    symbols = ts_distribution[ts]
                    period = get_period_number(ts)
                    print(f"  - {ts_to_str(ts)} (周期 {period}): {len(symbols)} 个币种")
                    if len(symbols) <= 5:
                        print(f"    {symbols}")

            # 计算距离下一个8h周期的时间
            next_period_ts = (current_period + 1) * PERIOD_MS
            time_to_next = (next_period_ts - current_ts) / 1000 / 60  # 分钟
            next_period_str = ts_to_str(next_period_ts)

            print()
            print(f"下一个8h周期: {next_period_str} (约 {time_to_next:.1f} 分钟后)")
            print()
            print(f"按 Ctrl+C 退出 | 每 {REFRESH_INTERVAL} 秒刷新")

            time.sleep(REFRESH_INTERVAL)

    except KeyboardInterrupt:
        print()
        print("监控已停止")


if __name__ == "__main__":
    main()
