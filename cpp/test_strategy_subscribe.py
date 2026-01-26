#!/usr/bin/env python3
"""
测试策略基类的订阅功能
"""

import sys
import time
sys.path.append('/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies')

import strategy_base

class TestStrategy(strategy_base.StrategyBase):
    def __init__(self):
        super().__init__("test_subscribe")

    def on_init(self):
        print("[TestStrategy] 初始化...")
        print("[TestStrategy] 发送订阅请求...")
        result = self.subscribe_kline("BTC-USDT-SWAP", "1s")
        print(f"[TestStrategy] subscribe_kline 返回: {result}")

    def on_start(self):
        print("[TestStrategy] 启动...")

    def on_stop(self):
        print("[TestStrategy] 停止...")

    def on_kline(self, kline):
        print(f"[TestStrategy] 收到K线: {kline}")

def main():
    print("=" * 60)
    print("  测试策略订阅功能")
    print("=" * 60)
    print()

    strategy = TestStrategy()

    print("连接到服务器...")
    if not strategy.connect():
        print("连接失败")
        return

    print("✓ 连接成功")
    print()

    print("初始化策略...")
    strategy.on_init()
    print()

    print("等待5秒...")
    time.sleep(5)

    print()
    print("断开连接...")
    strategy.disconnect()

    print("测试完成")

if __name__ == "__main__":
    main()
