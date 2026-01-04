# Binance 市场数据测试指南

## 📋 功能说明

全面测试 Binance 市场数据流，支持：
- **现货市场**：K线、深度、成交、Ticker
- **合约市场**：K线、深度、成交、标记价格、全市场标记价格
- **测试网（模拟账户）**和**主网（真实账户）**

## 🔧 编译

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
cmake --build . --target test_binance_market_data_comprehensive -- -j$(nproc)
```

## 🚀 运行测试

### 1. 测试网（模拟账户）- 现货市场

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
export BINANCE_TESTNET=1
export MARKET_TYPE=SPOT
./test_binance_market_data_comprehensive
```

### 2. 测试网（模拟账户）- 合约市场

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
export BINANCE_TESTNET=1
export MARKET_TYPE=FUTURES
./test_binance_market_data_comprehensive
```

### 3. 主网（真实账户）- 现货市场

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
export BINANCE_TESTNET=0  # 或不设置（默认主网）
export MARKET_TYPE=SPOT   # 或不设置（默认现货）
./test_binance_market_data_comprehensive
```

### 4. 主网（真实账户）- 合约市场

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
export BINANCE_TESTNET=0
export MARKET_TYPE=FUTURES
./test_binance_market_data_comprehensive
```

## 📊 测试内容

### 现货市场（SPOT）
- ✅ 成交流（trade）
- ✅ K线流（kline，1分钟）
- ✅ Ticker流（24小时行情）
- ✅ 深度流（depth，20档@100ms）

### 合约市场（FUTURES/COIN_FUTURES）
- ✅ 成交流（trade）
- ✅ K线流（kline，1分钟）
- ✅ Ticker流（24小时行情）
- ✅ 深度流（depth，20档@100ms）
- ✅ 标记价格流（markPrice）
- ✅ 全市场标记价格流（!markPrice@arr）

## 📝 输出示例

```
========================================
  Binance 市场数据全面测试
========================================
网络: TESTNET(模拟账户)
市场: FUTURES(USDT合约)
提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890
按 Ctrl+C 退出
========================================

正在连接 WebSocket...
✅ 连接成功！

正在订阅数据流（交易对: BTCUSDT）...
  ✓ 成交流
  ✓ K线流 (1m)
  ✓ Ticker流
  ✓ 深度流 (20档@100ms)
  ✓ 标记价格流
  ✓ 全市场标记价格流

✅ 订阅完成！等待数据推送...

[成交] BTCUSDT px=91177.30 qty=0.002000 side=BUY t=02:27:54
[K线] BTCUSDT 1m O=91150.00 H=91200.00 L=91100.00 C=91177.30 V=125.50 closed=✅ t=02:27:54
[标记价格] BTCUSDT mark=91177.50 index=91177.30 funding=0.0001

[统计] 10秒 | 成交: 45 | K线: 1 | Ticker: 12 | 深度: 100 | 标记价格: 3 | 全市场标记价格: 30
```

## ⚙️ 环境变量说明

- `BINANCE_TESTNET=1`：使用测试网（模拟账户）
- `BINANCE_TESTNET=0` 或不设置：使用主网（真实账户）
- `MARKET_TYPE=SPOT`：现货市场（默认）
- `MARKET_TYPE=FUTURES`：USDT合约市场
- `MARKET_TYPE=COIN_FUTURES`：币本位合约市场

## ⚠️ 注意事项

1. **代理设置**：WebSocket 默认使用 HTTP 代理 `127.0.0.1:7890`
2. **运行时间**：程序默认运行 60 秒，可按 Ctrl+C 提前退出
3. **数据频率**：
   - 成交数据：高频推送（限频打印，每10条打印1条）
   - K线数据：每分钟推送一次
   - Ticker数据：每秒推送（限频打印，每5条打印1条）
   - 深度数据：每100ms推送（限频打印，每20条打印1条）
   - 标记价格：每3秒推送一次

## 🔍 验证要点

测试时请确认：
1. ✅ WebSocket 连接成功
2. ✅ 所有订阅请求发送成功
3. ✅ 收到各类数据推送（成交、K线、Ticker等）
4. ✅ 统计数据正常增长
5. ✅ 合约市场能收到标记价格数据

## 📚 相关文档

- [Binance WebSocket 文档](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams)
- [Binance 合约 WebSocket 文档](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-data)

