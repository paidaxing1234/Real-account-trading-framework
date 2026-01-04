# PaperTrading 前端启动功能测试指南

## 实现完成 ✅

已成功实现从前端启动 PaperTrading 的完整功能。

## 架构说明

```
前端 (Vue.js)
  ↓ WebSocket (ws://localhost:8002)
trading_server_full (主服务器)
  ↓ 接收命令: start_paper_strategy
  ↓ 执行: system("./papertrading_server &")
papertrading_server (子进程)
  ↓ WebSocket (ws://localhost:8001)
前端 (接收模拟交易数据)
```

## 端口配置

- **8002**: 主服务器 WebSocket (用于发送启动/停止命令)
- **8001**: PaperTrading WebSocket (用于接收模拟交易数据)

## 测试步骤

### 1. 启动主服务器

```bash
cd /home/llx/Real-account-trading-framework/cpp/build
./trading_server_full
```

预期输出：
```
[前端] WebSocket服务器已启动（端口8002）
```

### 2. 启动前端

```bash
cd /home/llx/Real-account-trading-framework/实盘框架前端页面
npm run dev
```

### 3. 测试前端启动 PaperTrading

1. 打开浏览器访问前端页面
2. 进入 "模拟交易 (Paper Trading)" 页面
3. 点击 "启动模拟交易" 按钮
4. 填写配置：
   - 交易所: OKX
   - API Key: (你的测试 API Key)
   - Secret Key: (你的测试 Secret Key)
   - Passphrase: (你的 Passphrase)
   - 初始资金: 100000 USDT
   - 策略类型: 网格策略
   - 交易对: BTC-USDT-SWAP
   - 网格数量: 10
   - 网格间距: 0.002 (0.2%)
   - 单次下单: 100 USDT
5. 点击 "启动"

### 4. 验证启动成功

**后端日志检查：**
```bash
# 检查 papertrading_server 进程
ps aux | grep papertrading_server

# 查看日志
tail -f /tmp/papertrading.log
```

**前端界面检查：**
- 应该显示 "运行中" 状态
- 显示运行时长计时器
- 显示当前配置信息

### 5. 测试停止功能

1. 点击 "停止模拟交易" 按钮
2. 确认停止
3. 验证进程已停止：
```bash
ps aux | grep papertrading_server  # 应该没有结果
```

## 已实现的功能

### 后端 (C++)

1. **WebSocket 服务器** (端口 8002)
   - 接收前端命令
   - 处理启动/停止/状态查询请求

2. **命令处理函数**
   - `process_start_paper_strategy()` - 启动 papertrading_server
   - `process_stop_paper_strategy()` - 停止进程
   - `process_get_paper_strategy_status()` - 查询状态

3. **进程管理**
   - 使用 `system()` 启动子进程
   - 使用 `pgrep` 获取 PID
   - 使用 `kill()` 停止进程

### 前端 (Vue.js)

1. **PaperTrading 页面** (`src/views/PaperTrading.vue`)
   - 配置表单
   - 启动/停止按钮
   - 运行状态显示
   - 实时统计面板

2. **API 接口** (`src/api/papertrading.js`)
   - `startStrategy()` - 启动策略
   - `stopStrategy()` - 停止策略
   - `getStrategyStatus()` - 获取状态

3. **WebSocket 客户端** (`src/services/WebSocketClient.js`)
   - 连接到 8002 端口
   - 发送命令请求
   - 接收响应

## 消息格式

### 启动请求
```json
{
  "action": "start_paper_strategy",
  "data": {
    "requestId": "req_1234567890_abc123",
    "exchange": "okx",
    "apiKey": "your-api-key",
    "secretKey": "your-secret-key",
    "passphrase": "your-passphrase",
    "initialBalance": 100000,
    "strategy": "grid",
    "symbol": "BTC-USDT-SWAP",
    "strategyParams": {
      "gridNum": 10,
      "gridSpread": 0.002,
      "orderAmount": 100
    }
  }
}
```

### 启动响应
```json
{
  "type": "response",
  "data": {
    "requestId": "req_1234567890_abc123",
    "success": true,
    "message": "模拟交易已启动",
    "data": {
      "strategyId": "paper_trading",
      "startTime": 1704384000000
    }
  }
}
```

## 故障排查

### 问题1: 前端无法连接到服务器
```bash
# 检查主服务器是否运行
ps aux | grep trading_server_full

# 检查端口是否监听
netstat -tlnp | grep 8002
```

### 问题2: PaperTrading 启动失败
```bash
# 查看日志
tail -f /tmp/papertrading.log

# 检查 papertrading_server 是否存在
ls -la /home/llx/Real-account-trading-framework/cpp/build/papertrading_server
```

### 问题3: 进程无法停止
```bash
# 手动停止
pkill -f papertrading_server

# 强制停止
pkill -9 -f papertrading_server
```

## 下一步优化建议

1. **进程管理改进**
   - 使用 pidfile 而不是 pgrep
   - 添加进程健康检查
   - 实现优雅关闭

2. **配置持久化**
   - 保存配置到文件
   - 支持配置模板

3. **状态同步**
   - 定期查询 PaperTrading 状态
   - 实时更新前端显示

4. **错误处理**
   - 更详细的错误信息
   - 自动重启机制

## 更新日期

2026-01-04
