# Core 核心模块

参考 HftBacktest 框架设计，提供实盘交易的核心基础设施。

## 📁 模块结构

```
core/
├── __init__.py          # 模块导出
├── event_engine.py      # 事件引擎（核心）
├── order.py             # 订单模型
├── data.py              # 数据模型
└── README.md            # 本文档
```

## 🔧 核心组件

### 1. EventEngine（事件引擎）

**作用**：事件驱动架构的核心，负责事件的分发和管理。

**关键类**：
- `Event`: 事件基类
- `EventEngine`: 事件引擎
- `Component`: 组件基类

**使用示例**：

```python
from core import EventEngine, Event, Component

# 创建引擎
engine = EventEngine()

# 定义组件
class MyComponent(Component):
    def start(self, engine):
        self.engine = engine
        engine.register(Event, self.on_event)
    
    def on_event(self, event):
        print(f"收到事件: {event}")
    
    def stop(self):
        pass

# 启动组件
component = MyComponent()
component.start(engine)

# 推送事件
event = Event(timestamp=1000)
engine.put(event)
```

**核心特性**：
- ✅ 事件按时间戳顺序处理
- ✅ 支持类型化监听（只监听特定事件）
- ✅ 支持全局监听（监听所有事件）
- ✅ 防止死循环（ignore_self参数）
- ✅ 动态接口注入（方便组件间协作）

---

### 2. Order（订单模型）

**作用**：定义订单的数据结构和状态机。

**关键类**：
- `Order`: 订单类（继承自Event）
- `OrderType`: 订单类型枚举
- `OrderSide`: 买卖方向枚举
- `OrderState`: 订单状态枚举

**使用示例**：

```python
from core import Order, OrderSide, OrderState

# 创建限价买单
order = Order.buy_limit(
    symbol="BTC-USDT-SWAP",
    quantity=0.01,
    price=50000
)

print(order)
# Order(id=0, exchange=okx, symbol=BTC-USDT-SWAP, 
#       side=BUY, type=LIMIT, price=50000, qty=0.01, 
#       filled=0.0, state=CREATED)

# 更新订单状态
order.state = OrderState.ACCEPTED
order.exchange_order_id = "123456789"

# 部分成交
order.state = OrderState.PARTIALLY_FILLED
order.filled_quantity = 0.005
order.filled_price = 50100

# 完全成交
order.state = OrderState.FILLED
order.filled_quantity = 0.01
```

**订单状态流转**：

```
CREATED（本地创建）
    ↓
SUBMITTED（已提交到交易所）
    ↓
ACCEPTED（交易所已接受）
    ↓
PARTIALLY_FILLED（部分成交）
    ↓
FILLED（完全成交）

或者：
ACCEPTED → CANCELLED（已取消）
SUBMITTED → REJECTED（被拒绝）
```

**工厂方法**：
- `Order.buy_limit()` - 限价买单
- `Order.sell_limit()` - 限价卖单
- `Order.buy_market()` - 市价买单
- `Order.sell_market()` - 市价卖单

---

### 3. Data（数据模型）

**作用**：封装各类市场数据。

**关键类**：
- `Data`: 数据基类（继承自Event）
- `TickerData`: 行情快照
- `TradeData`: 逐笔成交
- `OrderBookData`: 订单簿
- `KlineData`: K线数据

**使用示例**：

```python
from core import TickerData, TradeData, OrderBookData

# 行情数据
ticker = TickerData(
    symbol="BTC-USDT-SWAP",
    last_price=50000,
    bid_price=49999,
    ask_price=50001,
    volume_24h=10000
)
print(f"中间价: {ticker.mid_price}")
print(f"价差: {ticker.spread}")

# 逐笔成交
trade = TradeData(
    symbol="BTC-USDT-SWAP",
    trade_id="12345",
    price=50000,
    quantity=0.01,
    side="buy"
)

# 订单簿
orderbook = OrderBookData(
    symbol="BTC-USDT-SWAP",
    bids=[(49999, 1.0), (49998, 2.0)],
    asks=[(50001, 1.5), (50002, 2.0)]
)
print(f"最优买价: {orderbook.best_bid}")
print(f"最优卖价: {orderbook.best_ask}")
```

---

## 🎯 设计理念

### 1. 事件驱动

所有模块通过事件通信，实现松耦合：

```
组件A → Event → EventEngine → Event → 组件B
```

### 2. 组件化

所有功能模块继承 `Component` 基类，统一生命周期：

```python
class MyComponent(Component):
    def start(self, engine):
        """启动时注册监听器"""
        pass
    
    def stop(self):
        """停止时清理资源"""
        pass
```

### 3. 类型安全

使用枚举和类型注解，提高代码可靠性：

```python
OrderType.LIMIT     # 而不是字符串 "limit"
OrderSide.BUY       # 而不是字符串 "buy"
OrderState.FILLED   # 而不是字符串 "filled"
```

---

## 🧪 测试

每个模块都包含测试代码，可以直接运行：

```bash
# 测试事件引擎
python -m backend.core.event_engine

# 测试订单模型
python -m backend.core.order

# 测试数据模型
python -m backend.core.data
```

---

## 📚 下一步

基于这些核心组件，你可以：

1. **实现交易所适配器**（`adapters/okx/`）
   - WebSocket连接
   - REST API封装
   - 消息转换

2. **实现策略层**（`strategies/`）
   - 策略基类
   - 具体策略实现

3. **实现工具层**（`utils/`）
   - 账户管理
   - 风控模块
   - 数据记录

---

## 💡 参考资料

- HftBacktest 框架：`/Users/wuyh/Desktop/Sequence/Real-account-trading-framework/HftBacktest-main`
- 事件驱动模式：观察者模式的高级应用
- 组件化设计：单一职责原则

