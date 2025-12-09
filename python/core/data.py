"""
数据模型
定义行情、交易等数据事件
"""

from typing import Any, Optional
from .event_engine import Event


class Data(Event):
    """
    数据事件基类
    
    用于封装各类市场数据：
    - ticker: 行情数据
    - trades: 成交数据
    - orderbook: 订单簿数据
    - kline: K线数据
    等
    """
    
    __slots__ = (
        "name",      # 数据类型名称（如 'ticker', 'trades'）
        "symbol",    # 交易对
        "exchange",  # 交易所
        "data",      # 实际数据（字典或对象）
    )
    
    def __init__(
        self,
        name: str,
        symbol: Optional[str] = None,
        exchange: str = "okx",
        data: Any = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.name = name
        self.symbol = symbol
        self.exchange = exchange
        self.data = data
    
    def __repr__(self) -> str:
        return (
            f"Data(name={self.name}, "
            f"symbol={self.symbol}, "
            f"exchange={self.exchange}, "
            f"timestamp={self.timestamp})"
        )


class TickerData(Data):
    """
    行情快照数据
    
    包含最新价、买卖价、成交量等
    """
    
    __slots__ = (
        "last_price",     # 最新价
        "bid_price",      # 买一价
        "ask_price",      # 卖一价
        "bid_size",       # 买一量
        "ask_size",       # 卖一量
        "volume_24h",     # 24小时成交量
        "high_24h",       # 24小时最高价
        "low_24h",        # 24小时最低价
        "open_24h",       # 24小时开盘价
    )
    
    def __init__(
        self,
        symbol: str,
        last_price: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        bid_size: Optional[float] = None,
        ask_size: Optional[float] = None,
        volume_24h: Optional[float] = None,
        high_24h: Optional[float] = None,
        low_24h: Optional[float] = None,
        open_24h: Optional[float] = None,
        exchange: str = "okx",
        **kwargs  # 忽略额外参数
    ):
        # 不传递kwargs给父类，避免参数错误
        super().__init__(name="ticker", symbol=symbol, exchange=exchange)
        
        self.last_price = last_price
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_size = bid_size
        self.ask_size = ask_size
        self.volume_24h = volume_24h
        self.high_24h = high_24h
        self.low_24h = low_24h
        self.open_24h = open_24h
    
    def __repr__(self) -> str:
        return (
            f"TickerData(symbol={self.symbol}, "
            f"last={self.last_price}, "
            f"bid={self.bid_price}, "
            f"ask={self.ask_price}, "
            f"timestamp={self.timestamp})"
        )
    
    @property
    def mid_price(self) -> Optional[float]:
        """中间价"""
        if self.bid_price and self.ask_price:
            return (self.bid_price + self.ask_price) / 2
        return self.last_price
    
    @property
    def spread(self) -> Optional[float]:
        """买卖价差"""
        if self.bid_price and self.ask_price:
            return self.ask_price - self.bid_price
        return None


class TradeData(Data):
    """
    逐笔成交数据
    """
    
    __slots__ = (
        "trade_id",       # 成交ID
        "price",          # 成交价
        "quantity",       # 成交量
        "side",           # 成交方向（买/卖）
        "is_buyer_maker", # 是否买方为Maker
    )
    
    def __init__(
        self,
        symbol: str,
        trade_id: str,
        price: float,
        quantity: float,
        side: Optional[str] = None,
        is_buyer_maker: Optional[bool] = None,
        exchange: str = "okx",
        **kwargs
    ):
        super().__init__(name="trade", symbol=symbol, exchange=exchange, **kwargs)
        
        self.trade_id = trade_id
        self.price = price
        self.quantity = quantity
        self.side = side
        self.is_buyer_maker = is_buyer_maker
    
    def __repr__(self) -> str:
        return (
            f"TradeData(symbol={self.symbol}, "
            f"price={self.price}, "
            f"qty={self.quantity}, "
            f"side={self.side}, "
            f"timestamp={self.timestamp})"
        )


class OrderBookData(Data):
    """
    订单簿数据
    """
    
    __slots__ = (
        "bids",  # 买盘 [(price, size), ...]
        "asks",  # 卖盘 [(price, size), ...]
    )
    
    def __init__(
        self,
        symbol: str,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        exchange: str = "okx",
        **kwargs
    ):
        super().__init__(name="orderbook", symbol=symbol, exchange=exchange, **kwargs)
        
        self.bids = bids  # [(price, size), ...] 按价格从高到低
        self.asks = asks  # [(price, size), ...] 按价格从低到高
    
    def __repr__(self) -> str:
        return (
            f"OrderBookData(symbol={self.symbol}, "
            f"bids_depth={len(self.bids)}, "
            f"asks_depth={len(self.asks)}, "
            f"timestamp={self.timestamp})"
        )
    
    @property
    def best_bid(self) -> Optional[tuple[float, float]]:
        """最优买价"""
        return self.bids[0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[tuple[float, float]]:
        """最优卖价"""
        return self.asks[0] if self.asks else None
    
    @property
    def mid_price(self) -> Optional[float]:
        """中间价"""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid and best_ask:
            return (best_bid[0] + best_ask[0]) / 2
        return None
    
    @property
    def spread(self) -> Optional[float]:
        """价差"""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid and best_ask:
            return best_ask[0] - best_bid[0]
        return None


class KlineData(Data):
    """
    K线数据
    """
    
    __slots__ = (
        "interval",  # 时间间隔（如 '1m', '5m', '1h'）
        "open",      # 开盘价
        "high",      # 最高价
        "low",       # 最低价
        "close",     # 收盘价
        "volume",    # 成交量
        "turnover",  # 成交额
    )
    
    def __init__(
        self,
        symbol: str,
        interval: str,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        turnover: Optional[float] = None,
        exchange: str = "okx",
        **kwargs
    ):
        super().__init__(name="kline", symbol=symbol, exchange=exchange, **kwargs)
        
        self.interval = interval
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.turnover = turnover
    
    def __repr__(self) -> str:
        return (
            f"KlineData(symbol={self.symbol}, "
            f"interval={self.interval}, "
            f"O={self.open}, H={self.high}, L={self.low}, C={self.close}, "
            f"V={self.volume}, "
            f"timestamp={self.timestamp})"
        )


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    import time
    
    print("=" * 60)
    print("Data 模型测试")
    print("=" * 60)
    
    current_ts = int(time.time() * 1000)
    
    # 测试 TickerData
    print("\n1. TickerData:")
    ticker = TickerData(
        symbol="BTC-USDT-SWAP",
        last_price=50000,
        bid_price=49999,
        ask_price=50001,
        bid_size=1.5,
        ask_size=2.0,
        volume_24h=10000,
        timestamp=current_ts
    )
    print(ticker)
    print(f"   中间价: {ticker.mid_price}")
    print(f"   价差: {ticker.spread}")
    
    # 测试 TradeData
    print("\n2. TradeData:")
    trade = TradeData(
        symbol="BTC-USDT-SWAP",
        trade_id="12345",
        price=50000,
        quantity=0.01,
        side="buy",
        timestamp=current_ts
    )
    print(trade)
    
    # 测试 OrderBookData
    print("\n3. OrderBookData:")
    orderbook = OrderBookData(
        symbol="BTC-USDT-SWAP",
        bids=[(49999, 1.0), (49998, 2.0), (49997, 1.5)],
        asks=[(50001, 1.5), (50002, 2.0), (50003, 1.0)],
        timestamp=current_ts
    )
    print(orderbook)
    print(f"   最优买价: {orderbook.best_bid}")
    print(f"   最优卖价: {orderbook.best_ask}")
    print(f"   中间价: {orderbook.mid_price}")
    print(f"   价差: {orderbook.spread}")
    
    # 测试 KlineData
    print("\n4. KlineData:")
    kline = KlineData(
        symbol="BTC-USDT-SWAP",
        interval="1m",
        open=49900,
        high=50100,
        low=49800,
        close=50000,
        volume=100.5,
        timestamp=current_ts
    )
    print(kline)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

