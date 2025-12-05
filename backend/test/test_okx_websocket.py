"""
OKX WebSocket 行情接口测试
测试：公共频道行情数据订阅和接收
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx import OKXWebSocketPublic
from core import EventEngine, TickerData
from adapters.okx.adapter import OKXMarketDataAdapter


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


async def test_websocket_basic():
    """测试基础WebSocket连接和订阅"""
    print_section("测试1: 基础WebSocket连接和订阅")
    
    print("\n📝 测试1.1: 创建WebSocket客户端...")
    ws = OKXWebSocketPublic(is_demo=True)
    
    print("\n📝 测试1.2: 建立连接...")
    await ws.connect()
    
    # 等待连接稳定
    await asyncio.sleep(1)
    
    print("\n📝 测试1.3: 订阅BTC-USDT行情...")
    
    # 消息计数器
    message_count = [0]
    received_data = []
    
    def callback(message):
        message_count[0] += 1
        received_data.append(message)
        
        if 'data' in message:
            data = message['data'][0]
            print(f"\n💰 收到行情数据 #{message_count[0]}:")
            print(f"   产品: {data['instId']}")
            print(f"   最新价: {data['last']}")
            print(f"   买一价: {data['bidPx']}")
            print(f"   卖一价: {data['askPx']}")
            print(f"   24h成交量: {data['vol24h']}")
            print(f"   时间戳: {data['ts']}")
    
    await ws.subscribe_tickers("BTC-USDT", callback=callback)
    
    print("\n⏳ 等待15秒接收行情数据...")
    await asyncio.sleep(15)
    
    print(f"\n✅ 共收到 {message_count[0]} 条行情数据")
    
    print("\n📝 测试1.4: 取消订阅...")
    await ws.unsubscribe_tickers("BTC-USDT")
    
    await asyncio.sleep(2)
    
    print("\n📝 测试1.5: 断开连接...")
    await ws.disconnect()
    
    print(f"\n✅ 测试完成")
    
    return message_count[0] > 0


async def test_multiple_subscriptions():
    """测试多个订阅"""
    print_section("测试2: 多个产品订阅")
    
    print("\n📝 测试2.1: 创建WebSocket客户端...")
    ws = OKXWebSocketPublic(is_demo=True)
    
    await ws.connect()
    await asyncio.sleep(1)
    
    print("\n📝 测试2.2: 订阅多个产品行情...")
    
    message_counts = {
        "BTC-USDT": 0,
        "ETH-USDT": 0
    }
    
    def create_callback(symbol):
        def callback(message):
            if 'data' in message:
                message_counts[symbol] += 1
                data = message['data'][0]
                print(f"💰 {symbol}: 最新价={data['last']}, 数量={message_counts[symbol]}")
        return callback
    
    # 订阅BTC-USDT
    await ws.subscribe_tickers("BTC-USDT", callback=create_callback("BTC-USDT"))
    
    # 订阅ETH-USDT
    await ws.subscribe_tickers("ETH-USDT", callback=create_callback("ETH-USDT"))
    
    print("\n⏳ 等待15秒接收行情数据...")
    await asyncio.sleep(15)
    
    print(f"\n✅ BTC-USDT: 收到 {message_counts['BTC-USDT']} 条数据")
    print(f"✅ ETH-USDT: 收到 {message_counts['ETH-USDT']} 条数据")
    
    await ws.disconnect()
    
    return all(count > 0 for count in message_counts.values())


async def test_adapter():
    """测试适配器（与EventEngine集成）"""
    print_section("测试3: 适配器与EventEngine集成")
    
    print("\n📝 测试3.1: 创建EventEngine...")
    event_engine = EventEngine()
    
    print("\n📝 测试3.2: 创建OKXMarketDataAdapter...")
    adapter = OKXMarketDataAdapter(
        event_engine=event_engine,
        is_demo=True
    )
    
    print("\n📝 测试3.3: 启动适配器...")
    await adapter.start()
    
    await asyncio.sleep(1)
    
    print("\n📝 测试3.4: 订阅BTC-USDT行情...")
    await adapter.subscribe_ticker("BTC-USDT")
    
    # 注册事件监听器
    ticker_count = [0]
    
    def on_ticker(event: TickerData):
        ticker_count[0] += 1
        print(f"\n📊 收到TickerData事件 #{ticker_count[0]}:")
        print(f"   交易所: {event.exchange}")
        print(f"   产品: {event.symbol}")
        print(f"   最新价: {event.last_price}")
        print(f"   买一价: {event.bid_price}")
        print(f"   卖一价: {event.ask_price}")
        print(f"   24h成交量: {event.volume_24h}")
    
    event_engine.register(TickerData, on_ticker)
    
    print("\n⏳ 等待15秒接收事件...")
    await asyncio.sleep(15)
    
    print(f"\n✅ EventEngine共分发 {ticker_count[0]} 个TickerData事件")
    
    print("\n📝 测试3.5: 取消订阅...")
    await adapter.unsubscribe_ticker("BTC-USDT")
    
    await asyncio.sleep(2)
    
    print("\n📝 测试3.6: 停止适配器...")
    await adapter.stop()
    
    return ticker_count[0] > 0


async def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX WebSocket 行情接口测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: 基础WebSocket连接和订阅
    try:
        results['basic_websocket'] = await test_websocket_basic()
    except Exception as e:
        print(f"❌ 测试1失败: {e}")
        import traceback
        traceback.print_exc()
        results['basic_websocket'] = False
    
    # 测试2: 多个订阅
    try:
        results['multiple_subscriptions'] = await test_multiple_subscriptions()
    except Exception as e:
        print(f"❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
        results['multiple_subscriptions'] = False
    
    # 测试3: 适配器与EventEngine集成
    try:
        results['adapter_integration'] = await test_adapter()
    except Exception as e:
        print(f"❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
        results['adapter_integration'] = False
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n测试结果:")
    test_names = {
        'basic_websocket': 'WebSocket基础连接和订阅',
        'multiple_subscriptions': '多产品订阅',
        'adapter_integration': '适配器与EventEngine集成'
    }
    
    for test_key, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_names[test_key]:30s} : {status}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

