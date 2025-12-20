#!/usr/bin/env python3
"""
示例策略 - 展示如何使用 C++ 策略基类

演示功能:
1. 继承 StrategyBase
2. 订阅 K 线数据
3. 读取历史 K 线
4. 计算简单指标
5. 下单接口

使用方法:
    python3 example_strategy.py

@author Sequence Team
@date 2025-12
"""

import sys
import signal
import time

try:
    from strategy_base import StrategyBase, KlineBar
except ImportError:
    print("错误: 未找到 strategy_base 模块")
    print("请先编译 C++ 模块:")
    print("  cd strategies && mkdir -p build && cd build && cmake .. && make")
    sys.exit(1)


class ExampleStrategy(StrategyBase):
    """
    示例策略
    
    展示如何：
    - 继承 StrategyBase
    - 订阅多个币种
    - 读取历史 K 线
    - 计算技术指标
    """
    
    def __init__(self, strategy_id: str):
        # 初始化基类，存储 2 小时 1s K 线
        super().__init__(strategy_id, max_kline_bars=7200)
        
        # 订阅的币种
        self.symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
        self.interval = "1s"
        
        # 统计
        self.last_print_time = 0
    
    def on_init(self):
        """策略初始化"""
        self.log_info("=== 示例策略初始化 ===")
        
        # 订阅 K 线
        for symbol in self.symbols:
            self.subscribe_kline(symbol, self.interval)
            self.log_info(f"订阅 K 线: {symbol} {self.interval}")
        
        self.log_info("等待 K 线数据...")
    
    def on_stop(self):
        """策略停止"""
        self.log_info("=== 策略停止 ===")
        
        # 取消订阅
        for symbol in self.symbols:
            self.unsubscribe_kline(symbol, self.interval)
        
        # 打印各币种 K 线数量
        for symbol in self.symbols:
            count = self.get_kline_count(symbol, self.interval)
            self.log_info(f"{symbol}: {count} 根 K 线")
    
    def on_kline(self, symbol: str, interval: str, bar: KlineBar):
        """K 线回调"""
        # 每 5 秒打印一次状态
        current_time = time.time()
        if current_time - self.last_print_time >= 5:
            self.last_print_time = current_time
            self.print_status()
    
    def on_tick(self):
        """每次循环调用"""
        # 可以在这里添加定时逻辑
        pass
    
    def print_status(self):
        """打印状态"""
        print("\n" + "-" * 60)
        print(f"[状态] 时间: {time.strftime('%H:%M:%S')}")
        
        for symbol in self.symbols:
            count = self.get_kline_count(symbol, self.interval)
            
            # 获取最后一根 K 线
            last_bar = self.get_last_kline(symbol, self.interval)
            if last_bar:
                print(f"  {symbol:15s}: {count:4d} 根 | 最新: {last_bar.close:.2f}")
            else:
                print(f"  {symbol:15s}: 无数据")
            
            # 如果有足够数据，计算简单均线
            if count >= 20:
                closes = self.get_closes(symbol, self.interval)
                ma20 = sum(closes[-20:]) / 20
                print(f"                   MA20: {ma20:.2f}")
        
        print("-" * 60)
    
    def calculate_sma(self, symbol: str, period: int) -> float:
        """计算简单移动平均"""
        closes = self.get_closes(symbol, self.interval)
        if len(closes) < period:
            return 0.0
        return sum(closes[-period:]) / period


def main():
    print()
    print("╔" + "═" * 50 + "╗")
    print("║" + "  示例策略 (C++ 基类版)".center(44) + "║")
    print("╚" + "═" * 50 + "╝")
    print()
    
    # 创建策略
    strategy = ExampleStrategy("example_strategy")
    
    # 信号处理
    def signal_handler(signum, frame):
        print("\n收到停止信号...")
        strategy.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("按 Ctrl+C 停止\n")
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

