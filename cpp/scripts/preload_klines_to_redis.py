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

        OKX API 实际行为（经过测试验证）:
        - after=ts: 返回时间戳 < ts 的数据（倒序，最新的在前）
        - before=ts: 在查询历史数据时会被忽略，总是返回最新数据

        策略：使用 after 参数，传入 end_time + interval_ms，这样可以获取 <= end_time 的数据
        """
        url = f"{self.base_url}/api/v5/market/history-candles"
        okx_interval = self.convert_interval(interval)

        # 使用 after 参数来获取指定时间范围的数据
        # after=ts 实际返回时间戳 < ts 的数据（倒序，最新的在前）
        # 所以我们传入 end_time + interval_ms，这样可以包含 end_time 这根K线
        interval_ms = interval_to_ms(interval)
        params = {
            "instId": symbol,
            "bar": okx_interval,
            "after": str(end_time + interval_ms),  # 获取 < end_time+interval 的数据
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
                            ts = int(item[0])
                            # 只保留在 [start_time, end_time] 范围内的K线
                            if start_time <= ts <= end_time:
                                kline = {
                                    "timestamp": ts,
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
        """存储 K 线数据到 Redis（格式与data_recorder完全一致）"""
        if not self.client or not klines:
            return 0

        key = f"kline:{exchange}:{symbol}:{interval}"

        try:
            # 使用 pipeline 批量写入
            pipe = self.client.pipeline()

            for kline in klines:
                timestamp = kline["timestamp"]
                # 确保数据格式与data_recorder一致：不添加timestamp_ns
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

    def get_all_usdt_contracts(self) -> Dict[str, List[str]]:
        """
        从Redis扫描所有USDT合约

        Returns:
            {"okx": ["BTC-USDT-SWAP", ...], "binance": ["BTCUSDT", ...]}
        """
        if not self.client:
            return {}

        contracts = {"okx": [], "binance": []}

        try:
            # 扫描所有 kline:*:1m keys
            keys = self.client.keys("kline:*:1m")

            for key in keys:
                # key格式: kline:exchange:symbol:1m
                parts = key.split(":")
                if len(parts) != 4:
                    continue

                exchange = parts[1]
                symbol = parts[2]

                # 只处理USDT合约
                if exchange == "okx" and "-USDT-SWAP" in symbol:
                    contracts["okx"].append(symbol)
                elif exchange == "binance" and symbol.endswith("USDT"):
                    contracts["binance"].append(symbol)

            # 排序
            contracts["okx"] = sorted(contracts["okx"])
            contracts["binance"] = sorted(contracts["binance"])

        except Exception as e:
            print(f"[Redis] 扫描合约失败: {e}")

        return contracts


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


def check_continuity(storage: RedisKlineStorage, symbol: str, interval: str, exchange: str) -> Dict:
    """
    检查K线数据的连续性

    Args:
        storage: Redis存储
        symbol: 交易对
        interval: K线周期
        exchange: 交易所

    Returns:
        包含连续性信息的字典
    """
    key = f"kline:{exchange}:{symbol}:{interval}"
    interval_ms = interval_to_ms(interval)

    try:
        # 获取所有时间戳
        all_data = storage.client.zrange(key, 0, -1, withscores=True)
        if not all_data:
            return {
                "continuous": False,
                "count": 0,
                "missing": 0,
                "time_range": None,
                "message": "无数据"
            }

        timestamps = sorted([int(score) for _, score in all_data])
        count = len(timestamps)

        if count < 2:
            return {
                "continuous": True,
                "count": count,
                "missing": 0,
                "time_range": (timestamps[0], timestamps[0]),
                "message": "数据不足2条，无法检测连续性"
            }

        # 计算应有的K线数量
        time_span_ms = timestamps[-1] - timestamps[0]
        expected_count = (time_span_ms // interval_ms) + 1
        missing_count = expected_count - count

        # 检测间隔
        gaps = []
        for i in range(1, len(timestamps)):
            gap_ms = timestamps[i] - timestamps[i-1]
            if gap_ms > interval_ms * 1.5:  # 允许一定误差
                gap_count = (gap_ms // interval_ms) - 1
                if gap_count > 0:
                    gaps.append({
                        'start': timestamps[i-1],
                        'end': timestamps[i],
                        'count': gap_count
                    })

        continuous = (missing_count == 0 and len(gaps) == 0)

        start_time = datetime.fromtimestamp(timestamps[0]/1000).strftime('%Y-%m-%d %H:%M:%S')
        end_time = datetime.fromtimestamp(timestamps[-1]/1000).strftime('%Y-%m-%d %H:%M:%S')

        if continuous:
            message = f"✓ 连续 ({count} 根)"
        else:
            message = f"✗ 缺失 {missing_count} 根 (应有 {expected_count} 根)"

        return {
            "continuous": continuous,
            "count": count,
            "expected": expected_count,
            "missing": missing_count,
            "gaps": len(gaps),
            "time_range": (timestamps[0], timestamps[-1]),
            "time_range_str": f"{start_time} ~ {end_time}",
            "message": message
        }

    except Exception as e:
        return {
            "continuous": False,
            "count": 0,
            "missing": 0,
            "time_range": None,
            "message": f"检测失败: {e}"
        }


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


def load_historical_before_oldest(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbol: str,
    interval: str,
    days: int
) -> int:
    """
    从最早的K线时间戳往前加载历史数据

    Args:
        loader: K线加载器
        storage: Redis存储
        symbol: 交易对
        interval: K线周期
        days: 往前加载的天数

    Returns:
        加载的K线数量
    """
    total_loaded = 0
    interval_ms = interval_to_ms(interval)
    exchange = loader.exchange_name
    batch_size = loader.batch_size

    # 获取当前最早的K线时间戳
    oldest_ts = storage.get_oldest_timestamp(symbol, interval, exchange)

    if not oldest_ts:
        print(f"[{exchange.upper()}] {symbol}:{interval} - Redis中无数据，跳过")
        return 0

    # 计算目标时间范围：从最早时间戳往前推days天
    end_time = oldest_ts - interval_ms  # 从最早K线的前一根开始
    start_time = end_time - days * 24 * 60 * 60 * 1000

    print(f"[{exchange.upper()}] {symbol}:{interval}")
    print(f"  当前最早: {datetime.fromtimestamp(oldest_ts/1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标范围: {datetime.fromtimestamp(start_time/1000).strftime('%Y-%m-%d %H:%M:%S')} ~ {datetime.fromtimestamp(end_time/1000).strftime('%Y-%m-%d %H:%M:%S')}")

    # 从end_time往前批量拉取
    current_end = end_time
    current_start = max(start_time, current_end - batch_size * interval_ms)

    while current_start < current_end and current_start >= start_time:
        klines = loader.get_klines(symbol, interval, current_start, current_end, batch_size)

        if klines:
            stored = storage.store_klines(symbol, interval, exchange, klines)
            total_loaded += stored
            print(f"  拉取: {datetime.fromtimestamp(klines[0]['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')} ~ {datetime.fromtimestamp(klines[-1]['timestamp']/1000).strftime('%Y-%m-%d %H:%M:%S')} (+{stored}根)")

            # 更新范围，继续往前拉取
            current_end = klines[0]["timestamp"] - interval_ms
            current_start = max(start_time, current_end - batch_size * interval_ms)
        else:
            print(f"  拉取失败，停止")
            break

        time.sleep(REQUEST_DELAY)

    if total_loaded > 0:
        print(f"  ✓ 完成: 共加载 {total_loaded} 根K线")
    else:
        print(f"  无新数据")

    return total_loaded


def fill_gaps_in_existing_data(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbol: str,
    interval: str
) -> int:
    """
    填补现有数据中的间隔

    Args:
        loader: K线加载器
        storage: Redis存储
        symbol: 交易对
        interval: K线周期

    Returns:
        填补的K线数量
    """
    total_loaded = 0
    interval_ms = interval_to_ms(interval)
    exchange = loader.exchange_name
    batch_size = loader.batch_size

    # 获取所有现有K线的时间戳
    key = f"kline:{exchange}:{symbol}:{interval}"
    try:
        # 获取所有时间戳
        all_data = storage.client.zrange(key, 0, -1, withscores=True)
        if not all_data or len(all_data) < 2:
            return 0

        timestamps = sorted([int(score) for _, score in all_data])

        print(f"[{exchange.upper()}] {symbol}:{interval} - 检测间隔")
        print(f"  现有K线数: {len(timestamps)}")

        # 检测间隔（大于2倍interval的视为间隔）
        gaps = []
        for i in range(1, len(timestamps)):
            gap_ms = timestamps[i] - timestamps[i-1]
            if gap_ms > interval_ms * 2:  # 间隔大于2倍周期
                gap_count = (gap_ms // interval_ms) - 1
                if gap_count > 0:
                    gaps.append({
                        'start': timestamps[i-1] + interval_ms,
                        'end': timestamps[i] - interval_ms,
                        'count': gap_count
                    })

        if not gaps:
            print(f"  ✓ 数据连续，无需填补")
            return 0

        print(f"  发现 {len(gaps)} 个间隔，共缺失 {sum(g['count'] for g in gaps)} 根K线")

        # 填补每个间隔
        for idx, gap in enumerate(gaps, 1):
            gap_start = gap['start']
            gap_end = gap['end']

            print(f"  [{idx}/{len(gaps)}] 填补间隔: {datetime.fromtimestamp(gap_start/1000).strftime('%Y-%m-%d %H:%M:%S')} ~ {datetime.fromtimestamp(gap_end/1000).strftime('%Y-%m-%d %H:%M:%S')} ({gap['count']}根)")

            # 分批拉取
            current_start = gap_start
            while current_start <= gap_end:
                current_end = min(current_start + (batch_size - 1) * interval_ms, gap_end)

                klines = loader.get_klines(symbol, interval, current_start, current_end, batch_size)

                if klines and len(klines) > 0:
                    stored = storage.store_klines(symbol, interval, exchange, klines)
                    total_loaded += stored
                    print(f"    拉取: {datetime.fromtimestamp(klines[0]['timestamp']/1000).strftime('%H:%M:%S')} ~ {datetime.fromtimestamp(klines[-1]['timestamp']/1000).strftime('%H:%M:%S')} (+{stored}根)")

                    # 更新起始位置：从最后一根K线的下一根开始
                    last_ts = klines[-1]["timestamp"]
                    current_start = last_ts + interval_ms

                    # 如果已经超过gap_end，退出循环
                    if last_ts >= gap_end:
                        break
                else:
                    print(f"    拉取失败，跳过此间隔")
                    break

                time.sleep(REQUEST_DELAY)

        if total_loaded > 0:
            print(f"  ✓ 完成: 共填补 {total_loaded} 根K线")

    except Exception as e:
        print(f"  ✗ 填补失败: {e}")

    return total_loaded


def load_from_current_time(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbol: str,
    interval: str,
    days: int
) -> int:
    """
    从当前时间往前拉取指定天数的K线数据（智能检测，只拉取缺失部分）

    Args:
        loader: K线加载器
        storage: Redis存储
        symbol: 交易对
        interval: K线周期
        days: 往前拉取的天数

    Returns:
        加载的K线数量
    """
    total_loaded = 0
    interval_ms = interval_to_ms(interval)
    exchange = loader.exchange_name
    batch_size = loader.batch_size

    # 计算目标时间范围：从当前时间往前推days天，对齐到interval边界
    current_time = int(time.time() * 1000)
    # 对齐到interval边界（向下取整）
    end_time = (current_time // interval_ms) * interval_ms
    start_time = end_time - days * 24 * 60 * 60 * 1000

    print(f"  目标范围: {datetime.fromtimestamp(start_time/1000).strftime('%Y-%m-%d %H:%M:%S')} ~ {datetime.fromtimestamp(end_time/1000).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标天数: {days} 天")

    # 步骤1: 删除超出时间范围的旧数据
    key = f"kline:{exchange}:{symbol}:{interval}"
    try:
        # 删除早于start_time的数据
        deleted_old = storage.client.zremrangebyscore(key, '-inf', start_time - 1)
        # 删除晚于end_time的数据（未来数据）
        deleted_future = storage.client.zremrangebyscore(key, end_time + 1, '+inf')

        total_deleted = deleted_old + deleted_future
        if total_deleted > 0:
            print(f"  清理数据: 删除 {deleted_old} 根旧数据, {deleted_future} 根未来数据")
    except Exception as e:
        print(f"  清理数据失败: {e}")

    # 步骤2: 检测现有数据，找出缺失的时间段
    try:
        all_data = storage.client.zrangebyscore(key, start_time, end_time, withscores=True)
        existing_timestamps = set(int(score) for _, score in all_data)

        if len(existing_timestamps) > 0:
            print(f"  现有数据: {len(existing_timestamps)} 根K线")

        # 计算应有的所有时间戳
        expected_timestamps = set()
        current_ts = start_time
        while current_ts <= end_time:
            expected_timestamps.add(current_ts)
            current_ts += interval_ms

        # 找出缺失的时间戳
        missing_timestamps = sorted(expected_timestamps - existing_timestamps)

        if len(missing_timestamps) == 0:
            print(f"  ✓ 数据完整，无需拉取")
            return 0

        print(f"  缺失数据: {len(missing_timestamps)} 根K线")

        # 将缺失的时间戳合并为连续的时间段
        gaps = []
        if missing_timestamps:
            gap_start = missing_timestamps[0]
            gap_end = missing_timestamps[0]

            for ts in missing_timestamps[1:]:
                if ts - gap_end <= interval_ms * 1.5:  # 连续
                    gap_end = ts
                else:  # 新的间隔
                    gaps.append((gap_start, gap_end))
                    gap_start = ts
                    gap_end = ts

            gaps.append((gap_start, gap_end))

        print(f"  需要拉取 {len(gaps)} 个时间段:")
        for idx, (gap_start, gap_end) in enumerate(gaps, 1):
            gap_count = len([ts for ts in missing_timestamps if gap_start <= ts <= gap_end])
            start_str = datetime.fromtimestamp(gap_start/1000).strftime('%Y-%m-%d %H:%M:%S')
            end_str = datetime.fromtimestamp(gap_end/1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"    [{idx}] {start_str} ~ {end_str} ({gap_count}根)")

        # 步骤3: 批量拉取缺失的时间段
        for idx, (gap_start, gap_end) in enumerate(gaps, 1):
            gap_count = len([ts for ts in missing_timestamps if gap_start <= ts <= gap_end])
            start_str = datetime.fromtimestamp(gap_start/1000).strftime('%Y-%m-%d %H:%M:%S')
            end_str = datetime.fromtimestamp(gap_end/1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  [{idx}/{len(gaps)}] 开始拉取: {start_str} ~ {end_str}")

            # 分批拉取这个时间段
            current_start = gap_start
            batch_num = 0
            while current_start <= gap_end:
                current_end = min(current_start + (batch_size - 1) * interval_ms, gap_end)
                batch_num += 1

                klines = loader.get_klines(symbol, interval, current_start, current_end, batch_size)

                if klines:
                    stored = storage.store_klines(symbol, interval, exchange, klines)
                    total_loaded += stored
                    batch_start_str = datetime.fromtimestamp(klines[0]['timestamp']/1000).strftime('%H:%M:%S')
                    batch_end_str = datetime.fromtimestamp(klines[-1]['timestamp']/1000).strftime('%H:%M:%S')
                    print(f"    批次{batch_num}: {batch_start_str} ~ {batch_end_str} (+{stored}根)")

                    current_start = klines[-1]["timestamp"] + interval_ms
                    if current_start > gap_end:
                        break
                else:
                    print(f"    批次{batch_num}: 拉取失败，跳过")
                    break

                time.sleep(REQUEST_DELAY)

        if total_loaded > 0:
            print(f"  ✓ 完成: 共加载 {total_loaded} 根K线")

    except Exception as e:
        print(f"  ✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()

    return total_loaded


def process_single_contract(
    loader: BaseKlineLoader,
    storage: RedisKlineStorage,
    symbol: str,
    interval: str,
    days: int,
    index: int,
    total: int
) -> tuple:
    """
    处理单个合约的数据加载和连续性检测

    Returns:
        (symbol, interval, loaded_count, continuity_result)
    """
    try:
        print(f"\n{'='*60}")
        print(f"[{index}/{total}] 处理合约: {symbol} | 周期: {interval}")
        print(f"{'='*60}")

        # 从当前时间往前加载数据
        loaded = load_from_current_time(
            loader, storage, symbol, interval, days
        )

        # 连续性检测
        print(f"\n  【连续性检测】")
        continuity = check_continuity(storage, symbol, interval, loader.exchange_name)
        print(f"  状态: {continuity['message']}")
        if continuity['time_range_str']:
            print(f"  时间范围: {continuity['time_range_str']}")
        print(f"{'='*60}")

        return (symbol, interval, loaded, continuity)

    except Exception as e:
        print(f"  ✗ 失败: {e}")
        import traceback
        traceback.print_exc()
        return (symbol, interval, 0, None)


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
    parser.add_argument("--mode", type=str, default="current", choices=["auto", "manual", "current"],
                        help="运行模式: current=从当前时间往前加载(默认), auto=从Redis最早时间戳往前加载, manual=手动指定参数")
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
    print(f"  模式: {args.mode.upper()}")
    print(f"  交易所: {args.exchange.upper()}")
    print(f"  网络: {'测试网' if args.testnet else '主网'}")
    print(f"  并发: {args.workers} 线程")
    print(f"  代理: {'禁用' if args.no_proxy else '启用'}")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print()

    if args.mode == "current":
        print("  当前时间模式说明:")
        print("  - 从Redis扫描所有USDT合约")
        print("  - 从当前时间往前加载:")
        print("    * 1m/5m/15m/30m: 2个月")
        print("    * 1h: 6个月")
        print("  - 每个合约加载完成后进行连续性检测")
    elif args.mode == "auto":
        print("  自动模式说明:")
        print("  - 从Redis扫描所有USDT合约")
        print("  - 检测每个合约的最早1min K线时间戳")
        print("  - 从最早时间戳往前加载:")
        print("    * 1m/5m/15m/30m: 2个月")
        print("    * 1h: 6个月")
    else:
        print(f"  手动模式: {args.days} 天, {args.interval}")

    print()
    print("-" * 60)

    # 初始化 Redis
    storage = RedisKlineStorage()
    if not storage.connect():
        print("[错误] Redis 连接失败，退出")
        return 1

    use_proxy = not args.no_proxy
    results = {}

    # ==================== 当前时间模式 ====================
    if args.mode == "current":
        print("\n[当前时间模式] 从Redis扫描USDT合约...")

        # 获取所有USDT合约
        contracts = storage.get_all_usdt_contracts()

        if not contracts["okx"] and not contracts["binance"]:
            print("[错误] Redis中没有找到任何USDT合约数据")
            print("[提示] 请先运行 trading_server_full 和 data_recorder 收集实时数据")
            return 1

        print(f"\n[扫描结果]")
        print(f"  OKX: {len(contracts['okx'])} 个合约")
        print(f"  Binance: {len(contracts['binance'])} 个合约")

        # 定义要加载的周期和对应的天数
        intervals_config = [
            ("1m", 60),    # 2个月
            ("5m", 60),    # 2个月
            ("15m", 60),   # 2个月
            ("30m", 60),   # 2个月
            ("1h", 180),   # 6个月
        ]

        # 加载 OKX 数据
        if contracts["okx"] and args.exchange in ["okx", "all"]:
            loader = OKXKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

            for interval, days in intervals_config:
                print(f"\n{'='*60}")
                print(f"[OKX] 处理 {interval} K线 (从当前时间往前 {days} 天)")
                print(f"{'='*60}")

                total_loaded = 0
                success_count = 0

                # 使用线程池并发处理
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    futures = []
                    for i, symbol in enumerate(contracts["okx"], 1):
                        future = executor.submit(
                            process_single_contract,
                            loader, storage, symbol, interval, days, i, len(contracts["okx"])
                        )
                        futures.append(future)

                    # 收集结果
                    for future in as_completed(futures):
                        _, _, loaded, _ = future.result()
                        total_loaded += loaded
                        if loaded > 0:
                            success_count += 1

                print(f"\n[OKX {interval}] 完成: {success_count}/{len(contracts['okx'])} 个合约")
                print(f"  总计加载: {total_loaded} 根K线")

        # 加载 Binance 数据
        if contracts["binance"] and args.exchange in ["binance", "all"]:
            loader = BinanceKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

            for interval, days in intervals_config:
                print(f"\n{'='*60}")
                print(f"[Binance] 处理 {interval} K线 (从当前时间往前 {days} 天)")
                print(f"{'='*60}")

                total_loaded = 0
                success_count = 0

                # 使用线程池并发处理
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    futures = []
                    for i, symbol in enumerate(contracts["binance"], 1):
                        future = executor.submit(
                            process_single_contract,
                            loader, storage, symbol, interval, days, i, len(contracts["binance"])
                        )
                        futures.append(future)

                    # 收集结果
                    for future in as_completed(futures):
                        _, _, loaded, _ = future.result()
                        total_loaded += loaded
                        if loaded > 0:
                            success_count += 1

                print(f"\n[Binance {interval}] 完成: {success_count}/{len(contracts['binance'])} 个合约")
                print(f"  总计加载: {total_loaded} 根K线")

        print()
        print("=" * 60)
        print("       当前时间模式加载完成")
        print("=" * 60)
        storage.disconnect()
        return 0

    # ==================== 自动模式 ====================
    if args.mode == "auto":
        print("\n[自动模式] 从Redis扫描USDT合约...")

        # 获取所有USDT合约
        contracts = storage.get_all_usdt_contracts()

        if not contracts["okx"] and not contracts["binance"]:
            print("[错误] Redis中没有找到任何USDT合约数据")
            print("[提示] 请先运行 trading_server_full 和 data_recorder 收集实时数据")
            return 1

        print(f"\n[扫描结果]")
        print(f"  OKX: {len(contracts['okx'])} 个合约")
        print(f"  Binance: {len(contracts['binance'])} 个合约")

        # 定义要加载的周期和对应的天数
        intervals_config = [
            ("1m", 60),    # 2个月
            ("5m", 60),    # 2个月
            ("15m", 60),   # 2个月
            ("30m", 60),   # 2个月
            ("1h", 180),   # 6个月
        ]

        # 加载 OKX 数据
        if contracts["okx"] and args.exchange in ["okx", "all"]:
            loader = OKXKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

            for interval, days in intervals_config:
                print(f"\n{'='*60}")
                print(f"[OKX] 处理 {interval} K线")
                print(f"{'='*60}")

                total_loaded = 0
                total_filled = 0
                success_count = 0

                for i, symbol in enumerate(contracts["okx"], 1):
                    print(f"\n[{i}/{len(contracts['okx'])}] {symbol}:{interval}")

                    try:
                        # 步骤1: 填补现有数据的间隔
                        filled = fill_gaps_in_existing_data(loader, storage, symbol, interval)
                        total_filled += filled

                        # 步骤2: 从最早时间戳往前加载历史数据
                        loaded = load_historical_before_oldest(
                            loader, storage, symbol, interval, days
                        )
                        total_loaded += loaded

                        if filled > 0 or loaded > 0:
                            success_count += 1
                    except Exception as e:
                        print(f"  ✗ 失败: {e}")

                print(f"\n[OKX {interval}] 完成: {success_count}/{len(contracts['okx'])} 个合约")
                print(f"  填补间隔: {total_filled} 根K线")
                print(f"  历史数据: {total_loaded} 根K线")
                print(f"  总计: {total_filled + total_loaded} 根K线")

        # 加载 Binance 数据
        if contracts["binance"] and args.exchange in ["binance", "all"]:
            loader = BinanceKlineLoader(testnet=args.testnet, use_proxy=use_proxy)

            for interval, days in intervals_config:
                print(f"\n{'='*60}")
                print(f"[Binance] 处理 {interval} K线")
                print(f"{'='*60}")

                total_loaded = 0
                total_filled = 0
                success_count = 0

                for i, symbol in enumerate(contracts["binance"], 1):
                    print(f"\n[{i}/{len(contracts['binance'])}] {symbol}:{interval}")

                    try:
                        # 步骤1: 填补现有数据的间隔
                        filled = fill_gaps_in_existing_data(loader, storage, symbol, interval)
                        total_filled += filled

                        # 步骤2: 从最早时间戳往前加载历史数据
                        loaded = load_historical_before_oldest(
                            loader, storage, symbol, interval, days
                        )
                        total_loaded += loaded

                        if filled > 0 or loaded > 0:
                            success_count += 1
                    except Exception as e:
                        print(f"  ✗ 失败: {e}")

                print(f"\n[Binance {interval}] 完成: {success_count}/{len(contracts['binance'])} 个合约")
                print(f"  填补间隔: {total_filled} 根K线")
                print(f"  历史数据: {total_loaded} 根K线")
                print(f"  总计: {total_filled + total_loaded} 根K线")

        print()
        print("=" * 60)
        print("       自动加载完成")
        print("=" * 60)
        storage.disconnect()
        return 0

    # ==================== 手动模式 ====================

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
