#!/usr/bin/env python3
"""
多账户网格策略启动器

从配置文件读取多个账户配置，为每个账户启动独立的策略实例。
每个策略实例使用不同的 strategy_id，连接到同一个服务器。

使用方法:
    python3 run_multi_account.py --config multi_account_config.yaml
"""

import sys
import yaml
import signal
import time
from multiprocessing import Process
from typing import List

try:
    from strategy_base import StrategyBase
except ImportError:
    print("错误: 未找到 strategy_base 模块")
    print("请先编译 C++ 模块: cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)

# 导入网格策略
sys.path.append('/home/llx/Real-account-trading-framework/cpp/strategies')
from grid_strategy_cpp import GridStrategy


def run_strategy_instance(config: dict):
    """运行单个策略实例"""
    try:
        # 创建策略
        strategy = GridStrategy(
            strategy_id=config['strategy_id'],
            symbol=config['symbol'],
            grid_num=config['grid_num'],
            grid_spread=config['grid_spread'],
            order_amount=config['order_amount'],
            api_key=config.get('api_key', ''),
            secret_key=config.get('secret_key', ''),
            passphrase=config.get('passphrase', ''),
            is_testnet=config.get('is_testnet', True)
        )

        # 运行策略
        strategy.run()

    except Exception as e:
        print(f"[{config['strategy_id']}] 错误: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='多账户网格策略启动器')
    parser.add_argument('--config', type=str, default='multi_account_config.yaml',
                       help='配置文件路径')
    args = parser.parse_args()

    # 读取配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"错误: 无法读取配置文件 {args.config}: {e}")
        sys.exit(1)

    accounts = config.get('accounts', [])
    if not accounts:
        print("错误: 配置文件中没有账户配置")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  多账户网格策略启动器")
    print("=" * 60)
    print(f"\n配置文件: {args.config}")
    print(f"账户数量: {len(accounts)}\n")

    # 启动所有策略实例
    processes: List[Process] = []

    for i, account_config in enumerate(accounts, 1):
        strategy_id = account_config['strategy_id']
        symbol = account_config['symbol']

        print(f"[{i}/{len(accounts)}] 启动策略: {strategy_id} ({symbol})")

        # 创建进程
        p = Process(target=run_strategy_instance, args=(account_config,))
        p.start()
        processes.append(p)

        print(f"  PID: {p.pid}")
        time.sleep(1)  # 避免同时启动导致资源竞争

    print("\n" + "=" * 60)
    print("  所有策略已启动")
    print("=" * 60)
    print("\n运行中的策略:")
    for i, (p, account_config) in enumerate(zip(processes, accounts), 1):
        print(f"  [{i}] {account_config['strategy_id']}: PID {p.pid}")

    print("\n按 Ctrl+C 停止所有策略\n")

    # 信号处理
    def signal_handler(signum, frame):
        print("\n\n收到停止信号，正在停止所有策略...")
        for p in processes:
            if p.is_alive():
                p.terminate()

        # 等待所有进程结束
        for p in processes:
            p.join(timeout=5)

        print("所有策略已停止")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 等待所有进程
    for p in processes:
        p.join()


if __name__ == "__main__":
    main()
