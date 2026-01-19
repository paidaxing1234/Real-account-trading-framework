#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预加载历史 K 线数据到 Redis

从 Binance/OKX API 拉取历史 K 线数据并存储到 Redis，供策略使用。

使用方法：
    python preload_klines_to_redis.py [--days 60] [--interval 1m] [--exchange binance]
    python preload_klines_to_redis.py --exchange okx --days 60 --interval 1m
    python preload_klines_to_redis.py --exchange all --days 60  # 同时加载两个交易所

环境变量：
    REDIS_HOST       - Redis 主机地址 (默认: 127.0.0.1)
    REDIS_PORT       - Redis 端口 (默认: 6379)
    REDIS_PASSWORD   - Redis 密码 (默认: 空)
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
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置 ====================

# Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Binance API 配置
BINANCE_FUTURES_URL = "https://fapi.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binancefuture.com"

# OKX API 配置
OKX_API_URL = "https://www.okx.com"
OKX_TESTNET_URL = "https://www.okx.com"  # OKX 测试网使用相同域名，通过 header 区分

# 每批次最大数量
BATCH_SIZE = 300  # OKX 限制 300，Binance 限制 1500

# 并发线程数
MAX_WORKERS = 3

# 请求间隔（秒）
REQUEST_DELAY = 0.3


class BaseKlineLoader:
    """K 线数据加载器基类"""

    def __init__(self, use_proxy: bool = True):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

        # 代理配置
        if use_proxy:
            proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
            proxy_port = os.getenv("PROXY_PORT", "7890")
            proxy_url = f"http://{proxy_host}:{proxy_port}"
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            print(f"[代理] 使用代理: {proxy_url}")

    def get_exchange_info(self) -> List[str]:
        raise NotImplementedError

    def get_klines(self, symbol: str, interval: str, start_time: int, end_time: int, limit: int) -> List[Dict]:
        raise NotImplementedError

    @property
    def exchange_name(self) -> str:
        raise NotImplementedError

    @property
    def batch_size(self) -> int:
        return BATCH_SIZE


class BinanceKlineLoader(BaseKlineLoader):
    """Binance K 线数据加载器"""

    def __init__(self, testnet: bool = False, use_proxy: bool = True):
        super().__init__(use_proxy)
        self.base_url = BINANCE_TESTNET_URL if testnet else BINANCE_FUTURES_URL
        self.testnet = testnet

    @property
    def exchange_name(self) -> str:
        return "binance"

    @property
    def batch_size(self) -> int:
        return 1500

    def get_exchange_info(self) -> List[str]:
        """获取所有永续合约交易对"""
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                symbols = []
                for sym in data.get("symbols", []):
                    if sym.get("contractType") == "PERPETUAL" and sym.get("status") == "TRADING":
                        symbols.append(sym["symbol"])
                return sorted(symbols)
        except Exception as e:
            print(f"[Binance] 获取交易对列表失败: {e}")
        return []

    def get_klines(self, symbol: str, interval: str, start_time: int, end_time: int, limit: int = 1500) -> List[Dict]:
        """获取 K 线数据"""
        url = f"{self.base_url}/fapi/v1/continuousKlines"
        params = {
            "pair": symbol,
            "contractType": "PERPETUAL",
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
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
            else:
                print(f"[Binance] {symbol} API 返回 {response.status_code}: {response.text[:100]}")
        except Exception as e:
            print(f"[Binance] {symbol} 获取 K 线失败: {e}")
        return []


class OKXKlineLoader(BaseKlineLoader):
    """OKX K 线数据加载器"""

    def __init__(self, testnet: bool = False, use_proxy: bool = True):
        super().__init__(use_proxy)
        self.base_url = OKX_API_URL
        self.testnet = testnet
        if testnet:
            self.session.headers.update({
                "x-simulated-trading": "1"
            })

    @property
    def exchange_name(self) -> str:
        return "okx"

    @property
    def batch_size(self) -> int:
        return 300

    def get_exchange_info(self) -> List[str]:
        """获取所有永续合约交易对"""
        url = f"{self.base_url}/api/v5/public/instruments"
        params = {
            "instType": "SWAP"
        }
        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "0":
                    symbols = []
                    for inst in data.get("data", []):
                        inst_id = inst.get("instId", "")
                        state = inst.get("state", "")
                        # 只获取 USDT 永续合约且正在交易的
                        if inst_id.endswith("-USDT-SWAP") and state == "live":
                            symbols.append(inst_id)
                    return sorted(symbols)
        except Exception as e:
            print(f"[OKX] 获取交易对列表失败: {e}")
        return []

    def convert_interval(self, interval: str) -> str:
        """转换周期格式到 OKX 格式"""
        # Binance: 1m, 5m, 15m, 1h, 4h, 1d
        # OKX: 1m, 5m, 15m, 1H, 4H, 1D
        mapping = {
            "1m": "1m",
            "3m": "3m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "2h": "2H",
            "4h": "4H",
            "6h": "6H",
            "12h": "12H",
            "1d": "1D",
            "1w": "1W",
        }
        return mapping.get(interval.lower(), interval)

    def get_klines(self, symbol: str, interval: str, start_time: int, end_time: int, limit: int = 300) -> List[Dict]:
        """获取 K 线数据

        OKX API 参数说明:
        - before: 请求此时间戳之前的数据（返回更早的数据）
        - after: 请求此时间戳之后的数据（返回更新的数据）
        """
        url = f"{self.base_url}/api/v5/market/history-candles"
        okx_interval = self.convert_interval(interval)

        # OKX 的 before/after 参数含义与直觉相反
        # before=ts 返回 ts 之前的数据，after=ts 返回 ts 之后的数据
        params = {
            "instId": symbol,
            "bar": okx_interval,
            "after": str(start_time),  # 返回 start_time 之后的数据
            "limit": str(min(limit, 300))
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "0":
                    klines = []
                    # OKX 返回的数据是倒序的（最新的在前），需要反转
                    raw_data = data.get("data", [])
                    for item in reversed(raw_data):
                        if len(item) >= 6:
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
                else:
                    print(f"[OKX] {symbol} API 错误: {data.get('msg', 'Unknown error')}")
            else:
                print(f"[OKX] {symbol} API 返回 {response.status_code}: {response.text[:100]}")
        except Exception as e:
            print(f"[OKX] {symbol} 获取 K 线失败: {e}")
        return []


class RedisKlineStorage:
    """Redis K 线数据存储"""

    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT, password: str = REDIS_PASSWORD):
        self.host = host
        self.port = port
        self.password = password
        self.client: Optional[redis.Redis] = None

    def connect(self) -> bool:
        """连接到 Redis"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                decode_responses=True
            )
            self.client.ping()
            print(f"[Redis] 连接成功: {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"[Redis] 连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            self.client = None

    def store_klines(self, symbol: str, interval: str, exchange: str, klines: List[Dict]) -> int:
        """存储 K 线数据到 Redis"""
        if not self.client or not klines:
            return 0

        key = f"kline:{exchange}:{symbol}:{interval}"

        try:
            # 使用 pipeline 批量写入
            pipe = self.client.pipeline()

            for kline in klines:
                timestamp = kline["timestamp"]
                # 添加纳秒时间戳
                kline["timestamp_ns"] = timestamp * 1000000
                value = json.dumps(kline)
                pipe.zadd(key, {value: timestamp})

            pipe.execute()
            return len(klines)
        except Exception as e:
            print(f"[错误] 存储 {symbol} K 线失败: {e}")
            return 0

    def get_kline_count(self, symbol: str, interval: str, exchange: str) -> int:
        """获取已存储的 K 线数量"""
        if not self.client:
            return 0
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            return self.client.zcard(key)
        except:
            return 0

    def get_latest_timestamp(self, symbol: str, interval: str, exchange: str) -> Optional[int]:
        """获取最新的 K 线时间戳"""
        if not self.client:
            return None
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            result = self.client.zrevrange(key, 0, 0, withscores=True)
            if result:
                return int(result[0][1])
        except:
            pass
        return None

    def get_oldest_timestamp(self, symbol: str, interval: str, exchange: str) -> Optional[int]:
        """获取最早的 K 线时间戳"""
        if not self.client:
            return None
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            result = self.client.zrange(key, 0, 0, withscores=True)
            if result:
                return int(result[0][1])
        except:
            pass
        return None


def interval_to_ms(interval: str) -> int:
    """将周期转换为毫秒"""
    interval = interval.lower()
    unit = interval[-1]
    value = int(interval[:-1])

    if unit == 'm':
        return value * 60 * 1000
    elif unit == 'h':
        return value * 60 * 60 * 1000
    elif unit == 'd':
        return value * 24 * 60 * 60 * 1000
    elif unit == 'w':
        return value * 7 * 24 * 60 * 60 * 1000
    else:
        return value * 60 * 1000  # 默认分钟


def load_symbol_klines(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbol: str,
    interval: str,
    days: int
) -> int:
    """加载单个交易对的 K 线数据"""
    total_loaded = 0
    interval_ms = interval_to_ms(interval)
    exchange = loader.exchange_name
    batch_size = loader.batch_size

    # 计算时间范围
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - days * 24 * 60 * 60 * 1000

    # 检查已有数据
    existing_count = storage.get_kline_count(symbol, interval, exchange)
    latest_ts = storage.get_latest_timestamp(symbol, interval, exchange)
    oldest_ts = storage.get_oldest_timestamp(symbol, interval, exchange)

    # 智能加载：检查是否需要加载更早的数据或更新最新数据
    need_load_old = True
    need_load_new = True

    if oldest_ts and oldest_ts <= start_time:
        need_load_old = False  # 已有足够早的数据

    if latest_ts:
        # 只加载最新的缺失数据
        if latest_ts > end_time - interval_ms * 2:
            need_load_new = False  # 数据已是最新

    if not need_load_old and not need_load_new:
        return 0  # 数据已完整

    # 加载更早的历史数据
    if need_load_old and oldest_ts:
        current_end = oldest_ts - interval_ms
        current_start = max(start_time, current_end - batch_size * interval_ms)

        while current_start < current_end and current_start >= start_time:
            klines = loader.get_klines(symbol, interval, current_start, current_end, batch_size)

            if klines:
                stored = storage.store_klines(symbol, interval, exchange, klines)
                total_loaded += stored
                current_end = klines[0]["timestamp"] - interval_ms
                current_start = max(start_time, current_end - batch_size * interval_ms)
            else:
                break

            time.sleep(REQUEST_DELAY)

    # 加载最新数据
    if need_load_new:
        if latest_ts:
            current_start = latest_ts + interval_ms
        else:
            current_start = start_time

        while current_start < end_time:
            current_end = min(current_start + batch_size * interval_ms, end_time)

            klines = loader.get_klines(symbol, interval, current_start, current_end, batch_size)

            if klines:
                stored = storage.store_klines(symbol, interval, exchange, klines)
                total_loaded += stored
                current_start = klines[-1]["timestamp"] + interval_ms
            else:
                current_start = current_end

            time.sleep(REQUEST_DELAY)

    return total_loaded


def load_exchange_data(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbols: List[str],
    interval: str,
    days: int,
    workers: int
) -> tuple:
    """加载单个交易所的数据"""
    exchange = loader.exchange_name
    print(f"\n[{exchange.upper()}] 开始加载 {len(symbols)} 个交易对的 {days} 天 {interval} K 线数据...")

    start_time = time.time()
    total_klines = 0
    success_count = 0
    failed_symbols = []

    # 使用线程池并发加载
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for symbol in symbols:
            future = executor.submit(
                load_symbol_klines,
                loader, storage, symbol, interval, days
            )
            futures[future] = symbol

        for i, future in enumerate(as_completed(futures)):
            symbol = futures[future]
            try:
                loaded = future.result()
                if loaded > 0:
                    total_klines += loaded
                    success_count += 1
                    print(f"[{exchange.upper()}] [{i+1}/{len(symbols)}] {symbol}: +{loaded} 条")
                else:
                    # 检查是否已有数据
                    existing = storage.get_kline_count(symbol, interval, exchange)
                    if existing > 0:
                        success_count += 1
                        print(f"[{exchange.upper()}] [{i+1}/{len(symbols)}] {symbol}: 已是最新 ({existing} 条)")
                    else:
                        failed_symbols.append(symbol)
                        print(f"[{exchange.upper()}] [{i+1}/{len(symbols)}] {symbol}: 无数据")
            except Exception as e:
                failed_symbols.append(symbol)
                print(f"[{exchange.upper()}] [{i+1}/{len(symbols)}] {symbol}: 失败 - {e}")

    elapsed = time.time() - start_time
    return total_klines, success_count, failed_symbols, elapsed


def main():
    parser = argparse.ArgumentParser(description="预加载 K 线数据到 Redis")
    parser.add_argument("--days", type=int, default=60, help="加载天数 (默认: 60)")
    parser.add_argument("--interval", type=str, default="1m", help="K 线周期 (默认: 1m)")
    parser.add_argument("--exchange", type=str, default="all", choices=["binance", "okx", "all"],
                        help="交易所 (默认: all)")
    parser.add_argument("--testnet", action="store_true", help="使用测试网")
    parser.add_argument("--symbols", type=str, default="", help="指定交易对，逗号分隔 (默认: 全部)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"并发线程数 (默认: {MAX_WORKERS})")
    parser.add_argument("--no-proxy", action="store_true", help="不使用代理")
    args = parser.parse_args()

    print("=" * 60)
    print("       K 线数据预加载工具")
    print("=" * 60)
    print()
    print(f"  交易所: {args.exchange.upper()}")
    print(f"  网络: {'测试网' if args.testnet else '主网'}")
    print(f"  天数: {args.days} 天")
    print(f"  周期: {args.interval}")
    print(f"  并发: {args.workers} 线程")
    print(f"  代理: {'禁用' if args.no_proxy else '启用'}")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print()
    print("-" * 60)

    # 初始化 Redis
    storage = RedisKlineStorage()
    if not storage.connect():
        print("[错误] Redis 连接失败，退出")
        return 1

    use_proxy = not args.no_proxy
    results = {}

    # 加载 Binance 数据
    if args.exchange in ["binance", "all"]:
        loader = BinanceKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            # 确保是 Binance 格式
            symbols = [s.replace("-", "").replace("SWAP", "") for s in symbols]
            if symbols[0].endswith("USDT"):
                pass  # 已经是 Binance 格式
            print(f"[Binance] 使用指定的 {len(symbols)} 个交易对")
        else:
            print("[Binance] 获取交易对列表...")
            symbols = loader.get_exchange_info()
            print(f"[Binance] 获取到 {len(symbols)} 个永续合约交易对")

        if symbols:
            total, success, failed, elapsed = load_exchange_data(
                loader, storage, symbols, args.interval, args.days, args.workers
            )
            results["binance"] = {
                "total": total,
                "success": success,
                "failed": failed,
                "elapsed": elapsed,
                "symbols": symbols
            }

    # 加载 OKX 数据
    if args.exchange in ["okx", "all"]:
        loader = OKXKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            # 转换为 OKX 格式
            okx_symbols = []
            for s in symbols:
                if "-SWAP" in s:
                    okx_symbols.append(s)
                elif s.endswith("USDT"):
                    base = s[:-4]
                    okx_symbols.append(f"{base}-USDT-SWAP")
                else:
                    okx_symbols.append(s)
            symbols = okx_symbols
            print(f"[OKX] 使用指定的 {len(symbols)} 个交易对")
        else:
            print("[OKX] 获取交易对列表...")
            symbols = loader.get_exchange_info()
            print(f"[OKX] 获取到 {len(symbols)} 个永续合约交易对")

        if symbols:
            total, success, failed, elapsed = load_exchange_data(
                loader, storage, symbols, args.interval, args.days, args.workers
            )
            results["okx"] = {
                "total": total,
                "success": success,
                "failed": failed,
                "elapsed": elapsed,
                "symbols": symbols
            }

    # 统计结果
    print()
    print("=" * 60)
    print("       加载完成")
    print("=" * 60)

    for exchange, data in results.items():
        print()
        print(f"[{exchange.upper()}]")
        print(f"  总耗时: {data['elapsed']:.1f} 秒")
        print(f"  成功: {data['success']}/{len(data['symbols'])} 个交易对")
        print(f"  新增: {data['total']} 条 K 线")
        if data['failed']:
            print(f"  失败: {len(data['failed'])} 个")
            print(f"  失败列表: {data['failed'][:5]}{'...' if len(data['failed']) > 5 else ''}")

    # 显示部分交易对的数据量
    print()
    print("[数据统计]")

    if "binance" in results:
        sample_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        print("  Binance:")
        for sym in sample_symbols:
            count = storage.get_kline_count(sym, args.interval, "binance")
            if count > 0:
                print(f"    {sym}: {count} 条")

    if "okx" in results:
        sample_symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "DOGE-USDT-SWAP", "XRP-USDT-SWAP"]
        print("  OKX:")
        for sym in sample_symbols:
            count = storage.get_kline_count(sym, args.interval, "okx")
            if count > 0:
                print(f"    {sym}: {count} 条")

    storage.disconnect()
    print()
    print("[完成] 数据已存储到 Redis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
