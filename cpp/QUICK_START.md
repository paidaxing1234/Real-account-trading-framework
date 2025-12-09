# C++ 实盘交易框架 - 快速入门

## 🚀 5分钟快速开始

### 1. 环境准备

**系统要求**：
- C++17或更高版本编译器（GCC 7+, Clang 5+, MSVC 2017+）
- CMake 3.15+
- Git

**安装依赖**（Ubuntu/Debian）：
```bash
sudo apt update
sudo apt install -y build-essential cmake git
```

**安装依赖**（macOS）：
```bash
brew install cmake
```

### 2. 下载和编译

```bash
# 进入框架目录
cd Real-account-trading-framework/cpp

# 创建构建目录
mkdir build && cd build

# 配置（自动下载nlohmann/json）
cmake ..

# 编译
cmake --build .

# 查看生成的可执行文件
ls -lh
```

你将看到：
- `test_core` - 核心模块测试程序
- `main_example` - 完整示例程序

### 3. 运行测试

```bash
# 运行核心模块测试
./test_core
```

预期输出：
```
==================================================
       C++ 实盘交易框架 - 核心模块测试
==================================================

============================================================
测试 EventEngine
============================================================
...
✅ EventEngine 测试通过

============================================================
测试 Order
============================================================
...
✅ Order 测试通过

✅ 所有测试通过！
```

### 4. 运行示例程序

```bash
# 运行示例程序（模拟行情）
./main_example
```

按 `Ctrl+C` 退出。

## 📝 编写第一个策略

### 步骤1：创建策略文件

创建 `my_strategy.h`：

```cpp
#pragma once
#include "strategies/strategy_base.h"

class MyStrategy : public trading::StrategyBase {
public:
    MyStrategy() : StrategyBase("MyStrategy") {}
    
    virtual void on_init() override {
        log_info("策略初始化");
    }
    
    virtual void on_ticker(const trading::TickerData::Ptr& ticker) override {
        double price = ticker->last_price();
        log_info("收到行情，价格: " + std::to_string(price));
        
        // 你的交易逻辑
        // if (价格低于某个值) {
        //     buy("BTC-USDT-SWAP", 0.01, price);
        // }
    }
    
    virtual void on_order(const trading::Order::Ptr& order) override {
        if (order->is_filled()) {
            log_info("订单成交: " + order->to_string());
        }
    }
};
```

### 步骤2：在主程序中使用

创建 `my_main.cpp`：

```cpp
#include "core/event_engine.h"
#include "my_strategy.h"
#include "utils/account_manager.h"
#include "utils/recorder.h"

int main() {
    // 创建引擎
    auto engine = std::make_unique<trading::EventEngine>();
    
    // 创建组件
    auto account = std::make_unique<trading::AccountManager>();
    auto recorder = std::make_unique<trading::Recorder>("my_trading.log");
    auto strategy = std::make_unique<MyStrategy>();
    
    // 启动组件
    account->start(engine.get());
    recorder->start(engine.get());
    strategy->start(engine.get());
    
    // 模拟推送行情
    auto ticker = std::make_shared<trading::TickerData>("BTC-USDT-SWAP", 50000.0);
    engine->put(ticker);
    
    // 停止组件
    strategy->stop();
    recorder->stop();
    account->stop();
    
    return 0;
}
```

### 步骤3：编译和运行

修改 `CMakeLists.txt`，添加：

```cmake
add_executable(my_main my_main.cpp)
target_link_libraries(my_main
    PRIVATE trading_core
    PRIVATE trading_strategies
    PRIVATE trading_utils
    PRIVATE nlohmann_json::nlohmann_json
)
```

编译运行：

```bash
cd build
cmake ..
cmake --build .
./my_main
```

## 🎯 核心概念

### 1. 事件引擎（EventEngine）

事件引擎是框架的心脏，负责事件的接收和分发。

```cpp
// 创建引擎
auto engine = std::make_unique<EventEngine>();

// 注册监听器
engine->register_listener(typeid(Order), [](const Event::Ptr& e) {
    auto order = std::dynamic_pointer_cast<Order>(e);
    std::cout << "收到订单: " << order->to_string() << std::endl;
});

// 推送事件
auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000);
engine->put(order);
```

### 2. 订单（Order）

```cpp
// 创建限价买单
auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000);

// 创建市价卖单
auto order = Order::sell_market("BTC-USDT-SWAP", 0.01);

// 查询订单状态
if (order->is_filled()) {
    std::cout << "订单成交" << std::endl;
}

// 获取订单信息
std::cout << "订单ID: " << order->order_id() << std::endl;
std::cout << "交易对: " << order->symbol() << std::endl;
std::cout << "价格: " << order->price() << std::endl;
```

### 3. 行情数据（TickerData）

```cpp
// 创建行情数据
auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", 50000.0);
ticker->set_bid_price(49999.0);
ticker->set_ask_price(50001.0);

// 获取中间价和价差
auto mid = ticker->mid_price();
auto spread = ticker->spread();
std::cout << "中间价: " << *mid << ", 价差: " << *spread << std::endl;
```

### 4. 策略基类（StrategyBase）

```cpp
class MyStrategy : public StrategyBase {
    // on_init()    - 策略初始化
    // on_ticker()  - 行情回调
    // on_order()   - 订单回调
    // buy()/sell() - 下单方法
};
```

### 5. 组件生命周期

```cpp
// 所有组件都实现 Component 接口
class MyComponent : public Component {
public:
    virtual void start(EventEngine* engine) override {
        // 启动时注册监听器
        engine_ = engine;
        engine->register_listener(...);
    }
    
    virtual void stop() override {
        // 停止时清理资源
    }
};
```

## 🔧 常见问题

### Q1: 编译时找不到 nlohmann/json？

A: CMake会自动下载。如果失败，手动安装：

```bash
# Ubuntu/Debian
sudo apt install nlohmann-json3-dev

# macOS
brew install nlohmann-json

# 或者手动下载头文件到项目中
```

### Q2: 如何连接真实交易所？

A: 需要实现 OKX 适配器的 `.cpp` 文件（websocket和REST API）。参考 `adapters/okx/` 目录下的头文件。

### Q3: 如何记录日志？

A: 使用 `Recorder` 组件：

```cpp
auto recorder = std::make_unique<Recorder>("trading.log");
recorder->start(engine.get());
```

### Q4: 如何查询持仓？

A: 通过 `AccountManager`：

```cpp
auto account = std::make_unique<AccountManager>();
account->start(engine.get());

// 查询持仓
auto pos = account->get_position("BTC-USDT-SWAP");
std::cout << "持仓: " << pos.quantity << std::endl;
```

## 📚 下一步

1. **阅读架构说明**：`架构说明.md` - 了解设计理念
2. **研究示例代码**：`examples/main_example.cpp` - 完整示例
3. **实现OKX适配器**：`adapters/okx/` - 对接真实交易所
4. **开发自己的策略**：继承 `StrategyBase` 类

## 💡 提示

- 核心模块是 header-only 的，无需编译，直接 include 即可使用
- 使用智能指针（`std::shared_ptr`）管理对象生命周期
- 所有事件都通过 `engine->put()` 推送
- 组件之间完全解耦，通过事件通信

## 📞 获取帮助

- 查看 `README.md` - 完整文档
- 查看 `架构说明.md` - 架构设计
- 运行 `test_core` - 核心功能测试
- 查看示例代码 - `examples/` 目录

---

**祝你交易顺利！** 🚀

