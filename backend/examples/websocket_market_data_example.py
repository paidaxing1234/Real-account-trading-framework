"""
OKX WebSocket 行情数据使用示例

展示如何使用WebSocket获取实时行情数据，并通过EventEngine分发给多个策略组件
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import EventEngine, TickerData
from adapters.okx import OKXMarketDataAdapter


class SimpleStrategy:
    """
    简单策略示例
    监控BTC价格，在特定条件下产生交易信号
    """
    
    def __init__(self, name: str):
        self.name = name
        self.last_price = None
        self.buy_threshold = 90000  # 买入阈值
        self.sell_threshold = 100000  # 卖出阈值
    
    def on_ticker(self, event: TickerData):
        """处理行情数据"""
        if event.symbol != "BTC-USDT":
            return
        
        current_price = event.last_price
        
        # 打印行情
        print(f"[{self.name}] BTC价格: {current_price:.2f} USDT")
        
        # 交易信号
        if current_price < self.buy_threshold:
            print(f"  └─> 🔵 买入信号！价格低于{self.buy_threshold}")
        elif current_price > self.sell_threshold:
            print(f"  └─> 🔴 卖出信号！价格高于{self.sell_threshold}")
        
        # 价格变化
        if self.last_price:
            change = current_price - self.last_price
            change_pct = (change / self.last_price) * 100
            if abs(change_pct) > 0.1:  # 变化超过0.1%
                direction = "📈" if change > 0 else "📉"
                print(f"  └─> {direction} 价格变化: {change:+.2f} ({change_pct:+.2f}%)")
        
        self.last_price = current_price


class PriceMonitor:
    """
    价格监控组件
    记录24h高低价，计算波动率
    """
    
    def __init__(self):
        self.prices = {}
        self.count = 0
    
    def on_ticker(self, event: TickerData):
        """处理行情数据"""
        symbol = event.symbol
        
        if symbol not in self.prices:
            self.prices[symbol] = {
                'high': event.last_price,
                'low': event.last_price,
                'count': 0
            }
        
        # 更新统计
        info = self.prices[symbol]
        info['high'] = max(info['high'], event.last_price)
        info['low'] = min(info['low'], event.last_price)
        info['count'] += 1
        
        self.count += 1
        
        # 每100次更新打印统计
        if self.count % 100 == 0:
            print(f"\n📊 [{symbol}] 统计信息:")
            print(f"   最高价: {info['high']:.2f}")
            print(f"   最低价: {info['low']:.2f}")
            print(f"   波动幅度: {info['high'] - info['low']:.2f}")
            print(f"   更新次数: {info['count']}")
            print(f"   24h成交量: {event.volume_24h}")
            print()


class DataRecorder:
    """
    数据记录组件
    可选：将数据保存到文件或数据库
    """
    
    def __init__(self, filename="market_data.csv"):
        self.filename = filename
        self.buffer = []
        self.buffer_size = 100
        
        # 创建文件并写入表头
        with open(self.filename, 'w') as f:
            f.write("timestamp,symbol,last_price,bid_price,ask_price,volume_24h\n")
    
    def on_ticker(self, event: TickerData):
        """记录行情数据"""
        # 添加到缓冲区
        self.buffer.append({
            'timestamp': event.timestamp,
            'symbol': event.symbol,
            'last_price': event.last_price,
            'bid_price': event.bid_price,
            'ask_price': event.ask_price,
            'volume_24h': event.volume_24h
        })
        
        # 缓冲区满时写入文件
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def flush(self):
        """将缓冲区数据写入文件"""
        if not self.buffer:
            return
        
        with open(self.filename, 'a') as f:
            for data in self.buffer:
                f.write(f"{data['timestamp']},{data['symbol']},{data['last_price']},"
                       f"{data['bid_price']},{data['ask_price']},{data['volume_24h']}\n")
        
        print(f"💾 已保存 {len(self.buffer)} 条数据到 {self.filename}")
        self.buffer.clear()


async def example_basic():
    """示例1: 基础使用 - 单个策略"""
    print("\n" + "="*80)
    print("示例1: 基础使用 - 单个策略")
    print("="*80)
    
    # 创建事件引擎
    engine = EventEngine()
    
    # 创建适配器
    adapter = OKXMarketDataAdapter(
        event_engine=engine,
        is_demo=True  # 使用模拟盘
    )
    
    # 创建策略
    strategy = SimpleStrategy(name="策略A")
    
    # 注册事件监听
    engine.register(TickerData, strategy.on_ticker)
    
    # 启动适配器
    print("\n🚀 启动适配器...")
    await adapter.start()
    
    # 订阅行情
    print("📡 订阅BTC-USDT行情...")
    await adapter.subscribe_ticker("BTC-USDT")
    
    # 运行60秒
    print("⏳ 运行60秒...\n")
    await asyncio.sleep(60)
    
    # 停止
    print("\n🛑 停止适配器...")
    await adapter.stop()
    
    print("✅ 示例1完成\n")


async def example_multiple_strategies():
    """示例2: 多策略系统"""
    print("\n" + "="*80)
    print("示例2: 多策略系统 - 多个组件同时工作")
    print("="*80)
    
    # 创建事件引擎
    engine = EventEngine()
    
    # 创建适配器
    adapter = OKXMarketDataAdapter(
        event_engine=engine,
        is_demo=True
    )
    
    # 创建多个组件
    strategy1 = SimpleStrategy(name="策略A")
    strategy2 = SimpleStrategy(name="策略B")
    strategy2.buy_threshold = 85000  # 不同的阈值
    strategy2.sell_threshold = 105000
    
    monitor = PriceMonitor()
    recorder = DataRecorder("btc_market_data.csv")
    
    # 注册所有监听器
    engine.register(TickerData, strategy1.on_ticker)
    engine.register(TickerData, strategy2.on_ticker)
    engine.register(TickerData, monitor.on_ticker)
    engine.register(TickerData, recorder.on_ticker)
    
    # 启动
    print("\n🚀 启动适配器...")
    await adapter.start()
    
    # 订阅多个产品
    print("📡 订阅行情...")
    await adapter.subscribe_ticker("BTC-USDT")
    await adapter.subscribe_ticker("ETH-USDT")
    
    # 运行120秒
    print("⏳ 运行120秒...\n")
    await asyncio.sleep(120)
    
    # 保存剩余数据
    recorder.flush()
    
    # 停止
    print("\n🛑 停止适配器...")
    await adapter.stop()
    
    print("✅ 示例2完成\n")


async def example_dynamic_subscription():
    """示例3: 动态订阅管理"""
    print("\n" + "="*80)
    print("示例3: 动态订阅管理")
    print("="*80)
    
    # 创建事件引擎和适配器
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    # 简单的打印回调
    def on_ticker(event: TickerData):
        print(f"📊 {event.symbol}: {event.last_price:.2f}")
    
    engine.register(TickerData, on_ticker)
    
    # 启动
    await adapter.start()
    
    # 第一阶段：订阅BTC
    print("\n📡 第一阶段：订阅BTC-USDT")
    await adapter.subscribe_ticker("BTC-USDT")
    await asyncio.sleep(20)
    
    # 第二阶段：添加ETH
    print("\n📡 第二阶段：添加ETH-USDT")
    await adapter.subscribe_ticker("ETH-USDT")
    await asyncio.sleep(20)
    
    # 第三阶段：取消BTC
    print("\n📡 第三阶段：取消BTC-USDT订阅")
    await adapter.unsubscribe_ticker("BTC-USDT")
    await asyncio.sleep(20)
    
    # 停止
    await adapter.stop()
    
    print("✅ 示例3完成\n")


async def main():
    """主函数"""
    print("\n" + "🚀"*40)
    print("OKX WebSocket 行情数据使用示例")
    print("🚀"*40)
    
    # 运行示例（根据需要选择）
    
    # 示例1: 基础使用
    await example_basic()
    
    # 示例2: 多策略系统（需要更多时间）
    # await example_multiple_strategies()
    
    # 示例3: 动态订阅
    # await example_dynamic_subscription()
    
    print("\n" + "="*80)
    print("所有示例完成！")
    print("="*80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

