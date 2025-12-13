"""
数据模型定义

本模块定义了交易系统中使用的所有数据结构：
- TickerData: 行情快照数据
- OrderRequest: 订单请求
- OrderReport: 订单回报

使用 dataclass 实现，提供：
- 自动生成 __init__, __repr__, __eq__ 等方法
- 类型提示支持
- 序列化/反序列化方法

作者: Sequence Team
日期: 2024-12
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum
import time


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"    # 买入
    SELL = "sell"  # 卖出


class OrderType(str, Enum):
    """订单类型"""
    LIMIT = "limit"        # 限价单
    MARKET = "market"      # 市价单
    POST_ONLY = "post_only"  # 只做 Maker


class OrderStatus(str, Enum):
    """订单状态"""
    CREATED = "created"        # 本地创建
    SUBMITTED = "submitted"    # 已提交
    ACCEPTED = "accepted"      # 已接受（交易所确认）
    FILLED = "filled"          # 已成交
    PARTIAL = "partial"        # 部分成交
    CANCELLED = "cancelled"    # 已取消
    REJECTED = "rejected"      # 被拒绝


@dataclass
class TickerData:
    """
    行情快照数据
    
    包含交易对的最新价格、买卖盘口信息。
    这是策略最常用的数据类型。
    
    属性：
        symbol: 交易对，如 "BTC-USDT"
        last_price: 最新成交价
        bid_price: 买一价（最高买价）
        ask_price: 卖一价（最低卖价）
        bid_size: 买一量
        ask_size: 卖一量
        volume_24h: 24小时成交量
        timestamp: 时间戳（毫秒）
        timestamp_ns: 时间戳（纳秒）- 用于精确延迟测量
    
    示例：
        ticker = TickerData(
            symbol="BTC-USDT",
            last_price=43250.5,
            bid_price=43250.0,
            ask_price=43251.0
        )
        
        # 计算买卖价差
        spread = ticker.spread()  # 1.0
        
        # 中间价
        mid = ticker.mid_price()  # 43250.5
    """
    symbol: str                         # 交易对
    last_price: float                   # 最新价
    bid_price: float = 0.0              # 买一价
    ask_price: float = 0.0              # 卖一价
    bid_size: float = 0.0               # 买一量
    ask_size: float = 0.0               # 卖一量
    volume_24h: float = 0.0             # 24小时成交量
    timestamp: int = 0                  # 时间戳（毫秒）
    timestamp_ns: int = 0               # 时间戳（纳秒）- 用于延迟测量
    
    def spread(self) -> float:
        """
        计算买卖价差
        
        价差 = 卖一价 - 买一价
        价差越小，流动性越好
        
        返回：价差
        """
        return self.ask_price - self.bid_price
    
    def spread_bps(self) -> float:
        """
        计算买卖价差（基点）
        
        价差基点 = (卖一价 - 买一价) / 中间价 * 10000
        
        返回：价差基点数
        """
        mid = self.mid_price()
        if mid == 0:
            return 0.0
        return (self.ask_price - self.bid_price) / mid * 10000
    
    def mid_price(self) -> float:
        """
        计算中间价
        
        中间价 = (买一价 + 卖一价) / 2
        
        返回：中间价
        """
        return (self.bid_price + self.ask_price) / 2
    
    @classmethod
    def from_dict(cls, data: dict) -> "TickerData":
        """
        从字典创建 TickerData 对象
        
        参数：
            data: 包含行情数据的字典
            
        返回：TickerData 对象
        """
        return cls(
            symbol=data.get("symbol", ""),
            last_price=float(data.get("last_price", 0)),
            bid_price=float(data.get("bid_price", 0)),
            ask_price=float(data.get("ask_price", 0)),
            bid_size=float(data.get("bid_size", 0)),
            ask_size=float(data.get("ask_size", 0)),
            volume_24h=float(data.get("volume_24h", 0)),
            timestamp=int(data.get("timestamp", 0)),
            timestamp_ns=int(data.get("timestamp_ns", 0))  # 纳秒时间戳用于延迟测量
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


@dataclass
class OrderRequest:
    """
    订单请求
    
    策略向交易服务器发送的订单请求。
    
    属性：
        strategy_id: 策略ID，用于识别订单来源
        client_order_id: 客户端订单ID，用于订单追踪
        symbol: 交易对
        side: 订单方向（buy/sell）
        order_type: 订单类型（limit/market）
        price: 价格（限价单必填）
        quantity: 数量
        timestamp: 时间戳（毫秒）
    
    示例：
        # 创建限价买单
        order = OrderRequest(
            strategy_id="my_strategy",
            symbol="BTC-USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=43000.0,
            quantity=0.001
        )
    """
    strategy_id: str                           # 策略ID
    symbol: str                                # 交易对
    side: str                                  # 方向: "buy" / "sell"
    order_type: str = "limit"                  # 类型: "limit" / "market"
    price: float = 0.0                         # 价格
    quantity: float = 0.0                      # 数量
    client_order_id: str = ""                  # 客户端订单ID（自动生成）
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    
    def __post_init__(self):
        """初始化后处理：自动生成订单ID"""
        if not self.client_order_id:
            # ⚠️ OKX 要求 clOrdId 只能是字母和数字，不能有下划线！
            # 格式: {strategyid}{timestamp}{随机数} (全部连在一起，无分隔符)
            import random
            safe_strategy_id = self.strategy_id.replace("_", "").replace("-", "")
            self.client_order_id = f"{safe_strategy_id}{self.timestamp}{random.randint(1000, 9999)}"
    
    def to_dict(self) -> dict:
        """
        转换为字典
        
        用于 JSON 序列化发送给服务器
        """
        return {
            "type": "order_request",
            "strategy_id": self.strategy_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "OrderRequest":
        """从字典创建"""
        return cls(
            strategy_id=data.get("strategy_id", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", "buy"),
            order_type=data.get("order_type", "limit"),
            price=float(data.get("price", 0)),
            quantity=float(data.get("quantity", 0)),
            client_order_id=data.get("client_order_id", ""),
            timestamp=int(data.get("timestamp", 0))
        )


@dataclass
class OrderReport:
    """
    订单回报
    
    交易服务器返回的订单执行结果。
    
    属性：
        strategy_id: 策略ID
        client_order_id: 客户端订单ID
        exchange_order_id: 交易所订单ID
        symbol: 交易对
        status: 订单状态（accepted/filled/cancelled/rejected）
        filled_price: 成交价格
        filled_quantity: 成交数量
        fee: 手续费
        error_msg: 错误信息（如果失败）
        timestamp: 时间戳（毫秒）
        timestamp_ns: 时间戳（纳秒）- 用于延迟测量
    
    示例：
        report = OrderReport.from_dict(data)
        
        if report.is_success():
            print(f"订单成功: {report.exchange_order_id}")
        else:
            print(f"订单失败: {report.error_msg}")
    """
    strategy_id: str                          # 策略ID
    client_order_id: str                      # 客户端订单ID
    exchange_order_id: str = ""               # 交易所订单ID
    symbol: str = ""                          # 交易对
    status: str = ""                          # 状态
    filled_price: float = 0.0                 # 成交价
    filled_quantity: float = 0.0              # 成交量
    fee: float = 0.0                          # 手续费
    error_msg: str = ""                       # 错误信息
    timestamp: int = 0                        # 时间戳（毫秒）
    timestamp_ns: int = 0                     # 时间戳（纳秒）- 用于延迟测量
    
    def is_success(self) -> bool:
        """
        检查订单是否成功
        
        返回：True 如果状态是 accepted 或 filled
        """
        return self.status in ("accepted", "filled", "partial")
    
    def is_filled(self) -> bool:
        """
        检查订单是否已成交
        
        返回：True 如果状态是 filled
        """
        return self.status == "filled"
    
    def is_rejected(self) -> bool:
        """
        检查订单是否被拒绝
        
        返回：True 如果状态是 rejected
        """
        return self.status == "rejected"
    
    @classmethod
    def from_dict(cls, data: dict) -> "OrderReport":
        """从字典创建"""
        return cls(
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
            timestamp_ns=int(data.get("timestamp_ns", 0))  # 纳秒时间戳用于延迟测量
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

