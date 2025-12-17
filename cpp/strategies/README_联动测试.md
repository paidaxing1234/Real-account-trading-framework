# 交易所-实盘-策略 联动测试指南

## 测试目标

验证完整的交易链路：
1. **交易所** → WebSocket 推送 trades 数据
2. **实盘服务器** → 接收 trades，通过 ZeroMQ 分发给策略
3. **策略** → 接收 trades，每 10 秒发送订单请求
4. **实盘服务器** → 调用 OKX REST API 下单
5. **实盘服务器** → 通过 ZeroMQ 返回订单回报给策略

## CPU 绑核配置

### NUMA Node 0 分配方案

```
CPU 0:     系统中断（保留）
CPU 1:     实盘服务器主线程（WebSocket + ZMQ 发布）
CPU 2:     实盘服务器订单线程
CPU 3:     备用
CPU 4-11:  策略进程（最多8个策略）
```

## 测试步骤

### 1. 启动实盘服务器（终端 1）

```bash
cd /path/to/Real-account-trading-framework/cpp/build

# 方式 A：普通启动（自动绑核）
./trading_server_live

# 方式 B：NUMA 绑定（推荐）
numactl --cpunodebind=0 --membind=0 ./trading_server_live

# 方式 C：实时调度 + NUMA 绑定（最低延迟，需要 sudo）
sudo numactl --cpunodebind=0 --membind=0 chrt -f 50 ./trading_server_live
```

**预期输出：**
```
========================================
    Sequence 实盘交易服务器 (Live)
    OKX WebSocket + ZeroMQ
========================================

============================================================
  CPU 亲和性配置 (NUMA Node 0)
============================================================
  主线程 (WebSocket+ZMQ): CPU 1
  订单处理线程:          CPU 2
  策略进程建议:          CPU 4-11
============================================================

[绑核] 线程已绑定到 CPU 1
[NUMA] 内存绑定到节点 0
[调度] 已设置为 SCHED_FIFO，优先级 50
[配置] 交易模式: 模拟盘
[初始化] OKX REST API 已创建
[初始化] ZeroMQ 通道:
  - 行情: ipc:///tmp/trading_md.ipc
  - 订单: ipc:///tmp/trading_order.ipc
  - 回报: ipc:///tmp/trading_report.ipc

[WebSocket] 连接中...
[WebSocket] ✓ 连接成功
[WebSocket] 订阅 trades 频道...
[WebSocket] ✓ 订阅成功: {"channel":"trades","instId":"BTC-USDT"}

========================================
  服务器启动完成！
  等待策略连接...
  按 Ctrl+C 停止
========================================
```

### 2. 启动策略客户端（终端 2）

```bash
cd /path/to/Real-account-trading-framework/cpp/strategies

# 方式 A：自动绑核（策略编号 0，绑定 CPU 4）
python3 zmq_strategy_client.py --strategy-index 0

# 方式 B：指定 CPU
python3 zmq_strategy_client.py --cpu 4

# 方式 C：实时调度（需要 sudo）
sudo python3 zmq_strategy_client.py --strategy-index 0 --realtime

# 方式 D：自定义下单间隔（默认 10 秒）
python3 zmq_strategy_client.py --strategy-index 0 --order-interval 10
```

**预期输出：**
```
============================================================
    Sequence ZeroMQ 策略客户端
    交易所 -> 实盘 -> 策略 联动测试
============================================================

[配置] 策略 ID: test
[配置] 策略编号: 0
[配置] 下单间隔: 10 秒
[配置] 目标 CPU: 4
[绑核] 进程已绑定到 CPU 4

[Strategy] ID: test
[连接] 行情通道: ipc:///tmp/trading_md.ipc
[连接] 订单通道: ipc:///tmp/trading_order.ipc
[连接] 回报通道: ipc:///tmp/trading_report.ipc
[连接] ✓ 所有通道连接成功

============================================================
  策略启动！
  - 接收 trades 数据
  - 每 10 秒自动下单
  按 Ctrl+C 停止
============================================================

[Trade #50] BTC-USDT
  方向: buy | 价格: 104250.50 | 数量: 0.001

**************************************************
[定时下单] 10:30:00
**************************************************

[订单] 已发送: buy BTC-USDT market
       数量: 1, 价格: market
       订单ID: test1734356400123

==================================================
[回报] 订单状态: accepted
       客户端ID: test1734356400123
       交易所ID: 3130138109650751488
==================================================
```

## 观察要点

### 1. Trades 数据流

- **实盘服务器**：每 100 条 trades 打印一次统计
- **策略客户端**：每 50 条 trades 打印一次详情

### 2. 订单流程

- **每 10 秒**：策略自动发送订单请求
- **实盘服务器**：接收订单 → 调用 OKX API → 返回结果
- **策略客户端**：接收订单回报并打印

### 3. CPU 使用情况

```bash
# 查看进程 CPU 亲和性
taskset -p <PID>

# 查看进程运行在哪个 CPU
ps -o pid,psr,comm -p <PID>

# 实时监控
htop
```

## 多策略测试

可以同时启动多个策略进程，每个绑定不同的 CPU：

```bash
# 终端 2：策略 0（CPU 4）
python3 zmq_strategy_client.py --strategy-index 0 --strategy-id strategy0

# 终端 3：策略 1（CPU 5）
python3 zmq_strategy_client.py --strategy-index 1 --strategy-id strategy1

# 终端 4：策略 2（CPU 6）
python3 zmq_strategy_client.py --strategy-index 2 --strategy-id strategy2
```

## 故障排查

### 1. 连接失败

```
[错误] 无法连接到交易服务器
```

**解决：**
- 确保 `trading_server_live` 已启动
- 检查 IPC 文件是否存在：`ls -la /tmp/trading_*.ipc`
- 检查权限：`chmod 666 /tmp/trading_*.ipc`（如果需要）

### 2. 没有收到 trades

**检查：**
- WebSocket 是否连接成功
- 是否订阅了正确的频道
- 交易所是否有活跃交易

### 3. 订单失败

**检查：**
- API 密钥是否正确
- 模拟盘余额是否充足
- 订单参数是否正确（symbol, quantity 等）

## 性能指标

### 延迟测量

- **WebSocket → 实盘服务器**：通常 < 10ms
- **实盘服务器 → 策略**：通常 < 1ms（IPC）
- **策略 → 实盘服务器**：通常 < 1ms（IPC）
- **实盘服务器 → OKX API**：通常 50-200ms（网络）

### 吞吐量

- **Trades 接收**：取决于市场活跃度
- **订单处理**：每 10 秒 1 笔（可配置）

## 命令行参数

### 策略客户端参数

```bash
python3 zmq_strategy_client.py --help

选项:
  --cpu CPU           绑定到指定 CPU 核心 (默认: 自动分配)
  --strategy-id ID    策略 ID (默认: test)
  --strategy-index N   策略编号，用于自动分配 CPU (默认: 0)
  --order-interval N  下单间隔秒数 (默认: 10)
  --realtime          启用实时调度优先级 (需要 sudo)
  --no-bindcpu        禁用 CPU 绑定
```

## 注意事项

1. **模拟盘模式**：默认使用 OKX 模拟盘，不会产生真实交易
2. **下单金额**：每次下单 1 USDT，用于测试
3. **CPU 绑定**：确保所有进程在同一 NUMA 节点（Node 0）
4. **实时调度**：需要 root 权限或 CAP_SYS_NICE 能力
5. **按 Ctrl+C 停止**：两个终端都可以优雅退出

