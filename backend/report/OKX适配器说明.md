# 什么是OKX适配器？

## 🎯 简单理解

**OKX适配器** = 你的框架和OKX交易所之间的"翻译官"

```
你的策略（说"中文"）
    ↓
OKX适配器（翻译官）
    ↓
OKX交易所（说"OKX语言"）
```

---

## 📊 详细示例

### 场景1：策略想下单

```python
# 1. 策略发出订单（使用内部Order对象）
order = Order.buy_limit(
    symbol="BTC-USDT-SWAP",
    quantity=0.01,
    price=50000
)
order.state = OrderState.SUBMITTED
engine.put(order)  # 推送到事件引擎
```

```
    ↓ 事件引擎分发
```

```python
# 2. OKX适配器监听到Order事件
class OKXAdapter(Component):
    def on_order(self, order: Order):
        if order.state == OrderState.SUBMITTED:
            # 翻译成OKX API的格式
            okx_request = {
                "instId": "BTC-USDT-SWAP",
                "tdMode": "cross",
                "side": "buy",
                "ordType": "limit",
                "px": "50000",
                "sz": "0.01"
            }
            
            # 调用OKX REST API
            response = self.rest_api.place_order(okx_request)
            
            # 更新订单状态
            order.exchange_order_id = response['ordId']
            order.state = OrderState.ACCEPTED
            engine.put(order.derive())  # 推送更新后的订单
```

```
    ↓ 发送到OKX交易所
```

```
OKX交易所收到请求，返回：
{
    "code": "0",
    "msg": "",
    "data": [{
        "ordId": "123456789",
        "sCode": "0",
        "sMsg": ""
    }]
}
```

---

### 场景2：OKX推送订单成交

```
OKX交易所通过WebSocket推送：
{
    "arg": {"channel": "orders", "instId": "BTC-USDT-SWAP"},
    "data": [{
        "ordId": "123456789",
        "state": "filled",
        "fillPx": "50100",
        "fillSz": "0.01",
        ...
    }]
}
```

```
    ↓ OKX适配器接收
```

```python
# OKX适配器解析WebSocket消息
class OKXAdapter(Component):
    def handle_ws_order_message(self, msg):
        # 翻译成内部Order对象
        order = Order(
            exchange_order_id=msg['data'][0]['ordId'],
            symbol="BTC-USDT-SWAP",
            state=OrderState.FILLED,  # "filled" → OrderState.FILLED
            filled_quantity=float(msg['data'][0]['fillSz']),
            filled_price=float(msg['data'][0]['fillPx']),
            ...
        )
        
        # 推送到事件引擎
        engine.put(order)
```

```
    ↓ 事件引擎分发
```

```python
# 策略收到成交通知
class MyStrategy(Component):
    def on_order(self, order: Order):
        if order.state == OrderState.FILLED:
            print(f"订单成交了！价格={order.filled_price}")
```

---

## 🏗️ OKX适配器的结构

```python
adapters/okx/
├── __init__.py
│
├── websocket.py           # WebSocket连接管理
│   └── class OKXWebSocket:
│       ├── connect()           # 连接
│       ├── login()             # 登录
│       ├── subscribe()         # 订阅频道
│       ├── on_message()        # 接收消息
│       └── reconnect()         # 自动重连
│
├── rest_api.py            # REST API封装
│   └── class OKXRestAPI:
│       ├── place_order()       # 下单
│       ├── cancel_order()      # 撤单
│       ├── get_order()         # 查询订单
│       ├── get_balance()       # 查询余额
│       └── get_positions()     # 查询持仓
│
└── adapter.py             # 适配器组件（整合WebSocket和REST）
    └── class OKXAdapter(Component):
        ├── start(engine)       # 启动
        ├── on_order()          # 监听内部订单 → 发送到OKX
        ├── handle_ws_msg()     # 接收OKX推送 → 转换为内部事件
        └── stop()              # 停止
```

---

## 🔄 完整数据流

```
┌─────────────────────────────────────────────────────────────┐
│                     实盘交易完整流程                          │
└─────────────────────────────────────────────────────────────┘

1️⃣ 行情数据流
OKX交易所
    ↓ WebSocket推送ticker
OKXAdapter.handle_ws_message()
    ↓ 解析并转换
TickerData事件
    ↓ engine.put(ticker)
EventEngine分发
    ↓
Strategy.on_ticker(ticker)
    ↓ 策略逻辑判断
    
2️⃣ 下单流程
Strategy决定下单
    ↓ 创建Order对象
Order事件 (state=SUBMITTED)
    ↓ engine.put(order)
EventEngine分发
    ↓
OKXAdapter.on_order(order)
    ↓ 调用REST API
OKX交易所
    ↓ 返回orderId
Order事件 (state=ACCEPTED, exchange_order_id=xxx)
    ↓ engine.put(order)
Strategy.on_order(order) # 知道订单被接受了

3️⃣ 成交推送
OKX交易所成交
    ↓ WebSocket推送order update
OKXAdapter.handle_ws_message()
    ↓ 解析成交信息
Order事件 (state=FILLED)
    ↓ engine.put(order)
EventEngine分发
    ↓
├→ Strategy.on_order(order)     # 策略知道成交了
├→ Account.on_order(order)      # 账户更新持仓
└→ Recorder.on_order(order)     # 记录器记录成交
```

---

## 💡 为什么需要适配器？

### 1. 解耦

**没有适配器**：策略直接调用OKX API
```python
# ❌ 不好的设计
class Strategy:
    def on_ticker(self, ticker):
        # 直接调用OKX API
        okx_client.place_order(...)
```

**有适配器**：策略只需要推送事件
```python
# ✅ 好的设计
class Strategy:
    def on_ticker(self, ticker):
        # 只推送事件，不关心具体交易所
        order = Order.buy_limit(...)
        self.engine.put(order)
```

### 2. 可扩展

如果要支持币安，只需要添加 `BinanceAdapter`，策略代码不用改：

```
Strategy
    ↓ Order事件
EventEngine
    ↓ 分发给所有监听器
    ├→ OKXAdapter → OKX交易所
    └→ BinanceAdapter → 币安交易所
```

### 3. 统一接口

不同交易所的API格式不同，适配器统一转换：

```python
# OKX的下单参数
{
    "instId": "BTC-USDT-SWAP",
    "tdMode": "cross",
    "side": "buy",
    "ordType": "limit",
    "px": "50000",
    "sz": "0.01"
}

# 币安的下单参数
{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": "50000",
    "quantity": "0.01"
}

# 但在框架内部都是同一个Order对象
Order.buy_limit("BTC-USDT-SWAP", 0.01, 50000)
```

---

## 🎯 总结

**OKX适配器的职责**：

1. **向下**：把内部事件 → 转换为OKX API调用
   - Order事件 → REST API下单
   - 查询请求 → REST API查询

2. **向上**：把OKX推送 → 转换为内部事件
   - WebSocket订单推送 → Order事件
   - WebSocket行情推送 → TickerData事件

3. **连接管理**：
   - WebSocket连接和重连
   - 登录认证
   - 心跳保持

4. **错误处理**：
   - API错误捕获
   - 重试机制
   - 异常告警

---

**简单记忆**：
> OKX适配器 = 你和OKX之间的"插头转接器"  
> 策略说人话，适配器帮你翻译成OKX能理解的话

