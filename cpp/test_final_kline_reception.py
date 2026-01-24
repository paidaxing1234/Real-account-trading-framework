#!/usr/bin/env python3
"""
最终测试：验证策略能否接收K线数据
"""

import sys
import time
import subprocess
import signal

sys.path.append('/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies')

import strategy_base

# 全局计数器
kline_count = 0

class TestStrategy(strategy_base.StrategyBase):
    def __init__(self):
        super().__init__("test_final")

    def on_init(self):
        print("[TestStrategy] 初始化...")
        print("[TestStrategy] 订阅 BTC-USDT-SWAP 1s K线...")
        result = self.subscribe_kline("BTC-USDT-SWAP", "1s")
        print(f"[TestStrategy] 订阅结果: {result}")

    def on_start(self):
        print("[TestStrategy] 启动...")

    def on_stop(self):
        global kline_count
        print(f"[TestStrategy] 停止... 共收到 {kline_count} 根K线")

    def on_kline(self, kline):
        global kline_count
        kline_count += 1
        if kline_count <= 3:
            print(f"[TestStrategy] 收到K线 #{kline_count}:")
            print(f"  交易所: {kline.get('exchange', 'N/A')}")
            print(f"  交易对: {kline.get('symbol', 'N/A')}")
            print(f"  周期: {kline.get('interval', 'N/A')}")
            print(f"  收盘价: {kline.get('close', 'N/A')}")
            print(f"  时间: {kline.get('timestamp', 'N/A')}")

def main():
    print("=" * 60)
    print("  最终测试：验证策略能否接收K线数据")
    print("=" * 60)
    print()

    # 启动服务器
    print("1. 启动 trading_server_full...")
    server_process = subprocess.Popen(
        ["/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build/trading_server_full"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    print("   等待服务器启动...")
    time.sleep(3)

    # 创建策略
    print()
    print("2. 创建并连接策略...")
    strategy = TestStrategy()

    if not strategy.connect():
        print("   ✗ 连接失败")
        server_process.terminate()
        return

    print("   ✓ 连接成功")

    # 初始化策略
    print()
    print("3. 初始化策略...")
    strategy.on_init()

    # 等待接收K线
    print()
    print("4. 等待接收K线（10秒）...")
    time.sleep(10)

    # 停止策略
    print()
    print("5. 停止策略...")
    strategy.on_stop()
    strategy.disconnect()

    # 停止服务器
    print()
    print("6. 停止服务器...")
    server_process.send_signal(signal.SIGINT)
    server_process.wait(timeout=5)

    # 结果
    print()
    print("=" * 60)
    print("  测试结果")
    print("=" * 60)
    if kline_count > 0:
        print(f"  ✓ 成功接收 {kline_count} 根K线")
    else:
        print("  ✗ 未接收到K线")
    print("=" * 60)

if __name__ == "__main__":
    main()
