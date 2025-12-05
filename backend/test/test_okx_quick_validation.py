"""
OKX WebSocket 快速验证测试
快速测试K线和交易频道的连接和订阅功能（每个测试只运行10-15秒）
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx import OKXWebSocketPublic
from core import EventEngine, KlineData, TradeData
from adapters.okx.adapter import OKXMarketDataAdapter


async def test_candles_quick():
    """快速测试K线频道"""
    print("\n" + "="*80)
    print("📋 测试1: K线频道快速验证（15秒）")
    print("="*80)
    
    ws = OKXWebSocketPublic(is_demo=True, url_type="business")
    
    print("\n✅ 创建WebSocket客户端（business端点）")
    
    await ws.connect()
    print("✅ WebSocket连接成功")
    
    message_count = [0]
    
    def callback(message):
        message_count[0] += 1
        if 'data' in message and message_count[0] <= 3:
            data = message['data'][0]
            print(f"   收到K线数据: O={data[1]}, H={data[2]}, L={data[3]}, C={data[4]}")
    
    await ws.subscribe_candles("BTC-USDT", interval="1m", callback=callback)
    print("✅ 订阅成功: BTC-USDT 1分钟K线")
    
    print("\n⏳ 等待15秒接收数据...")
    await asyncio.sleep(15)
    
    print(f"\n✅ 共收到 {message_count[0]} 条K线数据")
    
    await ws.unsubscribe_candles("BTC-USDT", interval="1m")
    await ws.disconnect()
    print("✅ 测试完成")
    
    return message_count[0] > 0


async def test_trades_quick():
    """快速测试交易频道"""
    print("\n" + "="*80)
    print("📋 测试2: 交易频道快速验证（10秒）")
    print("="*80)
    
    ws = OKXWebSocketPublic(is_demo=True)
    
    print("\n✅ 创建WebSocket客户端")
    
    await ws.connect()
    print("✅ WebSocket连接成功")
    
    trade_count = [0]
    
    def callback(message):
        if 'data' in message:
            for data in message['data']:
                trade_count[0] += 1
                if trade_count[0] <= 5:
                    print(f"   交易: {data['side']} {data['sz']} @ {data['px']}")
    
    await ws.subscribe_trades("BTC-USDT", callback=callback)
    print("✅ 订阅成功: BTC-USDT 交易数据")
    
    print("\n⏳ 等待10秒接收数据...")
    await asyncio.sleep(10)
    
    print(f"\n✅ 共收到 {trade_count[0]} 笔交易")
    
    await ws.unsubscribe_trades("BTC-USDT")
    await ws.disconnect()
    print("✅ 测试完成")
    
    return trade_count[0] > 0


async def test_adapter_quick():
    """快速测试适配器"""
    print("\n" + "="*80)
    print("📋 测试3: 适配器集成快速验证（15秒）")
    print("="*80)
    
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    print("\n✅ 创建EventEngine和适配器")
    
    event_counts = {'kline': 0, 'trade': 0}
    
    def on_kline(event: KlineData):
        event_counts['kline'] += 1
        if event_counts['kline'] <= 3:
            print(f"   📊 KlineData: {event.symbol} {event.interval} C={event.close}")
    
    def on_trade(event: TradeData):
        event_counts['trade'] += 1
        if event_counts['trade'] <= 5:
            print(f"   💰 TradeData: {event.symbol} {event.side} {event.quantity} @ {event.price}")
    
    engine.register(KlineData, on_kline)
    engine.register(TradeData, on_trade)
    
    await adapter.start()
    print("✅ 适配器启动成功")
    
    await adapter.subscribe_candles("BTC-USDT", interval="1m")
    print("✅ 订阅K线: BTC-USDT 1m")
    
    await adapter.subscribe_trades("BTC-USDT")
    print("✅ 订阅交易: BTC-USDT")
    
    print("\n⏳ 等待15秒接收事件...")
    await asyncio.sleep(15)
    
    print(f"\n✅ 收到事件: KlineData={event_counts['kline']}, TradeData={event_counts['trade']}")
    
    await adapter.stop()
    print("✅ 测试完成")
    
    return event_counts['kline'] > 0 and event_counts['trade'] > 0


async def main():
    """主测试函数"""
    print("\n" + "🚀"*40)
    print("OKX WebSocket 快速验证测试")
    print("🚀"*40)
    
    results = {}
    
    try:
        results['candles'] = await test_candles_quick()
    except Exception as e:
        print(f"\n❌ K线测试失败: {e}")
        results['candles'] = False
    
    try:
        results['trades'] = await test_trades_quick()
    except Exception as e:
        print(f"\n❌ 交易测试失败: {e}")
        results['trades'] = False
    
    try:
        results['adapter'] = await test_adapter_quick()
    except Exception as e:
        print(f"\n❌ 适配器测试失败: {e}")
        results['adapter'] = False
    
    # 汇总结果
    print("\n" + "="*80)
    print("📊 测试结果汇总")
    print("="*80)
    
    print("\n测试结果:")
    print(f"   K线频道           : {'✅ 通过' if results['candles'] else '❌ 失败'}")
    print(f"   交易频道           : {'✅ 通过' if results['trades'] else '❌ 失败'}")
    print(f"   适配器集成         : {'✅ 通过' if results['adapter'] else '❌ 失败'}")
    
    passed = sum(results.values())
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
    
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

