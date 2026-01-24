# 策略与配置文件对应关系

## 概述

本文档说明每个策略程序对应的配置文件，以及如何启动策略。

## 策略列表

### 1. BTC网格策略（主账户）

**策略程序**: `grid_strategy_cpp.py`
**配置文件**: `configs/grid_btc_main.json`
**策略ID**: `grid_btc_main`

**启动命令**:
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies
python3 grid_strategy_cpp.py \
    --strategy-id grid_btc_main \
    --symbol BTC-USDT-SWAP \
    --grid-num 20 \
    --grid-spread 0.002 \
    --order-amount 50
```

**联系人**:
- 张三 (+86-138-0000-0001) - 策略负责人
- 李四 (+86-138-0000-0002) - 风控负责人

---

### 2. ETH网格策略（备用账户）

**策略程序**: `grid_strategy_cpp_2.py`
**配置文件**: `configs/grid_eth_backup.json`
**策略ID**: `grid_eth_backup`

**启动命令**:
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies
python3 grid_strategy_cpp_2.py \
    --strategy-id grid_eth_backup \
    --symbol ETH-USDT-SWAP \
    --grid-num 15 \
    --grid-spread 0.0015 \
    --order-amount 100
```

**联系人**:
- 王五 (+86-139-0000-0003) - 策略负责人

---

### 3. GNN多币种预测策略

**策略程序**: `GNN_model/trading/GNNstr/gnn_strategy.py`
**配置文件**: `configs/gnn_multi_coin.json`
**策略ID**: `gnn_multi_coin`

**启动命令**:
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/GNN_model/trading/GNNstr
python3 gnn_strategy.py \
    --strategy-id gnn_multi_coin \
    --model-path ../../models/best_model.pth \
    --symbols BTCUSDT ETHUSDT BNBUSDT SOLUSDT
```

**联系人**:
- 孙七 (+86-137-0000-0005) - 策略负责人
- 周八 (+86-135-0000-0006) - 风控负责人

---

### 4. 模拟盘网格策略（测试）

**策略程序**: `grid_strategy_paper.py`
**配置文件**: `configs/grid_paper_test.json`
**策略ID**: `grid_paper_test`

**启动命令**:
```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies
python3 grid_strategy_paper.py \
    --strategy-id grid_paper_test \
    --symbol SOL-USDT-SWAP \
    --grid-num 20 \
    --grid-spread 0.001 \
    --order-amount 30
```

**联系人**:
- 赵六 (+86-136-0000-0004) - 测试负责人

---

## 配置文件说明

每个配置文件包含以下信息：

1. **基本信息**: strategy_id, strategy_name, strategy_type
2. **交易所账户**: exchange, api_key, secret_key, passphrase
3. **联系人信息**: 姓名、电话、邮箱、微信、部门、角色
4. **风控配置**: 最大持仓、最大日亏损、单笔最大金额等
5. **策略参数**: 交易对、网格数量、间距等

## 启动流程

### 1. 启动交易服务器

```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build
./trading_server_full
```

服务器会自动加载所有配置文件并注册账户。

### 2. 启动策略程序

根据上面的启动命令启动对应的策略程序。策略程序会：
1. 使用 `strategy_id` 连接到服务器
2. 服务器自动使用对应的账户
3. 开始交易

## 风控查询示例

风控端可以查询任何策略的配置和联系人信息：

```python
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("ipc:///tmp/trading_query.ipc")

# 查询BTC网格策略的联系人
query = {
    "strategy_id": "grid_btc_main",
    "query_type": "get_strategy_contacts",
    "params": {"strategy_id": "grid_btc_main"}
}
socket.send_json(query)
response = socket.recv_json()

if response['code'] == 0:
    contacts = response['data']
    for contact in contacts:
        print(f"{contact['name']}: {contact['phone']} ({contact['role']})")
    # 输出:
    # 张三: +86-138-0000-0001 (策略负责人)
    # 李四: +86-138-0000-0002 (风控负责人)
```

## 添加新策略

### 步骤1: 创建配置文件

在 `configs/` 目录创建新的配置文件，例如 `my_strategy.json`:

```json
{
  "strategy_id": "my_strategy",
  "strategy_name": "我的策略",
  "strategy_type": "custom",
  "enabled": true,
  "exchange": "okx",
  "api_key": "your_api_key",
  "secret_key": "your_secret_key",
  "passphrase": "your_passphrase",
  "is_testnet": true,
  "contacts": [
    {
      "name": "你的名字",
      "phone": "+86-xxx-xxxx-xxxx",
      "role": "策略负责人"
    }
  ],
  "risk_control": {
    "enabled": true,
    "max_position_value": 10000,
    "max_daily_loss": 1000,
    "max_order_amount": 500,
    "max_orders_per_minute": 10
  },
  "params": {
    "symbol": "BTC-USDT-SWAP"
  }
}
```

### 步骤2: 重启服务器

```bash
cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build
./trading_server_full
```

服务器会自动加载新配置。

### 步骤3: 启动策略

```bash
python3 your_strategy.py --strategy-id my_strategy
```

## 注意事项

1. **策略ID必须唯一**: 不同策略不能使用相同的 strategy_id
2. **配置文件命名**: 建议使用 `{strategy_id}.json` 格式
3. **联系人信息必填**: 至少填写姓名和电话
4. **测试网优先**: 新策略应先在测试网测试
5. **API密钥安全**: 不要将真实密钥提交到版本控制

## 故障排查

### 策略无法连接

检查：
1. 服务器是否启动
2. strategy_id 是否正确
3. 配置文件是否存在且格式正确

### 订单被拒绝

检查：
1. 策略是否已注册（查看服务器启动日志）
2. API密钥是否有效
3. 账户余额是否充足

### 联系人信息查询失败

检查：
1. strategy_id 是否正确
2. 配置文件中是否有 contacts 字段
3. 服务器是否正常运行
