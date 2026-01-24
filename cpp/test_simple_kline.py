#!/usr/bin/env python3
"""
简单测试：验证策略能否接收K线数据
"""

import sys
import time
import signal
sys.path.append('/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies')

import strategy_base

class SimpleKlineTest(strategy_base.StrategyBase):
    def __init__(self):
        super().__init__("simple_kline_test")
        self._kline_count = 0
        self._start_time = None

    def on_init(self):
        print("[测试] 初始化...")
        print("[测试] 订阅 BTC-USDT-SWAP 1s K线...")
        result = self.subscribe_kline("BTC-USDT-SWAP", "1s")
        print(f"[测试] subscribe_kline 返回: {result}")
        self._start_time = time.time()

    def on_kline(self, symbol, interval, bar):
        """K线回调"""
        self._kline_count += 1
        print(f"[测试] ✓ 收到K线 #{self._kline_count}: {symbol} {interval} close={bar.close}")

    def on_tick(self):
        """每个tick检查是否超时"""
        if self._start_time and time.time() - self._start_time > 30:
            print(f"\n[测试] 30秒已到，停止测试")
            self.stop()

    def on_stop(self):
        print(f"[测试] 停止... 共收到 {self._kline_count} 根K线")

def main():
    print("=" * 60)
    print("  简单K线接收测试")
    print("=" * 60)
    print()

    strategy = SimpleKlineTest()

    # 信号处理
    def signal_handler(signum, frame):
        print("\n收到停止信号...")
        strategy.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 运行策略
    strategy.run()

    print()
    if strategy._kline_count > 0:
        print(f"✓ 测试成功！共收到 {strategy._kline_count} 根K线")
    else:
        print("✗ 测试失败！未收到任何K线")

if __name__ == "__main__":
    main()
