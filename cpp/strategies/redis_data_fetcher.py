#!/usr/bin/env python3
"""
Redis 数据拉取器

功能：
1. 从服务器 Redis 拉取行情数据
2. 存储到本地数据库/文件

使用方法：
    python3 redis_data_fetcher.py --redis-host 192.168.1.100 --output ./data

依赖：
    pip install redis pandas

@author Sequence Team
@date 2025-12
"""

import redis
import json
import time
import argparse
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any


class RedisDataFetcher:
    """Redis 数据拉取器"""
    
    def __init__(self, host: str, port: int, password: str = "", db: int = 0):
        """
        初始化
        
        Args:
            host: Redis 主机
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
            # 测试连接
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
    
    def get_trades(self, symbol: str, limit: int = 1000) -> List[Dict]:
        """
        获取 trades 数据
        
        Args:
            symbol: 交易对
            limit: 获取数量
            
        Returns:
            trades 列表（按时间降序）
        """
        if not self.client:
            return []
        
        key = f"trades:{symbol}"
        try:
            raw_data = self.client.lrange(key, 0, limit - 1)
            return [json.loads(item) for item in raw_data]
        except Exception as e:
            print(f"[错误] 获取 trades 失败: {e}")
            return []
    
    def get_klines(self, symbol: str, interval: str, 
                   start_ts: int = 0, end_ts: int = 0,
                   limit: int = 1000) -> List[Dict]:
        """
        获取 K 线数据
        
        Args:
            symbol: 交易对
            interval: K线周期
            start_ts: 开始时间戳（毫秒）
            end_ts: 结束时间戳（毫秒）
            limit: 获取数量
            
        Returns:
            K线列表（按时间升序）
        """
        if not self.client:
            return []
        
        key = f"kline:{symbol}:{interval}"
        try:
            if start_ts > 0 or end_ts > 0:
                # 按时间范围查询
                min_score = start_ts if start_ts > 0 else '-inf'
                max_score = end_ts if end_ts > 0 else '+inf'
                raw_data = self.client.zrangebyscore(
                    key, min_score, max_score, 
                    start=0, num=limit
                )
            else:
                # 获取最新 N 条
                raw_data = self.client.zrevrange(key, 0, limit - 1)
                raw_data = list(reversed(raw_data))  # 转为升序
            
            return [json.loads(item) for item in raw_data]
        except Exception as e:
            print(f"[错误] 获取 K线 失败: {e}")
            return []
    
    def get_all_symbols(self) -> Dict[str, Dict[str, int]]:
        """
        获取所有有数据的交易对
        
        Returns:
            {
                "trades": {"BTC-USDT": 1234, ...},
                "klines": {"BTC-USDT:1s": 5678, ...}
            }
        """
        if not self.client:
            return {}
        
        result = {"trades": {}, "klines": {}}
        
        try:
            # 扫描 trades
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match="trades:*", count=100)
                for key in keys:
                    symbol = key.replace("trades:", "")
                    count = self.client.llen(key)
                    result["trades"][symbol] = count
                if cursor == 0:
                    break
            
            # 扫描 K线
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor, match="kline:*", count=100)
                for key in keys:
                    # kline:BTC-USDT:1s
                    parts = key.split(":", 2)
                    if len(parts) >= 3:
                        symbol_interval = f"{parts[1]}:{parts[2]}"
                        count = self.client.zcard(key)
                        result["klines"][symbol_interval] = count
                if cursor == 0:
                    break
                    
        except Exception as e:
            print(f"[错误] 扫描失败: {e}")
        
        return result


class LocalDatabase:
    """本地 SQLite 数据库"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self):
        """连接到本地数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self._create_tables()
        print(f"[SQLite] 数据库: {self.db_path}")
    
    def disconnect(self):
        """断开连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def _create_tables(self):
        """创建数据表"""
        cursor = self.conn.cursor()
        
        # trades 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                price REAL,
                size REAL,
                side TEXT,
                raw_data TEXT,
                UNIQUE(symbol, timestamp, price, size)
            )
        """)
        
        # klines 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                raw_data TEXT,
                UNIQUE(symbol, interval, timestamp)
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trades(symbol, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval_ts ON klines(symbol, interval, timestamp)
        """)
        
        self.conn.commit()
    
    def insert_trades(self, trades: List[Dict]) -> int:
        """批量插入 trades"""
        if not self.conn or not trades:
            return 0
        
        cursor = self.conn.cursor()
        inserted = 0
        
        for trade in trades:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO trades 
                    (symbol, timestamp, price, size, side, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    trade.get("symbol", ""),
                    trade.get("timestamp", 0),
                    trade.get("price", 0),
                    trade.get("size", 0),
                    trade.get("side", ""),
                    json.dumps(trade)
                ))
                inserted += cursor.rowcount
            except sqlite3.IntegrityError:
                pass  # 重复数据，忽略
        
        self.conn.commit()
        return inserted
    
    def insert_klines(self, klines: List[Dict]) -> int:
        """批量插入 K线"""
        if not self.conn or not klines:
            return 0
        
        cursor = self.conn.cursor()
        inserted = 0
        
        for kline in klines:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO klines 
                    (symbol, interval, timestamp, open, high, low, close, volume, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    kline.get("symbol", ""),
                    kline.get("interval", ""),
                    kline.get("timestamp", 0),
                    kline.get("open", 0),
                    kline.get("high", 0),
                    kline.get("low", 0),
                    kline.get("close", 0),
                    kline.get("volume", 0),
                    json.dumps(kline)
                ))
                inserted += cursor.rowcount
            except sqlite3.IntegrityError:
                pass
        
        self.conn.commit()
        return inserted
    
    def get_latest_timestamp(self, table: str, symbol: str, 
                            interval: str = None) -> int:
        """获取最新的时间戳"""
        if not self.conn:
            return 0
        
        cursor = self.conn.cursor()
        
        if table == "trades":
            cursor.execute("""
                SELECT MAX(timestamp) FROM trades WHERE symbol = ?
            """, (symbol,))
        else:
            cursor.execute("""
                SELECT MAX(timestamp) FROM klines WHERE symbol = ? AND interval = ?
            """, (symbol, interval))
        
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0


def fetch_and_store(fetcher: RedisDataFetcher, db: LocalDatabase,
                   symbols: List[str], intervals: List[str]):
    """
    从 Redis 拉取数据并存储到本地
    """
    print("\n[拉取] 开始拉取数据...\n")
    
    total_trades = 0
    total_klines = 0
    
    # 拉取 trades
    for symbol in symbols:
        trades = fetcher.get_trades(symbol, limit=10000)
        if trades:
            inserted = db.insert_trades(trades)
            total_trades += inserted
            print(f"  [trades] {symbol}: 获取 {len(trades)} 条, 新增 {inserted} 条")
    
    # 拉取 K线
    for symbol in symbols:
        for interval in intervals:
            klines = fetcher.get_klines(symbol, interval, limit=10000)
            if klines:
                # 添加 interval 字段（Redis 数据可能没有）
                for k in klines:
                    k["interval"] = interval
                inserted = db.insert_klines(klines)
                total_klines += inserted
                print(f"  [kline] {symbol}:{interval}: 获取 {len(klines)} 条, 新增 {inserted} 条")
    
    print(f"\n[完成] Trades: {total_trades} 条, K线: {total_klines} 条")


def main():
    parser = argparse.ArgumentParser(description='Redis 数据拉取器')
    
    # Redis 配置
    parser.add_argument('--redis-host', type=str, default='127.0.0.1',
                        help='Redis 主机')
    parser.add_argument('--redis-port', type=int, default=6379,
                        help='Redis 端口')
    parser.add_argument('--redis-pass', type=str, default='',
                        help='Redis 密码')
    
    # 本地存储
    parser.add_argument('--output', type=str, default='./market_data.db',
                        help='本地数据库路径')
    
    # 数据范围
    parser.add_argument('--symbols', type=str, 
                        default='BTC-USDT,ETH-USDT,SOL-USDT',
                        help='要拉取的交易对，逗号分隔')
    parser.add_argument('--intervals', type=str,
                        default='1s,1m,5m,1H',
                        help='要拉取的K线周期，逗号分隔')
    
    # 模式
    parser.add_argument('--daemon', action='store_true',
                        help='守护进程模式，每小时拉取一次')
    parser.add_argument('--interval-hours', type=float, default=1.0,
                        help='守护进程模式下的拉取间隔（小时）')
    parser.add_argument('--list', action='store_true',
                        help='列出 Redis 中所有数据')
    
    args = parser.parse_args()
    
    print("╔" + "═" * 48 + "╗")
    print("║        Redis 数据拉取器                          ║")
    print("╚" + "═" * 48 + "╝\n")
    
    # 解析交易对和周期
    symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    intervals = [i.strip() for i in args.intervals.split(',') if i.strip()]
    
    # 连接 Redis
    fetcher = RedisDataFetcher(args.redis_host, args.redis_port, args.redis_pass)
    if not fetcher.connect():
        return
    
    # 列出数据
    if args.list:
        print("\n[Redis 数据统计]\n")
        all_data = fetcher.get_all_symbols()
        
        print("Trades:")
        for symbol, count in sorted(all_data["trades"].items()):
            print(f"  {symbol}: {count} 条")
        
        print("\nK线:")
        for key, count in sorted(all_data["klines"].items()):
            print(f"  {key}: {count} 条")
        
        fetcher.disconnect()
        return
    
    # 连接本地数据库
    db = LocalDatabase(args.output)
    db.connect()
    
    print(f"[配置]")
    print(f"  Redis: {args.redis_host}:{args.redis_port}")
    print(f"  本地数据库: {args.output}")
    print(f"  交易对: {symbols}")
    print(f"  K线周期: {intervals}")
    
    if args.daemon:
        print(f"\n[守护进程模式] 每 {args.interval_hours} 小时拉取一次")
        print("  按 Ctrl+C 停止\n")
        
        try:
            while True:
                fetch_and_store(fetcher, db, symbols, intervals)
                print(f"\n[等待] 下次拉取: {args.interval_hours} 小时后\n")
                time.sleep(args.interval_hours * 3600)
        except KeyboardInterrupt:
            print("\n[停止] 已退出")
    else:
        # 单次拉取
        fetch_and_store(fetcher, db, symbols, intervals)
    
    # 清理
    db.disconnect()
    fetcher.disconnect()


if __name__ == "__main__":
    main()

