# 策略配置系统使用说明

## 概述

策略配置系统允许每个策略拥有独立的配置文件，包含账户信息、联系人信息、风控配置等。服务器启动时自动加载所有策略配置并注册账户。

## 目录结构

```
cpp/
├── strategies/
│   ├── configs/                         # 策略配置目录
│   │   ├── grid_strategy_1.json        # 网格策略1配置
│   │   ├── arbitrage_strategy_1.json   # 套利策略配置
│   │   └── gnn_strategy_1.json         # GNN策略配置
│   ├── grid_strategy_cpp.py            # 网格策略程序
│   └── test/
│       ├── test_strategy_config.py     # 完整测试脚本
│       └── test_config_quick.py        # 快速测试脚本
├── trading/
│   └── strategy_config_loader.h         # 策略配置加载器
└── server/
    └── trading_server_main.cpp          # 服务器主程序
```

## 配置文件格式

### 完整示例

```json
{
  "strategy_id": "grid_strategy_1",
  "strategy_name": "BTC网格策略-主账户",
  "strategy_type": "grid",
  "enabled": true,
  "description": "BTC永续合约网格交易策略",

  "exchange": "okx",
  "api_key": "your_okx_api_key_here",
  "secret_key": "your_okx_secret_key_here",
  "passphrase": "your_okx_passphrase_here",
  "is_testnet": true,
  "market": "futures",

  "contacts": [
    {
      "name": "张三",
      "phone": "+86-138-0000-0001",
      "email": "zhangsan@example.com",
      "wechat": "zhangsan_wx",
      "department": "量化交易部",
      "role": "策略负责人"
    },
    {
      "name": "李四",
      "phone": "+86-138-0000-0002",
      "email": "lisi@example.com",
      "department": "风控部",
      "role": "风控负责人"
    }
  ],

  "risk_control": {
    "enabled": true,
    "max_position_value": 50000,
    "max_daily_loss": 5000,
    "max_order_amount": 1000,
    "max_orders_per_minute": 20
  },

  "params": {
    "symbol": "BTC-USDT-SWAP",
    "grid_num": 20,
    "grid_spread": 0.002
  }
}
```

### 字段说明

#### 基本信息
- `strategy_id` (必填): 策略唯一标识符
- `strategy_name` (可选): 策略可读名称
- `strategy_type` (可选): 策略类型 (grid/arbitrage/gnn等)
- `enabled` (必填): 是否启用该策略
- `description` (可选): 策略描述

#### 交易所账户
- `exchange` (必填): 交易所 (okx/binance)
- `api_key` (必填): API Key
- `secret_key` (必填): Secret Key
- `passphrase` (OKX必填): Passphrase
- `is_testnet` (必填): 是否测试网
- `market` (Binance必填): 市场类型 (futures/spot/coin_futures)

#### 联系人信息 (数组)
- `name` (必填): 姓名
- `phone` (必填): 电话号码
- `email` (可选): 邮箱
- `wechat` (可选): 微信号
- `department` (可选): 部门
- `role` (可选): 角色

#### 风控配置
- `enabled`: 是否启用风控
- `max_position_value`: 最大持仓价值 (USD)
- `max_daily_loss`: 最大日亏损 (USD)
- `max_order_amount`: 单笔最大下单金额 (USD)
- `max_orders_per_minute`: 每分钟最大下单次数

#### 策略参数
- `params`: 策略自定义参数 (JSON对象)

## 使用流程

### 1. 创建策略配置文件

在 `cpp/strategies/configs/` 目录下创建 `your_strategy.json`:

```bash
cd cpp/strategies/configs
cp grid_strategy_1.json my_strategy.json
# 编辑 my_strategy.json，填写你的配置
```

### 2. 编译服务器

```bash
cd cpp/build
cmake ..
make trading_server_full
```

### 3. 启动服务器

```bash
cd cpp/build
./trading_server_full
```

服务器启动时会自动：
1. 扫描 `../strategies/configs/` 目录
2. 加载所有 `.json` 配置文件
3. 注册策略账户到 `AccountRegistry`
4. 显示加载结果

### 4. 启动策略程序

```bash
cd cpp/strategies
python3 grid_strategy_cpp.py --strategy-id my_strategy --symbol BTC-USDT-SWAP
```

策略程序使用 `strategy_id` 连接到服务器，服务器会自动使用对应的账户。

## 风控端查询接口

风控端可以通过 ZeroMQ 查询接口获取策略配置信息。

### 查询单个策略配置

```python
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("ipc:///tmp/trading_query.ipc")

query = {
    "strategy_id": "grid_strategy_1",
    "query_type": "get_strategy_config",
    "params": {"strategy_id": "grid_strategy_1"}
}
socket.send_json(query)
response = socket.recv_json()

if response['code'] == 0:
    config = response['data']
    print(f"策略名称: {config['strategy_name']}")
    print(f"交易所: {config['exchange']}")
    print(f"联系人: {config['contacts']}")
    print(f"风控配置: {config['risk_control']}")
```

### 查询所有策略配置

```python
query = {
    "strategy_id": "any",
    "query_type": "get_all_strategy_configs"
}
socket.send_json(query)
response = socket.recv_json()

if response['code'] == 0:
    configs = response['data']
    for config in configs:
        print(f"{config['strategy_id']}: {config['strategy_name']}")
```

### 查询联系人信息

```python
query = {
    "strategy_id": "grid_strategy_1",
    "query_type": "get_strategy_contacts",
    "params": {"strategy_id": "grid_strategy_1"}
}
socket.send_json(query)
response = socket.recv_json()

if response['code'] == 0:
    contacts = response['data']
    for contact in contacts:
        print(f"{contact['name']}: {contact['phone']} ({contact['role']})")
```

### 查询风控配置

```python
query = {
    "strategy_id": "grid_strategy_1",
    "query_type": "get_strategy_risk_control",
    "params": {"strategy_id": "grid_strategy_1"}
}
socket.send_json(query)
response = socket.recv_json()

if response['code'] == 0:
    risk = response['data']
    print(f"风控启用: {risk['enabled']}")
    print(f"最大持仓: {risk['max_position_value']}")
    print(f"最大日亏损: {risk['max_daily_loss']}")
```

## 测试

### 快速测试（推荐）

测试配置文件格式和内容：

```bash
cd cpp/strategies/test
python3 test_config_quick.py
```

### 完整测试

测试服务器启动和配置加载：

```bash
cd cpp/strategies/test
python3 test_strategy_config.py --mode mock
```

## 注意事项

1. **配置文件命名**: 文件名应为 `{strategy_id}.json`
2. **API密钥安全**: 不要将真实API密钥提交到版本控制系统
3. **测试网优先**: 新策略应先在测试网测试
4. **联系人信息**: 至少填写一个联系人的姓名和电话
5. **禁用策略**: 设置 `"enabled": false` 可以禁用策略而不删除配置文件

## 故障排查

### 配置未加载

检查：
1. 配置文件是否在 `cpp/strategies/configs/` 目录
2. 文件扩展名是否为 `.json`
3. JSON格式是否正确
4. 必填字段是否完整

### 策略未注册

检查：
1. `enabled` 是否为 `true`
2. `api_key` 和 `secret_key` 是否填写
3. 服务器启动日志中是否有错误信息

### 订单被拒绝

检查：
1. 策略ID是否正确
2. 策略是否已注册（查看服务器启动日志）
3. API密钥是否有效

## 示例配置

项目中提供了以下示例配置（对应实际策略文件）：

### 生产环境配置

1. **grid_btc_main.json** - BTC网格策略主账户
   - 对应策略: `grid_strategy_cpp.py`
   - 交易对: BTC-USDT-SWAP
   - 联系人: 张三（策略负责人）、李四（风控负责人）

2. **grid_eth_backup.json** - ETH网格策略备用账户
   - 对应策略: `grid_strategy_cpp_2.py`
   - 交易对: ETH-USDT-SWAP
   - 联系人: 王五（策略负责人）

3. **gnn_multi_coin.json** - GNN多币种预测策略
   - 对应策略: `GNN_model/trading/GNNstr/gnn_strategy.py`
   - 交易对: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
   - 联系人: 孙七（策略负责人）、周八（风控负责人）

### 测试环境配置

4. **grid_paper_test.json** - 模拟盘网格策略
   - 对应策略: `grid_strategy_paper.py`
   - 交易对: SOL-USDT-SWAP
   - 联系人: 赵六（测试负责人）

5. **test_strategy_disabled.json** - 禁用策略示例
   - 用于演示如何禁用策略

可以参考这些示例创建自己的配置文件。

## 技术支持

如有问题，请联系：
- 技术支持: tech@example.com
- 风控部门: risk@example.com
