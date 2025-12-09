"""
WebSocket私有频道 - 订单推送示例

演示如何使用WebSocket实时接收订单更新，而不是通过REST API轮询查询。

功能:
1. 实时接收订单创建推送
2. 实时接收订单成交推送
3. 实时接收订单取消推送
4. 自动管理订单状态

性能优势:
- 延迟: REST 1-2秒 vs WebSocket <100ms (快10-20倍)
- API调用: REST 60次/分钟 vs WebSocket 1次 (减少99%)
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import EventEngine, Order, OrderState
from adapters.okx import OKXWebSocketPrivate, OKXRestAPI


class OrderTracker:
    """
    订单跟踪器
    
    使用WebSocket实时跟踪所有订单状态
    """
    
    def __init__(self):
        # 活跃订单（未完结的订单）
        self.active_orders = {}
        
        # 历史订单（已完结的订单）
        self.completed_orders = {}
        
        # 统计信息
        self.total_created = 0
        self.total_filled = 0
        self.total_cancelled = 0
        self.total_partial = 0
    
    def on_order_update(self, order: Order):
        """
        处理订单更新事件
        
        Args:
            order: 订单事件
        """
        order_id = order.exchange_order_id
        
        # 记录统计
        if order.state == OrderState.ACCEPTED:
            self.total_created += 1
            self.log_order_created(order)
        elif order.state == OrderState.PARTIALLY_FILLED:
            self.total_partial += 1
            self.log_order_partial(order)
        elif order.state == OrderState.FILLED:
            self.total_filled += 1
            self.log_order_filled(order)
        elif order.state == OrderState.CANCELLED:
            self.total_cancelled += 1
            self.log_order_cancelled(order)
        
        # 更新订单状态
        if order.state in [OrderState.FILLED, OrderState.CANCELLED]:
            # 移到历史订单
            if order_id in self.active_orders:
                del self.active_orders[order_id]
            self.completed_orders[order_id] = order
        else:
            # 保持在活跃订单中
            self.active_orders[order_id] = order
    
    def log_order_created(self, order: Order):
        """记录订单创建"""
        print(f"\n📝 [{datetime.now().strftime('%H:%M:%S')}] 订单创建")
        print(f"   订单ID: {order.exchange_order_id}")
        print(f"   客户ID: {order.client_order_id}")
        print(f"   产品: {order.symbol}")
        print(f"   方向: {order.side.name}")
        print(f"   价格: {order.price}")
        print(f"   数量: {order.quantity}")
        print(f"   状态: {order.state.name}")
    
    def log_order_partial(self, order: Order):
        """记录部分成交"""
        fill_pct = (order.filled_quantity / order.quantity * 100) if order.quantity > 0 else 0
        print(f"\n📊 [{datetime.now().strftime('%H:%M:%S')}] 订单部分成交")
        print(f"   订单ID: {order.exchange_order_id}")
        print(f"   已成交: {order.filled_quantity} / {order.quantity} ({fill_pct:.1f}%)")
        print(f"   成交均价: {order.filled_price}")
    
    def log_order_filled(self, order: Order):
        """记录完全成交"""
        print(f"\n✅ [{datetime.now().strftime('%H:%M:%S')}] 订单完全成交")
        print(f"   订单ID: {order.exchange_order_id}")
        print(f"   成交数量: {order.filled_quantity}")
        print(f"   成交均价: {order.filled_price}")
        print(f"   手续费: {order.fee} {order.fee_currency}")
    
    def log_order_cancelled(self, order: Order):
        """记录订单取消"""
        print(f"\n❌ [{datetime.now().strftime('%H:%M:%S')}] 订单取消")
        print(f"   订单ID: {order.exchange_order_id}")
        print(f"   已成交: {order.filled_quantity} / {order.quantity}")
    
    def print_summary(self):
        """打印统计摘要"""
        print(f"\n" + "="*60)
        print(f"📊 订单统计")
        print(f"="*60)
        print(f"   创建: {self.total_created} 个")
        print(f"   部分成交: {self.total_partial} 个")
        print(f"   完全成交: {self.total_filled} 个")
        print(f"   取消: {self.total_cancelled} 个")
        print(f"   活跃订单: {len(self.active_orders)} 个")
        print(f"   历史订单: {len(self.completed_orders)} 个")


async def example_1_basic_usage():
    """示例1: 基础用法 - 实时接收订单推送"""
    print("\n" + "🔷"*30)
    print("示例1: 基础用法 - 实时接收订单推送")
    print("🔷"*30)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建EventEngine
    engine = EventEngine()
    
    # 创建订单跟踪器
    tracker = OrderTracker()
    engine.register(Order, tracker.on_order_update)
    
    # 创建WebSocket私有频道客户端
    ws = OKXWebSocketPrivate(
        url="wss://wspap.okx.com:8443/ws/v5/private",
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        event_engine=engine,
        is_demo=True
    )
    
    try:
        print("\n1️⃣  连接WebSocket...")
        await ws.connect()
        
        print("\n2️⃣  订阅订单频道（币币）...")
        await ws.subscribe_orders(inst_type="SPOT")
        
        print("\n3️⃣  等待订单推送（60秒）...")
        print("   💡 提示: 请在OKX模拟盘网页或APP手动下单测试")
        print("   💡 建议: 下一个BTC-USDT的限价单，然后取消")
        
        await asyncio.sleep(60)
        
        # 打印统计
        tracker.print_summary()
        
        print("\n4️⃣  断开连接...")
        await ws.disconnect()
        
        print("\n✅ 示例1完成")
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def example_2_auto_trading():
    """示例2: 自动交易 - REST下单 + WebSocket监控"""
    print("\n" + "🔷"*30)
    print("示例2: 自动交易 - REST下单 + WebSocket监控")
    print("🔷"*30)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建EventEngine
    engine = EventEngine()
    
    # 创建订单跟踪器
    tracker = OrderTracker()
    engine.register(Order, tracker.on_order_update)
    
    # 创建REST客户端
    rest = OKXRestAPI(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        is_demo=True
    )
    
    # 创建WebSocket私有频道客户端
    ws = OKXWebSocketPrivate(
        url="wss://wspap.okx.com:8443/ws/v5/private",
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        passphrase=PASSPHRASE,
        event_engine=engine,
        is_demo=True
    )
    
    try:
        print("\n1️⃣  连接WebSocket...")
        await ws.connect()
        
        print("\n2️⃣  订阅订单频道...")
        await ws.subscribe_orders(inst_type="SPOT")
        await asyncio.sleep(2)
        
        print("\n3️⃣  查询当前价格...")
        ticker = rest.get_ticker(inst_id="BTC-USDT")
        if ticker and ticker.get('code') == '0':
            last_price = float(ticker['data'][0]['last'])
            print(f"   当前价格: {last_price} USDT")
            
            # 设置一个不会立即成交的价格
            order_price = last_price * 0.85
            print(f"   下单价格: {order_price:.2f} USDT")
        else:
            print("   ❌ 获取价格失败")
            return
        
        print("\n4️⃣  下单（通过REST API）...")
        import uuid
        cl_ord_id = uuid.uuid4().hex[:16]
        
        result = rest.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px=str(order_price),
            sz="0.001",
            cl_ord_id=cl_ord_id
        )
        
        order_id = None
        if result and result.get('code') == '0':
            order_data = result['data'][0]
            order_id = order_data.get('ordId')
            print(f"✅ 下单成功")
            print(f"   订单ID: {order_id}")
            print(f"   客户ID: {cl_ord_id}")
        else:
            print(f"❌ 下单失败: {result}")
            return
        
        print("\n5️⃣  等待WebSocket推送（5秒）...")
        print("   💡 您将看到订单创建推送")
        await asyncio.sleep(5)
        
        print("\n6️⃣  撤单（通过REST API）...")
        cancel_result = rest.cancel_order(inst_id="BTC-USDT", ord_id=order_id)
        if cancel_result and cancel_result.get('code') == '0':
            print(f"✅ 撤单请求成功")
        else:
            print(f"❌ 撤单失败: {cancel_result}")
        
        print("\n7️⃣  等待撤单推送（5秒）...")
        print("   💡 您将看到订单取消推送")
        await asyncio.sleep(5)
        
        # 打印统计
        tracker.print_summary()
        
        print("\n8️⃣  断开连接...")
        await ws.disconnect()
        
        print("\n✅ 示例2完成")
        print("\n💡 总结:")
        print("   - REST API用于主动操作（下单、撤单）")
        print("   - WebSocket用于被动监听（订单状态推送）")
        print("   - 两者配合使用，效率最高！")
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def example_3_multi_product():
    """示例3: 多产品订阅"""
    print("\n" + "🔷"*30)
    print("示例3: 多产品订阅 - 同时监控多个市场")
    print("🔷"*30)
    
    # API配置
    API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
    SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
    PASSPHRASE = "Sequence2025."
    
    # 创建EventEngine
    engine = EventEngine()
    
    # 订单统计（按产品类型）
    stats = {
        'SPOT': [],
        'SWAP': [],
        'FUTURES': []
    }
    
    def on_order(order: Order):
        print(f"\n📦 订单推送:")
        print(f"   产品: {order.symbol}")
        print(f"   方向: {order.side.name}")
        print(f"   状态: {order.state.name}")
        
        # 统计（简化处理，实际应根据symbol判断类型）
        # stats['SPOT'].append(order)
    
    engine.register(Order, on_order)
    
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
        print("\n1️⃣  连接WebSocket...")
        await ws.connect()
        
        print("\n2️⃣  订阅多个产品类型...")
        
        # 订阅币币
        await ws.subscribe_orders(inst_type="SPOT")
        print("   ✅ 订阅币币订单")
        await asyncio.sleep(1)
        
        # 订阅永续合约
        await ws.subscribe_orders(inst_type="SWAP")
        print("   ✅ 订阅永续合约订单")
        await asyncio.sleep(1)
        
        # 订阅交割合约
        await ws.subscribe_orders(inst_type="FUTURES")
        print("   ✅ 订阅交割合约订单")
        await asyncio.sleep(1)
        
        print("\n3️⃣  等待订单推送（30秒）...")
        print("   💡 提示: 现在可以在任何市场下单，都会收到推送")
        await asyncio.sleep(30)
        
        print("\n4️⃣  断开连接...")
        await ws.disconnect()
        
        print("\n✅ 示例3完成")
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if ws.connected:
            await ws.disconnect()


async def main():
    """运行所有示例"""
    print("\n" + "🚀"*40)
    print("WebSocket私有频道 - 订单推送示例集合")
    print("🚀"*40)
    
    # 选择运行的示例
    print("\n请选择要运行的示例:")
    print("1. 基础用法 - 实时接收订单推送")
    print("2. 自动交易 - REST下单 + WebSocket监控")
    print("3. 多产品订阅 - 同时监控多个市场")
    print("4. 运行所有示例")
    
    # 为了自动化，直接运行示例2（最完整）
    print("\n自动运行示例2（最完整的演示）...\n")
    
    await example_2_auto_trading()
    
    # 如果需要运行其他示例，取消下面的注释
    # await example_1_basic_usage()
    # await example_3_multi_product()


if __name__ == "__main__":
    asyncio.run(main())





