"""
核心组件使用演示
展示如何使用EventEngine、Order、Data等核心组件
"""

from core import (
    EventEngine, Component,
    Order, OrderSide, OrderState,
    TickerData
)


class SimpleStrategy(Component):
    """简单策略示例"""
    
    def __init__(self):
        self.position = 0  # 当前持仓
        self.order_count = 0
    
    def start(self, engine: EventEngine):
        """启动策略，注册监听器"""
        self.engine = engine
        print("📈 策略启动")
        
        # 监听行情数据
        engine.register(TickerData, self.on_ticker)
        # 监听订单更新
        engine.register(Order, self.on_order)
    
    def on_ticker(self, ticker: TickerData):
        """收到行情数据"""
        print(f"\n📊 收到行情: {ticker.symbol} 价格={ticker.last_price}")
        
        # 简单策略：如果没有持仓且价格低于50000，买入
        if self.position == 0 and ticker.last_price < 50000:
            print("💡 策略判断: 价格低于50000，发出买入订单")
            order = Order.buy_limit(
                symbol=ticker.symbol,
                quantity=0.01,
                price=ticker.last_price
            )
            order.state = OrderState.SUBMITTED
            self.engine.put(order)  # 推送订单事件
            self.order_count += 1
    
    def on_order(self, order: Order):
        """收到订单更新"""
        if order.state == OrderState.FILLED:
            print(f"✅ 订单成交: {order}")
            # 更新持仓
            if order.is_buy:
                self.position += order.filled_quantity
            else:
                self.position -= order.filled_quantity
            print(f"📦 当前持仓: {self.position}")
    
    def stop(self):
        """停止策略"""
        print(f"\n🛑 策略停止，共发出{self.order_count}个订单")


class OrderManager(Component):
    """订单管理器示例"""
    
    def __init__(self):
        self.orders = {}  # 订单字典
    
    def start(self, engine: EventEngine):
        """启动订单管理器"""
        self.engine = engine
        print("📋 订单管理器启动")
        
        # 监听订单事件
        engine.register(Order, self.on_order)
    
    def on_order(self, order: Order):
        """处理订单"""
        # 模拟订单流转
        if order.state == OrderState.SUBMITTED:
            print(f"📤 订单管理器: 收到新订单 {order.client_order_id}")
            
            # 模拟发送到交易所
            print(f"🔄 订单管理器: 正在发送到交易所...")
            
            # 模拟交易所接受
            order_copy = order.derive()
            order_copy.state = OrderState.ACCEPTED
            order_copy.exchange_order_id = f"OKX-{order.order_id}"
            self.engine.put(order_copy)
            
            # 存储订单
            self.orders[order.order_id] = order
        
        elif order.state == OrderState.ACCEPTED:
            print(f"✓ 订单管理器: 交易所已接受订单 {order.exchange_order_id}")
            
            # 模拟立即成交
            order_copy = order.derive()
            order_copy.state = OrderState.FILLED
            order_copy.filled_quantity = order.quantity
            order_copy.filled_price = order.price
            order_copy.fee = order.quantity * order.price * 0.0002  # 0.02%手续费
            self.engine.put(order_copy)
        
        elif order.state == OrderState.FILLED:
            print(f"💰 订单管理器: 订单完全成交 {order.exchange_order_id}")
    
    def stop(self):
        """停止订单管理器"""
        print(f"\n📋 订单管理器停止，共处理{len(self.orders)}个订单")


class DataRecorder(Component):
    """数据记录器示例"""
    
    def __init__(self):
        self.ticker_count = 0
        self.order_count = 0
    
    def start(self, engine: EventEngine):
        """启动记录器"""
        self.engine = engine
        print("📝 数据记录器启动")
        
        # 全局监听所有事件（用于日志记录）
        engine.global_register(self.on_any_event, is_senior=False)
    
    def on_any_event(self, event):
        """记录所有事件"""
        if isinstance(event, TickerData):
            self.ticker_count += 1
        elif isinstance(event, Order):
            self.order_count += 1
    
    def stop(self):
        """停止记录器"""
        print(f"\n📝 数据记录器停止")
        print(f"   - 记录了 {self.ticker_count} 个行情事件")
        print(f"   - 记录了 {self.order_count} 个订单事件")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 核心组件演示")
    print("=" * 60)
    
    # 1. 创建事件引擎
    print("\n1️⃣ 创建事件引擎...")
    engine = EventEngine()
    
    # 2. 创建并启动组件
    print("\n2️⃣ 启动组件...")
    strategy = SimpleStrategy()
    order_manager = OrderManager()
    recorder = DataRecorder()
    
    strategy.start(engine)
    order_manager.start(engine)
    recorder.start(engine)
    
    # 3. 模拟推送行情数据
    print("\n" + "=" * 60)
    print("3️⃣ 开始推送行情数据...")
    print("=" * 60)
    
    # 推送第一个行情（价格49800，触发买入）
    ticker1 = TickerData(
        symbol="BTC-USDT-SWAP",
        last_price=49800,
        bid_price=49799,
        ask_price=49801,
        timestamp=1000
    )
    engine.put(ticker1)
    
    # 推送第二个行情（价格50200，不触发交易）
    ticker2 = TickerData(
        symbol="BTC-USDT-SWAP",
        last_price=50200,
        bid_price=50199,
        ask_price=50201,
        timestamp=2000
    )
    engine.put(ticker2)
    
    # 4. 停止所有组件
    print("\n" + "=" * 60)
    print("4️⃣ 停止所有组件...")
    print("=" * 60)
    
    strategy.stop()
    order_manager.stop()
    recorder.stop()
    
    print("\n" + "=" * 60)
    print("✅ 演示完成！")
    print("=" * 60)
    
    print("\n💡 关键概念总结:")
    print("   1. EventEngine: 事件引擎，负责事件分发")
    print("   2. Component: 组件基类，所有模块都继承它")
    print("   3. Event子类: Order和TickerData都是Event")
    print("   4. 事件驱动: 组件通过事件通信，不直接调用")
    print("   5. 解耦设计: 可以随时添加/删除组件")


if __name__ == "__main__":
    main()

