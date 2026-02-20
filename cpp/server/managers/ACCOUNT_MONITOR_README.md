# 账户监控模块使用说明

## 📋 功能概述

账户监控模块 (`account_monitor.h`) 提供实时监控账户状态的功能，自动更新风控管理器，实现：

1. **定期查询账户余额** - 检测余额不足
2. **实时监控持仓** - 更新持仓到风控管理器
3. **计算盈亏** - 监控每日盈亏和最大回撤
4. **自动告警** - 触发风控告警

## 🚀 快速集成

### 1. 在 trading_server_main.cpp 中添加

```cpp
#include "managers/account_monitor.h"

int main() {
    // ... 现有初始化代码 ...

    // 创建账户监控器（使用全局风控管理器）
    AccountMonitor account_monitor(g_risk_manager);

    // 注册需要监控的账户
    // 方式1: 从 account_registry 获取所有已注册账户
    for (const auto& [strategy_id, api] : g_account_registry.get_all_okx_accounts()) {
        account_monitor.register_okx_account(strategy_id, api);
    }

    // 方式2: 手动注册特定账户
    // okx::OKXRestAPI* api = get_okx_api_for_strategy("my_strategy");
    // if (api) {
    //     account_monitor.register_okx_account("my_strategy", api);
    // }

    // 启动监控（每5秒查询一次）
    account_monitor.start(5);

    std::cout << "[服务器] 账户监控已启动\n";

    // ... 主循环 ...

    // 停止监控
    account_monitor.stop();

    return 0;
}
```

### 2. 修改 account_registry.h 添加获取所有账户的方法

在 `AccountRegistry` 类中添加：

```cpp
// 获取所有 OKX 账户（用于监控）
const std::map<std::string, okx::OKXRestAPI*>& get_all_okx_accounts() const {
    return okx_accounts_;
}

// 获取所有 Binance 账户（用于监控）
const std::map<std::string, binance::BinanceRestAPI*>& get_all_binance_accounts() const {
    return binance_accounts_;
}
```

## 📊 监控内容

### OKX 账户监控

- ✅ 账户总权益 (total equity)
- ✅ 未实现盈亏 (unrealized PnL)
- ✅ 持仓信息 (positions)
- ✅ 挂单数量 (open orders)

### Binance 账户监控

- ✅ 账户余额 (wallet balance)
- ✅ 未实现盈亏 (unrealized profit)
- ✅ 持仓信息 (positions)

## ⚙️ 配置选项

### 监控间隔

```cpp
// 默认5秒
account_monitor.start(5);

// 更频繁的监控（1秒）
account_monitor.start(1);

// 较慢的监控（30秒）
account_monitor.start(30);
```

### 风控阈值

在 `risk_config.json` 中配置：

```json
{
  "risk_limits": {
    "max_order_value": 10000.0,
    "max_position_value": 50000.0,
    "max_total_exposure": 100000.0,
    "daily_loss_limit": 5000.0,
    "max_drawdown_pct": 0.10
  }
}
```

## 🔔 告警触发条件

监控模块会在以下情况触发告警：

1. **账户余额不足** - 低于最小余额要求（默认1000 USDT）
2. **每日亏损超限** - 超过 `daily_loss_limit`
3. **最大回撤超限** - 超过 `max_drawdown_pct`，自动激活 Kill Switch

## 📝 日志输出示例

```
[账户监控] 启动，间隔: 5秒
[账户监控] 注册 OKX 账户: strategy_001
[账户监控] 注册 OKX 账户: strategy_002
[风控] ✓ 账户余额正常: 15000.0 USDT
[风控] ⚠ 每日亏损: -3500.0 USDT
[账户监控] 已停止
```

## 🛠️ 高级用法

### 手动触发更新

```cpp
// 不启动定时监控，手动触发
account_monitor.update_all_accounts();
```

### 动态添加账户

```cpp
// 运行时添加新账户
okx::OKXRestAPI* new_api = new okx::OKXRestAPI(...);
account_monitor.register_okx_account("new_strategy", new_api);
```

### 与 WebSocket 回调结合

在 WebSocket 订单成交回调中实时更新：

```cpp
void on_order_filled(const nlohmann::json& order_data) {
    // 订单成交后立即更新账户状态
    account_monitor.update_all_accounts();
}
```

## ⚠️ 注意事项

1. **API 频率限制** - 不要设置过短的监控间隔（建议 ≥ 5秒）
2. **线程安全** - 风控管理器内部已使用 mutex 保护
3. **异常处理** - 监控线程会捕获异常，不会导致程序崩溃
4. **资源清理** - 析构函数会自动停止监控线程

## 🔗 相关文件

- [account_monitor.h](account_monitor.h) - 账户监控模块
- [risk_manager.h](../../trading/risk_manager.h) - 风控管理器
- [order_processor.cpp](../handlers/order_processor.cpp) - 订单处理（风控集成）
- [risk_config.json](../../risk_config.json) - 风控配置文件

---

**版本**: v1.0.0
**更新时间**: 2025-02-10
**状态**: ✅ 可用
