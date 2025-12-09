"""
OKX WebSocket 私有频道客户端

实现私有频道订阅，包括：
- 订单频道（orders）
- 账户频道（account）
- 持仓频道（positions）

需要API认证才能使用
"""

import asyncio
import json
import hmac
import base64
import time
from typing import Optional, Callable, Dict, Any, List
import websockets
from websockets.client import WebSocketClientProtocol

from core.event_engine import EventEngine
from core.order import Order, OrderState, OrderSide, OrderType


class OKXWebSocketPrivate:
    """
    OKX WebSocket 私有频道客户端
    
    支持订阅需要认证的私有频道：
    - orders: 订单更新
    - account: 账户更新
    - positions: 持仓更新
    """
    
    def __init__(
        self,
        url: str,
        api_key: str,
        secret_key: str,
        passphrase: str,
        event_engine: Optional[EventEngine] = None,
        is_demo: bool = True
    ):
        """
        初始化WebSocket私有频道客户端
        
        Args:
            url: WebSocket URL
            api_key: API Key
            secret_key: Secret Key
            passphrase: Passphrase
            event_engine: 事件引擎（用于分发事件）
            is_demo: 是否为模拟盘
        """
        self.url = url
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.event_engine = event_engine
        self.is_demo = is_demo
        
        # WebSocket连接
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self._running = False
        
        # 订阅管理
        self.subscriptions: Dict[str, Optional[Callable]] = {}
        
        # 任务
        self._recv_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    def _generate_signature(self) -> tuple[str, str]:
        """
        生成签名
        
        Returns:
            (timestamp, signature)
        """
        timestamp = str(int(time.time()))
        method = 'GET'
        request_path = '/users/self/verify'
        
        # 拼接签名字符串
        message = timestamp + method + request_path
        
        # HMAC SHA256签名
        mac = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            digestmod='sha256'
        )
        
        # Base64编码
        signature = base64.b64encode(mac.digest()).decode('utf-8')
        
        return timestamp, signature
    
    async def connect(self):
        """建立WebSocket连接"""
        if self.connected:
            print("⚠️  WebSocket已连接")
            return
        
        try:
            self.ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10
            )
            self.connected = True
            self._running = True
            
            print(f"✅ WebSocket私有频道连接成功: {self.url}")
            
            # 登录
            await self.login()
            
            # 启动接收任务
            self._recv_task = asyncio.create_task(self._receive_messages())
            
            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
        except Exception as e:
            self.connected = False
            print(f"❌ WebSocket私有频道连接失败: {e}")
            raise
    
    async def disconnect(self):
        """断开WebSocket连接"""
        self._running = False
        
        # 取消任务
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                print("📥 接收消息任务已取消")
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                print("💓 心跳任务已取消")
        
        # 关闭连接
        if self.ws:
            await self.ws.close()
            print("✅ WebSocket私有频道连接已关闭")
        
        self.connected = False
    
    async def login(self):
        """
        登录私有频道
        """
        timestamp, sign = self._generate_signature()
        
        login_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": sign
            }]
        }
        
        await self.ws.send(json.dumps(login_msg))
        print("📤 已发送登录请求")
        
        # 等待登录响应
        response = await self.ws.recv()
        data = json.loads(response)
        
        if data.get('event') == 'login':
            if data.get('code') == '0':
                print(f"✅ 登录成功！连接ID: {data.get('connId')}")
            else:
                raise Exception(f"登录失败：{data.get('msg')} (code: {data.get('code')})")
        elif data.get('event') == 'error':
            raise Exception(f"登录错误：{data.get('msg')} (code: {data.get('code')})")
    
    async def subscribe_orders(
        self,
        inst_type: str = "SPOT",
        inst_id: Optional[str] = None,
        inst_family: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        订阅订单频道
        
        Args:
            inst_type: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION/ANY）
            inst_id: 产品ID（可选）
            inst_family: 交易品种（可选）
            callback: 回调函数（可选）
        """
        args = {
            "channel": "orders",
            "instType": inst_type
        }
        
        if inst_id:
            args["instId"] = inst_id
        if inst_family:
            args["instFamily"] = inst_family
        
        # 生成订阅key
        channel_key = f"orders_{inst_type}"
        if inst_id:
            channel_key += f"_{inst_id}"
        elif inst_family:
            channel_key += f"_{inst_family}"
        
        self.subscriptions[channel_key] = callback
        
        request = {
            "op": "subscribe",
            "args": [args]
        }
        
        await self.ws.send(json.dumps(request))
        print(f"📤 发送订阅请求: {args}")
    
    async def unsubscribe_orders(
        self,
        inst_type: str = "SPOT",
        inst_id: Optional[str] = None,
        inst_family: Optional[str] = None
    ):
        """
        取消订阅订单频道
        
        Args:
            inst_type: 产品类型
            inst_id: 产品ID（可选）
            inst_family: 交易品种（可选）
        """
        args = {
            "channel": "orders",
            "instType": inst_type
        }
        
        if inst_id:
            args["instId"] = inst_id
        if inst_family:
            args["instFamily"] = inst_family
        
        # 生成订阅key
        channel_key = f"orders_{inst_type}"
        if inst_id:
            channel_key += f"_{inst_id}"
        elif inst_family:
            channel_key += f"_{inst_family}"
        
        if channel_key in self.subscriptions:
            del self.subscriptions[channel_key]
        
        request = {
            "op": "unsubscribe",
            "args": [args]
        }
        
        await self.ws.send(json.dumps(request))
        print(f"📤 发送取消订阅请求: {args}")
    
    async def _receive_messages(self):
        """接收并处理WebSocket消息"""
        try:
            while self._running and self.ws:
                message = await self.ws.recv()
                
                # 忽略心跳响应（pong）
                if message == "pong" or not message or not message.strip():
                    continue
                
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    # 忽略无法解析的消息
                    continue
                
                # 处理不同类型的消息
                event = data.get('event')
                
                if event == 'subscribe':
                    # 订阅成功响应
                    print(f"✅ 订阅成功: {data.get('arg')}")
                
                elif event == 'unsubscribe':
                    # 取消订阅响应
                    print(f"✅ 取消订阅成功: {data.get('arg')}")
                
                elif event == 'error':
                    # 错误响应
                    print(f"❌ 错误: {data.get('msg')} (code: {data.get('code')})")
                
                elif 'arg' in data and 'data' in data:
                    # 数据推送
                    self._process_message(data)
        
        except asyncio.CancelledError:
            print("📥 接收消息任务已取消")
        except Exception as e:
            print(f"❌ 接收消息错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _process_message(self, data: Dict[str, Any]):
        """
        处理推送消息
        
        Args:
            data: WebSocket推送的数据
        """
        arg = data.get('arg', {})
        channel = arg.get('channel')
        
        if channel == 'orders':
            self._process_order_message(data)
    
    def _process_order_message(self, data: Dict[str, Any]):
        """
        处理订单推送消息
        
        Args:
            data: 订单推送数据
        """
        arg = data.get('arg', {})
        orders_data = data.get('data', [])
        
        for order_data in orders_data:
            # 转换为Order事件
            order = self._convert_to_order(order_data)
            
            # 分发给EventEngine
            if self.event_engine:
                self.event_engine.put(order)
            
            # 调用回调函数
            channel_key = f"orders_{arg.get('instType')}"
            inst_id = arg.get('instId')
            inst_family = arg.get('instFamily')
            
            if inst_id:
                channel_key += f"_{inst_id}"
            elif inst_family:
                channel_key += f"_{inst_family}"
            
            callback = self.subscriptions.get(channel_key)
            if callback:
                callback(order_data)
    
    def _convert_to_order(self, order_data: Dict[str, Any]) -> Order:
        """
        将OKX订单数据转换为Order对象
        
        Args:
            order_data: OKX订单数据
        
        Returns:
            Order对象
        """
        # 订单类型映射
        ord_type_map = {
            'market': OrderType.MARKET,
            'limit': OrderType.LIMIT,
            'post_only': OrderType.POST_ONLY,
            'fok': OrderType.FOK,
            'ioc': OrderType.IOC,
        }
        
        # 订单状态映射
        state_map = {
            'live': OrderState.ACCEPTED,
            'partially_filled': OrderState.PARTIALLY_FILLED,
            'filled': OrderState.FILLED,
            'canceled': OrderState.CANCELLED,
            'mmp_canceled': OrderState.CANCELLED,
        }
        
        # 买卖方向
        side = OrderSide.BUY if order_data['side'] == 'buy' else OrderSide.SELL
        
        # 创建Order对象
        order = Order(
            symbol=order_data['instId'],
            order_type=ord_type_map.get(order_data['ordType'], OrderType.LIMIT),
            side=side,
            quantity=float(order_data['sz']),
            price=float(order_data['px']) if order_data['px'] else None,
            client_order_id=order_data.get('clOrdId', ''),
            exchange_order_id=order_data['ordId'],
            exchange="OKX",
            state=state_map.get(order_data['state'], OrderState.ACCEPTED),
            filled_quantity=float(order_data['accFillSz']),
            filled_price=float(order_data['avgPx']) if order_data['avgPx'] and float(order_data['avgPx']) > 0 else None,
            fee=float(order_data.get('fee', 0)),
            fee_currency=order_data.get('feeCcy', ''),
            create_time=int(order_data['cTime']),
            update_time=int(order_data['uTime']),
            timestamp=int(order_data['uTime'])
        )
        
        return order
    
    async def _heartbeat(self):
        """发送心跳保持连接"""
        try:
            while self._running:
                await asyncio.sleep(25)  # 每25秒发送一次心跳
                # 安全检查连接状态
                if self.ws:
                    try:
                        # 使用hasattr检查closed属性是否存在
                        if not hasattr(self.ws, 'closed') or not self.ws.closed:
                            await self.ws.send("ping")
                    except Exception:
                        # 如果发送失败，连接可能已经关闭，忽略错误
                        pass
        except asyncio.CancelledError:
            print("💓 心跳任务已取消")
        except Exception as e:
            print(f"❌ 心跳错误: {e}")


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OKX WebSocket 私有频道测试")
    print("=" * 60)
    
    async def test_orders_channel():
        """测试订单频道"""
        # 请替换为您的API密钥
        API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e"
        SECRET_KEY = "888CC77C745F1B49E75A992F38929992"
        PASSPHRASE = "Sequence2025."
        
        # 创建EventEngine
        from core.event_engine import EventEngine
        engine = EventEngine()
        
        # 订单事件监听器
        def on_order(order: Order):
            print(f"\n📦 收到订单事件:")
            print(f"   订单ID: {order.exchange_order_id}")
            print(f"   产品: {order.symbol}")
            print(f"   方向: {order.side.name}")
            print(f"   类型: {order.order_type.name}")
            print(f"   价格: {order.price}")
            print(f"   数量: {order.quantity}")
            print(f"   已成交: {order.filled_quantity}")
            print(f"   状态: {order.state.name}")
        
        engine.register(Order, on_order)
        
        # 创建WebSocket客户端（模拟盘）
        ws = OKXWebSocketPrivate(
            url="wss://wspap.okx.com:8443/ws/v5/private",
            api_key=API_KEY,
            secret_key=SECRET_KEY,
            passphrase=PASSPHRASE,
            event_engine=engine,
            is_demo=True
        )
        
        try:
            # 连接
            print("\n1. 建立连接...")
            await ws.connect()
            
            # 订阅订单频道（币币）
            print("\n2. 订阅订单频道（币币）...")
            await ws.subscribe_orders(inst_type="SPOT")
            
            # 等待接收消息
            print("\n3. 等待订单推送（60秒）...")
            print("   💡 提示：请在OKX模拟盘手动下单测试")
            await asyncio.sleep(60)
            
            # 取消订阅
            print("\n4. 取消订阅...")
            await ws.unsubscribe_orders(inst_type="SPOT")
            
            # 断开连接
            print("\n5. 断开连接...")
            await ws.disconnect()
            
            print("\n✅ 测试完成！")
        
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            if ws.connected:
                await ws.disconnect()
    
    asyncio.run(test_orders_channel())

