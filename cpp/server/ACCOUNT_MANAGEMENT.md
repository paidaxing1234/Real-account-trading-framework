# 账户管理系统使用指南

## 概述

新的账户管理系统支持：
- ✅ 多策略独立账户
- ✅ 默认账户（未注册策略使用）
- ✅ OKX 和 Binance 双交易所
- ✅ 配置文件 + 环境变量
- ✅ 线程安全

---

## 快速开始

### 1. 配置文件方式（推荐）

创建 `accounts.json`：

```json
{
  "default": {
    "exchange": "okx",
    "api_key": "your_api_key",
    "secret_key": "your_secret_key",
    "passphrase": "your_passphrase",
    "is_testnet": true
  },
  "strategies": {
    "grid_strategy_1": {
      "exchange": "okx",
      "api_key": "strategy1_api_key",
      "secret_key": "strategy1_secret_key",
      "passphrase": "strategy1_passphrase",
      "is_testnet": false
    },
    "arbitrage_binance": {
      "exchange": "binance",
      "api_key": "binance_api_key",
      "secret_key": "binance_secret_key",
      "is_testnet": false
    }
  }
}
```

启动服务器：
```bash
cd cpp/server
./trading_server_full
```

服务器会自动加载配置文件。

---

### 2. 环境变量方式

```bash
export OKX_API_KEY="your_api_key"
export OKX_SECRET_KEY="your_secret_key"
export OKX_PASSPHRASE="your_passphrase"
export OKX_TESTNET="1"  # 1=模拟盘, 0=实盘

./trading_server_full
```

环境变量会覆盖配置文件中的默认账户。

---

### 3. 运行时注册（动态）

策略可以在运行时通过 ZMQ 消息注册账户：

```python
# Python 策略端
import zmq
import json

context = zmq.Context()
order_socket = context.socket(zmq.PUSH)
order_socket.connect("ipc:///tmp/trading_order")

# 注册账户
register_msg = {
    "type": "register_account",
    "strategy_id": "my_strategy",
    "api_key": "xxx",
    "secret_key": "yyy",
    "passphrase": "zzz",
    "is_testnet": True
}

order_socket.send_string(json.dumps(register_msg))
```

---

## 代码使用示例

### C++ 端

```cpp
#include "core/account_registry.h"
#include "core/config_loader.h"

using namespace trading;

int main() {
    // 创建账户注册器
    AccountRegistry registry;

    // 方式1：从配置文件加载
    load_accounts_from_config(registry, "accounts.json");

    // 方式2：手动注册
    registry.register_okx_account(
        "my_strategy",
        "api_key",
        "secret_key",
        "passphrase",
        true  // is_testnet
    );

    // 方式3：设置默认账户
    registry.set_default_okx_account(
        "default_api_key",
        "default_secret_key",
        "default_passphrase",
        true
    );

    // 获取策略的 API 客户端
    okx::OKXRestAPI* api = registry.get_okx_api("my_strategy");
    if (api) {
        // 使用 API 下单
        auto result = api->place_order(...);
    }

    // 查询统计
    std::cout << "已注册账户: " << registry.count() << "\n";
    std::cout << "OKX账户: " << registry.okx_count() << "\n";
    std::cout << "Binance账户: " << registry.binance_count() << "\n";

    return 0;
}
```

---

## 配置文件详解

### 默认账户配置

```json
{
  "default": {
    "exchange": "okx",           // 交易所: "okx" 或 "binance"
    "api_key": "xxx",            // API Key
    "secret_key": "yyy",         // Secret Key
    "passphrase": "zzz",         // Passphrase (仅OKX需要)
    "is_testnet": true           // true=模拟盘, false=实盘
  }
}
```

### 策略账户配置

```json
{
  "strategies": {
    "strategy_id_1": {           // 策略ID（自定义）
      "exchange": "okx",
      "api_key": "xxx",
      "secret_key": "yyy",
      "passphrase": "zzz",
      "is_testnet": false
    },
    "strategy_id_2": {
      "exchange": "binance",     // Binance不需要passphrase
      "api_key": "aaa",
      "secret_key": "bbb",
      "is_testnet": true
    }
  }
}
```

---

## 账户查找逻辑

当策略发送订单时，服务器按以下顺序查找账户：

1. **策略独立账户**：查找 `strategy_id` 对应的账户
2. **默认账户**：如果策略未注册，使用默认账户
3. **失败**：如果都没有，订单被拒绝

示例：
```
策略 "grid_1" 下单
  ↓
查找 registry.get_okx_api("grid_1")
  ↓
找到 → 使用 grid_1 的账户
未找到 → 使用默认账户
```

---

## 安全建议

### 1. 配置文件权限

```bash
# 设置配置文件为只读（仅所有者）
chmod 600 accounts.json

# 不要提交到 Git
echo "accounts.json" >> .gitignore
```

### 2. 使用环境变量（生产环境）

```bash
# 不要在代码中硬编码密钥
# 使用环境变量或密钥管理服务（如 AWS Secrets Manager）

export OKX_API_KEY=$(aws secretsmanager get-secret-value --secret-id okx-api-key --query SecretString --output text)
```

### 3. 分离测试和生产配置

```
accounts.testnet.json  # 测试环境
accounts.prod.json     # 生产环境
```

---

## 常见问题

### Q1: 配置文件加载失败怎么办？

**A**: 服务器会自动回退到环境变量或默认值，不会崩溃。

```
[配置] 配置文件加载失败，使用环境变量/默认值
[初始化] 默认OKX账户 ✓ (API Key: 5dee6507...)
```

### Q2: 如何支持多个交易所？

**A**: 在配置文件中指定 `exchange` 字段：

```json
{
  "strategies": {
    "okx_strategy": {
      "exchange": "okx",
      ...
    },
    "binance_strategy": {
      "exchange": "binance",
      ...
    }
  }
}
```

### Q3: 如何动态切换账户？

**A**: 发送 `unregister_account` 后再 `register_account`：

```python
# 注销旧账户
unregister_msg = {
    "type": "unregister_account",
    "strategy_id": "my_strategy"
}
order_socket.send_string(json.dumps(unregister_msg))

# 注册新账户
register_msg = {
    "type": "register_account",
    "strategy_id": "my_strategy",
    "api_key": "new_key",
    ...
}
order_socket.send_string(json.dumps(register_msg))
```

### Q4: 如何查看已注册的账户？

**A**: 通过查询接口：

```python
query_msg = {
    "type": "query",
    "query_type": "registered_accounts"
}
# 返回: {"count": 3}
```

---

## 迁移指南

### 从旧版本迁移

**旧代码**（硬编码）：
```cpp
OKXRestAPI api(api_key, secret_key, passphrase, is_testnet);
```

**新代码**（使用注册器）：
```cpp
AccountRegistry registry;
registry.set_default_okx_account(api_key, secret_key, passphrase, is_testnet);
OKXRestAPI* api = registry.get_okx_api("strategy_id");
```

**优势**：
- ✅ 支持多账户
- ✅ 配置文件管理
- ✅ 线程安全
- ✅ 动态注册/注销

---

## 性能说明

- **查找开销**：O(log n)，使用 `std::map`
- **线程安全**：使用 `std::mutex`，锁粒度小
- **内存占用**：每个账户约 200 字节
- **推荐规模**：< 100 个策略账户

---

## 下一步

- [ ] 添加账户权限管理（只读/交易）
- [ ] 添加账户使用统计（订单数、成交量）
- [ ] 添加账户热切换（无需重启）
- [ ] 添加账户健康检查（API 有效性）

---

**更新时间**: 2026-01
**维护者**: Sequence Team
