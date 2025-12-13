"""
动量策略示例

策略逻辑：
- 跟踪价格的最高点和最低点
- 当价格突破最近的高点时买入
- 当价格跌破最近的低点时卖出

这是一个简单的趋势跟踪策略，适合作为入门示例。

运行方式：
    python momentum_strategy.py

作者: Sequence Team
日期: 2024-12
"""

import sys
import os

# 添加项目路径（确保可以导入 trading_client）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_client import TradingClient, Strategy, TickerData, OrderReport


class MomentumStrategy(Strategy):
    """
    动量策略
    
    核心思想：
    - 价格创新高 → 趋势向上 → 买入
    - 价格创新低 → 趋势向下 → 卖出
    
    参数：
        lookback_period: 观察周期（多少个 tick）
        breakout_threshold: 突破阈值（百分比）
        position_size: 每次交易数量
        max_position: 最大持仓
    """
    
    def __init__(
        self,
        lookback_period: int = 20,
        breakout_threshold: float = 0.001,  # 0.1%
        position_size: float = 0.001,
        max_position: float = 0.01
    ):
        """
        初始化策略
        
        参数：
            lookback_period: 观察窗口大小
            breakout_threshold: 突破阈值（小数形式）
            position_size: 每次交易的数量
            max_position: 最大持仓限制
        """
        super().__init__()
        
        # 策略参数
        self.lookback_period = lookback_period
        self.breakout_threshold = breakout_threshold
        self.position_size = position_size
        self.max_position = max_position
        
        # 状态变量
        self.prices = []                  # 历史价格
        self.high_price = 0.0             # 窗口内最高价
        self.low_price = float('inf')     # 窗口内最低价
        self.position = 0.0               # 当前持仓
        
        # 统计
        self.buy_count = 0
        self.sell_count = 0
    
    def on_start(self):
        """策略启动"""
        self.log("=" * 40)
        self.log("动量策略启动")
        self.log(f"  观察周期: {self.lookback_period}")
        self.log(f"  突破阈值: {self.breakout_threshold * 100:.2f}%")
        self.log(f"  每次数量: {self.position_size}")
        self.log(f"  最大持仓: {self.max_position}")
        self.log("=" * 40)
    
    def on_ticker(self, data: TickerData):
        """
        处理行情
        
        策略逻辑：
        1. 记录历史价格
        2. 计算窗口内的高低点
        3. 判断是否突破
        4. 执行交易
        """
        price = data.last_price
        
        # ========================================
        # 1. 记录历史价格
        # ========================================
        self.prices.append(price)
        
        # 保持窗口大小
        if len(self.prices) > self.lookback_period:
            self.prices.pop(0)
        
        # 窗口还没满，不交易
        if len(self.prices) < self.lookback_period:
            return
        
        # ========================================
        # 2. 计算窗口内的高低点
        # ========================================
        self.high_price = max(self.prices[:-1])  # 不包含当前价格
        self.low_price = min(self.prices[:-1])
        
        # ========================================
        # 3. 判断突破并交易
        # ========================================
        
        # 突破高点 → 买入信号
        breakout_high = self.high_price * (1 + self.breakout_threshold)
        if price > breakout_high and self.position < self.max_position:
            self.log(f"📈 突破高点! 价格: {price:.2f} > {breakout_high:.2f}")
            
            # 买入
            qty = min(self.position_size, self.max_position - self.position)
            order_id = self.buy_limit(data.symbol, qty, data.bid_price)
            
            if order_id:
                self.log(f"   发送买单: {qty} @ {data.bid_price:.2f}")
                self.buy_count += 1
        
        # 跌破低点 → 卖出信号
        breakout_low = self.low_price * (1 - self.breakout_threshold)
        if price < breakout_low and self.position > 0:
            self.log(f"📉 跌破低点! 价格: {price:.2f} < {breakout_low:.2f}")
            
            # 卖出
            qty = min(self.position_size, self.position)
            order_id = self.sell_limit(data.symbol, qty, data.ask_price)
            
            if order_id:
                self.log(f"   发送卖单: {qty} @ {data.ask_price:.2f}")
                self.sell_count += 1
    
    def on_order(self, report: OrderReport):
        """
        处理订单回报
        
        更新持仓状态
        """
        if report.is_success():
            # 根据订单方向更新持仓
            # 这里简化处理，实际应该根据订单详情
            self.log(f"✓ 订单成功 | ID: {report.exchange_order_id} | 状态: {report.status}")
            
            # 模拟持仓更新
            if "buy" in report.client_order_id.lower() or self.buy_count > self.sell_count:
                self.position += report.filled_quantity if report.filled_quantity > 0 else self.position_size
            else:
                self.position -= report.filled_quantity if report.filled_quantity > 0 else self.position_size
                self.position = max(0, self.position)
            
            self.log(f"   当前持仓: {self.position}")
        else:
            self.log(f"✗ 订单失败 | 错误: {report.error_msg}")
    
    def on_stop(self):
        """策略停止"""
        self.log("=" * 40)
        self.log("动量策略停止")
        self.log(f"  买入次数: {self.buy_count}")
        self.log(f"  卖出次数: {self.sell_count}")
        self.log(f"  最终持仓: {self.position}")
        self.log("=" * 40)


# ============================================================
# 主程序
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  动量策略客户端")
    print("=" * 50)
    print()
    print("确保 C++ 交易服务器 (trading_server) 已启动！")
    print()
    
    # 创建客户端
    # strategy_id 用于识别订单来源，每个策略应该有唯一的 ID
    client = TradingClient(strategy_id="momentum_btc")
    
    # 创建策略
    strategy = MomentumStrategy(
        lookback_period=20,       # 20 个 tick 的观察窗口
        breakout_threshold=0.001, # 0.1% 的突破阈值
        position_size=0.001,      # 每次交易 0.001 BTC
        max_position=0.01         # 最大持仓 0.01 BTC
    )
    
    # 运行策略
    # 这会阻塞直到按 Ctrl+C
    client.run(strategy, log_interval=30)

