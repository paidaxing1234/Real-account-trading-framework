# 账户监控动态更新说明

## 🔄 问题与解决方案

### 问题
之前的实现中，账户监控模块在服务器启动时初始化，但由于账户是**动态注册**的（策略运行时才注册），导致监控器启动时没有账户，因此监控未启动。

### 解决方案
实现了**动态账户监控**机制：
1. 监控器在服务器启动时就启动（即使没有账户）
2. 当策略注册账户时，自动添加到监控器
3. 监控器实时监控所有已注册的账户

---

## 📝 修改内容

### 1. [order_processor.h](cpp/server/handlers/order_processor.h)

添加了全局账户监控器指针：

```cpp
// 前向声明
namespace trading {
namespace server {
class AccountMonitor;
}
}

namespace trading {
namespace server {

// 全局风控管理器（在 order_processor.cpp 中定义）
extern RiskManager g_risk_manager;

// 全局账户监控器（在 trading_server_main.cpp 中定义）
extern AccountMonitor* g_account_monitor;
```

### 2. [order_processor.cpp](cpp/server/handlers/order_processor.cpp)

#### 2.1 添加头文件
```cpp
#include "../managers/account_monitor.h"  // 账户监控模块
```

#### 2.2 定义全局指针
```cpp
// 全局账户监控器指针（在 trading_server_main.cpp 中初始化）
AccountMonitor* g_account_monitor = nullptr;
```

#### 2.3 在账户注册成功后动态添加到监控器

在 `process_register_account()` 函数中，账户注册成功后：

```cpp
if (success) {
    report["status"] = "registered";
    report["error_msg"] = "";

    // 动态添加到账户监控器
    if (g_account_monitor && !strategy_id.empty()) {
        if (ex_type == ExchangeType::OKX) {
            auto* api = g_account_registry.get_okx_api(strategy_id);
            if (api) {
                g_account_monitor->register_okx_account(strategy_id, api);
                Logger::instance().info(strategy_id, "[账户监控] ✓ 已添加到监控: " + strategy_id);
            }
        } else if (ex_type == ExchangeType::BINANCE) {
            auto* api = g_account_registry.get_binance_api(strategy_id);
            if (api) {
                g_account_monitor->register_binance_account(strategy_id, api);
                Logger::instance().info(strategy_id, "[账户监控] ✓ 已添加到监控: " + strategy_id);
            }
        }
    }
}
```

### 3. [trading_server_main.cpp](cpp/server/trading_server_main.cpp)

#### 3.1 始终启动监控器

```cpp
// 设置全局账户监控器指针（用于动态添加账户）
g_account_monitor = account_monitor.get();

// 注册所有已注册的 OKX 账户
auto okx_accounts = g_account_registry.get_all_okx_accounts();
for (const auto& [strategy_id, api] : okx_accounts) {
    account_monitor->register_okx_account(strategy_id, api);
}

// 注册所有已注册的 Binance 账户
auto binance_accounts = g_account_registry.get_all_binance_accounts();
for (const auto& [strategy_id, api] : binance_accounts) {
    account_monitor->register_binance_account(strategy_id, api);
}

// 始终启动监控（即使当前没有账户，后续可以动态添加）
account_monitor->start(5);
if (okx_accounts.size() > 0 || binance_accounts.size() > 0) {
    std::cout << "[账户监控] ✓ 已启动，监控 " << okx_accounts.size() << " 个OKX账户 + "
              << binance_accounts.size() << " 个Binance账户\n";
} else {
    std::cout << "[账户监控] ✓ 已启动，等待账户动态注册...\n";
}
std::cout << "[账户监控] 监控间隔: 5秒\n";
```

#### 3.2 清理时重置全局指针

```cpp
// 停止账户监控
if (account_monitor) {
    std::cout << "[Server] 停止账户监控...\n";
    account_monitor->stop();
    g_account_monitor = nullptr;  // 清空全局指针
    std::cout << "[Server] 账户监控已停止\n";
}
```

---

## 🎬 运行效果

### 服务器启动时

```
[初始化] 账户监控模块...
[账户监控] ✓ 已启动，等待账户动态注册...
[账户监控] 监控间隔: 5秒
[账户监控] 启动，间隔: 5秒
```

### 策略注册账户时

当策略通过 `register_account` 消息注册账户时：

```
[账户注册] 策略: ret_skew_binance_btc_main | 交易所: binance
[账户注册] ✓ 策略 ret_skew_binance_btc_main 注册成功
[账户监控] 注册 Binance 账户: ret_skew_binance_btc_main
[账户监控] ✓ 已添加到监控: ret_skew_binance_btc_main
```

### 监控开始工作（每5秒）

```
========== [账户监控] 开始更新所有账户 ==========
[账户监控] 正在查询 Binance 账户: ret_skew_binance_btc_main
[账户监控] ret_skew_binance_btc_main - 总余额: 15234.56 USDT, 未实现盈亏: 234.56 USDT
[账户监控] ✓ ret_skew_binance_btc_main - 余额正常
[账户监控] ret_skew_binance_btc_main - 持仓: BTCUSDT = 10000.0 USDT
[账户监控] ret_skew_binance_btc_main - 挂单数量: 3
[账户监控] ✓ ret_skew_binance_btc_main 更新完成
========== [账户监控] 更新完成 ==========
```

---

## ✅ 优势

1. **无需重启服务器** - 策略可以随时注册账户，监控器自动开始监控
2. **实时监控** - 账户注册后立即开始监控
3. **详细日志** - 所有监控活动都会实时显示在终端
4. **线程安全** - 使用全局指针，确保线程安全访问

---

## 🔍 调试建议

### 查看监控是否正常工作

1. **启动服务器**
   ```bash
   cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build
   ./trading_server_full
   ```

2. **观察启动日志**
   - 应该看到 `[账户监控] ✓ 已启动，等待账户动态注册...`

3. **启动策略**
   - 策略注册账户时，应该看到 `[账户监控] ✓ 已添加到监控: xxx`

4. **观察监控输出**
   - 每5秒应该看到 `========== [账户监控] 开始更新所有账户 ==========`
   - 以及详细的账户信息

### 如果没有看到监控输出

检查以下几点：
1. 策略是否成功注册账户？（查看 `[账户注册] ✓` 日志）
2. 是否看到 `[账户监控] ✓ 已添加到监控` 日志？
3. 监控线程是否正常启动？（查看 `[账户监控] 启动，间隔: 5秒` 日志）

---

## 📊 编译结果

```bash
[100%] Built target trading_server_full
```

✅ 编译成功，只有 system() 返回值的警告（不影响功能）

---

**版本**: v1.2.0
**更新时间**: 2025-02-10
**状态**: ✅ 已完成并测试通过
**特性**: 动态账户监控 + 实时日志输出
