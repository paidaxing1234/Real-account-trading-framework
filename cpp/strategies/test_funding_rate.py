#!/usr/bin/env python3
"""
资金费率（FundingRate）测试程序

测试内容：
- 订阅资金费率数据
- 接收并存储资金费率记录
- 查询历史资金费率数据

运行方式：
    python test_funding_rate.py

编译依赖：
    cd cpp/build && cmake .. && make strategy_base
"""

import sys
import signal
import time

try:
    from strategy_base import StrategyBase, FundingRateData
except ImportError:
    print("错误: 未找到 strategy_base 模块，请先编译:")
    print("  cd cpp/build && cmake .. && make strategy_base")
    sys.exit(1)


class FundingRateTestStrategy(StrategyBase):
    """资金费率测试策略"""
    
    def __init__(self, max_funding_rate_records: int = 100):
        super().__init__("funding_rate_test",
                        max_kline_bars=100,
                        max_trades=1000,
                        max_orderbook_snapshots=100,
                        max_funding_rate_records=max_funding_rate_records)
        
        # 交易对（必须是永续合约）
        self.symbol = "BTC-USDT-SWAP"
        
        # 统计
        self.record_count = 0
        self.start_time = None
    
    def on_init(self):
        """初始化"""
        self.start_time = time.time()
        
        print("=" * 60)
        print("       资金费率（FundingRate）测试程序")
        print("=" * 60)
        print()
        print(f"交易对: {self.symbol}")
        print()
        print("注意: 资金费率数据推送频率为30-90秒一次")
        print("按 Ctrl+C 停止测试")
        print()
        print("-" * 60)
        
        # 订阅资金费率
        print(f"[初始化] 正在订阅 {self.symbol} 资金费率...")
        self.subscribe_funding_rate(self.symbol)
        
        print("[初始化] 订阅完成，等待数据...")
        print("-" * 60)
    
    def on_funding_rate(self, symbol: str, fr: FundingRateData):
        """资金费率回调"""
        if symbol != self.symbol:
            return
        
        self.record_count += 1
        elapsed = time.time() - self.start_time
        
        print(f"[{elapsed:6.1f}s] 收到资金费率 #{self.record_count}")
        print(f"  当前资金费率: {fr.funding_rate:.6f} ({fr.funding_rate * 100:.4f}%)")
        print(f"  下一期预测费率: {fr.next_funding_rate:.6f} ({fr.next_funding_rate * 100:.4f}%)")
        print(f"  资金费时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(fr.funding_time / 1000))}")
        print(f"  下一期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(fr.next_funding_time / 1000))}")
        print(f"  费率范围: [{fr.min_funding_rate:.6f}, {fr.max_funding_rate:.6f}]")
        print(f"  溢价指数: {fr.premium:.6f}")
        print(f"  结算状态: {fr.sett_state}")
        print()
    
    def on_stop(self):
        """停止 - 打印统计"""
        elapsed = time.time() - self.start_time
        
        # 取消订阅
        self.unsubscribe_funding_rate(self.symbol)
        
        print()
        print("=" * 60)
        print("                测试结果")
        print("=" * 60)
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  收到记录: {self.record_count} 条")
        print()
        
        # 查询存储的数据
        stored_count = self.get_funding_rate_count(self.symbol)
        print(f"  存储的记录数: {stored_count}")
        
        if stored_count > 0:
            # 获取所有记录
            all_records = self.get_funding_rates(self.symbol)
            print(f"  所有记录:")
            for i, fr in enumerate(all_records, 1):
                print(f"    {i}. 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(fr.timestamp / 1000))} | "
                      f"费率: {fr.funding_rate:.6f} ({fr.funding_rate * 100:.4f}%)")
            
            # 获取最近3条记录
            recent = self.get_recent_funding_rates(self.symbol, 3)
            print(f"  最近3条记录:")
            for i, fr in enumerate(recent, 1):
                print(f"    {i}. 费率: {fr.funding_rate:.6f} | "
                      f"下一期: {fr.next_funding_rate:.6f} | "
                      f"状态: {fr.sett_state}")
            
            # 获取最后一条记录
            last = self.get_last_funding_rate(self.symbol)
            if last:
                print(f"  最后一条记录:")
                print(f"    当前费率: {last.funding_rate:.6f} ({last.funding_rate * 100:.4f}%)")
                print(f"    下一期费率: {last.next_funding_rate:.6f} ({last.next_funding_rate * 100:.4f}%)")
                print(f"    资金费时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last.funding_time / 1000))}")
                print(f"    下一期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last.next_funding_time / 1000))}")
        
        print("=" * 60)


def main():
    strategy = FundingRateTestStrategy()
    
    # 注册信号处理
    signal.signal(signal.SIGINT, lambda s, f: strategy.stop())
    signal.signal(signal.SIGTERM, lambda s, f: strategy.stop())
    
    # 运行策略
    strategy.run()


if __name__ == "__main__":
    main()

