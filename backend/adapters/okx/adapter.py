"""
OKX 适配器组件
将OKX的WebSocket数据转换为内部事件格式，并通过EventEngine分发
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

from core import Component, EventEngine, TickerData, KlineData, TradeData
from .websocket import OKXWebSocketPublic, OKXWebSocketPrivate


class OKXMarketDataAdapter(Component):
    """
    OKX 行情数据适配器
    订阅OKX行情数据，转换为TickerData事件并分发
    """
    
    def __init__(
        self,
        event_engine: EventEngine,
        is_demo: bool = False
    ):
        """
        初始化OKX行情数据适配器
        
        Args:
            event_engine: 事件引擎
            is_demo: 是否为模拟盘
        """
        self.event_engine = event_engine
        self.is_demo = is_demo
        self.ws: Optional[OKXWebSocketPublic] = None
        self.subscribed_symbols: set = set()
        
        # 异步任务
        self._ws_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动适配器"""
        print("🚀 启动OKX行情数据适配器...")
        
        # 创建WebSocket客户端
        self.ws = OKXWebSocketPublic(is_demo=self.is_demo)
        
        # 连接
        await self.ws.connect()
        
        print("✅ OKX行情数据适配器启动成功")
    
    async def stop(self):
        """停止适配器"""
        print("🛑 停止OKX行情数据适配器...")
        
        if self.ws:
            await self.ws.disconnect()
        
        print("✅ OKX行情数据适配器已停止")
    
    async def subscribe_ticker(self, inst_id: str):
        """
        订阅行情数据
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
        """
        if inst_id in self.subscribed_symbols:
            print(f"⚠️  已经订阅过 {inst_id}")
            return
        
        # 订阅行情
        await self.ws.subscribe_tickers(
            inst_id=inst_id,
            callback=self._on_ticker
        )
        
        self.subscribed_symbols.add(inst_id)
        print(f"✅ 订阅行情: {inst_id}")
    
    async def unsubscribe_ticker(self, inst_id: str):
        """
        取消订阅行情数据
        
        Args:
            inst_id: 产品ID
        """
        if inst_id not in self.subscribed_symbols:
            print(f"⚠️  未订阅 {inst_id}")
            return
        
        await self.ws.unsubscribe_tickers(inst_id)
        
        self.subscribed_symbols.remove(inst_id)
        print(f"✅ 取消订阅: {inst_id}")
    
    async def subscribe_candles(self, inst_id: str, interval: str = "1m"):
        """
        订阅K线数据
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            interval: K线间隔，如 1m, 5m, 1H, 1D等
        """
        # K线需要使用business端点，创建新的WebSocket连接
        if not hasattr(self, 'ws_business'):
            self.ws_business = OKXWebSocketPublic(is_demo=self.is_demo, url_type="business")
            await self.ws_business.connect()
        
        # 订阅K线
        await self.ws_business.subscribe_candles(
            inst_id=inst_id,
            interval=interval,
            callback=self._on_candle
        )
        
        print(f"✅ 订阅K线: {inst_id} ({interval})")
    
    async def subscribe_trades(self, inst_id: str):
        """
        订阅交易数据（逐笔成交）
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
        """
        # 交易数据使用public端点
        await self.ws.subscribe_trades(
            inst_id=inst_id,
            callback=self._on_trade
        )
        
        print(f"✅ 订阅交易数据: {inst_id}")
    
    def _on_ticker(self, message: Dict[str, Any]):
        """
        处理行情数据推送
        转换为TickerData事件并分发
        
        Args:
            message: WebSocket消息
        """
        try:
            arg = message['arg']
            data_list = message['data']
            
            for data in data_list:
                # 转换为TickerData事件
                ticker = TickerData(
                    exchange="OKX",
                    symbol=data['instId'],
                    last_price=float(data['last']),
                    last_size=float(data.get('lastSz', 0)),
                    bid_price=float(data['bidPx']) if data['bidPx'] else None,
                    bid_size=float(data['bidSz']) if data['bidSz'] else None,
                    ask_price=float(data['askPx']) if data['askPx'] else None,
                    ask_size=float(data['askSz']) if data['askSz'] else None,
                    high_24h=float(data['high24h']) if data['high24h'] else None,
                    low_24h=float(data['low24h']) if data['low24h'] else None,
                    volume_24h=float(data['vol24h']) if data['vol24h'] else None,
                    volume_ccy_24h=float(data['volCcy24h']) if data['volCcy24h'] else None,
                    open_24h=float(data['open24h']) if data['open24h'] else None,
                    timestamp=int(data['ts'])
                )
                
                # 通过事件引擎分发
                self.event_engine.put(ticker)
                
        except Exception as e:
            print(f"❌ 处理行情数据错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_candle(self, message: Dict[str, Any]):
        """
        处理K线数据推送
        转换为KlineData事件并分发
        
        Args:
            message: WebSocket消息
        """
        try:
            arg = message['arg']
            channel = arg['channel']
            inst_id = arg['instId']
            data_list = message['data']
            
            # 提取间隔信息
            interval = channel.replace('candle', '').replace('utc', '')
            
            for data in data_list:
                # OKX K线数据格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                kline = KlineData(
                    exchange="OKX",
                    symbol=inst_id,
                    interval=interval,
                    open=float(data[1]),
                    high=float(data[2]),
                    low=float(data[3]),
                    close=float(data[4]),
                    volume=float(data[5]),
                    turnover=float(data[6]) if len(data) > 6 else None,
                    timestamp=int(data[0])
                )
                
                # 通过事件引擎分发
                self.event_engine.put(kline)
                
        except Exception as e:
            print(f"❌ 处理K线数据错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_trade(self, message: Dict[str, Any]):
        """
        处理交易数据推送
        转换为TradeData事件并分发
        
        Args:
            message: WebSocket消息
        """
        try:
            arg = message['arg']
            data_list = message['data']
            
            for data in data_list:
                # 转换为TradeData事件
                trade = TradeData(
                    exchange="OKX",
                    symbol=data['instId'],
                    trade_id=data['tradeId'],
                    price=float(data['px']),
                    quantity=float(data['sz']),
                    side=data['side'],
                    timestamp=int(data['ts'])
                )
                
                # 通过事件引擎分发
                self.event_engine.put(trade)
                
        except Exception as e:
            print(f"❌ 处理交易数据错误: {e}")
            import traceback
            traceback.print_exc()


class OKXAccountDataAdapter(Component):
    """
    OKX 账户数据适配器
    订阅OKX账户数据（订单、持仓等），转换为内部事件并分发
    """
    
    def __init__(
        self,
        event_engine: EventEngine,
        api_key: str,
        secret_key: str,
        passphrase: str,
        is_demo: bool = False
    ):
        """
        初始化OKX账户数据适配器
        
        Args:
            event_engine: 事件引擎
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码
            is_demo: 是否为模拟盘
        """
        self.event_engine = event_engine
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        self.ws: Optional[OKXWebSocketPrivate] = None
    
    async def start(self):
        """启动适配器"""
        print("🚀 启动OKX账户数据适配器...")
        
        # 创建WebSocket客户端
        self.ws = OKXWebSocketPrivate(
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase,
            is_demo=self.is_demo
        )
        
        # 连接
        await self.ws.connect()
        
        # 登录
        await self.ws.login()
        
        # 等待登录完成
        await asyncio.sleep(1)
        
        print("✅ OKX账户数据适配器启动成功")
    
    async def stop(self):
        """停止适配器"""
        print("🛑 停止OKX账户数据适配器...")
        
        if self.ws:
            await self.ws.disconnect()
        
        print("✅ OKX账户数据适配器已停止")
    
    async def subscribe_orders(self, inst_type: str = "SPOT"):
        """
        订阅订单更新
        
        Args:
            inst_type: 产品类型
        """
        await self.ws.subscribe_orders(
            inst_type=inst_type,
            callback=self._on_order
        )
        print(f"✅ 订阅订单更新: {inst_type}")
    
    async def subscribe_account(self):
        """订阅账户更新"""
        await self.ws.subscribe_account(callback=self._on_account)
        print(f"✅ 订阅账户更新")
    
    def _on_order(self, message: Dict[str, Any]):
        """
        处理订单更新推送
        
        Args:
            message: WebSocket消息
        """
        try:
            print(f"📦 收到订单更新: {message}")
            # TODO: 转换为Order事件并分发
        except Exception as e:
            print(f"❌ 处理订单更新错误: {e}")
    
    def _on_account(self, message: Dict[str, Any]):
        """
        处理账户更新推送
        
        Args:
            message: WebSocket消息
        """
        try:
            print(f"📦 收到账户更新: {message}")
            # TODO: 转换为Account事件并分发
        except Exception as e:
            print(f"❌ 处理账户更新错误: {e}")

