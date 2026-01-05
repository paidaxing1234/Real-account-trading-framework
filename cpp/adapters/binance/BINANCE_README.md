# Binance API 集成说明

## 📦 已实现的功能

### ✅ REST API (`binance_rest_api.h/cpp`)

支持三种市场类型：
- **现货市场** (`MarketType::SPOT`)
- **U本位合约** (`MarketType::FUTURES`)
- **币本位合约** (`MarketType::COIN_FUTURES`)

#### 市场数据接口（公开，无需API密钥）
- `test_connectivity()` - 测试连接
- `get_server_time()` - 获取服务器时间
- `get_exchange_info()` - 获取交易规则
- `get_depth()` - 获取深度信息
- `get_recent_trades()` - 获取最新成交
- `get_klines()` - 获取K线数据
- `get_ticker_24hr()` - 获取24小时价格变动
- `get_ticker_price()` - 获取最新价格
- `get_funding_rate()` - 获取资金费率（仅合约）

#### 交易接口（需要API密钥和签名）
- `place_order()` - 下单
- `cancel_order()` - 撤单
- `cancel_all_orders()` - 撤销所有挂单
- `get_order()` - 查询订单
- `get_open_orders()` - 查询挂单
- `get_all_orders()` - 查询所有订单

#### 账户接口（需要API密钥和签名）
- `get_account_info()` - 查询账户信息（含余额和持仓）
- `get_account_balance()` - 查询账户余额
- `get_positions()` - 查询持仓（仅合约）
- `change_leverage()` - 调整杠杆（仅合约）
- `change_position_mode()` - 切换持仓模式（仅合约）
- `get_position_mode()` - 获取持仓模式（仅合约）
- `change_margin_type()` - 调整保证金模式（仅合约）

#### 批量操作接口（仅合约）
- `place_batch_orders()` - 批量下单

### ✅ WebSocket API (`binance_websocket.h`)

支持三种连接类型：

#### 1. 交易API (`WsConnectionType::TRADING`)
**低延迟交易 - 比REST API更快！**

根据[币安WebSocket API文档](https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/websocket-api/trading-requests)实现：

- `place_order_ws()` - WebSocket下单
- `cancel_order_ws()` - WebSocket撤单
- `cancel_all_orders_ws()` - WebSocket撤销所有挂单
- `query_order_ws()` - WebSocket查询订单

**优势：**
- 延迟更低（通常<50ms）
- 保持长连接，无需频繁建立HTTP连接
- 实时响应

#### 2. 行情推送 (`WsConnectionType::MARKET`)
**实时行情数据订阅**

- `subscribe_trade()` - 订阅逐笔成交
- `subscribe_kline()` - 订阅K线数据
- `subscribe_mini_ticker()` - 订阅精简Ticker
- `subscribe_ticker()` - 订阅完整Ticker
- `subscribe_depth()` - 订阅深度信息
- `subscribe_book_ticker()` - 订阅最优挂单

#### 3. 用户数据流 (`WsConnectionType::USER_DATA`)
**实时账户和订单更新**

- `subscribe_user_data()` - 订阅用户数据流
  - 订单更新推送
  - 账户余额更新
  - 持仓变化推送

---

## 🚀 使用示例

### REST API 示例

```cpp
#include "adapters/binance/binance_rest_api.h"

using namespace trading::binance;

// 1. 创建现货API客户端
BinanceRestAPI spot_api("API_KEY", "SECRET_KEY", MarketType::SPOT);

// 2. 获取BTC价格（无需认证）
auto price = spot_api.get_ticker_price("BTCUSDT");
std::cout << "BTC价格: $" << price["price"] << std::endl;

// 3. 下限价单（需要认证）
OrderResponse order = spot_api.place_order(
    "BTCUSDT",
    OrderSide::BUY,
    OrderType::LIMIT,
    "0.001",    // 数量
    "50000"     // 价格
);

// 4. 查询账户余额
auto balances = spot_api.get_account_balance();
for (const auto& bal : balances) {
    if (std::stod(bal.free) > 0) {
        std::cout << bal.asset << ": " << bal.free << std::endl;
    }
}

// 5. U本位合约
BinanceRestAPI futures_api("API_KEY", "SECRET_KEY", MarketType::FUTURES);
futures_api.change_leverage("BTCUSDT", 10);  // 设置10倍杠杆
auto positions = futures_api.get_positions();
```

### WebSocket交易API 示例（低延迟下单）

```cpp
#include "adapters/binance/binance_websocket.h"

using namespace trading::binance;

// 创建交易API WebSocket
auto ws = create_trading_ws("API_KEY", "SECRET_KEY", MarketType::SPOT);

// 设置订单响应回调
ws->set_order_response_callback([](const nlohmann::json& response) {
    if (response["status"] == 200) {
        auto result = response["result"];
        std::cout << "订单成功: " << result["orderId"] << std::endl;
        std::cout << "状态: " << result["status"] << std::endl;
    }
});

// 连接
ws->connect();

// WebSocket下单（比REST API快得多！）
std::string req_id = ws->place_order_ws(
    "BTCUSDT",
    OrderSide::BUY,
    OrderType::LIMIT,
    "0.001",
    "50000"
);

// WebSocket撤单
ws->cancel_order_ws("BTCUSDT", order_id);

// 保持连接
while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
}
```

### WebSocket行情推送示例

```cpp
#include "adapters/binance/binance_websocket.h"

using namespace trading::binance;

// 创建行情WebSocket
auto ws = create_market_ws(MarketType::SPOT);

// 设置成交回调
ws->set_trade_callback([](const TradeData::Ptr& trade) {
    std::cout << "成交: " << trade->symbol() 
              << " 价格: " << trade->price()
              << " 数量: " << trade->quantity() << std::endl;
});

// 设置K线回调
ws->set_kline_callback([](const KlineData::Ptr& kline) {
    std::cout << "K线: " << kline->symbol()
              << " 收盘价: " << kline->close() << std::endl;
});

// 连接
ws->connect();

// 订阅行情
ws->subscribe_trade("btcusdt");
ws->subscribe_kline("btcusdt", "1m");
ws->subscribe_ticker("btcusdt");
ws->subscribe_depth("btcusdt", 20);

// 保持运行
while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
}
```

---

## 📝 编译和测试

### ✅ 一键启动（默认启用代理 127.0.0.1:7890）

仓库已提供一键脚本（会自动配置并编译，然后运行 REST + WebSocket 行情示例）：

```bash
cd /home/llx/Real-account-trading-framework/cpp/examples
chmod +x run_test_binance_api.sh
./run_test_binance_api.sh
```

### ✅ 合约（U本位）测试网下单（REST）

安全模式默认**不下单**，只打印参数；你确认后再设置 `BINANCE_DO_TRADE=1`。

```bash
cd /home/llx/Real-account-trading-framework/cpp/examples
chmod +x run_test_binance_futures_order_testnet.sh

# 你的 futures testnet key（建议单独申请合约测试网key）
export BINANCE_FUTURES_API_KEY="xxx"
export BINANCE_FUTURES_SECRET_KEY="yyy"

# 可选：代理
# export PROXY_URL="http://127.0.0.1:7890"

./run_test_binance_futures_order_testnet.sh
```

真的下单（testnet）：

```bash
export BINANCE_DO_TRADE=1
./run_test_binance_futures_order_testnet.sh
```

如需撤单（注意可能触发你贴的 1min order rate limit，本程序会等 65s 后撤）：

```bash
export BINANCE_DO_TRADE=1
export BINANCE_DO_CANCEL=1
./run_test_binance_futures_order_testnet.sh
```

### ✅ 合约（U本位）测试网下单（最简：直接把 key 写进脚本）

如果你想要和 `run_test_okx_api.sh` 一样“脚本里直接填 key”，用这个：

```bash
cd /home/llx/Real-account-trading-framework/cpp/examples
chmod +x run_binance_futures_testnet_place_order_simple.sh
./run_binance_futures_testnet_place_order_simple.sh
```

编辑脚本顶部两行即可：
`API_KEY=...`
`SECRET_KEY=...`

如需修改代理端口：

```bash
PROXY_URL=http://127.0.0.1:7891 ./run_test_binance_api.sh
```

如需启用私有/交易相关测试（会额外编译并运行 `test_binance_ws_trading`）：

```bash
export BINANCE_API_KEY="xxx"
export BINANCE_SECRET_KEY="yyy"
./run_test_binance_api.sh
```

### 编译币安现货测试程序

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make test_binance_spot -j$(nproc)
```

### 运行测试

```bash
# 如需代理
https_proxy=http://127.0.0.1:7890 ./test_binance_spot

# 无需代理
./test_binance_spot
```

---

## 🔑 API密钥申请

### 主网（实盘）
1. 登录 [Binance官网](https://www.binance.com)
2. 进入 **API管理** 页面
3. 创建新的API密钥
4. **重要**：记录 `API Key` 和 `Secret Key`
5. 设置IP白名单（推荐）

### 测试网
1. 访问 [Binance测试网](https://testnet.binance.vision/)
2. 登录并申请测试网API密钥
3. 使用测试网URL进行测试

**⚠️ 安全提示：**
- 切勿在代码中硬编码API密钥
- 建议从环境变量或配置文件读取
- 设置IP白名单限制访问
- 定期更换API密钥

---

## 📊 WebSocket vs REST API 性能对比

| 特性 | REST API | WebSocket API |
|------|----------|---------------|
| 延迟 | 100-300ms | 10-50ms |
| 连接 | 每次请求建立 | 保持长连接 |
| 限速 | 较严格 | 相对宽松 |
| 使用场景 | 查询、低频交易 | 高频交易、实时数据 |
| 推荐用途 | 初始查询、偶尔下单 | 算法交易、做市商 |

**结论：高频交易强烈推荐使用WebSocket API！**

---

## 🌐 URL端点

### 主网（实盘）
- REST API: `https://api.binance.com`
- U本位合约REST: `https://fapi.binance.com`
- 币本位合约REST: `https://dapi.binance.com`
- WebSocket交易API: `wss://ws-api.binance.com/ws-api/v3`
- WebSocket行情: `wss://stream.binance.com:9443/ws`

### 测试网
- REST API: `https://testnet.binance.vision`
- U本位合约REST: `https://demo-fapi.binance.com`
- WebSocket交易API: `wss://testnet.binance.vision/ws-api/v3`
- WebSocket交易API: `wss://ws-api.testnet.binance.vision/ws-api/v3`
- WebSocket行情: `wss://stream.testnet.binance.vision/ws`

---

## 📖 参考文档

- [币安现货API文档](https://binance-docs.github.io/apidocs/spot/cn/)
- [币安U本位合约API](https://binance-docs.github.io/apidocs/futures/cn/)
- [币安WebSocket API](https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/websocket-api)
- [币安WebSocket交易请求](https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/websocket-api/trading-requests)
- [币安行情推送](https://binance-docs.github.io/apidocs/spot/cn/#websocket)

---

## ⚡ 待完成功能

### WebSocket实现（cpp文件）
由于实现文件较大（预计2000+行），需要额外时间完成：

1. WebSocket底层连接管理（基于websocketpp）
2. 消息序列化和反序列化
3. 心跳保持机制
4. 自动重连逻辑
5. 完整的消息解析器

**如需完整实现，请告知我继续创建！**

---

## 💡 最佳实践

1. **使用WebSocket进行高频交易**
   - 延迟最低
   - 适合算法交易和做市

2. **REST API用于查询和低频操作**
   - 查询历史数据
   - 偶尔下单
   - 账户管理

3. **组合使用**
   ```cpp
   // REST API: 初始化查询
   auto account = rest_api.get_account_info();
   auto positions = rest_api.get_positions();
   
   // WebSocket: 实时交易
   ws_trading->place_order_ws(...);  // 低延迟下单
   
   // WebSocket: 实时行情
   ws_market->subscribe_ticker("btcusdt");
   ```

4. **错误处理**
   - 实现重连机制
   - 处理限速错误
   - 记录所有API调用日志

---

## 🎯 下一步

1. 完成WebSocket实现文件（binance_websocket.cpp）
2. 创建WebSocket测试程序
3. 添加更多便捷方法
4. 优化性能和错误处理

**需要帮助？请随时告知！**

