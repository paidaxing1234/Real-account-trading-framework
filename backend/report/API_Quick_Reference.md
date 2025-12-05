# OKX 实盘交易框架 - API快速参考

**版本**: v2.1.0  
**更新日期**: 2024-12-04

---

## 📊 快速索引

- [REST API](#rest-api) - 17个接口
- [WebSocket](#websocket) - 3个频道
- [事件类型](#事件类型) - 5种事件
- [使用示例](#使用示例)

---

## REST API

### 交易接口（9个）

| 方法 | 功能 | 限速 |
|------|------|------|
| `place_order()` | 下单 | 60次/2s |
| `place_batch_orders()` | 批量下单 | 300个/2s |
| `cancel_order()` | 撤单 | 60次/2s |
| `cancel_batch_orders()` | 批量撤单 | 300个/2s |
| `amend_order()` | 修改订单 | 60次/2s |
| `amend_batch_orders()` | 批量修改订单 | 300个/2s |
| `get_order()` | 查询订单详情 | 60次/2s |
| `get_orders_pending()` | 查询未成交订单 | 60次/2s |
| `get_orders_history()` | 查询历史订单（7天） | 40次/2s |

### 账户接口（6个）

| 方法 | 功能 | 限速 |
|------|------|------|
| `get_balance()` | 查询余额 | 10次/2s |
| `get_positions()` | 查询持仓 | 10次/2s |
| `get_positions_history()` | 查询历史持仓（3个月） | 10次/2s |
| `get_account_instruments()` | 获取可交易产品 | 20次/2s |
| `get_bills()` | 账单流水（7天） | 5次/s |
| `get_bills_archive()` | 账单流水（3个月） | 5次/2s |

### 行情接口（2个）

| 方法 | 功能 | 限速 |
|------|------|------|
| `get_ticker()` | 获取行情 | 20次/2s |
| `get_instruments()` | 获取产品信息 | 20次/2s |

---

## WebSocket

### 公共频道（3个）

| 频道 | 方法 | 推送频率 | 数据类型 |
|------|------|----------|----------|
| tickers | `subscribe_tickers()` | 最快100ms | TickerData |
| candles | `subscribe_candles()` | 最快1秒 | KlineData |
| trades | `subscribe_trades()` | 实时 | TradeData |

### K线间隔（17种）

```
1s, 1m, 3m, 5m, 15m, 30m
1H, 2H, 4H, 6H, 12H
1D, 2D, 3D, 5D
1W, 1M, 3M
```

---

## 事件类型

### TickerData
```python
TickerData(
    symbol="BTC-USDT",
    last_price=95000.0,
    bid_price=94999.0,
    ask_price=95001.0,
    volume_24h=1234.56
)
```

### KlineData
```python
KlineData(
    symbol="BTC-USDT",
    interval="1m",
    open=95000.0,
    high=95100.0,
    low=94900.0,
    close=95050.0,
    volume=123.45
)
```

### TradeData
```python
TradeData(
    symbol="BTC-USDT",
    trade_id="123456",
    price=95000.0,
    quantity=0.5,
    side="buy"
)
```

---

## 使用示例

### REST API - 完整交易流程

```python
from adapters.okx import OKXRestAPI

# 创建客户端
client = OKXRestAPI(api_key, secret_key, passphrase, is_demo=True)

# 1. 查询余额
balance = client.get_balance(ccy="USDT")

# 2. 下单
order = client.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",
    side="buy",
    ord_type="limit",
    px="90000",
    sz="0.01"
)

# 3. 查询订单
order_info = client.get_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId']
)

# 4. 修改订单
client.amend_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId'],
    new_px="90500"
)

# 5. 撤单
client.cancel_order(
    inst_id="BTC-USDT",
    ord_id=order['data'][0]['ordId']
)
```

### WebSocket - 实时数据监控

```python
import asyncio
from core import EventEngine, TickerData, KlineData, TradeData
from adapters.okx import OKXMarketDataAdapter

async def main():
    # 创建引擎和适配器
    engine = EventEngine()
    adapter = OKXMarketDataAdapter(engine, is_demo=True)
    
    # 定义事件处理
    def on_ticker(event: TickerData):
        print(f"价格: {event.last_price}")
    
    def on_kline(event: KlineData):
        print(f"K线: C={event.close}")
    
    def on_trade(event: TradeData):
        print(f"成交: {event.side} {event.quantity}")
    
    # 注册监听
    engine.register(TickerData, on_ticker)
    engine.register(KlineData, on_kline)
    engine.register(TradeData, on_trade)
    
    # 启动并订阅
    await adapter.start()
    await adapter.subscribe_ticker("BTC-USDT")
    await adapter.subscribe_candles("BTC-USDT", "1m")
    await adapter.subscribe_trades("BTC-USDT")
    
    # 运行
    await asyncio.sleep(300)
    await adapter.stop()

asyncio.run(main())
```

### 综合使用 - REST + WebSocket

```python
from adapters.okx import OKXRestAPI, OKXMarketDataAdapter
from core import EventEngine, TickerData

# REST API客户端（交易）
rest = OKXRestAPI(api_key, secret_key, passphrase, is_demo=True)

# WebSocket适配器（行情）
engine = EventEngine()
ws_adapter = OKXMarketDataAdapter(engine, is_demo=True)

# 策略：低于90000买入
def on_ticker(event: TickerData):
    if event.last_price < 90000:
        # 使用REST API下单
        rest.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px=str(event.last_price),
            sz="0.01"
        )
        print("已下单")

engine.register(TickerData, on_ticker)

# 启动并订阅
await ws_adapter.start()
await ws_adapter.subscribe_ticker("BTC-USDT")
```

---

## 🎯 常用代码片段

### 1. 初始化

```python
# REST API
from adapters.okx import OKXRestAPI
client = OKXRestAPI(api_key, secret_key, passphrase, is_demo=True)

# WebSocket
from core import EventEngine
from adapters.okx import OKXMarketDataAdapter

engine = EventEngine()
adapter = OKXMarketDataAdapter(engine, is_demo=True)
await adapter.start()
```

### 2. 下单

```python
# 限价单
client.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",
    side="buy",
    ord_type="limit",
    px="90000",
    sz="0.01"
)

# 市价单
client.place_order(
    inst_id="BTC-USDT",
    td_mode="cash",
    side="buy",
    ord_type="market",
    sz="100",  # 100 USDT
    tgt_ccy="quote_ccy"
)
```

### 3. 批量操作

```python
# 批量下单
orders = [
    {"instId": "BTC-USDT", "tdMode": "cash", "side": "buy", 
     "ordType": "limit", "px": "90000", "sz": "0.01"},
    {"instId": "ETH-USDT", "tdMode": "cash", "side": "buy", 
     "ordType": "limit", "px": "3000", "sz": "0.1"}
]
client.place_batch_orders(orders)

# 批量撤单
client.cancel_batch_orders([
    {"instId": "BTC-USDT", "ordId": "123456"},
    {"instId": "ETH-USDT", "ordId": "123457"}
])
```

### 4. 查询

```python
# 查询余额
balance = client.get_balance(ccy="USDT")

# 查询持仓
positions = client.get_positions(inst_type="MARGIN")

# 查询未成交订单
pending = client.get_orders_pending(inst_type="SPOT")

# 查询历史订单
history = client.get_orders_history(
    inst_type="SPOT",
    state="filled",
    limit="50"
)
```

### 5. 订阅WebSocket

```python
# 订阅行情
await adapter.subscribe_ticker("BTC-USDT")

# 订阅K线
await adapter.subscribe_candles("BTC-USDT", "1m")
await adapter.subscribe_candles("BTC-USDT", "5m")

# 订阅交易
await adapter.subscribe_trades("BTC-USDT")

# 取消订阅
await adapter.unsubscribe_ticker("BTC-USDT")
```

---

## 🔧 配置

### API密钥

```python
API_KEY = "your_api_key"
SECRET_KEY = "your_secret_key"
PASSPHRASE = "your_passphrase"
IS_DEMO = True  # True=模拟盘, False=实盘
```

### URL

**REST API**:
- 实盘: `https://www.okx.com`
- 模拟盘: `https://www.okx.com` (Header: `x-simulated-trading: 1`)

**WebSocket**:
- Public实盘: `wss://ws.okx.com:8443/ws/v5/public`
- Public模拟盘: `wss://wspap.okx.com:8443/ws/v5/public`
- Business实盘: `wss://ws.okx.com:8443/ws/v5/business`
- Business模拟盘: `wss://wspap.okx.com:8443/ws/v5/business`

---

## 📚 完整文档

详细文档请查看：
- [API接口文档.md](./API接口文档.md) - REST API完整参考
- [WebSocket行情接口实现总结.md](./WebSocket行情接口实现总结.md) - WebSocket基础
- [WebSocket_Candles_Trades_实现总结.md](./WebSocket_Candles_Trades_实现总结.md) - K线和交易频道
- [README.md](./README.md) - 使用指南

示例代码：
- `examples/websocket_market_data_example.py` - 行情数据示例
- `examples/multi_channel_strategy_example.py` - 多频道策略示例

---

**快速开始，轻松交易！** 🚀

