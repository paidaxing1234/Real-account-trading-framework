#!/usr/bin/env python3
"""
深度数据（OrderBook）测试程序

测试内容：
- 订阅深度数据（books5）
- 接收并存储深度快照
- 查询历史深度数据

运行方式：
    python test_orderbook.py

编译依赖：
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import signal
import time

try:
    from strategy_base import StrategyBase, OrderBookSnapshot
except ImportError:
    print("错误: 未找到 strategy_base 模块，请先编译:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


class OrderBookTestStrategy(StrategyBase):
    """深度数据测试策略"""
    
    def __init__(self, max_orderbook_snapshots: int = 1000):
        super().__init__("orderbook_test", 
                        max_kline_bars=100,
                        max_trades=1000,
                        max_orderbook_snapshots=max_orderbook_snapshots,
                        max_funding_rate_records=10)
        
        # 交易对
        self.symbol = "BTC-USDT-SWAP"
        self.channel = "books5"  # 5档深度
        
        # 统计
        self.snapshot_count = 0
        self.start_time = None
    
    def on_init(self):
        """初始化"""
        self.start_time = time.time()
        
        print("=" * 60)
        print("       深度数据（OrderBook）测试程序")
        print("=" * 60)
        print()
        print(f"交易对: {self.symbol}")
        print(f"深度频道: {self.channel}")
        print()
        print("按 Ctrl+C 停止测试")
        print()
        print("-" * 60)
        
        # 订阅深度数据
        print(f"[初始化] 正在订阅 {self.symbol} {self.channel}...")
        self.subscribe_orderbook(self.symbol, self.channel)
        
        print("[初始化] 订阅完成，等待数据...")
        print("-" * 60)
    
    def on_orderbook(self, symbol: str, snapshot: OrderBookSnapshot):
        """深度数据回调"""
        if symbol != self.symbol:
            return
        
        self.snapshot_count += 1
        
        # 每10个快照打印一次
        if self.snapshot_count % 10 == 0:
            elapsed = time.time() - self.start_time
            print(f"[{elapsed:6.1f}s] 收到快照 #{self.snapshot_count}")
            print(f"  最优买价: {snapshot.best_bid_price:.2f} x {snapshot.best_bid_size:.4f}")
            print(f"  最优卖价: {snapshot.best_ask_price:.2f} x {snapshot.best_ask_size:.4f}")
            print(f"  中间价: {snapshot.mid_price:.2f}")
            print(f"  价差: {snapshot.spread:.2f}")
            print(f"  买盘档数: {len(snapshot.bids)}, 卖盘档数: {len(snapshot.asks)}")
            print()
    
    def on_stop(self):
        """停止 - 打印统计"""
        elapsed = time.time() - self.start_time
        
        # 取消订阅
        self.unsubscribe_orderbook(self.symbol, self.channel)
        
        print()
        print("=" * 60)
        print("                测试结果")
        print("=" * 60)
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  收到快照: {self.snapshot_count} 个")
        print()
        
        # 查询存储的数据
        stored_count = self.get_orderbook_count(self.symbol, self.channel)
        print(f"  存储的快照数: {stored_count}")
        
        if stored_count > 0:
            # 获取最后5个快照
            recent = self.get_recent_orderbooks(self.symbol, 5, self.channel)
            print(f"  最近5个快照:")
            for i, snap in enumerate(recent, 1):
                print(f"    {i}. 时间: {snap.timestamp} | "
                      f"买价: {snap.best_bid_price:.2f} | "
                      f"卖价: {snap.best_ask_price:.2f}")
            
            # 获取最近1分钟的数据
            one_min_ago = self.get_orderbooks_by_time(self.symbol, 60000, self.channel)
            print(f"  最近1分钟内的快照: {len(one_min_ago)} 个")
            
            # 获取最后一个快照
            last = self.get_last_orderbook(self.symbol, self.channel)
            if last:
                print(f"  最后一个快照:")
                print(f"    时间: {last.timestamp}")
                print(f"    最优买价: {last.best_bid_price:.2f} x {last.best_bid_size:.4f}")
                print(f"    最优卖价: {last.best_ask_price:.2f} x {last.best_ask_size:.4f}")
                print(f"    中间价: {last.mid_price:.2f}")
                print(f"    价差: {last.spread:.2f}")
        
        print("=" * 60)


def main():
    strategy = OrderBookTestStrategy()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

