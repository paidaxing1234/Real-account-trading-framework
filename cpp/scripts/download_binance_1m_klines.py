#!/usr/bin/env python3
"""
从 Binance 数据中心下载 USDT 合约 K线数据并写入Redis
支持 1m 和 1h 周期
"""

import os
import requests
import zipfile
import io
import json
import redis
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import time

# 配置
BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"
OUTPUT_DIR = "/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/data"

# Redis配置
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# 请求配置
MAX_WORKERS = 200
RETRY_COUNT = 3
TIMEOUT = 30
    
# 周期配置: interval -> (默认月数, Redis key后缀)
INTERVAL_CONFIG = {
    "1m": {"months": 2, "redis_suffix": "1m"},
    "1h": {"months": 6, "redis_suffix": "1h"},
}


def get_symbols_from_redis(interval="1m"):
    """从Redis获取所有Binance USDT合约交易对"""
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    # 优先从1m获取，因为1m的交易对最全
    keys = r.keys("kline:binance:*:1m")
    symbols = []
    for key in keys:
        parts = key.decode().split(":")
        if len(parts) >= 3:
            symbol = parts[2]
            if symbol.endswith("USDT"):
                symbols.append(symbol)
    return sorted(list(set(symbols)))


def download_csv(symbol, date_str, interval):
    """下载并解压单个K线文件，返回CSV内容"""
    filename = f"{symbol}-{interval}-{date_str}.zip"
    url = f"{BASE_URL}/{symbol}/{interval}/{filename}"

    for retry in range(RETRY_COUNT):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code == 404:
                return None, 'notfound'
            resp.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    return None, 'error'
                with zf.open(csv_files[0]) as src:
                    return src.read().decode('utf-8'), 'success'

        except zipfile.BadZipFile:
            return None, 'error'
        except Exception as e:
            if retry == RETRY_COUNT - 1:
                return None, 'error'
            time.sleep(0.5)

    return None, 'error'


def parse_csv_to_klines(csv_content, symbol, interval):
    """解析CSV内容为K线数据列表"""
    klines = []
    lines = csv_content.strip().split('\n')

    for line in lines[1:]:  # 跳过header
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) < 6:
            continue

        try:
            timestamp = int(parts[0])
            kline = {
                "exchange": "binance",
                "symbol": symbol,
                "interval": interval,
                "type": "kline",
                "timestamp": timestamp,
                "timestamp_ns": timestamp * 1000000,
                "open": float(parts[1]),
                "high": float(parts[2]),
                "low": float(parts[3]),
                "close": float(parts[4]),
                "volume": float(parts[5])
            }
            klines.append((timestamp, json.dumps(kline)))
        except (ValueError, IndexError):
            continue

    return klines


def download_and_import(symbol, date_str, interval, redis_conn, save_csv=False, output_dir=None):
    """下载CSV并导入Redis"""
    csv_content, status = download_csv(symbol, date_str, interval)

    if status != 'success' or not csv_content:
        return status, 0

    # 可选：保存CSV文件
    if save_csv and output_dir:
        csv_path = os.path.join(output_dir, f"{symbol}-{interval}-{date_str}.csv")
        if not os.path.exists(csv_path):
            with open(csv_path, 'w') as f:
                f.write(csv_content)

    # 解析并写入Redis
    klines = parse_csv_to_klines(csv_content, symbol, interval)
    if not klines:
        return 'empty', 0

    redis_suffix = INTERVAL_CONFIG[interval]["redis_suffix"]
    key = f"kline:binance:{symbol}:{redis_suffix}"

    # 批量写入Redis
    pipe = redis_conn.pipeline()
    for timestamp, kline_json in klines:
        pipe.zadd(key, {kline_json: timestamp})
    pipe.execute()

    return 'success', len(klines)


def process_task(args_tuple):
    """处理单个下载任务"""
    symbol, date_str, interval, redis_pool, save_csv, output_dir = args_tuple
    redis_conn = redis.Redis(connection_pool=redis_pool)
    return symbol, date_str, download_and_import(symbol, date_str, interval, redis_conn, save_csv, output_dir)


def run_download(interval, months, symbols, workers, save_csv, output_dir, redis_host, redis_port):
    """执行下载任务"""
    # Redis连接池
    redis_pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=REDIS_DB)

    # 计算日期范围
    today = datetime.now().date()
    end_date = today - timedelta(days=1)
    start_date = today - timedelta(days=months * 30)

    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    print(f"\n{'=' * 60}")
    print(f"下载 {interval} K线")
    print(f"{'=' * 60}")
    print(f"日期范围: {start_date} ~ {end_date} ({len(dates)}天)")
    print(f"交易对: {len(symbols)} 个")
    print(f"{'=' * 60}")

    # 生成所有任务
    tasks = [
        (symbol, date_str, interval, redis_pool, save_csv, output_dir)
        for symbol in symbols
        for date_str in dates
    ]
    total_tasks = len(tasks)
    print(f"总任务: {total_tasks} ({len(symbols)}币种 x {len(dates)}天)")

    # 统计
    results = {'success': 0, 'notfound': 0, 'error': 0, 'empty': 0}
    total_klines = 0
    completed = 0
    last_print = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_task, task): task for task in tasks}

        for future in as_completed(futures):
            completed += 1
            try:
                symbol, date_str, (status, count) = future.result()
                results[status] += 1
                total_klines += count

                now = time.time()
                if status == 'error':
                    print(f"[错误] {symbol}-{interval}-{date_str}")
                elif now - last_print >= 1.0:
                    pct = completed * 100 / total_tasks
                    print(f"[{pct:.1f}%] {completed}/{total_tasks} | K线:{total_klines} | 成功:{results['success']} 未找到:{results['notfound']}")
                    last_print = now
            except Exception as e:
                results['error'] += 1

    print(f"{'=' * 60}")
    print(f"{interval} 完成! 成功:{results['success']} 未找到:{results['notfound']} 错误:{results['error']} K线:{total_klines}条")

    return results, total_klines


def main():
    parser = argparse.ArgumentParser(description='下载Binance K线并导入Redis')
    parser.add_argument('--interval', type=str, default="1m,1h", help='K线周期，逗号分隔 (默认: 1m,1h)')
    parser.add_argument('--months-1m', type=int, default=2, help='1m K线下载月数 (默认: 2)')
    parser.add_argument('--months-1h', type=int, default=6, help='1h K线下载月数 (默认: 6)')
    parser.add_argument('--symbols', type=str, help='指定交易对，逗号分隔 (默认: 从Redis获取)')
    parser.add_argument('--save-csv', action='store_true', help='同时保存CSV文件')
    parser.add_argument('--output', type=str, default=OUTPUT_DIR, help='CSV输出目录')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, help=f'并发数 (默认: {MAX_WORKERS})')
    parser.add_argument('--redis-host', type=str, default=REDIS_HOST, help='Redis主机')
    parser.add_argument('--redis-port', type=int, default=REDIS_PORT, help='Redis端口')
    args = parser.parse_args()

    # 创建输出目录
    if args.save_csv:
        os.makedirs(args.output, exist_ok=True)

    # 解析要下载的周期
    intervals = [i.strip() for i in args.interval.split(',')]

    print("=" * 60)
    print("Binance K线下载器 -> Redis")
    print("=" * 60)
    print(f"周期: {intervals}")
    print(f"Redis: {args.redis_host}:{args.redis_port}")
    print(f"并发数: {args.workers}")
    if args.save_csv:
        print(f"CSV目录: {args.output}")

    # 获取交易对列表
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]
        print(f"指定交易对: {len(symbols)} 个")
    else:
        print("从Redis获取交易对列表...")
        symbols = get_symbols_from_redis()
        print(f"找到 {len(symbols)} 个交易对")

    if not symbols:
        print("[错误] 没有找到交易对")
        return

    # 按周期下载
    total_results = {'success': 0, 'notfound': 0, 'error': 0, 'empty': 0}
    total_klines = 0

    for interval in intervals:
        if interval not in INTERVAL_CONFIG:
            print(f"[警告] 不支持的周期: {interval}")
            continue

        # 获取该周期的月数
        if interval == "1m":
            months = args.months_1m
        elif interval == "1h":
            months = args.months_1h
        else:
            months = INTERVAL_CONFIG[interval]["months"]

        results, klines = run_download(
            interval=interval,
            months=months,
            symbols=symbols,
            workers=args.workers,
            save_csv=args.save_csv,
            output_dir=args.output,
            redis_host=args.redis_host,
            redis_port=args.redis_port
        )

        for k, v in results.items():
            total_results[k] += v
        total_klines += klines

    print(f"\n{'=' * 60}")
    print("全部完成!")
    print(f"成功: {total_results['success']} 个文件")
    print(f"未找到: {total_results['notfound']} 个文件")
    print(f"错误: {total_results['error']} 个文件")
    print(f"导入K线: {total_klines} 条")


if __name__ == '__main__':
    main()
