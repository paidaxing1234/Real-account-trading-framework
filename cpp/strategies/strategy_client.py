#!/usr/bin/env python3
"""
Sequence 策略端客户端库 - 完整版

提供与实盘服务器通信的所有接口：
- 行情数据：trades, K线 (支持多币种、多周期订阅)
- 交易接口：下单、批量下单、撤单、批量撤单、修改订单
- 查询接口：账户余额、持仓信息、未成交订单
- 订单推送：实时订单状态更新

支持的产品类型：
- 现货 (SPOT): BTC-USDT, ETH-USDT
- 永续合约 (SWAP): BTC-USDT-SWAP, ETH-USDT-SWAP

@author Sequence Team
@date 2025-12
@version 2.0.0
"""

import zmq
import json
import time
import os
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# 数据结构定义
# ============================================================

class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"
    IOC = "ioc"
    FOK = "fok"


class TradingMode(Enum):
    """交易模式"""
    CASH = "cash"           # 现货
    CROSS = "cross"         # 全仓杠杆/合约
    ISOLATED = "isolated"   # 逐仓杠杆/合约


class PosSide(Enum):
    """持仓方向 (合约)"""
    LONG = "long"
    SHORT = "short"
    NET = "net"


@dataclass
class TradeData:
    """成交数据"""
    symbol: str
    trade_id: str
    price: float
    quantity: float
    side: str
    timestamp: int
    timestamp_ns: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'TradeData':
        return cls(
            symbol=data.get("symbol", ""),
            trade_id=data.get("trade_id", ""),
            price=float(data.get("price", 0)),
            quantity=float(data.get("quantity", 0)),
            side=data.get("side", ""),
            timestamp=int(data.get("timestamp", 0)),
            timestamp_ns=int(data.get("timestamp_ns", 0))
        )


@dataclass
class KlineData:
    """K线数据"""
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: int
    timestamp_ns: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'KlineData':
        return cls(
            symbol=data.get("symbol", ""),
            interval=data.get("interval", ""),
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", 0)),
            volume=float(data.get("volume", 0)),
            timestamp=int(data.get("timestamp", 0)),
            timestamp_ns=int(data.get("timestamp_ns", 0))
        )


@dataclass
class OrderReport:
    """订单回报"""
    type: str                       # 类型: order_report, batch_report, cancel_report, etc.
    strategy_id: str
    client_order_id: str = ""
    exchange_order_id: str = ""
    symbol: str = ""
    status: str = ""
    filled_price: float = 0.0
    filled_quantity: float = 0.0
    fee: float = 0.0
    error_msg: str = ""
    timestamp: int = 0
    # 批量订单相关
    batch_id: str = ""
    results: List[dict] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'OrderReport':
        return cls(
            type=data.get("type", "order_report"),
            strategy_id=data.get("strategy_id", ""),
            client_order_id=data.get("client_order_id", ""),
            exchange_order_id=data.get("exchange_order_id", ""),
            symbol=data.get("symbol", ""),
            status=data.get("status", ""),
            filled_price=float(data.get("filled_price", 0)),
            filled_quantity=float(data.get("filled_quantity", 0)),
            fee=float(data.get("fee", 0)),
            error_msg=data.get("error_msg", ""),
            timestamp=int(data.get("timestamp", 0)),
            batch_id=data.get("batch_id", ""),
            results=data.get("results", []),
            success_count=int(data.get("success_count", 0)),
            fail_count=int(data.get("fail_count", 0))
        )

    def is_success(self) -> bool:
        return self.status in ["accepted", "filled", "partial", "cancelled", "amended"]

    def is_filled(self) -> bool:
        return self.status == "filled"

    def is_rejected(self) -> bool:
        return self.status == "rejected"


@dataclass
class OrderRequest:
    """订单请求"""
    symbol: str
    side: str
    order_type: str = "limit"
    quantity: float = 0.0
    price: float = 0.0
    td_mode: str = "cash"
    pos_side: str = ""          # 合约持仓方向: long/short
    tgt_ccy: str = ""           # 目标货币
    client_order_id: str = ""


# ============================================================
# IPC 地址配置
# ============================================================

class IpcAddresses:
    """IPC 通道地址"""
    MARKET_DATA = "ipc:///tmp/trading_md.ipc"
    ORDER = "ipc:///tmp/trading_order.ipc"
    REPORT = "ipc:///tmp/trading_report.ipc"
    QUERY = "ipc:///tmp/trading_query.ipc"
    SUBSCRIBE = "ipc:///tmp/trading_sub.ipc"


# ============================================================
# 策略客户端
# ============================================================

class StrategyClient:
    """
    策略端客户端 - 完整版
    
    功能：
    - 行情订阅 (trades, K线)
    - 交易 (下单、撤单、修改订单)
    - 查询 (账户、持仓、订单)
    """

    def __init__(self, strategy_id: str = "default"):
        self.strategy_id = strategy_id
        self.context = zmq.Context()
        
        # Sockets
        self._market_sub: Optional[zmq.Socket] = None
        self._order_push: Optional[zmq.Socket] = None
        self._report_sub: Optional[zmq.Socket] = None
        self._query_req: Optional[zmq.Socket] = None
        self._subscribe_push: Optional[zmq.Socket] = None
        
        self.running = False
        
        # 统计
        self._trade_count = 0
        self._kline_count = 0
        self._funding_rate_count = 0
        self._order_count = 0
        self._report_count = 0

    # ========================================
    # 连接管理
    # ========================================

    def connect(self) -> bool:
        """连接到实盘服务器"""
        try:
            # 行情订阅 (SUB)
            self._market_sub = self.context.socket(zmq.SUB)
            self._market_sub.connect(IpcAddresses.MARKET_DATA)
            self._market_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self._market_sub.setsockopt(zmq.RCVTIMEO, 100)
            
            # 订单发送 (PUSH)
            self._order_push = self.context.socket(zmq.PUSH)
            self._order_push.connect(IpcAddresses.ORDER)
            
            # 回报订阅 (SUB)
            self._report_sub = self.context.socket(zmq.SUB)
            self._report_sub.connect(IpcAddresses.REPORT)
            self._report_sub.setsockopt_string(zmq.SUBSCRIBE, "")
            self._report_sub.setsockopt(zmq.RCVTIMEO, 100)
            
            # 查询通道 (REQ)
            self._query_req = self.context.socket(zmq.REQ)
            self._query_req.connect(IpcAddresses.QUERY)
            self._query_req.setsockopt(zmq.RCVTIMEO, 5000)
            
            # 订阅管理 (PUSH)
            self._subscribe_push = self.context.socket(zmq.PUSH)
            self._subscribe_push.connect(IpcAddresses.SUBSCRIBE)
            
            self.running = True
            return True
            
        except zmq.ZMQError as e:
            print(f"[错误] 连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        self.running = False
        for sock in [self._market_sub, self._order_push, self._report_sub,
                     self._query_req, self._subscribe_push]:
            if sock:
                sock.close()

    # ========================================
    # 行情订阅管理
    # ========================================

    def subscribe_trades(self, symbol: str) -> bool:
        """订阅 trades 数据"""
        return self._send_subscription("subscribe", "trades", symbol)

    def unsubscribe_trades(self, symbol: str) -> bool:
        """取消订阅 trades"""
        return self._send_subscription("unsubscribe", "trades", symbol)

    def subscribe_kline(self, symbol: str, interval: str = "1m") -> bool:
        """
        订阅 K线数据
        
        Args:
            symbol: 交易对
            interval: K线周期 (1s/1m/3m/5m/15m/30m/1H/2H/4H/6H/12H/1D/1W/1M)
        """
        return self._send_subscription("subscribe", "kline", symbol, interval)

    def unsubscribe_kline(self, symbol: str, interval: str = "1m") -> bool:
        """取消订阅 K线"""
        return self._send_subscription("unsubscribe", "kline", symbol, interval)

    def subscribe_funding_rate(self, symbol: str) -> bool:
        """
        订阅资金费率数据
        
        资金费率用于永续合约，30秒到90秒内推送一次数据
        
        Args:
            symbol: 合约交易对，如 "BTC-USDT-SWAP", "ETH-USDT-SWAP"
        """
        return self._send_subscription("subscribe", "funding_rate", symbol)

    def unsubscribe_funding_rate(self, symbol: str) -> bool:
        """取消订阅资金费率数据"""
        return self._send_subscription("unsubscribe", "funding_rate", symbol)

    def _send_subscription(self, action: str, channel: str, 
                          symbol: str, interval: str = "") -> bool:
        if not self._subscribe_push:
            return False
        try:
            msg = {
                "action": action,
                "channel": channel,
                "symbol": symbol,
                "interval": interval,
                "strategy_id": self.strategy_id,
                "timestamp": int(time.time() * 1000)
            }
            self._subscribe_push.send_string(json.dumps(msg))
            return True
        except zmq.ZMQError:
            return False

    # ========================================
    # 行情接收
    # ========================================

    def recv_market(self) -> Optional[dict]:
        """接收任意行情数据（非阻塞）"""
        if not self._market_sub:
            return None
        try:
            msg = self._market_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            msg_type = data.get("type", "")
            if msg_type == "trade":
                self._trade_count += 1
            elif msg_type == "kline":
                self._kline_count += 1
            elif msg_type == "funding_rate":
                self._funding_rate_count += 1
            return data
        except zmq.Again:
            return None
        except json.JSONDecodeError:
            return None

    def recv_trade(self) -> Optional[TradeData]:
        """接收 trades 数据（非阻塞）"""
        data = self.recv_market()
        if data and data.get("type") == "trade":
            return TradeData.from_dict(data)
        return None

    def recv_kline(self) -> Optional[KlineData]:
        """接收 K线数据（非阻塞）"""
        data = self.recv_market()
        if data and data.get("type") == "kline":
            return KlineData.from_dict(data)
        return None

    def recv_funding_rate(self) -> Optional[dict]:
        """
        接收资金费率数据（非阻塞）
        
        Returns:
            dict: 资金费率数据，包含 funding_rate, next_funding_rate, funding_time 等
        """
        data = self.recv_market()
        if data and data.get("type") == "funding_rate":
            return data
        return None

    # ========================================
    # 下单接口
    # ========================================

    def send_order(self, request: OrderRequest) -> str:
        """发送订单请求"""
        if not self._order_push:
            return ""
        
        client_order_id = request.client_order_id
        if not client_order_id:
            client_order_id = f"{self.strategy_id}{int(time.time()*1000) % 100000000}"
        
        order = {
            "type": "order_request",
            "strategy_id": self.strategy_id,
            "client_order_id": client_order_id,
            "symbol": request.symbol,
            "side": request.side,
            "order_type": request.order_type,
            "quantity": request.quantity,
            "price": request.price,
            "td_mode": request.td_mode,
            "pos_side": request.pos_side,
            "tgt_ccy": request.tgt_ccy,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._order_push.send_string(json.dumps(order))
            self._order_count += 1
            return client_order_id
        except zmq.ZMQError:
            return ""

    # ========================================
    # 现货下单便捷方法
    # ========================================

    def buy_market(self, symbol: str, quantity: float, 
                   tgt_ccy: str = "quote_ccy") -> str:
        """现货市价买入"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="buy", order_type="market",
            quantity=quantity, td_mode="cash", tgt_ccy=tgt_ccy
        ))

    def sell_market(self, symbol: str, quantity: float,
                    tgt_ccy: str = "base_ccy") -> str:
        """现货市价卖出"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="sell", order_type="market",
            quantity=quantity, td_mode="cash", tgt_ccy=tgt_ccy
        ))

    def buy_limit(self, symbol: str, quantity: float, price: float) -> str:
        """现货限价买入"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="buy", order_type="limit",
            quantity=quantity, price=price, td_mode="cash"
        ))

    def sell_limit(self, symbol: str, quantity: float, price: float) -> str:
        """现货限价卖出"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="sell", order_type="limit",
            quantity=quantity, price=price, td_mode="cash"
        ))

    # ========================================
    # 合约下单便捷方法
    # ========================================

    def swap_buy_market(self, symbol: str, quantity: float, 
                        pos_side: str = "") -> str:
        """
        合约市价开多
        
        Args:
            symbol: 合约交易对 (如 BTC-USDT-SWAP)
            quantity: 张数
            pos_side: 持仓方向 ("long" 双向持仓时需要)
        """
        return self.send_order(OrderRequest(
            symbol=symbol, side="buy", order_type="market",
            quantity=quantity, td_mode="cross", pos_side=pos_side
        ))

    def swap_sell_market(self, symbol: str, quantity: float,
                         pos_side: str = "") -> str:
        """合约市价开空"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="sell", order_type="market",
            quantity=quantity, td_mode="cross", pos_side=pos_side
        ))

    def swap_buy_limit(self, symbol: str, quantity: float, 
                       price: float, pos_side: str = "") -> str:
        """合约限价开多"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="buy", order_type="limit",
            quantity=quantity, price=price, td_mode="cross", pos_side=pos_side
        ))

    def swap_sell_limit(self, symbol: str, quantity: float,
                        price: float, pos_side: str = "") -> str:
        """合约限价开空"""
        return self.send_order(OrderRequest(
            symbol=symbol, side="sell", order_type="limit",
            quantity=quantity, price=price, td_mode="cross", pos_side=pos_side
        ))

    # ========================================
    # 批量下单
    # ========================================

    def batch_orders(self, orders: List[OrderRequest]) -> str:
        """
        批量下单 (最多20个)
        
        Args:
            orders: 订单列表
        
        Returns:
            批量ID
        """
        if not self._order_push or not orders:
            return ""
        
        batch_id = f"batch{self.strategy_id}{int(time.time()*1000) % 100000000}"
        
        order_list = []
        for i, req in enumerate(orders[:20]):
            order_list.append({
                "symbol": req.symbol,
                "side": req.side,
                "order_type": req.order_type,
                "quantity": req.quantity,
                "price": req.price,
                "td_mode": req.td_mode,
                "pos_side": req.pos_side,
                "client_order_id": req.client_order_id or f"{batch_id}{i}"
            })
        
        batch = {
            "type": "batch_order_request",
            "strategy_id": self.strategy_id,
            "batch_id": batch_id,
            "orders": order_list,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._order_push.send_string(json.dumps(batch))
            self._order_count += len(order_list)
            return batch_id
        except zmq.ZMQError:
            return ""

    # ========================================
    # 撤单接口
    # ========================================

    def cancel_order(self, symbol: str, order_id: str = "",
                     client_order_id: str = "") -> str:
        """撤销单个订单"""
        if not self._order_push:
            return ""
        
        request_id = f"cancel{int(time.time()*1000) % 100000000}"
        
        cancel = {
            "type": "cancel_request",
            "strategy_id": self.strategy_id,
            "request_id": request_id,
            "symbol": symbol,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._order_push.send_string(json.dumps(cancel))
            return request_id
        except zmq.ZMQError:
            return ""

    def batch_cancel(self, symbol: str, order_ids: List[str]) -> str:
        """批量撤单"""
        if not self._order_push or not order_ids:
            return ""
        
        request_id = f"bcancel{int(time.time()*1000) % 100000000}"
        
        cancel = {
            "type": "batch_cancel_request",
            "strategy_id": self.strategy_id,
            "request_id": request_id,
            "symbol": symbol,
            "order_ids": order_ids[:20],
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._order_push.send_string(json.dumps(cancel))
            return request_id
        except zmq.ZMQError:
            return ""

    # ========================================
    # 修改订单接口
    # ========================================

    def amend_order(self, symbol: str, order_id: str = "",
                    client_order_id: str = "",
                    new_price: float = 0.0,
                    new_quantity: float = 0.0) -> str:
        """修改订单"""
        if not self._order_push:
            return ""
        
        request_id = f"amend{int(time.time()*1000) % 100000000}"
        
        amend = {
            "type": "amend_request",
            "strategy_id": self.strategy_id,
            "request_id": request_id,
            "symbol": symbol,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "new_price": str(new_price) if new_price > 0 else "",
            "new_quantity": str(new_quantity) if new_quantity > 0 else "",
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._order_push.send_string(json.dumps(amend))
            return request_id
        except zmq.ZMQError:
            return ""

    # ========================================
    # 回报接收
    # ========================================

    def recv_report(self) -> Optional[OrderReport]:
        """接收订单回报（非阻塞）"""
        if not self._report_sub:
            return None
        try:
            msg = self._report_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self._report_count += 1
            return OrderReport.from_dict(data)
        except zmq.Again:
            return None
        except json.JSONDecodeError:
            return None

    def recv_report_raw(self) -> Optional[dict]:
        """接收原始回报数据"""
        if not self._report_sub:
            return None
        try:
            msg = self._report_sub.recv_string(zmq.NOBLOCK)
            data = json.loads(msg)
            self._report_count += 1
            return data
        except zmq.Again:
            return None
        except json.JSONDecodeError:
            return None

    # ========================================
    # 查询接口（同步）
    # ========================================

    def query_account(self, currency: str = "") -> Optional[dict]:
        """
        查询账户余额
        
        Args:
            currency: 币种 (空=全部)
        
        Returns:
            账户信息 (OKX原始格式)
        """
        return self._query("account", {"currency": currency})

    def query_positions(self, inst_type: str = "SWAP",
                        symbol: str = "") -> Optional[dict]:
        """
        查询持仓信息
        
        Args:
            inst_type: 产品类型 (SWAP/FUTURES/MARGIN)
            symbol: 交易对 (空=全部)
        """
        return self._query("positions", {"inst_type": inst_type, "symbol": symbol})

    def query_pending_orders(self, inst_type: str = "SPOT",
                             symbol: str = "") -> Optional[dict]:
        """
        查询未成交订单
        
        Args:
            inst_type: 产品类型 (SPOT/SWAP)
            symbol: 交易对 (空=全部)
        """
        return self._query("pending_orders", {"inst_type": inst_type, "symbol": symbol})

    def query_order(self, symbol: str, order_id: str = "",
                    client_order_id: str = "") -> Optional[dict]:
        """查询单个订单"""
        return self._query("order", {
            "symbol": symbol, "order_id": order_id,
            "client_order_id": client_order_id
        })

    def _query(self, query_type: str, params: dict) -> Optional[dict]:
        """发送查询请求"""
        if not self._query_req:
            return None
        
        request = {
            "type": "query_request",
            "query_type": query_type,
            "strategy_id": self.strategy_id,
            "params": params,
            "timestamp": int(time.time() * 1000)
        }
        
        try:
            self._query_req.send_string(json.dumps(request))
            response = self._query_req.recv_string()
            return json.loads(response)
        except (zmq.ZMQError, json.JSONDecodeError) as e:
            print(f"[查询错误] {e}")
            return None

    # ========================================
    # 统计信息
    # ========================================

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def kline_count(self) -> int:
        return self._kline_count

    @property
    def funding_rate_count(self) -> int:
        return self._funding_rate_count

    @property
    def order_count(self) -> int:
        return self._order_count

    @property
    def report_count(self) -> int:
        return self._report_count


# ============================================================
# 策略基类
# ============================================================

class BaseStrategy:
    """
    策略基类
    
    继承此类实现策略，需要实现 on_trade 方法
    """

    def __init__(self, strategy_id: str = "default"):
        self.strategy_id = strategy_id
        self.client = StrategyClient(strategy_id)

    # 生命周期
    def on_init(self): pass
    def on_start(self): pass
    def on_stop(self): pass

    # 事件回调
    def on_trade(self, trade: TradeData):
        raise NotImplementedError("请实现 on_trade 方法")

    def on_kline(self, kline: KlineData):
        pass

    def on_funding_rate(self, funding_rate: dict):
        """处理资金费率数据（可选覆盖）"""
        pass

    def on_report(self, report: OrderReport):
        pass

    # 交易便捷方法
    def buy_market(self, symbol: str, quantity: float, **kwargs) -> str:
        return self.client.buy_market(symbol, quantity, **kwargs)

    def sell_market(self, symbol: str, quantity: float, **kwargs) -> str:
        return self.client.sell_market(symbol, quantity, **kwargs)

    def buy_limit(self, symbol: str, quantity: float, price: float) -> str:
        return self.client.buy_limit(symbol, quantity, price)

    def sell_limit(self, symbol: str, quantity: float, price: float) -> str:
        return self.client.sell_limit(symbol, quantity, price)

    def cancel_order(self, symbol: str, order_id: str = "",
                     client_order_id: str = "") -> str:
        return self.client.cancel_order(symbol, order_id, client_order_id)

    # 合约交易
    def swap_buy(self, symbol: str, quantity: float, 
                 price: float = 0, pos_side: str = "") -> str:
        if price > 0:
            return self.client.swap_buy_limit(symbol, quantity, price, pos_side)
        return self.client.swap_buy_market(symbol, quantity, pos_side)

    def swap_sell(self, symbol: str, quantity: float,
                  price: float = 0, pos_side: str = "") -> str:
        if price > 0:
            return self.client.swap_sell_limit(symbol, quantity, price, pos_side)
        return self.client.swap_sell_market(symbol, quantity, pos_side)

    # 查询
    def query_account(self, currency: str = "") -> Optional[dict]:
        return self.client.query_account(currency)

    def query_positions(self, **kwargs) -> Optional[dict]:
        return self.client.query_positions(**kwargs)

    # 日志
    def log(self, message: str):
        print(f"[{self.strategy_id}] {message}")


# ============================================================
# 策略运行器
# ============================================================

def run_strategy(strategy: BaseStrategy):
    """运行策略"""
    import signal
    
    if not strategy.client.connect():
        print("[错误] 无法连接到交易服务器")
        return
    
    strategy.on_init()
    strategy.on_start()
    
    def signal_handler(signum, frame):
        strategy.client.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"[策略] {strategy.strategy_id} 已启动")
    
    try:
        while strategy.client.running:
            # 接收行情
            data = strategy.client.recv_market()
            if data:
                if data.get("type") == "trade":
                    strategy.on_trade(TradeData.from_dict(data))
                elif data.get("type") == "kline":
                    strategy.on_kline(KlineData.from_dict(data))
                elif data.get("type") == "funding_rate":
                    strategy.on_funding_rate(data)
            
            # 接收回报
            report = strategy.client.recv_report()
            if report:
                strategy.on_report(report)
            
            time.sleep(0.001)
            
    except Exception as e:
        print(f"[异常] {e}")
    finally:
        strategy.on_stop()
        strategy.client.disconnect()
        print(f"[策略] {strategy.strategy_id} 已停止")


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("策略客户端库已加载")
    print("使用方法: from strategy_client import StrategyClient, BaseStrategy")
