# 深度频道实现说明

> 更新日期: 2025-12-17

## 已实现功能

### 1. WebSocket 深度频道支持

✅ **支持的频道类型：**
- `books5` - 5档深度，推送频率100ms（推荐）
- `books` - 400档深度，推送频率100ms
- `bbo-tbt` - 1档最优价，推送频率10ms（最快）
- `books-l2-tbt` - 400档深度，推送频率10ms（需要VIP6+）
- `books50-l2-tbt` - 50档深度，推送频率10ms（需要VIP5+）
- `books-elp` - 400档ELP订单，推送频率100ms

### 2. 实盘服务器集成

✅ **trading_server_full.cpp 更新：**
- 添加深度数据回调处理
- 支持增量推送（snapshot/update）
- 发布深度数据到 ZeroMQ
- 支持订阅管理（动态订阅/取消订阅）

### 3. 策略端客户端库

✅ **strategy_client.py 更新：**
- 添加 `subscribe_orderbook()` 方法
- 添加 `unsubscribe_orderbook()` 方法
- 添加 `recv_orderbook()` 方法
- 添加 `on_orderbook()` 回调支持

### 4. 文档和示例

✅ **文档：**
- `README_策略端接口完整版.md` - 完整接口文档
- `example_full_features.py` - 完整功能示例代码

## 使用方法

### 订阅深度数据

```python
from strategy_client import StrategyClient

client = StrategyClient("my_strategy")
client.connect()

# 订阅 5档深度（推荐）
client.subscribe_orderbook("BTC-USDT", "books5")

# 订阅 1档最优价（最快）
client.subscribe_orderbook("BTC-USDT", "bbo-tbt")
```

### 接收深度数据

```python
# 方式1: 使用 BaseStrategy
class MyStrategy(BaseStrategy):
    def on_orderbook(self, orderbook: dict):
        best_bid = orderbook.get("best_bid_price", 0)
        best_ask = orderbook.get("best_ask_price", 0)
        print(f"买一: {best_bid}, 卖一: {best_ask}")

# 方式2: 手动接收
orderbook = client.recv_orderbook()
if orderbook:
    bids = orderbook["bids"]  # [[price, size], ...]
    asks = orderbook["asks"]  # [[price, size], ...]
```

## 深度数据格式

```python
{
    "type": "orderbook",
    "symbol": "BTC-USDT",
    "bids": [[50000.0, 1.5], [49999.0, 2.0], ...],  # [价格, 数量]
    "asks": [[50001.0, 1.2], [50002.0, 3.0], ...],
    "best_bid_price": 50000.0,
    "best_bid_size": 1.5,
    "best_ask_price": 50001.0,
    "best_ask_size": 1.2,
    "mid_price": 50000.5,
    "spread": 1.0,
    "timestamp": 1702000000000,
    "timestamp_ns": 1702000000000000000
}
```

## 注意事项

1. **增量推送处理：**
   - `books5` 和 `bbo-tbt` 是定量推送（每次完整数据）
   - `books`、`books-l2-tbt`、`books50-l2-tbt` 是增量推送（首次快照，后续增量）
   - 策略端需要自己维护全量深度（合并增量数据）

2. **VIP 限制：**
   - `books-l2-tbt` 需要 VIP6+
   - `books50-l2-tbt` 需要 VIP5+

3. **推送频率：**
   - `bbo-tbt`、`books-l2-tbt`、`books50-l2-tbt`：10ms（最快）
   - `books5`、`books`、`books-elp`：100ms

4. **订阅限制：**
   - 同一连接下，不能同时订阅 `books-l2-tbt` 和 `books50-l2-tbt`/`books`
   - 建议每个连接订阅不超过30个频道

## 测试

运行完整功能示例：

```bash
# 启动实盘服务器
./trading_server_full

# 运行示例（完整演示）
python3 example_full_features.py --strategy full

# 运行示例（批量交易）
python3 example_full_features.py --strategy batch

# 运行示例（多币种）
python3 example_full_features.py --strategy multi
```

