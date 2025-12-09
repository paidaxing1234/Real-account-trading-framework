"""
OKX WebSocket 私有频道测试

测试内容：
1. 连接与登录
2. 订单频道订阅
3. 订单推送接收
4. Order事件转换
5. 取消订阅与断开
"""

import asyncio
import time
import sys
import os
from typing import List

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.okx.websocket_private import OKXWebSocketPrivate
from adapters.okx.rest_api import OKXRestAPI
from core.event_engine import EventEngine
from core.order import Order, OrderState


class OrderCollector:
    """订单收集器"""
    def __init__(self):
        self.orders: List[Order] = []
        self.raw_data: List[dict] = []
    
    def on_order(self, order: Order):
        """订单事件监听器"""
        self.orders.append(order)
        print(f"\n📦 [{len(self.orders)}] 收到订单事件:")
        print(f"   订单ID: {order.exchange_order_id}")
        print(f"   客户订单ID: {order.client_order_id}")
        print(f"   产品: {order.symbol}")
        print(f"   方向: {order.side.name}")
        print(f"   类型: {order.order_type.name}")
        print(f"   价格: {order.price}")
        print(f"   数量: {order.quantity}")
        print(f"   已成交: {order.filled_quantity}")
        print(f"   成交均价: {order.filled_price}")
        print(f"   状态: {order.state.name}")
        print(f"   创建时间: {order.create_time}")
        print(f"   更新时间: {order.update_time}")
    
    def on_raw_data(self, data: dict):
        """原始数据回调"""
        self.raw_data.append(data)


async def test_1_connection_and_login():
    """测试1: 连接与登录"""
    print("\n" + "="*80)
    print("📋 测试1: WebSocket私有频道连接与登录")
    print("="*80)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    ws = OKXWebSocketPrivate(
        url="wss://wspap.okx.com:8443/ws/v5/private",
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    try:
        print("\n📝 步骤1: 建立连接...")
        await ws.connect()
        
        if ws.connected:
            print("✅ 连接成功")
            print("✅ 登录成功")
            
            await asyncio.sleep(2)
            
            print("\n📝 步骤2: 断开连接...")
            await ws.disconnect()
            print("✅ 断开成功")
            
            return True
        else:
            print("❌ 连接失败")
            return False
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def test_2_subscribe_orders():
    """测试2: 订阅订单频道"""
    print("\n" + "="*80)
    print("📋 测试2: 订阅订单频道")
    print("="*80)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建EventEngine
    engine = EventEngine()
    collector = OrderCollector()
    engine.register(Order, collector.on_order)
    
    ws = OKXWebSocketPrivate(
        url="wss://wspap.okx.com:8443/ws/v5/private",
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        event_engine=engine,
        is_demo=True
    )
    
    try:
        print("\n📝 步骤1: 建立连接...")
        await ws.connect()
        await asyncio.sleep(2)
        
        print("\n📝 步骤2: 订阅订单频道（币币）...")
        await ws.subscribe_orders(inst_type="SPOT", callback=collector.on_raw_data)
        await asyncio.sleep(2)
        
        print("\n📝 步骤3: 等待订单推送（30秒）...")
        print("   💡 提示：请在OKX模拟盘网页手动下单测试")
        print("   💡 建议：下一个BTC-USDT的限价单")
        await asyncio.sleep(30)
        
        print(f"\n📊 接收统计:")
        print(f"   收到订单事件: {len(collector.orders)} 个")
        print(f"   收到原始数据: {len(collector.raw_data)} 条")
        
        if collector.orders:
            print("\n✅ 订单推送正常")
            
            # 显示第一个订单的详细信息
            first_order = collector.orders[0]
            print(f"\n📦 第一个订单详情:")
            print(f"   订单ID: {first_order.exchange_order_id}")
            print(f"   产品: {first_order.symbol}")
            print(f"   方向: {first_order.side.name}")
            print(f"   状态: {first_order.state.name}")
        else:
            print("\n⚠️  未收到订单推送")
            print("   可能原因：")
            print("   1. 没有在模拟盘下单")
            print("   2. 下单的产品类型不是SPOT")
            print("   3. WebSocket连接有问题")
        
        print("\n📝 步骤4: 取消订阅...")
        await ws.unsubscribe_orders(inst_type="SPOT")
        await asyncio.sleep(1)
        
        print("\n📝 步骤5: 断开连接...")
        await ws.disconnect()
        
        return len(collector.orders) > 0
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def test_3_auto_order():
    """测试3: 自动下单并接收推送"""
    print("\n" + "="*80)
    print("📋 测试3: 自动下单并接收订单推送")
    print("="*80)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建REST客户端
    rest = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    # 创建EventEngine
    engine = EventEngine()
    collector = OrderCollector()
    engine.register(Order, collector.on_order)
    
    # 创建WebSocket客户端
    ws = OKXWebSocketPrivate(
        url="wss://wspap.okx.com:8443/ws/v5/private",
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        event_engine=engine,
        is_demo=True
    )
    
    try:
        print("\n📝 步骤1: 建立WebSocket连接...")
        await ws.connect()
        await asyncio.sleep(2)
        
        print("\n📝 步骤2: 订阅订单频道...")
        await ws.subscribe_orders(inst_type="SPOT")
        await asyncio.sleep(2)
        
        print("\n📝 步骤3: 查询当前价格...")
        ticker = rest.get_ticker(inst_id="BTC-USDT")
        if ticker and ticker.get('code') == '0':
            last_price = float(ticker['data'][0]['last'])
            print(f"   当前价格: {last_price} USDT")
            
            # 设置一个不会成交的价格（远低于当前价）
            order_price = last_price * 0.8
            print(f"   下单价格: {order_price:.2f} USDT (80%当前价)")
        else:
            print("   ❌ 获取价格失败，使用默认价格")
            order_price = 10000.0
        
        print("\n📝 步骤4: 下单...")
        import uuid
        # 使用纯UUID（无下划线前缀）
        cl_ord_id = uuid.uuid4().hex[:16]
        
        result = rest.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px=str(order_price),
            sz="0.001",  # 最小数量
            cl_ord_id=cl_ord_id
        )
        
        order_id = None
        if result and result.get('code') == '0':
            order_data = result['data'][0]
            order_id = order_data.get('ordId')
            print(f"✅ 下单成功")
            print(f"   订单ID: {order_id}")
            print(f"   客户订单ID: {cl_ord_id}")
        else:
            print(f"❌ 下单失败: {result}")
            return False
        
        print("\n📝 步骤5: 等待订单推送（10秒）...")
        await asyncio.sleep(10)
        
        print(f"\n📊 接收统计:")
        print(f"   收到订单事件: {len(collector.orders)} 个")
        
        # 查找我们下的订单
        our_order = None
        for order in collector.orders:
            if order.exchange_order_id == order_id or order.client_order_id == cl_ord_id:
                our_order = order
                break
        
        if our_order:
            print(f"\n✅ 成功接收到订单推送")
            print(f"   订单ID: {our_order.exchange_order_id}")
            print(f"   状态: {our_order.state.name}")
        else:
            print(f"\n⚠️  未接收到订单推送")
        
        print("\n📝 步骤6: 撤单...")
        if order_id:
            cancel_result = rest.cancel_order(inst_id="BTC-USDT", ord_id=order_id)
            if cancel_result and cancel_result.get('code') == '0':
                print(f"✅ 撤单成功")
                
                # 等待撤单推送
                print("\n📝 步骤7: 等待撤单推送（5秒）...")
                await asyncio.sleep(5)
                
                # 检查是否收到撤单推送
                for order in collector.orders:
                    if order.exchange_order_id == order_id:
                        if order.state == OrderState.CANCELLED:
                            print(f"✅ 收到撤单推送，状态: {order.state.name}")
                            break
            else:
                print(f"❌ 撤单失败: {cancel_result}")
        
        print("\n📝 步骤8: 断开连接...")
        await ws.disconnect()
        
        return our_order is not None
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def main():
    """运行所有测试"""
    print("\n" + "🚀"*40)
    print("OKX WebSocket 私有频道完整测试")
    print("🚀"*40)
    
    results = {}
    
    # 测试1: 连接与登录
    results['连接与登录'] = await test_1_connection_and_login()
    await asyncio.sleep(2)
    
    # 测试2: 订阅订单频道
    results['订阅订单频道'] = await test_2_subscribe_orders()
    await asyncio.sleep(2)
    
    # 测试3: 自动下单测试
    results['自动下单与推送'] = await test_3_auto_order()
    
    # 测试结果汇总
    print("\n" + "="*80)
    print("📊 测试结果汇总")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name:<20}: {status}")
    
    passed_count = sum(1 for p in results.values() if p)
    total_count = len(results)
    
    print(f"\n总计: {passed_count}/{total_count} 个测试通过")
    
    if passed_count == total_count:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️  有 {total_count - passed_count} 个测试失败")


if __name__ == "__main__":
    asyncio.run(main())

