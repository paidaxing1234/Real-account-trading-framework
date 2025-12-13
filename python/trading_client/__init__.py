"""
Trading Client - Python 策略客户端库

这是一个用于连接 C++ 交易服务器的 Python 客户端库。
通过 ZeroMQ IPC 与服务器通信，延迟约 30-100μs。

使用方法：
    from trading_client import TradingClient, Strategy
    
    class MyStrategy(Strategy):
        def on_ticker(self, data):
            print(f"收到行情: {data.symbol} {data.last_price}")
            
            if data.last_price > 45000:
                self.buy_limit(data.symbol, 0.001, data.bid_price)
    
    if __name__ == "__main__":
        client = TradingClient(strategy_id="my_strategy")
        client.run(MyStrategy())

作者: Sequence Team
日期: 2024-12
"""

from .client import TradingClient
from .strategy import Strategy
from .models import TickerData, OrderReport, OrderRequest

__version__ = "1.0.0"
__all__ = [
    "TradingClient",
    "Strategy", 
    "TickerData",
    "OrderReport",
    "OrderRequest"
]

