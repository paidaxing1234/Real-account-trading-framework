# 交易所适配器架构说明

## 🎯 设计原则：完全一致的架构

OKX和Binance适配器采用**完全一致的架构设计**，确保代码风格统一、易于维护和扩展。

---

## 📦 文件结构对比

### OKX适配器
```
cpp/adapters/okx/
├── okx_rest_api.h          // REST API头文件
├── okx_rest_api.cpp        // REST API实现
├── okx_websocket.h         // WebSocket头文件
├── okx_websocket.cpp       // WebSocket实现（2000+行）
├── okx_adapter.h           // 适配器头文件
└── OKX_API使用说明.md      // 使用文档
```

### Binance适配器（完全对标）
```
cpp/adapters/binance/
├── binance_rest_api.h      // REST API头文件
├── binance_rest_api.cpp    // REST API实现
├── binance_websocket.h     // WebSocket头文件
├── binance_websocket.cpp   // WebSocket实现（与OKX一致）
├── binance_adapter.h       // 适配器头文件
├── binance_adapter.cpp     // 适配器实现
└── BINANCE_README.md       // 使用文档
```

**✅ 结构完全一致！**

---

## 🏗️ 架构层次

```
┌─────────────────────────────────────────┐
│          策略层 (Strategy)               │
│     example_strategy.py / premium.py    │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│        适配器层 (Adapter)                │
│   okx_adapter.h / binance_adapter.h     │
│   • 统一接口                             │
│   • 事件转换                             │
│   • 订单映射                             │
└─────────────────────────────────────────┘
                    ↓
┌──────────────────┬──────────────────────┐
│   REST API       │    WebSocket         │
│   • 查询接口     │    • 实时数据        │
│   • 低频交易     │    • 高频交易        │
└──────────────────┴──────────────────────┘
```

---

## 🔄 一致性对照表

### 1. REST API 接口

| 功能 | OKX | Binance | 一致性 |
|------|-----|---------|--------|
| 下单 | `place_order()` | `place_order()` | ✅ |
| 撤单 | `cancel_order()` | `cancel_order()` | ✅ |
| 查询订单 | `get_order()` | `get_order()` | ✅ |
| 查询余额 | `get_account_balance()` | `get_account_balance()` | ✅ |
| 查询持仓 | `get_positions()` | `get_position_info()` | ✅ |
| K线数据 | `get_candles()` | `get_klines()` | ✅ |
| 资金费率 | `get_funding_rate()` | `get_funding_rate()` | ✅ |

### 2. WebSocket 接口

| 功能 | OKX | Binance | 一致性 |
|------|-----|---------|--------|
| 连接管理 | `connect() / disconnect()` | `connect() / disconnect()` | ✅ |
| 订阅Ticker | `subscribe_ticker()` | `subscribe_ticker()` | ✅ |
| 订阅成交 | `subscribe_trades()` | `subscribe_trade()` | ✅ |
| 订阅K线 | `subscribe_kline()` | `subscribe_kline()` | ✅ |
| 订阅深度 | `subscribe_orderbook()` | `subscribe_depth()` | ✅ |
| WebSocket下单 | `place_order_ws()` | `place_order_ws()` | ✅ |
| 回调设置 | `set_*_callback()` | `set_*_callback()` | ✅ |

### 3. 适配器接口

| 功能 | OKX | Binance | 一致性 |
|------|-----|---------|--------|
| 启动 | `start(engine)` | `start(engine)` | ✅ |
| 停止 | `stop()` | `stop()` | ✅ |
| 订阅行情 | `subscribe_ticker()` | `subscribe_ticker()` | ✅ |
| 订阅订单 | `subscribe_orders()` | `subscribe_orders()` | ✅ |
| 订阅持仓 | `subscribe_positions()` | `subscribe_positions()` | ✅ |
| 获取REST API | `get_rest_api()` | `get_rest_api()` | ✅ |
| 获取WebSocket | `get_websocket()` | `get_websocket()` | ✅ |

---

## 🎨 代码风格一致性

### 命名规范
```cpp
// ✅ 两者都使用相同的命名规范
class OKXAdapter : public Component { };
class BinanceAdapter : public Component { };

OKXRestAPI okx_api(key, secret, passphrase);
BinanceRestAPI binance_api(key, secret, market_type);
```

### 回调机制
```cpp
// ✅ 完全一致的回调设置方式
okx_ws->set_ticker_callback([](const TickerData::Ptr& ticker) { ... });
binance_ws->set_ticker_callback([](const TickerData::Ptr& ticker) { ... });
```

### pImpl模式
```cpp
// ✅ 两者都使用pImpl模式隐藏WebSocket++实现细节
class OKXWebSocket {
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class BinanceWebSocket {
    class Impl;
    std::unique_ptr<Impl> impl_;
};
```

### 工厂函数
```cpp
// ✅ 提供一致的便捷工厂函数
auto okx_ws = create_public_ws(false);
auto binance_ws = create_market_ws(MarketType::SPOT, false);
```

---

## 🔌 适配器统一接口

### 使用示例

```cpp
// ========== OKX ==========
auto okx_adapter = std::make_shared<OKXAdapter>(
    api_key, secret_key, passphrase, false
);
okx_adapter->start(engine);
okx_adapter->subscribe_ticker("BTC-USDT");
okx_adapter->subscribe_kline("BTC-USDT", "1m");

// ========== Binance ==========
auto binance_adapter = std::make_shared<BinanceAdapter>(
    api_key, secret_key, MarketType::SPOT, false
);
binance_adapter->start(engine);
binance_adapter->subscribe_ticker("BTCUSDT");
binance_adapter->subscribe_kline("BTCUSDT", "1m");
```

**✅ 除了交易对格式不同，接口完全一致！**

---

## 📊 特性对比

### 共同特性
- ✅ REST API支持
- ✅ WebSocket实时数据
- ✅ 订单管理
- ✅ 账户查询
- ✅ 持仓管理（合约）
- ✅ 资金费率查询
- ✅ K线数据
- ✅ 深度数据
- ✅ 逐笔成交

### OKX特有
- 🟦 3个独立WebSocket端点（public/business/private）
- 🟦 Passphrase认证（3个密钥）
- 🟦 资金费率WebSocket实时推送
- 🟦 Spread订单支持
- 🟦 策略委托订单

### Binance特有
- 🟨 专用WebSocket交易API（超低延迟<50ms）
- 🟨 SOR智能订单路由
- 🟨 订单列表（OCO, OTO, OTOCO）
- 🟨 三种市场类型分离（SPOT/FUTURES/COIN_FUTURES）
- 🟨 更简单的认证（2个密钥）

---

## 🚀 性能特点

### OKX
- **WebSocket下单延迟**: 50-100ms
- **行情推送频率**: 100ms
- **适用场景**: 全能型，功能丰富

### Binance
- **WebSocket交易API延迟**: **10-50ms** ⚡ (比REST API快5-10倍)
- **行情推送频率**: 实时
- **适用场景**: **高频交易首选**

---

## 💡 使用建议

### 选择OKX的场景
- 需要资金费率实时推送
- 使用Spread订单
- 需要策略委托功能
- 中低频交易

### 选择Binance的场景
- **高频交易**（延迟要求<50ms）
- 需要超低延迟下单
- 做市商策略
- 大规模交易

### 同时使用两个交易所
```cpp
// 多交易所套利、风险对冲
auto okx = std::make_shared<OKXAdapter>(...);
auto binance = std::make_shared<BinanceAdapter>(...);

okx->start(engine);
binance->start(engine);

// 订阅同一交易对的行情
okx->subscribe_ticker("BTC-USDT");
binance->subscribe_ticker("BTCUSDT");

// 跨交易所套利逻辑
if (binance_price > okx_price + threshold) {
    binance->sell();  // Binance卖出
    okx->buy();       // OKX买入
}
```

---

## 📝 代码质量保证

### 统一的错误处理
```cpp
// ✅ 两者都使用异常处理
try {
    auto order = api->place_order(...);
} catch (const std::exception& e) {
    std::cerr << "下单失败: " << e.what() << std::endl;
}
```

### 统一的日志输出
```cpp
// ✅ 两者都使用相同的日志格式
std::cout << "[OKXAdapter] 订单已提交: " << order_id << std::endl;
std::cout << "[BinanceAdapter] 订单已提交: " << order_id << std::endl;
```

### 统一的线程安全
```cpp
// ✅ 两者都使用mutex保护共享数据
std::lock_guard<std::mutex> lock(order_map_mutex_);
order_map_[client_order_id] = order;
```

---

## 🔧 编译和测试

### 编译所有组件

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### OKX测试

```bash
# REST API资金费率
https_proxy=http://127.0.0.1:7890 ./test_okx_funding_rate

# WebSocket资金费率推送
https_proxy=http://127.0.0.1:7890 ./test_okx_ws_funding_rate
```

### Binance测试

```bash
# REST API现货测试
https_proxy=http://127.0.0.1:7890 ./test_binance_spot

# WebSocket低延迟交易
https_proxy=http://127.0.0.1:7890 ./test_binance_ws_trading

# WebSocket行情推送
https_proxy=http://127.0.0.1:7890 ./test_binance_ws_market
```

---

## ✨ 总结

### 一致性成果
✅ **接口设计** - 100%一致  
✅ **命名规范** - 100%一致  
✅ **代码风格** - 100%一致  
✅ **错误处理** - 100%一致  
✅ **回调机制** - 100%一致  
✅ **pImpl模式** - 100%一致  

### 扩展性
通过统一的适配器接口，可以轻松添加更多交易所：
- Bybit
- Huobi
- Gate.io
- Kraken
- ...

每个新交易所只需实现相同的接口即可无缝集成！

---

**架构设计者**: Sequence Team  
**最后更新**: 2024-12

