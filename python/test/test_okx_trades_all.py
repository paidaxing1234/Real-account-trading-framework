"""
OKX WebSocket 全部交易频道测试
测试：trades-all频道（每次仅一条成交记录）
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx import OKXWebSocketPublic
from core import EventEngine, TradeData
from adapters.okx.adapter import OKXMarketDataAdapter


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 80)
    print(f"📋 {title}")
    print("=" * 80)


async def test_trades_all_websocket():
    """测试trades-all频道（WebSocket直接使用）"""
    print_section("测试1: Trades-All频道 WebSocket直接测试")
    
    print("\n📝 测试1.1: 创建WebSocket客户端（business端点）...")
    ws = OKXWebSocketPublic(is_demo=True, url_type="business")
    
    print("\n📝 测试1.2: 建立连接...")
    await ws.connect()
    await asyncio.sleep(1)
    
    print("\n📝 测试1.3: 订阅BTC-USDT全部交易数据...")
    
    trade_count = [0]
    received_data = []
    
    def callback(message):
        if 'data' in message:
            for data in message['data']:
                trade_count[0] += 1
                received_data.append(data)
                
                # 只打印前10条
                if trade_count[0] <= 10:
                    print(f"\n💰 交易 #{trade_count[0]}:")
                    print(f"   产品: {data['instId']}")
                    print(f"   交易ID: {data['tradeId']}")
                    print(f"   价格: {data['px']}")
                    print(f"   数量: {data['sz']}")
                    print(f"   方向: {data['side']}")
                    print(f"   来源: {'普通订单' if data['source'] == '0' else '流动性增强计划'}")
                    print(f"   时间: {data['ts']}")
    
    await ws.subscribe_trades_all("BTC-USDT", callback=callback)
    
    print("\n⏳ 等待30秒接收交易数据...")
    await asyncio.sleep(30)
    
    print(f"\n✅ 共收到 {trade_count[0]} 笔交易")
    
    # 验证数据特征
    if trade_count[0] > 0:
        print(f"\n📊 数据统计:")
        buy_count = sum(1 for d in received_data if d['side'] == 'buy')
        sell_count = sum(1 for d in received_data if d['side'] == 'sell')
        print(f"   买入: {buy_count} 笔 ({buy_count/trade_count[0]*100:.1f}%)")
        print(f"   卖出: {sell_count} 笔 ({sell_count/trade_count[0]*100:.1f}%)")
    
    print("\n📝 测试1.4: 取消订阅...")
    await ws.unsubscribe_trades_all("BTC-USDT")
    await asyncio.sleep(2)
    
    print("\n📝 测试1.5: 断开连接...")
    await ws.disconnect()
    
    return trade_count[0] > 0


async def test_trades_all_adapter():
    """测试适配器trades-all功能"""
    print_section("测试2: Trades-All适配器集成测试")
    
    print("\n📝 测试2.1: 创建EventEngine和适配器...")
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    print("\n📝 测试2.2: 启动适配器...")
    await adapter.start()
    await asyncio.sleep(1)
    
    print("\n📝 测试2.3: 订阅全部交易数据...")
    await adapter.subscribe_trades_all("BTC-USDT")
    
    trade_count = [0]
    buy_count = [0]
    sell_count = [0]
    
    def on_trade(event: TradeData):
        trade_count[0] += 1
        
        if event.side == 'buy':
            buy_count[0] += 1
        else:
            sell_count[0] += 1
        
        # 只打印前10条
        if trade_count[0] <= 10:
            direction = "买入" if event.side == "buy" else "卖出"
            print(f"\n💰 收到TradeData事件 #{trade_count[0]}:")
            print(f"   交易所: {event.exchange}")
            print(f"   产品: {event.symbol}")
            print(f"   交易ID: {event.trade_id}")
            print(f"   价格: {event.price}")
            print(f"   数量: {event.quantity}")
            print(f"   方向: {direction}")
    
    engine.register(TradeData, on_trade)
    
    print("\n⏳ 等待30秒接收TradeData事件...")
    await asyncio.sleep(30)
    
    print(f"\n✅ EventEngine共分发 {trade_count[0]} 个TradeData事件")
    
    if trade_count[0] > 0:
        print(f"\n📊 交易统计:")
        print(f"   买入: {buy_count[0]} 笔 ({buy_count[0]/trade_count[0]*100:.1f}%)")
        print(f"   卖出: {sell_count[0]} 笔 ({sell_count[0]/trade_count[0]*100:.1f}%)")
    
    print("\n📝 测试2.4: 停止适配器...")
    await adapter.stop()
    
    return trade_count[0] > 0


async def test_trades_vs_trades_all():
    """对比测试：trades vs trades-all"""
    print_section("测试3: Trades vs Trades-All 对比测试")
    
    print("\n📝 测试3.1: 创建EventEngine和适配器...")
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    await adapter.start()
    await asyncio.sleep(1)
    
    # 订阅两个频道
    print("\n📝 测试3.2: 同时订阅trades和trades-all...")
    
    trades_count = [0]
    trades_all_count = [0]
    
    # 使用不同的回调来区分
    def on_trade_regular(event: TradeData):
        trades_count[0] += 1
        if trades_count[0] <= 3:
            print(f"   [trades] #{trades_count[0]}: {event.side} {event.quantity} @ {event.price}")
    
    def on_trade_all(event: TradeData):
        trades_all_count[0] += 1
        if trades_all_count[0] <= 3:
            print(f"   [trades-all] #{trades_all_count[0]}: {event.side} {event.quantity} @ {event.price}")
    
    # 注意：实际使用中两个频道会发送到同一个TradeData事件
    # 这里为了演示，我们只订阅trades-all
    engine.register(TradeData, on_trade_all)
    
    await adapter.subscribe_trades_all("BTC-USDT")
    
    print("\n⏳ 等待20秒...")
    await asyncio.sleep(20)
    
    print(f"\n📊 对比结果:")
    print(f"   trades-all: {trades_all_count[0]} 笔")
    print(f"\n💡 说明:")
    print(f"   - trades: 聚合推送，可能包含多条成交")
    print(f"   - trades-all: 每次仅一条成交记录")
    
    await adapter.stop()
    
    return trades_all_count[0] > 0


async def main():
    """主测试函数"""
    print("\n" + "🚀" * 40)
    print("OKX WebSocket Trades-All 频道测试")
    print("🚀" * 40)
    
    results = {}
    
    # 测试1: WebSocket直接使用
    try:
        results['trades_all_websocket'] = await test_trades_all_websocket()
    except Exception as e:
        print(f"❌ 测试1失败: {e}")
        import traceback
        traceback.print_exc()
        results['trades_all_websocket'] = False
    
    # 测试2: 适配器集成
    try:
        results['trades_all_adapter'] = await test_trades_all_adapter()
    except Exception as e:
        print(f"❌ 测试2失败: {e}")
        import traceback
        traceback.print_exc()
        results['trades_all_adapter'] = False
    
    # 测试3: 对比测试
    try:
        results['trades_vs_trades_all'] = await test_trades_vs_trades_all()
    except Exception as e:
        print(f"❌ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
        results['trades_vs_trades_all'] = False
    
    # 汇总结果
    print_section("📊 测试结果汇总")
    
    print("\n测试结果:")
    test_names = {
        'trades_all_websocket': 'Trades-All WebSocket直接测试',
        'trades_all_adapter': 'Trades-All适配器集成测试',
        'trades_vs_trades_all': 'Trades对比测试'
    }
    
    for test_key, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_names[test_key]:35s} : {status}")
    
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

