# 多账户网格策略使用指南

## 概述

同一个网格策略代码可以用不同的账户启动多个实例，每个实例独立运行，互不干扰。

## 核心概念

### 1. 策略隔离
- 每个策略实例使用唯一的 `strategy_id`
- 服务器根据 `strategy_id` 路由订单到对应账户
- 不同实例可以交易不同的交易对

### 2. 账户类型
- **默认账户**: 不提供 API 密钥，使用服务器注册的默认账户
- **策略专用账户**: 提供 API 密钥，策略启动时自动注册到服务器

### 3. 服务器模式
- **实盘服务器**: 连接 `ipc:///tmp/trading_*.ipc`
- **模拟盘服务器**: 连接 `ipc:///tmp/paper_*.ipc`

---

## 方式一：命令行启动（手动）

### 启动账户1（使用默认账户）
```bash
python3 grid_strategy_cpp.py \
    --strategy-id grid_account1 \
    --symbol BTC-USDT-SWAP \
    --grid-num 10 \
    --grid-spread 0.002 \
    --order-amount 50 \
    --testnet
```

### 启动账户2（使用独立账户）
```bash
python3 grid_strategy_cpp.py \
    --strategy-id grid_account2 \
    --symbol ETH-USDT-SWAP \
    --grid-num 15 \
    --grid-spread 0.0015 \
    --order-amount 100 \
    --api-key "YOUR_API_KEY" \
    --secret-key "YOUR_SECRET_KEY" \
    --passphrase "YOUR_PASSPHRASE" \
    --testnet
```

### 启动账户3（连接模拟盘服务器）
需要修改 `grid_strategy_cpp.py` 中的 IPC 地址为模拟盘地址。

---

## 方式二：Shell 脚本启动（批量）

使用提供的 `run_multi_account.sh` 脚本：

```bash
cd /home/llx/Real-account-trading-framework/cpp/strategies
./run_multi_account.sh
```

**优点**:
- 一键启动多个账户
- 自动记录 PID
- 方便统一管理

**停止所有策略**:
```bash
# 查看运行中的策略
ps aux | grep grid_strategy_cpp

# 停止所有
pkill -f grid_strategy_cpp
```

---

## 方式三：配置文件启动（推荐）

### 1. 编辑配置文件

编辑 `multi_account_config.yaml`:

```yaml
accounts:
  # 账户1：默认账户
  - strategy_id: "grid_default"
    symbol: "BTC-USDT-SWAP"
    grid_num: 10
    grid_spread: 0.002
    order_amount: 50
    use_default_account: true

  # 账户2：OKX 专用账户
  - strategy_id: "grid_okx_eth"
    symbol: "ETH-USDT-SWAP"
    grid_num: 15
    grid_spread: 0.0015
    order_amount: 100
    api_key: "YOUR_API_KEY"
    secret_key: "YOUR_SECRET_KEY"
    passphrase: "YOUR_PASSPHRASE"
    is_testnet: true
```

### 2. 启动所有账户

```bash
python3 run_multi_account.py --config multi_account_config.yaml
```

**优点**:
- 配置集中管理
- 支持多进程并行
- 自动信号处理

---

## 连接不同服务器

### 修改策略连接地址

在 `grid_strategy_cpp.py` 中，策略通过 C++ 基类连接服务器。需要修改基类的 IPC 地址。

**实盘服务器**（默认）:
```python
# C++ 基类默认连接实盘地址
# ipc:///tmp/trading_md.ipc
# ipc:///tmp/trading_order.ipc
# ipc:///tmp/trading_report.ipc
```

**模拟盘服务器**:
需要在 C++ 基类中添加参数支持，或者创建专门的模拟盘策略基类。

---

## 实际使用示例

### 场景1：同一交易所，不同交易对

```bash
# 账户1交易 BTC
python3 grid_strategy_cpp.py --strategy-id grid_btc --symbol BTC-USDT-SWAP &

# 账户2交易 ETH
python3 grid_strategy_cpp.py --strategy-id grid_eth --symbol ETH-USDT-SWAP &

# 账户3交易 SOL
python3 grid_strategy_cpp.py --strategy-id grid_sol --symbol SOL-USDT-SWAP &
```

### 场景2：不同账户，相同交易对

```bash
# 账户1：激进策略（小网格）
python3 grid_strategy_cpp.py \
    --strategy-id grid_aggressive \
    --symbol BTC-USDT-SWAP \
    --grid-num 20 \
    --grid-spread 0.001 \
    --api-key "KEY1" --secret-key "SECRET1" --passphrase "PASS1" &

# 账户2：保守策略（大网格）
python3 grid_strategy_cpp.py \
    --strategy-id grid_conservative \
    --symbol BTC-USDT-SWAP \
    --grid-num 5 \
    --grid-spread 0.005 \
    --api-key "KEY2" --secret-key "SECRET2" --passphrase "PASS2" &
```

### 场景3：实盘 + 模拟盘测试

```bash
# 实盘账户（小资金）
python3 grid_strategy_cpp.py \
    --strategy-id grid_live \
    --symbol BTC-USDT-SWAP \
    --order-amount 10 \
    --live &

# 模拟盘账户（大资金测试）
python3 grid_strategy_cpp.py \
    --strategy-id grid_paper \
    --symbol BTC-USDT-SWAP \
    --order-amount 1000 \
    --testnet &
```

---

## 监控和管理

### 查看运行状态
```bash
# 查看所有策略进程
ps aux | grep grid_strategy_cpp

# 查看日志（如果有）
tail -f /tmp/grid_*.log
```

### 停止特定策略
```bash
# 根据 PID 停止
kill <PID>

# 根据策略ID停止（需要自定义脚本）
pkill -f "strategy-id grid_account1"
```

### 重启策略
```bash
# 停止
kill <PID>

# 重新启动
python3 grid_strategy_cpp.py --strategy-id grid_account1 ... &
```

---

## 注意事项

1. **strategy_id 必须唯一**
   - 每个策略实例必须有不同的 strategy_id
   - 服务器用 strategy_id 区分不同策略

2. **账户注册顺序**
   - 先在前端或通过 API 注册账户到服务器
   - 然后启动策略，策略会自动关联到对应账户

3. **资源限制**
   - 注意交易所 API 限流
   - 避免同时启动过多策略实例

4. **风险控制**
   - 每个账户设置独立的风险限制
   - 建议先在模拟盘测试

---

## 故障排查

### 问题1：策略无法连接服务器
```bash
# 检查服务器是否运行
ps aux | grep trading_server

# 检查 IPC 文件是否存在
ls -la /tmp/trading_*.ipc
```

### 问题2：订单没有执行
- 检查账户是否正确注册
- 检查 strategy_id 是否匹配
- 查看服务器日志

### 问题3：多个策略冲突
- 确保每个策略的 strategy_id 不同
- 检查是否使用了相同的账户

---

**更新时间**: 2026-01-04
