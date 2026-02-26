#!/usr/bin/env python3
"""
诊断脚本：检测 Redis 中是否有 8h K线数据
模拟策略的 on_tick() 逻辑，验证 Redis 数据是否正常更新
"""

import redis
import json
import time
from datetime import datetime

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_PASSWORD = ""

EXCHANGE = "binance"
INTERVAL = "8h"

# 测试几个代表性币种
TEST_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]


def main():
    print("=" * 60)
    print("  Redis 8h K线数据诊断")
    print("=" * 60)

    # 连接 Redis
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD or None, decode_responses=True)
        r.ping()
        print(f"[OK] Redis 连接成功 ({REDIS_HOST}:{REDIS_PORT})")
    except Exception as e:
        print(f"[FAIL] Redis 连接失败: {e}")
        return

    # 1. 检查有哪些 kline key
    print(f"\n--- 检查 kline:{EXCHANGE}:*:{INTERVAL} 的 key ---")
    pattern = f"kline:{EXCHANGE}:*:{INTERVAL}"
    keys = list(r.scan_iter(match=pattern, count=1000))
    print(f"找到 {len(keys)} 个 8h K线 key")

    if not keys:
        # 也检查一下有没有其他周期的
        all_kline_keys = list(r.scan_iter(match=f"kline:{EXCHANGE}:*", count=100))
        if all_kline_keys:
            intervals_found = set()
            for k in all_kline_keys[:50]:
                parts = k.split(":")
                if len(parts) >= 4:
                    intervals_found.add(parts[3])
            print(f"[INFO] Redis 中存在的K线周期: {intervals_found}")
            print(f"[INFO] 示例 key: {all_kline_keys[:5]}")
        else:
            print("[WARN] Redis 中没有任何 kline 数据")
        return

    # 2. 检查测试币种的数据
    print(f"\n--- 检查测试币种的 8h K线数据 ---")
    now_ms = int(time.time() * 1000)
    rebalance_interval_ms = 8 * 60 * 60 * 1000
    current_period = now_ms // rebalance_interval_ms

    for symbol in TEST_SYMBOLS:
        key = f"kline:{EXCHANGE}:{symbol}:{INTERVAL}"
        count = r.zcard(key)

        if count == 0:
            print(f"  {symbol}: 无数据")
            continue

        # 获取最新一根
        latest = r.zrange(key, -1, -1, withscores=True)
        # 获取最早一根
        oldest = r.zrange(key, 0, 0, withscores=True)

        if latest:
            latest_data = json.loads(latest[0][0])
            latest_ts = int(latest[0][1])
            latest_period = latest_ts // rebalance_interval_ms
            latest_time = datetime.fromtimestamp(latest_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
            age_hours = (now_ms - latest_ts) / 3600000

            oldest_ts = int(oldest[0][1])
            oldest_time = datetime.fromtimestamp(oldest_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

            status = "当前周期" if latest_period >= current_period else f"落后 {current_period - latest_period} 个周期"

            print(f"  {symbol}: {count}根 | 最新: {latest_time} ({age_hours:.1f}h前) | 最早: {oldest_time} | {status}")
            print(f"    close={latest_data.get('close', '?')} volume={latest_data.get('volume', '?')}")

    # 3. 统计所有币种的同步情况
    print(f"\n--- 全币种 8h K线同步统计 ---")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"当前8h周期: {current_period}")

    total = 0
    in_current_period = 0
    behind_1 = 0
    behind_more = 0
    empty = 0

    for key in keys:
        total += 1
        latest = r.zrange(key, -1, -1, withscores=True)
        if not latest:
            empty += 1
            continue
        latest_ts = int(latest[0][1])
        latest_period = latest_ts // rebalance_interval_ms

        if latest_period >= current_period:
            in_current_period += 1
        elif latest_period == current_period - 1:
            behind_1 += 1
        else:
            behind_more += 1

    print(f"  总计: {total} 个币种")
    print(f"  当前周期: {in_current_period} ({in_current_period/total*100:.1f}%)")
    print(f"  落后1个周期: {behind_1}")
    print(f"  落后>1个周期: {behind_more}")
    print(f"  无数据: {empty}")

    sync_ratio = in_current_period / total if total > 0 else 0
    if sync_ratio >= 0.8:
        print(f"\n[OK] 同步率 {sync_ratio*100:.1f}% >= 80%，策略应该能触发调仓")
    else:
        print(f"\n[WARN] 同步率 {sync_ratio*100:.1f}% < 80%，策略无法触发调仓")

    # 4. 持续监听模式（可选）
    print(f"\n--- 持续监听 Redis 8h K线更新 (Ctrl+C 退出) ---")
    last_counts = {}
    for key in keys[:10]:  # 只监听前10个
        last_counts[key] = r.zcard(key)

    try:
        while True:
            time.sleep(60)
            updated = 0
            for key in last_counts:
                new_count = r.zcard(key)
                if new_count > last_counts[key]:
                    symbol = key.split(":")[2]
                    latest = r.zrange(key, -1, -1, withscores=True)
                    latest_ts = int(latest[0][1])
                    latest_time = datetime.fromtimestamp(latest_ts / 1000).strftime('%H:%M:%S')
                    print(f"  [更新] {symbol} 新增 {new_count - last_counts[key]} 根K线, 最新: {latest_time}")
                    last_counts[key] = new_count
                    updated += 1
            if updated == 0:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] 无更新")
    except KeyboardInterrupt:
        print("\n已停止监听")


if __name__ == "__main__":
    main()
