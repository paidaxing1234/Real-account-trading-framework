#!/usr/bin/env python3
"""
测试8h K线数据读取
"""

import sys
import os
import time

# 添加策略路径
STRATEGIES_DIR = "/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies"
sys.path.insert(0, STRATEGIES_DIR)

from strategy_base import StrategyBase

class Test8hKline(StrategyBase):
    def __init__(self):
        super().__init__("test_8h_kline")

    def on_init(self):
        print("=" * 60)
        print("测试8h K线数据读取")
        print("=" * 60)

        # 连接Redis
        print("\n1. 连接Redis...")
        if not self.connect_historical_data():
            print("❌ 连接Redis失败")
            return
        print("✅ 连接Redis成功")

        # 测试读取8h K线
        print("\n2. 读取BTC 8h K线（最近10根）...")
        try:
            klines = self.get_latest_historical_klines(
                "BTC-USDT-SWAP",
                "okx",
                "8h",
                10
            )

            if klines:
                print(f"✅ 成功读取 {len(klines)} 根8h K线")
                print("\n最近3根K线:")
                for i, kline in enumerate(klines[-3:]):
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(kline.timestamp / 1000))
                    print(f"  [{i+1}] {ts} | O:{kline.open:.2f} H:{kline.high:.2f} L:{kline.low:.2f} C:{kline.close:.2f}")
            else:
                print("❌ 未读取到数据")

        except Exception as e:
            print(f"❌ 读取失败: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

if __name__ == "__main__":
    # 设置Redis环境变量
    os.environ["REDIS_HOST"] = "127.0.0.1"
    os.environ["REDIS_PORT"] = "6379"

    test = Test8hKline()
    test.on_init()
