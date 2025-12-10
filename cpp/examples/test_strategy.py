#!/usr/bin/env python3
"""
测试策略：基于Journal的Python策略示例

演示如何使用JournalReader实现超低延迟策略
"""

import sys
import os

# 添加core目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from journal_reader import JournalReader, TickerEvent

class MomentumStrategy:
    """
    简单的动量策略
    
    策略逻辑：
    - 价格突破阈值买入
    - 价格跌破阈值卖出
    """
    
    def __init__(self):
        self.position = 0.0
        self.threshold_high = 50500.0
        self.threshold_low = 49500.0
        self.event_count = 0
        
        print("=" * 60)
        print("         Momentum Strategy Started")
        print("=" * 60)
        print(f"  Buy Threshold:  {self.threshold_high}")
        print(f"  Sell Threshold: {self.threshold_low}")
        print("=" * 60)
    
    def on_ticker(self, ticker: TickerEvent):
        """处理Ticker事件"""
        self.event_count += 1
        
        # 简单的动量策略
        if ticker.last_price > self.threshold_high and self.position == 0:
            self.position = 0.01
            print(f"\n[BUY]  {ticker.symbol} @ {ticker.last_price:.2f}")
            print(f"       Position: {self.position}")
            
        elif ticker.last_price < self.threshold_low and self.position > 0:
            print(f"\n[SELL] {ticker.symbol} @ {ticker.last_price:.2f}")
            print(f"       Position: {self.position} -> 0")
            self.position = 0.0
        
        # 定期打印状态
        if self.event_count % 1000 == 0:
            print(f"[Status] Processed {self.event_count} events, "
                  f"Position: {self.position}, "
                  f"Last Price: {ticker.last_price:.2f}")
    
    def on_finish(self):
        """策略结束"""
        print("\n" + "=" * 60)
        print("         Strategy Finished")
        print("=" * 60)
        print(f"  Total Events: {self.event_count}")
        print(f"  Final Position: {self.position}")
        print("=" * 60)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_strategy.py <journal_file> [max_events]")
        sys.exit(1)
    
    journal_file = sys.argv[1]
    max_events = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    # 创建策略
    strategy = MomentumStrategy()
    
    # 创建Reader
    reader = JournalReader(journal_file, busy_spin_count=1000)
    
    try:
        # 运行策略
        reader.run(
            on_ticker=strategy.on_ticker,
            max_events=max_events
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        strategy.on_finish()
        reader.close()

if __name__ == "__main__":
    main()

