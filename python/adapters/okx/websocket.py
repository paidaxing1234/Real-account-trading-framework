"""
OKX WebSocket 客户端实现
支持公共频道（行情数据）和私有频道（账户数据）
"""

import asyncio
import json
import hmac
import base64
import time
from typing import Optional, Callable, Dict, Any, List, Tuple
from datetime import datetime
import websockets
from websockets.client import WebSocketClientProtocol


class OKXWebSocketBase:
    """OKX WebSocket 基类"""
    
    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None,
        is_demo: bool = False
    ):
        """
        初始化WebSocket客户端
        
        Args:
            url: WebSocket URL
            api_key: API密钥（私有频道需要）
            secret_key: Secret密钥（私有频道需要）
            passphrase: API密码（私有频道需要）
            is_demo: 是否为模拟盘
        """
        self.url = url
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        self.ws: Optional[WebSocketClientProtocol] = None
        self.callbacks: Dict[str, List[Callable]] = {}
        self.subscriptions: List[Dict[str, Any]] = []
        
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    def _generate_signature(self) -> Tuple[str, str]:
        """
        生成WebSocket登录签名
        
        Returns:
            (timestamp, sign)
        """
        timestamp = str(int(time.time()))
        message = timestamp + 'GET' + '/users/self/verify'
        
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        sign = base64.b64encode(mac.digest()).decode()
        
        return timestamp, sign
    
    async def connect(self):
        """建立WebSocket连接"""
        try:
            self.ws = await websockets.connect(self.url)
            self._running = True
            print(f"✅ WebSocket连接成功: {self.url}")
            
            # 启动接收消息任务
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
        except Exception as e:
            print(f"❌ WebSocket连接失败: {e}")
            raise
    
    async def disconnect(self):
        """断开WebSocket连接"""
        self._running = False
        
        # 取消任务
        if self._receive_task:
            self._receive_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        # 关闭连接
        if self.ws:
            await self.ws.close()
            print("✅ WebSocket连接已关闭")
    
    async def login(self):
        """
        登录私有频道
        仅在需要订阅私有频道时调用
        """
        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ValueError("登录需要提供 api_key, secret_key, passphrase")
        
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
        print("📤 发送登录请求")
    
    async def subscribe(self, args: List[Dict[str, str]], callback: Optional[Callable] = None):
        """
        订阅频道
        
        Args:
            args: 订阅参数列表，如 [{"channel": "tickers", "instId": "BTC-USDT"}]
            callback: 回调函数
        """
        msg = {
            "op": "subscribe",
            "args": args
        }
        
        await self.ws.send(json.dumps(msg))
        
        # 保存订阅信息和回调
        for arg in args:
            channel_key = f"{arg['channel']}:{arg.get('instId', 'all')}"
            if channel_key not in self.callbacks:
                self.callbacks[channel_key] = []
            if callback and callback not in self.callbacks[channel_key]:
                self.callbacks[channel_key].append(callback)
            
            if arg not in self.subscriptions:
                self.subscriptions.append(arg)
        
        print(f"📤 发送订阅请求: {args}")
    
    async def unsubscribe(self, args: List[Dict[str, str]]):
        """
        取消订阅频道
        
        Args:
            args: 取消订阅参数列表
        """
        msg = {
            "op": "unsubscribe",
            "args": args
        }
        
        await self.ws.send(json.dumps(msg))
        
        # 移除订阅信息
        for arg in args:
            channel_key = f"{arg['channel']}:{arg.get('instId', 'all')}"
            if channel_key in self.callbacks:
                del self.callbacks[channel_key]
            
            if arg in self.subscriptions:
                self.subscriptions.remove(arg)
        
        print(f"📤 发送取消订阅请求: {args}")
    
    async def _receive_messages(self):
        """接收WebSocket消息"""
        try:
            async for message in self.ws:
                # 忽略心跳响应（pong）
                if message == "pong" or not message or not message.strip():
                    continue
                
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    # 忽略无法解析的消息（可能是心跳等非JSON消息）
                    continue
        except asyncio.CancelledError:
            print("📥 接收消息任务已取消")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"⚠️ WebSocket连接关闭: {e}")
            if self._running:
                await self._reconnect()
        except Exception as e:
            print(f"❌ 接收消息错误: {e}")
            if self._running:
                # 尝试重连
                await self._reconnect()
    
    async def _handle_message(self, data: Dict[str, Any]):
        """
        处理接收到的消息
        
        Args:
            data: 消息数据
        """
        # 事件消息（订阅/取消订阅响应）
        if 'event' in data:
            event = data['event']
            if event == 'subscribe':
                print(f"✅ 订阅成功: {data.get('arg')}")
            elif event == 'unsubscribe':
                print(f"✅ 取消订阅成功: {data.get('arg')}")
            elif event == 'error':
                print(f"❌ 错误: {data.get('msg')} (code: {data.get('code')})")
            elif event == 'login':
                if data.get('code') == '0':
                    print(f"✅ 登录成功")
                else:
                    print(f"❌ 登录失败: {data.get('msg')}")
        
        # 数据推送
        elif 'arg' in data and 'data' in data:
            arg = data['arg']
            channel = arg['channel']
            inst_id = arg.get('instId', 'all')
            channel_key = f"{channel}:{inst_id}"
            
            # 调用回调函数
            if channel_key in self.callbacks:
                for callback in self.callbacks[channel_key]:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(data)
                        else:
                            callback(data)
                    except Exception as e:
                        print(f"❌ 回调函数执行错误: {e}")
    
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
    
    async def _reconnect(self):
        """重连逻辑"""
        print("🔄 尝试重新连接...")
        
        # 保存订阅列表和回调（在断开连接前）
        saved_subscriptions = self.subscriptions.copy()
        saved_callbacks = self.callbacks.copy()
        
        # 关闭旧连接（但不取消运行状态）
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        
        await asyncio.sleep(5)  # 等待5秒后重连
        
        try:
            # 重新建立连接
            self.ws = await websockets.connect(self.url)
            self._running = True
            print(f"✅ 重连成功: {self.url}")
            
            # 恢复回调
            self.callbacks = saved_callbacks
            
            # 重新订阅（使用保存的订阅列表）
            if saved_subscriptions:
                print(f"🔄 重新订阅 {len(saved_subscriptions)} 个频道...")
                await self.subscribe(saved_subscriptions)
            
            # 重新启动接收任务
            self._receive_task = asyncio.create_task(self._receive_messages())
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
        except Exception as e:
            print(f"❌ 重连失败: {e}")
            # 5秒后再次尝试
            await asyncio.sleep(5)
            if self._running:
                await self._reconnect()


class OKXWebSocketPublic(OKXWebSocketBase):
    """OKX 公共频道 WebSocket 客户端（行情数据）"""
    
    def __init__(self, is_demo: bool = False, url_type: str = "public"):
        """
        初始化公共频道WebSocket客户端
        
        Args:
            is_demo: 是否为模拟盘
            url_type: URL类型（public/business）
        """
        if url_type == "business":
            # K线频道使用business端点
            if is_demo:
                url = "wss://wspap.okx.com:8443/ws/v5/business"
            else:
                url = "wss://ws.okx.com:8443/ws/v5/business"
        else:
            # 行情、交易等使用public端点
            if is_demo:
                url = "wss://wspap.okx.com:8443/ws/v5/public"
            else:
                url = "wss://ws.okx.com:8443/ws/v5/public"
        
        super().__init__(url=url, is_demo=is_demo)
    
    async def subscribe_tickers(self, inst_id: str, callback: Optional[Callable] = None):
        """
        订阅行情频道
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            callback: 回调函数
        """
        args = [{
            "channel": "tickers",
            "instId": inst_id
        }]
        await self.subscribe(args, callback)
    
    async def unsubscribe_tickers(self, inst_id: str):
        """
        取消订阅行情频道
        
        Args:
            inst_id: 产品ID
        """
        args = [{
            "channel": "tickers",
            "instId": inst_id
        }]
        await self.unsubscribe(args)
    
    async def subscribe_candles(
        self, 
        inst_id: str, 
        interval: str = "1m",
        callback: Optional[Callable] = None
    ):
        """
        订阅K线频道
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            interval: K线间隔，如 1m, 5m, 1H, 1D等
                     支持: 1s, 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H,
                          1D, 2D, 3D, 5D, 1W, 1M, 3M
            callback: 回调函数
        """
        # 转换间隔格式
        channel_map = {
            "1s": "candle1s", "1m": "candle1m", "3m": "candle3m",
            "5m": "candle5m", "15m": "candle15m", "30m": "candle30m",
            "1H": "candle1H", "2H": "candle2H", "4H": "candle4H",
            "6H": "candle6H", "12H": "candle12H",
            "1D": "candle1D", "2D": "candle2D", "3D": "candle3D",
            "5D": "candle5D", "1W": "candle1W", "1M": "candle1M",
            "3M": "candle3M"
        }
        
        channel = channel_map.get(interval, f"candle{interval}")
        
        args = [{
            "channel": channel,
            "instId": inst_id
        }]
        await self.subscribe(args, callback)
    
    async def unsubscribe_candles(self, inst_id: str, interval: str = "1m"):
        """
        取消订阅K线频道
        
        Args:
            inst_id: 产品ID
            interval: K线间隔
        """
        channel_map = {
            "1s": "candle1s", "1m": "candle1m", "3m": "candle3m",
            "5m": "candle5m", "15m": "candle15m", "30m": "candle30m",
            "1H": "candle1H", "2H": "candle2H", "4H": "candle4H",
            "6H": "candle6H", "12H": "candle12H",
            "1D": "candle1D", "2D": "candle2D", "3D": "candle3D",
            "5D": "candle5D", "1W": "candle1W", "1M": "candle1M",
            "3M": "candle3M"
        }
        
        channel = channel_map.get(interval, f"candle{interval}")
        
        args = [{
            "channel": channel,
            "instId": inst_id
        }]
        await self.unsubscribe(args)
    
    async def subscribe_trades(self, inst_id: str, callback: Optional[Callable] = None):
        """
        订阅交易频道（逐笔成交）
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            callback: 回调函数
        """
        args = [{
            "channel": "trades",
            "instId": inst_id
        }]
        await self.subscribe(args, callback)
    
    async def unsubscribe_trades(self, inst_id: str):
        """
        取消订阅交易频道
        
        Args:
            inst_id: 产品ID
        """
        args = [{
            "channel": "trades",
            "instId": inst_id
        }]
        await self.unsubscribe(args)
    
    async def subscribe_trades_all(self, inst_id: str, callback: Optional[Callable] = None):
        """
        订阅全部交易频道（逐笔成交，每次仅一条）
        
        注意：使用business端点，需要创建专门的WebSocket连接
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            callback: 回调函数
        """
        args = [{
            "channel": "trades-all",
            "instId": inst_id
        }]
        await self.subscribe(args, callback)
    
    async def unsubscribe_trades_all(self, inst_id: str):
        """
        取消订阅全部交易频道
        
        Args:
            inst_id: 产品ID
        """
        args = [{
            "channel": "trades-all",
            "instId": inst_id
        }]
        await self.unsubscribe(args)


class OKXWebSocketPrivate(OKXWebSocketBase):
    """OKX 私有频道 WebSocket 客户端（账户数据）"""
    
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        is_demo: bool = False
    ):
        """
        初始化私有频道WebSocket客户端
        
        Args:
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码
            is_demo: 是否为模拟盘
        """
        if is_demo:
            url = "wss://wspap.okx.com:8443/ws/v5/private"
        else:
            url = "wss://ws.okx.com:8443/ws/v5/private"
        
        super().__init__(
            url=url,
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            is_demo=is_demo
        )
    
    async def subscribe_orders(self, inst_type: str, callback: Optional[Callable] = None):
        """
        订阅订单频道
        
        Args:
            inst_type: 产品类型（SPOT/MARGIN/SWAP/FUTURES/OPTION）
            callback: 回调函数
        """
        args = [{
            "channel": "orders",
            "instType": inst_type
        }]
        await self.subscribe(args, callback)
    
    async def subscribe_account(self, callback: Optional[Callable] = None):
        """
        订阅账户频道
        
        Args:
            callback: 回调函数
        """
        args = [{
            "channel": "account"
        }]
        await self.subscribe(args, callback)

