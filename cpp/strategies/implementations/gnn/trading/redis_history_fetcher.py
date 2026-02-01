#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 历史数据获取器

从 Redis 获取历史 K 线数据用于 GNN 策略

Redis 数据结构:
- kline:{symbol}:{interval} -> Sorted Set (score=timestamp, member=json)

@author Sequence Team
@date 2026-01
"""

import redis
import json
import pandas as pd
import numpy as np
from typing import Optional, List, Dict
from datetime import datetime
import os


class RedisHistoryFetcher:
    """从 Redis 获取历史数据"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379,
                 password: str = "", db: int = 0):
        """
        初始化 Redis 连接

        Args:
            host: Redis 主机地址
            port: Redis 端口
            password: Redis 密码
            db: Redis 数据库编号
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.client: Optional[redis.Redis] = None

    def connect(self) -> bool:
        """连接到 Redis"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                db=self.db,
                decode_responses=True
            )
            self.client.ping()
            print(f"[Redis] 连接成功: {self.host}:{self.port}")
            return True
        except redis.ConnectionError as e:
            print(f"[Redis] 连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            self.client = None

    def get_klines(self, symbol: str, interval: str, limit: int = 1500,
                    exchange: str = "binance") -> List[Dict]:
        """
        获取 K 线数据

        Args:
            symbol: 交易对 (Binance 格式: BTCUSDT 或 OKX 格式: BTC-USDT-SWAP)
            interval: K 线周期 (1s, 1m, 5m, 1H)
            limit: 获取数量
            exchange: 交易所 ("binance" 或 "okx")

        Returns:
            K 线数据列表，每个元素是包含 OHLCV 的字典
        """
        if not self.client:
            return []

        # Redis key 格式: kline:{exchange}:{symbol}:{interval}
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            # 获取最新 N 条（按时间升序）
            raw_data = self.client.zrange(key, -limit, -1)
            return [json.loads(item) for item in raw_data]
        except Exception as e:
            print(f"[错误] 获取 K线 失败: {e}")
            return []

    def get_klines_by_time_range(self, symbol: str, interval: str,
                                  start_ts: int, end_ts: int,
                                  exchange: str = "binance") -> List[Dict]:
        """
        按时间范围获取 K 线数据

        Args:
            symbol: 交易对
            interval: K 线周期
            start_ts: 开始时间戳（毫秒）
            end_ts: 结束时间戳（毫秒）
            exchange: 交易所 ("binance" 或 "okx")

        Returns:
            K 线数据列表
        """
        if not self.client:
            return []

        # Redis key 格式: kline:{exchange}:{symbol}:{interval}
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            # 使用 ZRANGEBYSCORE 按时间范围获取
            raw_data = self.client.zrangebyscore(key, start_ts, end_ts)
            return [json.loads(item) for item in raw_data]
        except Exception as e:
            print(f"[错误] 获取 K线 失败: {e}")
            return []

    def get_available_symbols(self, interval: str = "1m", exchange: str = "binance") -> List[str]:
        """
        获取 Redis 中有数据的交易对列表

        Args:
            interval: K 线周期
            exchange: 交易所 ("binance" 或 "okx")

        Returns:
            交易对列表
        """
        if not self.client:
            return []

        symbols = []
        try:
            cursor = 0
            while True:
                # Redis key 格式: kline:{exchange}:{symbol}:{interval}
                cursor, keys = self.client.scan(
                    cursor, match=f"kline:{exchange}:*:{interval}", count=100
                )
                for key in keys:
                    parts = key.split(":")
                    if len(parts) >= 4:
                        symbol = parts[2]  # kline:exchange:symbol:interval
                        if symbol not in symbols:
                            symbols.append(symbol)
                if cursor == 0:
                    break
        except Exception as e:
            print(f"[错误] 扫描失败: {e}")

        return symbols

    def get_kline_count(self, symbol: str, interval: str, exchange: str = "binance") -> int:
        """获取指定交易对的 K 线数量"""
        if not self.client:
            return 0

        # Redis key 格式: kline:{exchange}:{symbol}:{interval}
        key = f"kline:{exchange}:{symbol}:{interval}"
        try:
            return self.client.zcard(key)
        except Exception as e:
            print(f"[错误] 获取数量失败: {e}")
            return 0


def convert_binance_to_okx_symbol(binance_symbol: str) -> str:
    """
    将 Binance 格式的交易对转换为 OKX 格式
    Binance: BTCUSDT -> OKX: BTC-USDT-SWAP
    """
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}-USDT-SWAP"
    return binance_symbol


def convert_okx_to_binance_symbol(okx_symbol: str) -> str:
    """
    将 OKX 格式的交易对转换为 Binance 格式
    OKX: BTC-USDT-SWAP -> Binance: BTCUSDT
    """
    if "-SWAP" in okx_symbol:
        parts = okx_symbol.replace("-SWAP", "").split("-")
        return "".join(parts)
    elif "-" in okx_symbol:
        return okx_symbol.replace("-", "")
    return okx_symbol


def fetch_all_history_from_redis(
    fetcher: RedisHistoryFetcher,
    symbols: List[str],
    interval: str = "1m",
    limit: int = 1500,
    symbol_format: str = "binance",
    exchange: str = "binance"
) -> pd.DataFrame:
    """
    从 Redis 获取所有币种的历史数据

    Args:
        fetcher: RedisHistoryFetcher 实例
        symbols: 交易对列表 (Binance 格式: BTCUSDT 或 OKX 格式: BTC-USDT-SWAP)
        interval: K 线周期
        limit: 每个币种获取的 K 线数量
        symbol_format: 输入符号格式 "binance" 或 "okx"
        exchange: 交易所 ("binance" 或 "okx")

    Returns:
        包含所有币种 K 线数据的 DataFrame
    """
    all_dfs = []
    failed_symbols = []

    for symbol in symbols:
        # Redis 中存储的格式：直接使用 Binance 格式
        # 如果输入是 OKX 格式，转换为 Binance 格式
        if symbol_format == "binance":
            redis_symbol = symbol  # Binance 格式直接使用
        else:
            redis_symbol = convert_okx_to_binance_symbol(symbol)  # OKX -> Binance

        klines = fetcher.get_klines(redis_symbol, interval, limit, exchange=exchange)

        if not klines:
            failed_symbols.append(symbol)
            continue

        # 转换为 DataFrame
        df = pd.DataFrame(klines)

        # 统一列名
        df = df.rename(columns={
            "timestamp": "Time",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })

        # 使用输入的原始 symbol 格式作为 Ticker
        df["Ticker"] = symbol

        # 转换时间
        if "Time" in df.columns:
            df["Time"] = pd.to_datetime(df["Time"], unit="ms")

        # 转换数值类型
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        all_dfs.append(df)

    if failed_symbols:
        print(f"[Redis] 获取失败的币种 ({len(failed_symbols)}): {failed_symbols[:10]}...")

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        print(f"[Redis] 获取成功: {len(all_dfs)} 个币种, {len(combined_df)} 条数据")
        return combined_df[["Ticker", "Time", "Open", "High", "Low", "Close", "Volume"]]
    else:
        print("[Redis] 没有获取到任何数据")
        return pd.DataFrame()


def main():
    """测试 Redis 历史数据获取"""
    # 从环境变量获取 Redis 配置
    redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_pass = os.getenv("REDIS_PASSWORD", "")

    print("=" * 60)
    print("       Redis 历史数据获取器测试")
    print("=" * 60)

    fetcher = RedisHistoryFetcher(redis_host, redis_port, redis_pass)

    if not fetcher.connect():
        print("连接失败，退出")
        return

    # 获取可用的交易对
    print("\n[可用交易对]")
    symbols = fetcher.get_available_symbols("1m")
    print(f"  1m K线: {len(symbols)} 个")
    for s in symbols[:10]:
        count = fetcher.get_kline_count(s, "1m")
        print(f"    - {s}: {count} 条")

    if symbols:
        # 测试获取数据
        print("\n[获取历史数据]")
        df = fetch_all_history_from_redis(
            fetcher,
            symbols[:5],  # 只测试前 5 个
            interval="1m",
            limit=100,
            symbol_format="okx"
        )

        if not df.empty:
            print(f"\n数据预览:")
            print(df.head(10))
            print(f"\n数据统计:")
            print(df.describe())

    fetcher.disconnect()
    print("\n测试完成")


if __name__ == "__main__":
    main()
