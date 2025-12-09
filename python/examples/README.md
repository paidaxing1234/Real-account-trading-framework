# 使用示例

本目录包含各种使用示例，展示如何使用实盘交易框架。

---

## 📁 文件列表

### 1. websocket_market_data_example.py
WebSocket行情数据（Tickers频道）使用示例

**包含示例**：
1. **基础使用** - 单个策略监控BTC价格
2. **多策略系统** - 多个组件同时工作（策略、监控、记录）
3. **动态订阅管理** - 运行时动态添加/取消订阅

**运行方式**：
```bash
cd backend
python examples/websocket_market_data_example.py
```

**需要环境**：
- Python 3.8+
- websockets库
- 稳定的网络连接

---

### 2. multi_channel_strategy_example.py
多频道综合策略示例

**功能**：
- 同时使用Tickers、Candles、Trades三个频道
- 多数据源综合决策
- 订单流分析
- 风险监控

**展示内容**：
1. **多频道订阅** - 同时订阅行情、K线、交易数据
2. **趋势判断** - 基于K线识别趋势
3. **订单流分析** - 统计买卖比例
4. **综合决策** - 结合多个数据源做决策
5. **风险监控** - 监控价格波动和大单

**运行方式**：
```bash
cd backend
python examples/multi_channel_strategy_example.py
```

**数据源**：
- Tickers: 实时价格和买卖盘
- Candles: 1分钟K线
- Trades: 逐笔成交

**策略逻辑**：
```
1. K线判断趋势（连续3根）
2. Ticker监控实时价格
3. Trades分析订单流
4. 综合判断做多/做空信号
```

---

## 🚀 快速开始

### 1. 基础WebSocket使用

最简单的方式获取实时行情：

```python
import asyncio
from adapters.okx import OKXWebSocketPublic

async def main():
    # 创建客户端（模拟盘）
    ws = OKXWebSocketPublic(is_demo=True)
    
    # 连接
    await ws.connect()
    
    # 定义回调函数
    def on_ticker(message):
        data = message['data'][0]
        print(f"{data['instId']}: {data['last']}")
    
    # 订阅行情
    await ws.subscribe_tickers("BTC-USDT", callback=on_ticker)
    
    # 运行
    await asyncio.sleep(60)
    
    # 断开
    await ws.disconnect()

asyncio.run(main())
```

### 2. 使用适配器（推荐）

更好的方式是使用适配器和事件引擎：

```python
import asyncio
from core import EventEngine, TickerData
from adapters.okx import OKXMarketDataAdapter

async def main():
    # 创建事件引擎
    engine = EventEngine()
    
    # 创建适配器
    adapter = OKXMarketDataAdapter(
        event_engine=engine,
        is_demo=True
    )
    
    # 定义策略
    def on_ticker(event: TickerData):
        print(f"{event.symbol}: {event.last_price}")
        
        # 你的交易逻辑
        if event.last_price < 90000:
            print("  → 买入信号")
    
    # 注册监听器
    engine.register(TickerData, on_ticker)
    
    # 启动
    await adapter.start()
    
    # 订阅
    await adapter.subscribe_ticker("BTC-USDT")
    
    # 运行
    await asyncio.sleep(300)
    
    # 停止
    await adapter.stop()

asyncio.run(main())
```

---

## 📚 示例说明

### 示例1: 基础使用

展示最基本的使用方式：
- 创建EventEngine和适配器
- 注册事件监听器
- 订阅行情
- 接收和处理数据

**适合场景**：
- 学习框架基础
- 单个策略
- 快速原型开发

### 示例2: 多策略系统

展示如何构建完整的交易系统：
- 多个策略组件并行运行
- 价格监控组件
- 数据记录组件
- 所有组件共享同一个EventEngine

**适合场景**：
- 生产环境部署
- 多策略并行
- 需要数据记录和监控

### 示例3: 动态订阅管理

展示运行时管理订阅：
- 启动时订阅部分产品
- 运行中动态添加订阅
- 运行中取消订阅

**适合场景**：
- 需要动态调整监控列表
- 资源优化
- 灵活的策略切换

---

## 🎯 最佳实践

### 1. 事件驱动架构

**推荐**：使用EventEngine解耦各个组件

```python
# 好的做法 ✅
class Strategy:
    def on_ticker(self, event: TickerData):
        # 处理行情
        pass

engine.register(TickerData, strategy.on_ticker)
```

**不推荐**：直接在回调中编写复杂逻辑

```python
# 不好的做法 ❌
def callback(message):
    # 大量复杂逻辑
    # 难以维护和测试
    pass
```

### 2. 错误处理

始终添加错误处理：

```python
def on_ticker(self, event: TickerData):
    try:
        # 你的逻辑
        self.process_ticker(event)
    except Exception as e:
        print(f"错误: {e}")
        # 记录日志或发送告警
```

### 3. 资源管理

确保正确关闭资源：

```python
try:
    await adapter.start()
    await asyncio.sleep(300)
finally:
    await adapter.stop()
```

### 4. 数据记录

如果需要持久化数据，使用缓冲区：

```python
class DataRecorder:
    def __init__(self):
        self.buffer = []
        self.buffer_size = 1000
    
    def on_ticker(self, event: TickerData):
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            self.flush_to_database()
```

---

## 🔧 常见问题

### Q: 如何订阅多个产品？

```python
await adapter.subscribe_ticker("BTC-USDT")
await adapter.subscribe_ticker("ETH-USDT")
await adapter.subscribe_ticker("SOL-USDT")
```

### Q: 如何取消订阅？

```python
await adapter.unsubscribe_ticker("BTC-USDT")
```

### Q: 如何知道连接状态？

适配器会自动管理连接，并在连接/断开时打印日志：
- `✅ WebSocket连接成功`
- `❌ WebSocket连接失败`
- `🔄 尝试重新连接...`

### Q: 如何处理断线？

适配器会自动重连，你不需要手动处理。重连成功后会自动重新订阅之前的频道。

### Q: 数据推送频率是多少？

OKX行情数据最快100ms推送一次。没有成交或价格变动时不推送。

---

## 📊 性能优化建议

### 1. 只订阅需要的产品

不要订阅过多的产品，会增加网络和处理负载。

### 2. 使用异步处理

确保回调函数处理速度快，不要阻塞：

```python
# 如果处理耗时，使用异步
async def on_ticker(self, event: TickerData):
    await self.async_process(event)

# 或者使用线程池
def on_ticker(self, event: TickerData):
    self.executor.submit(self.slow_process, event)
```

### 3. 批量写入数据库

不要每次都写数据库，使用缓冲区批量写入。

### 4. 合理使用EventEngine

不要注册过多的监听器，每个事件都会触发所有监听器。

---

## 🎓 进阶主题

### 1. 自定义策略组件

```python
from core import Component

class MyStrategy(Component):
    def __init__(self, engine):
        self.engine = engine
        engine.register(TickerData, self.on_ticker)
    
    def on_ticker(self, event: TickerData):
        # 你的策略逻辑
        pass
```

### 2. 集成REST API

将WebSocket行情和REST API交易结合：

```python
from adapters.okx import OKXRestAPI, OKXMarketDataAdapter

# REST API客户端（交易）
rest_client = OKXRestAPI(api_key, secret_key, passphrase, is_demo=True)

# WebSocket适配器（行情）
market_adapter = OKXMarketDataAdapter(engine, is_demo=True)

def on_ticker(event: TickerData):
    if event.last_price < 90000:
        # 使用REST API下单
        rest_client.place_order(
            inst_id="BTC-USDT",
            td_mode="cash",
            side="buy",
            ord_type="limit",
            px="90000",
            sz="0.01"
        )
```

### 3. 多交易所支持

当添加更多交易所时，架构保持不变：

```python
# OKX
okx_adapter = OKXMarketDataAdapter(engine, is_demo=True)
await okx_adapter.subscribe_ticker("BTC-USDT")

# Binance (未来)
# binance_adapter = BinanceMarketDataAdapter(engine)
# await binance_adapter.subscribe_ticker("BTCUSDT")

# 策略自动接收所有交易所的数据
```

---

## 📞 获取帮助

- 查看 [API接口文档.md](../report/API接口文档.md)
- 查看 [WebSocket行情接口实现总结.md](../report/WebSocket行情接口实现总结.md)
- 查看源代码注释
- 运行示例代码学习

---

**祝交易顺利！** 🚀

