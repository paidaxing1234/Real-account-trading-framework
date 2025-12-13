"""
简单策略示例

这是一个最简单的策略，用于演示框架的基本用法。
每收到 10 条行情就发送一个测试订单。

运行方式：
    python simple_strategy.py

作者: Sequence Team
日期: 2024-12
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_client import TradingClient, Strategy, TickerData, OrderReport


class SimpleStrategy(Strategy):
    """
    简单策略
    
    功能：
    - 打印收到的行情
    - 每 N 条行情发送一个测试订单
    - 记录订单回报
    
    用于：
    - 测试框架连接是否正常
    - 理解策略的基本结构
    - 作为开发新策略的模板
    """
    
    def __init__(self, order_interval: int = 10):
        """
        初始化
        
        参数：
            order_interval: 每多少条行情发送一个订单
        """
        super().__init__()
        self.order_interval = order_interval
        self.tick_count = 0
        self.order_count = 0
    
    def on_start(self):
        """策略启动"""
        self.log("=" * 40)
        self.log("简单策略启动")
        self.log(f"  订单间隔: 每 {self.order_interval} 条行情")
        self.log("=" * 40)
    
    def on_ticker(self, data: TickerData):
        """
        处理行情
        
        1. 打印行情信息
        2. 定期发送测试订单
        """
        self.tick_count += 1
        
        # 打印行情（每 5 条打印一次）
        if self.tick_count % 5 == 0:
            self.log(
                f"[行情] {data.symbol} | "
                f"价格: {data.last_price:.2f} | "
                f"买一: {data.bid_price:.2f} | "
                f"卖一: {data.ask_price:.2f} | "
                f"价差: {data.spread():.2f}"
            )
        
        # 定期发送订单
        if self.tick_count % self.order_interval == 0:
            # 发送一个远离市价的限价单（不会成交，用于测试）
            test_price = data.bid_price - 1000  # 比市价低 1000
            
            self.log(f"[交易] 发送测试订单 #{self.order_count + 1}")
            order_id = self.buy_limit(
                symbol=data.symbol,
                quantity=0.001,
                price=test_price
            )
            
            if order_id:
                self.order_count += 1
                self.log(f"         订单ID: {order_id}")
                self.log(f"         买入 0.001 @ {test_price:.2f}")
    
    def on_order(self, report: OrderReport):
        """处理订单回报"""
        status_emoji = "✓" if report.is_success() else "✗"
        
        self.log(
            f"[回报] {status_emoji} "
            f"ID: {report.client_order_id} | "
            f"状态: {report.status} | "
            f"交易所ID: {report.exchange_order_id}"
        )
        
        if report.error_msg:
            self.log(f"        错误: {report.error_msg}")
    
    def on_stop(self):
        """策略停止"""
        self.log("=" * 40)
        self.log("简单策略停止")
        self.log(f"  收到行情: {self.tick_count}")
        self.log(f"  发送订单: {self.order_count}")
        self.log("=" * 40)


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  简单策略 - 测试用")
    print("=" * 50)
    print()
    print("这个策略会：")
    print("  1. 打印收到的行情数据")
    print("  2. 每 10 条行情发送一个测试订单")
    print("  3. 打印订单回报")
    print()
    print("确保 C++ 交易服务器 (trading_server) 已启动！")
    print()
    
    # 创建客户端
    client = TradingClient(strategy_id="simple_test")
    
    # 创建策略
    strategy = SimpleStrategy(order_interval=10)
    
    # 运行
    client.run(strategy, log_interval=30)

