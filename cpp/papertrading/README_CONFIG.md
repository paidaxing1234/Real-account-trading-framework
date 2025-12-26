# 模拟交易配置系统说明

## 概述

本次更新为模拟交易系统添加了完整的配置管理功能，将原本硬编码的参数提取到配置文件中，提高了系统的灵活性和可维护性。

## 主要改进

### 1. 配置文件系统

- **新增文件**：
  - `papertrading_config.h` / `papertrading_config.cpp`：配置管理类
  - `papertrading_config.json`：默认配置文件

- **配置项**：
  - **账户配置**：
    - `initial_balance`：初始USDT余额（默认：100000）
    - `default_leverage`：默认杠杆倍数（默认：1.0，无杠杆）
  
  - **手续费配置**：
    - `maker_fee_rate`：挂单手续费率（默认：0.0002 = 0.02%）
    - `taker_fee_rate`：市价单手续费率（默认：0.0005 = 0.05%）
  
  - **交易配置**：
    - `market_order_slippage`：市价单滑点（默认：0.0001 = 0.01%）
    - `default_contract_value`：默认合约面值（默认：1.0）
  
  - **行情配置**：
    - `is_testnet`：是否使用测试网（默认：true）
  
  - **交易对特定配置**：
    - `symbol_contract_values`：各交易对的合约面值
    - `symbol_leverages`：各交易对的杠杆倍数

### 2. 代码改进

- **PaperTradingServer**：
  - 构造函数现在接受配置对象
  - 从配置读取手续费率、滑点、初始余额等参数
  - 支持按交易对获取合约面值

- **OrderExecutionEngine**：
  - 构造函数接受配置对象（可选）
  - 手续费率和滑点从配置读取
  - 合约面值从配置获取（支持交易对特定配置）

- **main.cpp**：
  - 支持从配置文件加载配置
  - 支持命令行参数覆盖部分配置（--balance, --testnet, --prod）
  - 配置文件路径可通过 `--config` 参数指定

## 发现的不足和改进建议

### 1. 已修复的问题

✅ **硬编码的手续费率**：
- 之前：在 `papertrading_server.h` 和 `order_execution_engine.cpp` 中硬编码
- 现在：统一从配置文件读取

✅ **硬编码的滑点**：
- 之前：在多个地方硬编码为 0.0001
- 现在：从配置文件读取

✅ **硬编码的初始余额**：
- 之前：在 `main.cpp` 中硬编码为 100000
- 现在：从配置文件读取，支持命令行覆盖

✅ **硬编码的合约面值**：
- 之前：在 `order_execution_engine.cpp` 和 `mock_account_engine.cpp` 中硬编码为 1.0
- 现在：从配置文件读取，支持交易对特定配置

✅ **缺少杠杆配置**：
- 之前：没有杠杆配置，默认使用1倍
- 现在：支持默认杠杆和交易对特定杠杆配置

### 2. 待改进的问题

⚠️ **MockAccountEngine::update_unrealized_pnl()**：
- 问题：该函数中仍使用硬编码的合约面值（1.0）
- 影响：如果该函数被调用，未实现盈亏计算可能不准确
- 建议：修改函数签名接受合约面值参数，或让MockAccountEngine持有配置对象引用

⚠️ **杠杆计算**：
- 问题：虽然配置支持杠杆，但实际持仓计算中可能未完全使用杠杆
- 建议：检查持仓计算逻辑，确保杠杆正确应用

⚠️ **配置验证**：
- 问题：配置验证在加载时进行，但某些无效配置可能导致运行时错误
- 建议：增强配置验证，提供更详细的错误信息

⚠️ **向后兼容性**：
- 问题：旧的构造函数接口（`PaperTradingServer(double, bool)`）仍存在但功能受限
- 建议：考虑标记为废弃（deprecated），或完全移除

## 使用方法

### 1. 使用默认配置

```bash
./papertrading_server
```

### 2. 指定配置文件

```bash
./papertrading_server --config my_config.json
```

### 3. 命令行参数覆盖

```bash
# 覆盖初始余额
./papertrading_server --balance 50000

# 覆盖测试网设置
./papertrading_server --prod
```

### 4. 配置文件示例

```json
{
  "account": {
    "initial_balance": 100000.0,
    "default_leverage": 1.0
  },
  "fees": {
    "maker_fee_rate": 0.0002,
    "taker_fee_rate": 0.0005
  },
  "trading": {
    "market_order_slippage": 0.0001,
    "default_contract_value": 1.0
  },
  "market_data": {
    "is_testnet": true
  },
  "symbol_contract_values": {
    "BTC-USDT-SWAP": 0.01,
    "ETH-USDT-SWAP": 0.1
  },
  "symbol_leverages": {
    "BTC-USDT-SWAP": 10.0,
    "ETH-USDT-SWAP": 10.0
  }
}
```

## 配置项说明

### 手续费率

- **maker_fee_rate**：挂单（限价单）手续费率
  - OKX标准：0.02% (0.0002)
  - VIP等级可降低

- **taker_fee_rate**：吃单（市价单）手续费率
  - OKX标准：0.05% (0.0005)
  - VIP等级可降低

### 滑点

- **market_order_slippage**：市价单滑点
  - 模拟市价单执行时的价格偏差
  - 买单：价格向上滑点（对买方不利）
  - 卖单：价格向下滑点（对卖方不利）

### 合约面值

- **default_contract_value**：默认合约面值
  - 1.0 表示 1张 = 1个币（适用于大多数永续合约）
  - 不同交易对的合约面值可能不同

- **symbol_contract_values**：交易对特定合约面值
  - 例如：BTC-USDT-SWAP 的合约面值可能是 0.01（1张 = 0.01 BTC）

### 杠杆

- **default_leverage**：默认杠杆倍数
  - 1.0 表示无杠杆（现货模式）
  - 范围：1.0 - 125.0

- **symbol_leverages**：交易对特定杠杆倍数
  - 可以为不同交易对设置不同的杠杆

## 注意事项

1. **配置文件路径**：默认使用当前目录下的 `papertrading_config.json`
2. **配置验证**：启动时会验证配置有效性，无效配置会导致启动失败
3. **命令行覆盖**：命令行参数会覆盖配置文件中的对应项
4. **交易对配置**：如果交易对未在配置中指定，将使用默认值

## 未来改进方向

1. 支持环境变量配置
2. 支持配置热重载（无需重启）
3. 配置模板和示例文件
4. 更详细的配置验证和错误提示
5. 配置变更日志记录

