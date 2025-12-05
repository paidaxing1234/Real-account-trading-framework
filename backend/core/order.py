"""
订单模型
定义订单的数据结构、状态、类型等
"""

from enum import Enum, auto
from typing import Optional
from itertools import count

from .event_engine import Event


class OrderType(Enum):
    """订单类型"""
    LIMIT = auto()      # 限价单
    MARKET = auto()     # 市价单
    POST_ONLY = auto()  # 只做Maker（Post-only）
    FOK = auto()        # 全部成交或立即取消（Fill-or-Kill）
    IOC = auto()        # 立即成交并取消剩余（Immediate-or-Cancel）


class OrderSide(Enum):
    """订单方向"""
    BUY = auto()   # 买入
    SELL = auto()  # 卖出


class OrderState(Enum):
    """
    订单生命周期状态
    
    状态转换：
    CREATED → SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED
                                  → CANCELLED
    """
    CREATED = auto()            # 本地创建
    SUBMITTED = auto()          # 已提交到交易所
    ACCEPTED = auto()           # 交易所已接受
    PARTIALLY_FILLED = auto()   # 部分成交
    FILLED = auto()             # 完全成交
    CANCELLED = auto()          # 已取消
    REJECTED = auto()           # 被拒绝
    FAILED = auto()             # 失败


class Order(Event):
    """
    订单事件
    
    既是数据模型，也是事件
    订单的任何状态变化都会作为事件在引擎中流转
    """
    
    # 订单ID生成器（全局唯一）
    _ID_GEN = count()
    
    __slots__ = (
        "order_id",              # 本地订单ID
        "client_order_id",       # 客户端订单ID（发送给交易所）
        "exchange_order_id",     # 交易所订单ID
        "exchange",              # 交易所名称（okx, binance）
        "symbol",                # 交易对（如 BTC-USDT-SWAP）
        "order_type",            # 订单类型
        "side",                  # 买卖方向
        "price",                 # 价格
        "quantity",              # 数量
        "filled_quantity",       # 已成交数量
        "filled_price",          # 成交均价
        "state",                 # 订单状态
        "fee",                   # 手续费
        "fee_currency",          # 手续费币种
        "create_time",           # 创建时间
        "update_time",           # 更新时间
        "error_msg",             # 错误信息
    )
    
    def __init__(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        exchange: str = "okx",
        state: OrderState = OrderState.CREATED,
        filled_quantity: float = 0.0,
        filled_price: Optional[float] = None,
        fee: float = 0.0,
        fee_currency: Optional[str] = None,
        create_time: Optional[int] = None,
        update_time: Optional[int] = None,
        error_msg: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        # 基本信息
        self.order_id = order_id if order_id is not None else next(self._ID_GEN)
        self.client_order_id = client_order_id or f"order_{self.order_id}"
        self.exchange_order_id = exchange_order_id
        self.exchange = exchange
        
        # 订单参数
        self.symbol = symbol
        self.order_type = order_type
        self.side = side
        self.price = price
        self.quantity = quantity
        
        # 成交信息
        self.filled_quantity = filled_quantity
        self.filled_price = filled_price
        
        # 状态
        self.state = state
        
        # 费用
        self.fee = fee
        self.fee_currency = fee_currency
        
        # 时间
        self.create_time = create_time
        self.update_time = update_time
        
        # 错误信息
        self.error_msg = error_msg
    
    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id}, "
            f"exchange={self.exchange}, "
            f"symbol={self.symbol}, "
            f"side={self.side.name}, "
            f"type={self.order_type.name}, "
            f"price={self.price}, "
            f"qty={self.quantity}, "
            f"filled={self.filled_quantity}, "
            f"state={self.state.name})"
        )
    
    @property
    def is_buy(self) -> bool:
        """是否为买单"""
        return self.side == OrderSide.BUY
    
    @property
    def is_sell(self) -> bool:
        """是否为卖单"""
        return self.side == OrderSide.SELL
    
    @property
    def is_filled(self) -> bool:
        """是否完全成交"""
        return self.state == OrderState.FILLED
    
    @property
    def is_active(self) -> bool:
        """是否为活跃状态（未成交或部分成交）"""
        return self.state in (
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED
        )
    
    @property
    def is_final(self) -> bool:
        """是否为最终状态（成交、取消、拒绝、失败）"""
        return self.state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.FAILED
        )
    
    @property
    def remaining_quantity(self) -> float:
        """剩余未成交数量"""
        return self.quantity - self.filled_quantity
    
    # ========== 工厂方法 ==========
    
    @classmethod
    def limit_order(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        exchange: str = "okx",
        **kwargs
    ) -> "Order":
        """
        创建限价单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            quantity: 数量
            price: 价格
            exchange: 交易所
        
        Returns:
            Order实例
        """
        return cls(
            symbol=symbol,
            order_type=OrderType.LIMIT,
            side=side,
            quantity=quantity,
            price=price,
            exchange=exchange,
            **kwargs
        )
    
    @classmethod
    def market_order(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: float,
        exchange: str = "okx",
        **kwargs
    ) -> "Order":
        """
        创建市价单
        
        Args:
            symbol: 交易对
            side: 买卖方向
            quantity: 数量
            exchange: 交易所
        
        Returns:
            Order实例
        """
        return cls(
            symbol=symbol,
            order_type=OrderType.MARKET,
            side=side,
            quantity=quantity,
            price=None,
            exchange=exchange,
            **kwargs
        )
    
    @classmethod
    def buy_limit(cls, symbol: str, quantity: float, price: float, **kwargs) -> "Order":
        """限价买单快捷方法"""
        return cls.limit_order(symbol, OrderSide.BUY, quantity, price, **kwargs)
    
    @classmethod
    def sell_limit(cls, symbol: str, quantity: float, price: float, **kwargs) -> "Order":
        """限价卖单快捷方法"""
        return cls.limit_order(symbol, OrderSide.SELL, quantity, price, **kwargs)
    
    @classmethod
    def buy_market(cls, symbol: str, quantity: float, **kwargs) -> "Order":
        """市价买单快捷方法"""
        return cls.market_order(symbol, OrderSide.BUY, quantity, **kwargs)
    
    @classmethod
    def sell_market(cls, symbol: str, quantity: float, **kwargs) -> "Order":
        """市价卖单快捷方法"""
        return cls.market_order(symbol, OrderSide.SELL, quantity, **kwargs)


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Order 模型测试")
    print("=" * 60)
    
    # 测试限价单
    print("\n1. 创建限价买单:")
    order1 = Order.buy_limit("BTC-USDT-SWAP", quantity=0.01, price=50000)
    print(order1)
    
    # 测试市价单
    print("\n2. 创建市价卖单:")
    order2 = Order.sell_market("BTC-USDT-SWAP", quantity=0.01)
    print(order2)
    
    # 测试属性
    print("\n3. 订单属性:")
    print(f"   是否买单: {order1.is_buy}")
    print(f"   是否活跃: {order1.is_active}")
    print(f"   是否最终: {order1.is_final}")
    print(f"   剩余数量: {order1.remaining_quantity}")
    
    # 测试状态更新
    print("\n4. 更新订单状态:")
    order1.state = OrderState.ACCEPTED
    order1.exchange_order_id = "123456789"
    print(f"   {order1}")
    
    order1.state = OrderState.PARTIALLY_FILLED
    order1.filled_quantity = 0.005
    print(f"   {order1}")
    
    order1.state = OrderState.FILLED
    order1.filled_quantity = 0.01
    order1.filled_price = 50100
    print(f"   {order1}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

