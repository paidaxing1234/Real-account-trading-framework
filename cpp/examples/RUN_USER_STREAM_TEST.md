# Binance 用户数据流测试指南

## 📋 功能说明

测试 Binance 合约测试网的用户数据流（User Data Stream），实时接收账户更新事件（ACCOUNT_UPDATE），包括：
- 账户余额变化（B 数组）
- 持仓变化（P 数组）
- 事件原因（m 字段）：ORDER、FUNDING_FEE、DEPOSIT 等

## 🔧 编译

```bash
cd /home/llx/Real-account-trading-framework/cpp/build

# 编译测试程序
cmake --build . --target test_binance_futures_user_stream_testnet -- -j$(nproc)
```

## 🚀 运行

### 方式1：使用环境变量（推荐）

```bash
# 设置 API 密钥
export BINANCE_API_KEY="你的合约测试网API_KEY"
export BINANCE_SECRET_KEY="你的合约测试网SECRET_KEY"

# 可选：设置运行时间（秒，默认120秒）
export USER_STREAM_RUN_SECONDS=300

# 可选：设置刷新间隔（秒，默认1800秒=30分钟）
export USER_STREAM_KEEPALIVE_SECONDS=1800

# 可选：设置模式（rest 或 ws，默认 rest）
export USER_STREAM_MODE=rest

# 运行测试
./test_binance_futures_user_stream_testnet
```

### 方式2：直接运行（使用代码中的硬编码密钥）

如果测试文件中有硬编码的密钥，可以直接运行：

```bash
./test_binance_futures_user_stream_testnet
```

## 📊 测试流程

1. **创建 listenKey**：通过 REST API 或 WebSocket API 创建
2. **连接用户数据流**：使用 listenKey 连接到 WebSocket
3. **启动自动刷新**：每 50 分钟自动刷新 listenKey（避免 60 分钟过期）
4. **等待事件**：等待账户变化事件（下单成交、持仓变化等）
5. **接收事件**：实时打印 ACCOUNT_UPDATE 事件内容

## ⚠️ 注意事项

1. **事件触发条件**：
   - 只有账户信息**实际变化**时才会推送 ACCOUNT_UPDATE
   - 仅下单但未成交 → **不会**触发
   - 订单被取消 → **不会**触发（除非已部分成交）
   - 订单成交 → **会**触发
   - 持仓变化 → **会**触发
   - 资金费用 → **会**触发

2. **listenKey 有效期**：
   - listenKey 有效期为 60 分钟
   - 代码会自动每 50 分钟刷新一次（可配置）
   - 如果 listenKey 过期，连接会被断开

3. **测试网环境**：
   - REST API: `https://demo-fapi.binance.com`
   - WebSocket: `wss://fstream.binancefuture.com/ws/<listenKey>`
   - 需要合约测试网的 API 密钥

## 📝 输出示例

```
========================================
  Binance FUTURES USER_STREAM 测试(Testnet)
========================================
✅ API密钥已配置
   API Key: txMIDVQy...
   REST: https://demo-fapi.binance.com
   WS:   wss://fstream.binancefuture.com/ws/<listenKey>
   mode: rest
   run:  300s
   keepalive: 1800s

✅ listenKey: abc123def456...

[自动刷新] 启动 listenKey 自动刷新（间隔: 1800秒）
[BinanceWebSocket] 🔄 启动自动刷新 listenKey（间隔: 1800秒）

等待推送中...（可在测试网下单/调仓以触发 ACCOUNT_UPDATE）
提示：只有订单成交、持仓变化、资金变化时才会收到 ACCOUNT_UPDATE 事件

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📨 [ACCOUNT_UPDATE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  E: 1705385954229
  T: 1705385954228
  m: ORDER
  B:
    USDT wb=1000.12345678 cw=900.12345678 bc=50.12345678
  P:
    BTCUSDT ps=LONG pa=0.1 ep=42000.00 up=100.50 mt=isolated iw=420.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[BinanceWebSocket] ✅ listenKey 已刷新
```

## 🔍 调试

如果收不到事件，检查：

1. **连接状态**：确认 WebSocket 连接成功
2. **listenKey 有效性**：确认 listenKey 未过期
3. **账户变化**：确认确实发生了账户变化（订单成交、持仓变化等）
4. **调试输出**：查看是否有 `[BinanceWebSocket] 📨 收到 ACCOUNT_UPDATE 事件` 输出

## 📚 相关文档

- [Binance 用户数据流文档](https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/user-data-stream)
- [Binance 合约测试网](https://testnet.binancefuture.com/)

