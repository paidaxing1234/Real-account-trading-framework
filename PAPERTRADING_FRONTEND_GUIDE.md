# PaperTrading 前端启动指南

## 功能概述

通过前端界面配置并启动模拟交易，使用真实账户的 API 获取实时行情数据，进行模拟下单测试。

## 核心特性

✅ **真实行情数据** - 使用真实账户 API 获取实时行情
✅ **模拟交易** - 所有交易均为模拟，不会实际下单
✅ **策略选择** - 支持网格、趋势、做市等多种策略
✅ **参数配置** - 灵活配置策略参数和交易对
✅ **实时监控** - 查看模拟交易的实时统计数据

---

## 使用流程

### 1. 进入 PaperTrading 页面

在前端导航栏点击 **"模拟交易"** 进入页面。

### 2. 配置模拟交易

点击 **"启动模拟交易"** 按钮，填写配置信息：

#### 账户配置
- **交易所**: 选择 OKX 或 Binance
- **API Key**: 输入真实账户的 API Key（用于获取行情）
- **Secret Key**: 输入 Secret Key
- **Passphrase**: OKX 需要填写，Binance 不需要
- **初始资金**: 设置模拟账户的初始资金（USDT）

#### 策略配置
- **策略类型**: 选择要运行的策略
  - 网格策略
  - 趋势策略
  - 做市策略
- **交易对**: 选择要交易的币种（如 BTC-USDT-SWAP）

#### 网格策略参数（以网格策略为例）
- **网格数量**: 单边网格��量（5-50）
- **网格间距**: 网格价格间距百分比（如 0.002 = 0.2%）
- **单次下单**: 每次下单的金额（USDT）

### 3. 启动模拟交易

点击 **"启动"** 按钮，系统会：
1. 验证配置信息
2. 启动 PaperTrading 服务器
3. 使用真实 API 连接交易所获取行情
4. 开始模拟交易

### 4. 监控运行状态

启动后可以看到：
- **运行时长**: 策略运行的时间
- **当前配置**: 策略、交易对、交易所等信息
- **账户统计**:
  - 总权益
  - 总盈亏
  - 成交笔数
  - 持仓数量
- **收益率**: 实时计算的收益率

### 5. 停止模拟交易

点击 **"停止模拟交易"** 按钮即可停止。

---

## 工作原理

```
┌─────────────┐
│  前端界面    │
│  配置参数    │
└──────┬──────┘
       │ WebSocket
       ↓
┌─────────────────────┐
│  PaperTrading 服务器 │
│  - 接收配置          │
│  - 启动策略进程      │
└──────┬──────────────┘
       │
       ├─→ 使用真实 API 获取行情
       │   (OKX/Binance WebSocket)
       │
       └─→ 模拟下单执行
           (不发送到交易所)
```

### 关键点

1. **真实行情**: 使用你提供的 API Key 连接交易所，获取真实的实时行情数据
2. **模拟下单**: 所有订单只在本地模拟执行，不会发送到交易所
3. **独立进程**: 每个策略在独立的进程中运行，互不干扰

---

## 后端实现要点

### WebSocket 消息处理

后端需要处理以下 WebSocket 消息：

#### 1. 启动策略 (`start_paper_strategy`)

```cpp
// 接收消息
{
  "type": "start_paper_strategy",
  "requestId": "req_xxx",
  "exchange": "okx",
  "apiKey": "xxx",
  "secretKey": "yyy",
  "passphrase": "zzz",
  "initialBalance": 100000,
  "strategy": "grid",
  "symbol": "BTC-USDT-SWAP",
  "strategyParams": {
    "gridNum": 10,
    "gridSpread": 0.002,
    "orderAmount": 100
  }
}

// 返回响应
{
  "type": "response",
  "requestId": "req_xxx",
  "success": true,
  "message": "策略已启动",
  "data": {
    "strategyId": "paper_grid_xxx",
    "startTime": 1704355200000
  }
}
```

#### 2. 停止策略 (`stop_paper_strategy`)

```cpp
// 接收消息
{
  "type": "stop_paper_strategy",
  "requestId": "req_xxx"
}

// 返回响应
{
  "type": "response",
  "requestId": "req_xxx",
  "success": true,
  "message": "策略已停止"
}
```

#### 3. 获取状态 (`get_paper_strategy_status`)

```cpp
// 接收消息
{
  "type": "get_paper_strategy_status",
  "requestId": "req_xxx"
}

// 返回响应
{
  "type": "response",
  "requestId": "req_xxx",
  "success": true,
  "data": {
    "isRunning": true,
    "config": { ... },
    "startTime": 1704355200000
  }
}
```

### 实现步骤

1. **在 `trading_server_full.cpp` 中添加消息处理**:
   ```cpp
   if (msg_type == "start_paper_strategy") {
       process_start_paper_strategy(msg, ws_server);
   } else if (msg_type == "stop_paper_strategy") {
       process_stop_paper_strategy(msg, ws_server);
   } else if (msg_type == "get_paper_strategy_status") {
       process_get_paper_strategy_status(msg, ws_server);
   }
   ```

2. **启动 PaperTrading 服务器进程**:
   ```cpp
   void process_start_paper_strategy(const nlohmann::json& msg, WebSocketServer* ws_server) {
       // 1. 解析配置
       std::string exchange = msg.value("exchange", "okx");
       std::string api_key = msg.value("apiKey", "");
       // ...

       // 2. 启动 papertrading_server 进程
       std::string cmd = "./papertrading_server --api-key " + api_key + " ...";
       g_paper_trading_pid = fork_and_exec(cmd);

       // 3. 返回成功响应
       send_response(ws_server, msg["requestId"], true, "策略已启动");
   }
   ```

3. **管理策略进程**:
   - 使用 `fork()` 或 `system()` 启动策略进程
   - 记录进程 PID
   - 停止时使用 `kill(pid, SIGTERM)` 终止进程

---

## 安全注意事项

⚠️ **API 密钥安全**:
- API 密钥通过 WebSocket 传输，确保使用 WSS（加密连接）
- 后端不应持久化存储 API 密钥
- 建议使用只读权限的 API Key

⚠️ **权限控制**:
- 只有授权用户才能启动模拟交易
- 限制同时运行的策略数量

⚠️ **资源限制**:
- 限制单个用户的策略数量
- 监控服务器资源使用情况

---

## 常见问题

### Q: API Key 会被保存吗？
A: 不会。API Key 只用于启动策略时连接交易所，不会持久化存储。

### Q: 模拟交易会实际下单吗？
A: 不会。所有订单只在本地模拟执行，不会发送到交易所。

### Q: 可以同时运行多个策略吗？
A: 可以。每个策略在独立进程中运行，互不干扰。

### Q: 如何查看详细的交易记录？
A: 可以在 "订单管理" 和 "持仓管理" 页面查看模拟交易的详细记录。

---

## 下一步

- [ ] 后端实现 WebSocket 消息处理
- [ ] 实现策略进程管理
- [ ] 添加策略运行日志查看
- [ ] 支持更多策略类型
- [ ] 添加策略性能分析

---

**更新时间**: 2026-01-04
