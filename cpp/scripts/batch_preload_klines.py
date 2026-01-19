#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量预加载历史 K 线数据到 Redis

高效版本，支持 Binance 和 OKX 交易所。

使用方法：
    python batch_preload_klines.py --exchange okx --days 60 --interval 1m
    python batch_preload_klines.py --exchange binance --days 60 --interval 1m
    python batch_preload_klines.py --exchange all --days 60

环境变量：
    REDIS_HOST       - Redis 主机地址 (默认: 127.0.0.1)
    REDIS_PORT       - Redis 端口 (默认: 6379)
    PROXY_HOST       - 代理主机 (默认: 127.0.0.1)
    PROXY_PORT       - 代理端口 (默认: 7890)

@author Sequence Team
@date 2026-01
"""

import os
import sys
import json
import time
import argparse
import requests
import redis
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ==================== 配置 ====================

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = os.getenv("PROXY_PORT", "7890")

# API URLs
BINANCE_FUTURES_URL = "https://fapi.binance.com"
OKX_API_URL = "https://www.okx.com"

# Rate limiting
REQUEST_DELAY = 0.25
MAX_WORKERS = 2

# Thread-local storage for sessions
thread_local = threading.local()


def get_session():
    """Get thread-local session with proxy"""
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        proxy_url = f"http://{PROXY_HOST}:{PROXY_PORT}"
        session.proxies = {"http": proxy_url, "https": proxy_url}
        thread_local.session = session
    return thread_local.session


def get_redis():
    """Get thread-local Redis connection"""
    if not hasattr(thread_local, "redis"):
        thread_local.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
    return thread_local.redis


# ==================== OKX ====================

def get_okx_symbols() -> List[str]:
    """获取 OKX USDT 永续合约列表"""
    session = get_session()
    url = f"{OKX_API_URL}/api/v5/public/instruments"
    params = {"instType": "SWAP"}

    try:
        response = session.get(url, params=params, timeout=30)
        data = response.json()
        if data.get("code") == "0":
            symbols = []
            for inst in data.get("data", []):
                inst_id = inst.get("instId", "")
                state = inst.get("state", "")
                if inst_id.endswith("-USDT-SWAP") and state == "live":
                    symbols.append(inst_id)
            return sorted(symbols)
    except Exception as e:
        print(f"[OKX] 获取交易对失败: {e}")
    return []


def fetch_okx_klines(symbol: str, interval: str, after_ts: Optional[int] = None, limit: int = 300) -> List[Dict]:
    """获取 OKX K 线数据"""
    session = get_session()

    # 转换周期格式
    interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
    okx_interval = interval_map.get(interval.lower(), interval)

    url = f"{OKX_API_URL}/api/v5/market/history-candles"
    params = {"instId": symbol, "bar": okx_interval, "limit": str(limit)}
    if after_ts:
        params["after"] = str(after_ts)

    try:
        response = session.get(url, params=params, timeout=30)
        data = response.json()

        if data.get("code") == "0":
            klines = []
            for item in reversed(data.get("data", [])):
                kline = {
                    "timestamp": int(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "symbol": symbol,
                    "exchange": "okx",
                    "interval": interval,
                    "type": "kline"
                }
                klines.append(kline)
            return klines
    except Exception as e:
        pass
    return []


def load_okx_symbol(symbol: str, interval: str, days: int) -> int:
    """加载单个 OKX 交易对的 K 线数据"""
    r = get_redis()

    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - days * 24 * 60 * 60 * 1000

    # 60 天 1 分钟 K 线约 86400 条
    expected_bars = days * 24 * 60

    key = f"kline:okx:{symbol}:{interval}"

    # 检查已有数据
    existing = r.zcard(key)
    if existing >= expected_bars * 0.95:  # 95% 以上认为数据完整
        return 0

    total = 0
    current_ts = None

    while True:
        klines = fetch_okx_klines(symbol, interval, current_ts, 300)
        if not klines:
            break

        oldest_ts = klines[0]["timestamp"]

        # 过滤掉太早的数据
        if oldest_ts < start_time:
            klines = [k for k in klines if k["timestamp"] >= start_time]
            if klines:
                pipe = r.pipeline()
                for kline in klines:
                    ts = kline["timestamp"]
                    kline["timestamp_ns"] = ts * 1000000
                    pipe.zadd(key, {json.dumps(kline): ts})
                pipe.execute()
                total += len(klines)
            break

        # 存储数据
        pipe = r.pipeline()
        for kline in klines:
            ts = kline["timestamp"]
            kline["timestamp_ns"] = ts * 1000000
            pipe.zadd(key, {json.dumps(kline): ts})
        pipe.execute()
        total += len(klines)

        current_ts = oldest_ts
        time.sleep(REQUEST_DELAY)

    return total


# ==================== Binance ====================

def get_binance_symbols() -> List[str]:
    """获取 Binance 永续合约列表"""
    session = get_session()
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/exchangeInfo"

    try:
        response = session.get(url, timeout=30)
        data = response.json()
        symbols = []
        for sym in data.get("symbols", []):
            if sym.get("contractType") == "PERPETUAL" and sym.get("status") == "TRADING":
                symbols.append(sym["symbol"])
        return sorted(symbols)
    except Exception as e:
        print(f"[Binance] 获取交易对失败: {e}")
    return []


def fetch_binance_klines(symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1500) -> List[Dict]:
    """获取 Binance K 线数据"""
    session = get_session()
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/continuousKlines"
    params = {
        "pair": symbol,
        "contractType": "PERPETUAL",
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit
    }

    try:
        response = session.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            klines = []
            for item in data:
                if len(item) >= 6:
                    kline = {
                        "timestamp": item[0],
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "symbol": symbol,
                        "exchange": "binance",
                        "interval": interval,
                        "type": "kline"
                    }
                    klines.append(kline)
            return klines
    except Exception as e:
        pass
    return []


def load_binance_symbol(symbol: str, interval: str, days: int) -> int:
    """加载单个 Binance 交易对的 K 线数据"""
    r = get_redis()

    # 周期转毫秒
    interval_ms_map = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
    interval_ms = interval_ms_map.get(interval.lower(), 60000)

    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - days * 24 * 60 * 60 * 1000

    # 60 天 1 分钟 K 线约 86400 条
    expected_bars = days * 24 * 60

    key = f"kline:binance:{symbol}:{interval}"

    # 检查已有数据
    existing = r.zcard(key)
    if existing >= expected_bars * 0.95:  # 95% 以上认为数据完整
        return 0

    total = 0
    current_start = start_time

    while current_start < end_time:
        current_end = min(current_start + 1500 * interval_ms, end_time)

        klines = fetch_binance_klines(symbol, interval, current_start, current_end, 1500)

        if klines:
            pipe = r.pipeline()
            for kline in klines:
                ts = kline["timestamp"]
                kline["timestamp_ns"] = ts * 1000000
                pipe.zadd(key, {json.dumps(kline): ts})
            pipe.execute()
            total += len(klines)
            current_start = klines[-1]["timestamp"] + interval_ms
        else:
            current_start = current_end

        time.sleep(REQUEST_DELAY)

    return total


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(description="批量预加载 K 线数据到 Redis")
    parser.add_argument("--days", type=int, default=60, help="加载天数 (默认: 60)")
    parser.add_argument("--interval", type=str, default="1m", help="K 线周期 (默认: 1m)")
    parser.add_argument("--exchange", type=str, default="all", choices=["binance", "okx", "all"],
                        help="交易所 (默认: all)")
    parser.add_argument("--symbols", type=str, default="", help="指定交易对，逗号分隔")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"并发数 (默认: {MAX_WORKERS})")
    parser.add_argument("--limit", type=int, default=0, help="限制交易对数量 (0=全部)")
    args = parser.parse_args()

    print("=" * 60)
    print("       K 线数据批量预加载工具")
    print("=" * 60)
    print(f"  交易所: {args.exchange.upper()}")
    print(f"  天数: {args.days} 天")
    print(f"  周期: {args.interval}")
    print(f"  并发: {args.workers}")
    print(f"  代理: {PROXY_HOST}:{PROXY_PORT}")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print("-" * 60)

    # Test Redis connection
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        print("[Redis] 连接成功")
    except Exception as e:
        print(f"[Redis] 连接失败: {e}")
        return 1

    # Load OKX data
    if args.exchange in ["okx", "all"]:
        print("\n[OKX] 开始加载...")

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            symbols = [s if "-SWAP" in s else f"{s.replace('USDT', '')}-USDT-SWAP" for s in symbols]
        else:
            symbols = get_okx_symbols()

        if args.limit > 0:
            symbols = symbols[:args.limit]

        print(f"[OKX] 交易对数量: {len(symbols)}")

        total_klines = 0
        success = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(load_okx_symbol, s, args.interval, args.days): s for s in symbols}

            for i, future in enumerate(as_completed(futures)):
                symbol = futures[future]
                try:
                    loaded = future.result()
                    if loaded > 0:
                        total_klines += loaded
                        success += 1
                        print(f"[OKX] [{i+1}/{len(symbols)}] {symbol}: +{loaded}")
                    else:
                        existing = r.zcard(f"kline:okx:{symbol}:{args.interval}")
                        if existing > 0:
                            success += 1
                            print(f"[OKX] [{i+1}/{len(symbols)}] {symbol}: 已有 {existing} 条")
                        else:
                            print(f"[OKX] [{i+1}/{len(symbols)}] {symbol}: 无数据")
                except Exception as e:
                    print(f"[OKX] [{i+1}/{len(symbols)}] {symbol}: 失败 - {e}")

        print(f"\n[OKX] 完成: {success}/{len(symbols)} 成功, 新增 {total_klines} 条")

    # Load Binance data
    if args.exchange in ["binance", "all"]:
        print("\n[Binance] 开始加载...")

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            symbols = [s.replace("-", "").replace("SWAP", "") for s in symbols]
        else:
            symbols = get_binance_symbols()

        if args.limit > 0:
            symbols = symbols[:args.limit]

        print(f"[Binance] 交易对数量: {len(symbols)}")

        total_klines = 0
        success = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(load_binance_symbol, s, args.interval, args.days): s for s in symbols}

            for i, future in enumerate(as_completed(futures)):
                symbol = futures[future]
                try:
                    loaded = future.result()
                    if loaded > 0:
                        total_klines += loaded
                        success += 1
                        print(f"[Binance] [{i+1}/{len(symbols)}] {symbol}: +{loaded}")
                    else:
                        existing = r.zcard(f"kline:binance:{symbol}:{args.interval}")
                        if existing > 0:
                            success += 1
                            print(f"[Binance] [{i+1}/{len(symbols)}] {symbol}: 已有 {existing} 条")
                        else:
                            print(f"[Binance] [{i+1}/{len(symbols)}] {symbol}: 无数据")
                except Exception as e:
                    print(f"[Binance] [{i+1}/{len(symbols)}] {symbol}: 失败 - {e}")

        print(f"\n[Binance] 完成: {success}/{len(symbols)} 成功, 新增 {total_klines} 条")

    # Summary
    print("\n" + "=" * 60)
    print("[数据统计]")

    sample_okx = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
    sample_binance = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    print("  OKX:")
    for sym in sample_okx:
        count = r.zcard(f"kline:okx:{sym}:{args.interval}")
        if count > 0:
            print(f"    {sym}: {count} 条")

    print("  Binance:")
    for sym in sample_binance:
        count = r.zcard(f"kline:binance:{sym}:{args.interval}")
        if count > 0:
            print(f"    {sym}: {count} 条")

    print("=" * 60)
    print("[完成]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
