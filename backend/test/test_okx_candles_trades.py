"""
OKX WebSocket K线和交易频道测试
测试：K线数据订阅、交易数据订阅
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx import OKXWebSocketPublic
from core import EventEngine, KlineData, TradeData
from adapters.okx.adapter import OKXMarketDataAdapter


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


async def test_candles_websocket():
    """测试K线频道"""
    print_section("测试1: K线频道订阅")
    
    print("\n📝 测试1.1: 创建WebSocket客户端（business端点）...")
    ws = OKXWebSocketPublic(is_demo=True, url_type="business")
    
    print("\n📝 测试1.2: 建立连接...")
    await ws.connect()
    await asyncio.sleep(1)
    
    print("\n📝 测试1.3: 订阅BTC-USDT 1分钟K线...")
    
    message_count = [0]
    received_data = []
    
    def callback(message):
        message_count[0] += 1
        received_data.append(message)
        
        if 'data' in message:
            data = message['data'][0]
            print(f"\n📊 收到K线数据 #{message_count[0]}:")
            print(f"   产品: {message['arg']['instId']}")
            print(f"   间隔: {message['arg']['channel']}")
            print(f"   时间: {data[0]}")
            print(f"   开: {data[1]}, 高: {data[2]}, 低: {data[3]}, 收: {data[4]}")
            print(f"   成交量: {data[5]}")
            print(f"   状态: {'完结' if data[8] == '1' else '未完结'}")
    
    await ws.subscribe_candles("BTC-USDT", interval="1m", callback=callback)
    
    print("\n⏳ 等待90秒接收K线数据（至少会收到1根完整K线）...")
    await asyncio.sleep(90)
    
    print(f"\n✅ 共收到 {message_count[0]} 条K线数据")
    
    print("\n📝 测试1.4: 取消订阅...")
    await ws.unsubscribe_candles("BTC-USDT", interval="1m")
    await asyncio.sleep(2)
    
    print("\n📝 测试1.5: 断开连接...")
    await ws.disconnect()
    
    return message_count[0] > 0


async def test_trades_websocket():
    """测试交易频道"""
    print_section("测试2: 交易频道订阅")
    
    print("\n📝 测试2.1: 创建WebSocket客户端...")
    ws = OKXWebSocketPublic(is_demo=True)
    
    await ws.connect()
    await asyncio.sleep(1)
    
    print("\n📝 测试2.2: 订阅BTC-USDT交易数据...")
    
    message_count = [0]
    trade_count = [0]
    
    def callback(message):
        message_count[0] += 1
        
        if 'data' in message:
            for data in message['data']:
                trade_count[0] += 1
                if trade_count[0] <= 5:  # 只打印前5条
                    print(f"\n💰 交易 #{trade_count[0]}:")
                    print(f"   产品: {data['instId']}")
                    print(f"   交易ID: {data['tradeId']}")
                    print(f"   价格: {data['px']}")
                    print(f"   数量: {data['sz']}")
                    print(f"   方向: {'买入' if data['side'] == 'buy' else '卖出'}")
                    print(f"   聚合数: {data.get('count', '1')}")
                    print(f"   时间: {data['ts']}")
    
    await ws.subscribe_trades("BTC-USDT", callback=callback)
    
    print("\n⏳ 等待15秒接收交易数据...")
    await asyncio.sleep(15)
    
    print(f"\n✅ 共收到 {message_count[0]} 个消息推送，包含 {trade_count[0]} 笔交易")
    
    print("\n📝 测试2.3: 取消订阅...")
    await ws.unsubscribe_trades("BTC-USDT")
    await asyncio.sleep(2)
    
    print("\n📝 测试2.4: 断开连接...")
    await ws.disconnect()
    
    return trade_count[0] > 0


async def test_adapter_candles():
    """测试适配器K线数据"""
    print_section("测试3: 适配器K线数据集成")
    
    print("\n📝 测试3.1: 创建EventEngine和适配器...")
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    print("\n📝 测试3.2: 启动适配器...")
    await adapter.start()
    await asyncio.sleep(1)
    
    print("\n📝 测试3.3: 订阅K线数据...")
    await adapter.subscribe_candles("BTC-USDT", interval="1m")
    
    kline_count = [0]
    
    def on_kline(event: KlineData):
        kline_count[0] += 1
        print(f"\n📊 收到KlineData事件 #{kline_count[0]}:")
        print(f"   交易所: {event.exchange}")
        print(f"   产品: {event.symbol}")
        print(f"   间隔: {event.interval}")
        print(f"   开: {event.open}, 高: {event.high}, 低: {event.low}, 收: {event.close}")
        print(f"   成交量: {event.volume}")
        print(f"   时间戳: {event.timestamp}")
    
    engine.register(KlineData, on_kline)
    
    print("\n⏳ 等待90秒接收K线事件...")
    await asyncio.sleep(90)
    
    print(f"\n✅ EventEngine共分发 {kline_count[0]} 个KlineData事件")
    
    print("\n📝 测试3.4: 停止适配器...")
    await adapter.stop()
    
    return kline_count[0] > 0


async def test_adapter_trades():
    """测试适配器交易数据"""
    print_section("测试4: 适配器交易数据集成")
    
    print("\n📝 测试4.1: 创建EventEngine和适配器...")
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    print("\n📝 测试4.2: 启动适配器...")
    await adapter.start()
    await asyncio.sleep(1)
    
    print("\n📝 测试4.3: 订阅交易数据...")
    await adapter.subscribe_trades("BTC-USDT")
    
    trade_count = [0]
    
    def on_trade(event: TradeData):
        trade_count[0] += 1
        if trade_count[0] <= 5:  # 只打印前5条
            print(f"\n💰 收到TradeData事件 #{trade_count[0]}:")
            print(f"   交易所: {event.exchange}")
            print(f"   产品: {event.symbol}")
            print(f"   交易ID: {event.trade_id}")
            print(f"   价格: {event.price}")
            print(f"   数量: {event.quantity}")
            print(f"   方向: {event.side}")
    
    engine.register(TradeData, on_trade)
    
    print("\n⏳ 等待15秒接收交易事件...")
    await asyncio.sleep(15)
    
    print(f"\n✅ EventEngine共分发 {trade_count[0]} 个TradeData事件")
    
    print("\n📝 测试4.4: 停止适配器...")
    await adapter.stop()
    
    return trade_count[0] > 0


async def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX WebSocket K线和交易频道测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: K线频道
    try:
        results['candles_websocket'] = await test_candles_websocket()
    except Exception as e:
        print(f"❌ 测试1失败: {e}")
        import traceback
        traceback.print_exc()
        results['candles_websocket'] = False
    
    # 测试2: 交易频道
    try:
        results['trades_websocket'] = await test_trades_websocket()
    except Exception as e:
        print(f"❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
        results['trades_websocket'] = False
    
    # 测试3: 适配器K线数据
    try:
        results['adapter_candles'] = await test_adapter_candles()
    except Exception as e:
        print(f"❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
        results['adapter_candles'] = False
    
    # 测试4: 适配器交易数据
    try:
        results['adapter_trades'] = await test_adapter_trades()
    except Exception as e:
        print(f"❌ 测试4失败: {e}")
        import traceback
        traceback.print_exc()
        results['adapter_trades'] = False
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n测试结果:")
    test_names = {
        'candles_websocket': 'K线频道WebSocket',
        'trades_websocket': '交易频道WebSocket',
        'adapter_candles': '适配器K线数据集成',
        'adapter_trades': '适配器交易数据集成'
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

