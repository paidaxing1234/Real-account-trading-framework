# C++ 实盘交易框架

一个基于事件驱动架构的高性能C++实盘交易框架，对接OKX交易所API。

## 📊 项目特点

- ✅ **事件驱动架构**：松耦合、高扩展性
- ✅ **组件化设计**：统一的生命周期管理
- ✅ **类型安全**：C++强类型系统保证
- ✅ **高性能**：零拷贝、智能指针、移动语义
- ✅ **Header-Only核心**：大部分核心代码无需编译
- ✅ **跨平台**：支持Linux、macOS、Windows

## 🏗️ 项目结构

```
cpp/
├── core/                          # ✅ 核心模块
│   ├── event.h                    # 事件基类
│   ├── event_engine.h             # 事件引擎 + 组件基类
│   ├── order.h                    # 订单模型
│   └── data.h                     # 数据模型（行情、成交、订单簿、K线）
│
├── adapters/                      # ⏳ 交易所适配器
│   └── okx/
│       ├── okx_adapter.h          # OKX适配器组件
│       ├── okx_rest_api.h         # REST API封装
│       └── okx_websocket.h        # WebSocket连接
│
├── strategies/                    # ✅ 策略模块
│   ├── strategy_base.h            # 策略基类
│   └── demo_strategy.h            # 示例策略（网格策略）
│
├── utils/                         # ✅ 工具模块
│   ├── account_manager.h          # 账户管理
│   └── recorder.h                 # 数据记录
│
├── examples/                      # ✅ 示例程序
│   └── main_example.cpp           # 主程序示例
│
├── CMakeLists.txt                 # ✅ CMake配置
└── README.md                      # 本文档
```

## 🎯 核心设计

### 1. 事件驱动架构

所有组件通过事件通信，实现松耦合：

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   策略组件   │ ─Event→ │  事件引擎     │ ─Event→ │  订单管理器  │
│  Strategy   │         │ EventEngine  │         │OrderManager │
└─────────────┘         └──────────────┘         └─────────────┘
       ↑                        │                        │
       └────────────Event───────┴────────Event──────────┘
```

### 2. 组件化设计

所有功能模块继承 `Component` 基类：

```cpp
class Component {
public:
    virtual void start(EventEngine* engine) = 0;  // 启动时注册监听器
    virtual void stop() = 0;                      // 停止时清理资源
};
```

### 3. 类型系统

使用C++类型系统和智能指针：

```cpp
// 事件基类
class Event {
public:
    using Ptr = std::shared_ptr<Event>;
    // ...
};

// 订单事件（继承Event）
class Order : public Event {
public:
    using Ptr = std::shared_ptr<Order>;
    // ...
};

// 数据事件（继承Event）
class TickerData : public Event {
public:
    using Ptr = std::shared_ptr<TickerData>;
    // ...
};
```

## 🚀 快速开始

### 依赖项

- C++17或更高版本
- CMake 3.15+
- nlohmann/json（自动下载）
- （可选）WebSocket++（用于OKX WebSocket）
- （可选）OpenSSL（用于HTTPS和WSS）

### 编译

```bash
# 创建构建目录
mkdir build && cd build

# 配置
cmake ..

# 编译
cmake --build .

# 运行示例
./main_example
```

### 使用示例

```cpp
#include "core/event_engine.h"
#include "strategies/demo_strategy.h"
#include "utils/account_manager.h"
#include "utils/recorder.h"

using namespace trading;

int main() {
    // 1. 创建事件引擎
    auto engine = std::make_unique<EventEngine>();
    
    // 2. 创建组件
    auto account = std::make_unique<AccountManager>();
    auto recorder = std::make_unique<Recorder>("trading.log");
    auto strategy = std::make_unique<DemoStrategy>("BTC-USDT-SWAP", 100.0, 0.01, 5);
    
    // 3. 启动组件
    account->start(engine.get());
    recorder->start(engine.get());
    strategy->start(engine.get());
    
    // 4. 推送行情（实际由OKX适配器推送）
    auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", 50000.0);
    engine->put(ticker);
    
    // 5. 停止组件
    strategy->stop();
    recorder->stop();
    account->stop();
    
    return 0;
}
```

## 📝 核心API

### EventEngine

```cpp
// 注册事件监听器
engine.register_listener(typeid(Order), [](const Event::Ptr& e) {
    auto order = std::dynamic_pointer_cast<Order>(e);
    // 处理订单事件
});

// 推送事件
auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000);
engine.put(order);

// 动态注入接口
engine.inject<double>("get_balance", []() { return 10000.0; });
double balance = engine.call<double>("get_balance");
```

### Order（订单）

```cpp
// 创建订单
auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000);
auto order = Order::sell_market("BTC-USDT-SWAP", 0.01);

// 查询订单状态
if (order->is_filled()) {
    std::cout << "订单已成交" << std::endl;
}

// 订单属性
std::cout << order->to_string() << std::endl;
```

### StrategyBase（策略）

```cpp
class MyStrategy : public StrategyBase {
public:
    MyStrategy() : StrategyBase("MyStrategy") {}
    
    virtual void on_ticker(const TickerData::Ptr& ticker) override {
        // 处理行情
        double price = ticker->last_price();
        
        // 发送订单
        buy("BTC-USDT-SWAP", 0.01, price - 100);
    }
    
    virtual void on_order(const Order::Ptr& order) override {
        // 处理订单更新
        if (order->is_filled()) {
            log_info("订单成交: " + order->to_string());
        }
    }
};
```

## 🔄 与Python版本的对比

| 特性 | Python版本 | C++版本 |
|------|-----------|---------|
| **性能** | 解释执行 | 编译执行，性能高10-100倍 |
| **内存管理** | GC自动管理 | 智能指针RAII |
| **类型安全** | 运行时检查 | 编译时检查 |
| **并发** | GIL限制 | 真正的多线程 |
| **部署** | 需要Python环境 | 单一可执行文件 |
| **开发速度** | 快 | 中等 |
| **架构设计** | ✅ 相同 | ✅ 相同 |

## 🛠️ 开发计划

### Phase 1: 核心模块 ✅

- [x] EventEngine - 事件引擎
- [x] Event - 事件基类
- [x] Order - 订单模型
- [x] Data - 数据模型
- [x] Component - 组件基类

### Phase 2: OKX适配器 ⏳

- [ ] OKXRestAPI - REST API封装
- [ ] OKXWebSocket - WebSocket连接
- [ ] OKXAdapter - 统一适配器组件

### Phase 3: 策略和工具 ✅

- [x] StrategyBase - 策略基类
- [x] DemoStrategy - 示例策略
- [x] AccountManager - 账户管理
- [x] Recorder - 数据记录

### Phase 4: 高级功能 ⏳

- [ ] RiskControl - 风控模块
- [ ] Monitor - 监控告警
- [ ] Backtest - 回测引擎
- [ ] 性能优化

## 📚 学习资源

### C++特性

- 智能指针（shared_ptr, unique_ptr）
- RAII（资源获取即初始化）
- 模板和泛型编程
- 移动语义和完美转发
- std::function和lambda

### 设计模式

- 观察者模式（事件引擎）
- 工厂模式（订单创建）
- pImpl模式（隐藏实现）
- 模板方法模式（策略基类）

### 交易系统

- 事件驱动架构
- 订单生命周期管理
- 持仓和风控
- 行情数据处理

## 💡 最佳实践

### 1. 使用智能指针

```cpp
// 好的做法
auto order = std::make_shared<Order>(...);
engine->put(order);

// 避免裸指针
Order* order = new Order(...);  // ❌
```

### 2. 异常安全

```cpp
void on_ticker(const TickerData::Ptr& ticker) {
    try {
        // 交易逻辑
    } catch (const std::exception& e) {
        log_error(e.what());
    }
}
```

### 3. 线程安全

```cpp
class MyComponent {
private:
    std::mutex mutex_;
    std::map<int, Order::Ptr> orders_;
    
public:
    void add_order(const Order::Ptr& order) {
        std::lock_guard<std::mutex> lock(mutex_);
        orders_[order->order_id()] = order;
    }
};
```

## 📞 支持

如有问题，请参考：
1. 本README
2. examples/main_example.cpp - 使用示例
3. Python版本的架构说明.md - 设计理念

## 📄 许可证

MIT License

---

**版本**：v1.0.0  
**更新时间**：2025-12-08  
**状态**：核心模块已完成 ✅，OKX适配器待实现 ⏳

