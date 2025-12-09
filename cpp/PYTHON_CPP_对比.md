# Python vs C++ 实盘框架对比

本文档帮助你理解 Python 版本和 C++ 版本的对应关系。

## 📁 目录结构对比

| Python | C++ | 说明 |
|--------|-----|------|
| `core/event_engine.py` | `core/event_engine.h` | 事件引擎 |
| `core/order.py` | `core/order.h` | 订单模型 |
| `core/data.py` | `core/data.h` | 数据模型 |
| `adapters/okx/` | `adapters/okx/` | OKX适配器 |
| `strategies/` | `strategies/` | 策略模块 |
| `utils/` | `utils/` | 工具模块 |
| `examples/` | `examples/` | 示例程序 |

## 🔄 核心类对比

### EventEngine（事件引擎）

**Python**:
```python
class EventEngine:
    def register(self, event_type: Type[Event], listener: Callable):
        pass
    
    def put(self, event: Event):
        pass
```

**C++**:
```cpp
class EventEngine {
public:
    void register_listener(const std::type_index& event_type, Listener listener);
    void put(Event::Ptr event);
};
```

**主要差异**:
- C++ 使用 `std::type_index` 代替 Python 的 `Type`
- C++ 使用 `std::shared_ptr<Event>` 代替 Python 的裸对象
- C++ 使用 `std::function` 代替 Python 的 `Callable`

### Event（事件基类）

**Python**:
```python
class Event:
    __slots__ = ("timestamp", "source", "producer")
    
    def __init__(self, timestamp=None, source=None, producer=None):
        self.timestamp = timestamp
        self.source = source
        self.producer = producer
```

**C++**:
```cpp
class Event {
public:
    using Ptr = std::shared_ptr<Event>;
    
    int64_t timestamp() const;
    const EventEngine* source() const;
    size_t producer_id() const;
};
```

**主要差异**:
- C++ 使用 getter/setter 代替 Python 的直接访问
- C++ 使用智能指针管理生命周期
- C++ producer 使用 ID 而非函数指针

### Order（订单）

**Python**:
```python
class Order(Event):
    def __init__(self, symbol, order_type, side, quantity, price=None):
        super().__init__()
        self.symbol = symbol
        self.order_type = order_type
        # ...
    
    @classmethod
    def buy_limit(cls, symbol, quantity, price):
        return cls(symbol, OrderType.LIMIT, OrderSide.BUY, quantity, price)
```

**C++**:
```cpp
class Order : public Event {
public:
    Order(const std::string& symbol, OrderType order_type, 
          OrderSide side, double quantity, double price = 0.0);
    
    static Ptr buy_limit(const std::string& symbol, 
                         double quantity, double price);
};
```

**主要差异**:
- C++ 使用静态方法代替类方法
- C++ 使用 getter/setter 代替公共成员
- C++ 返回 `std::shared_ptr<Order>` 代替裸对象

### TickerData（行情数据）

**Python**:
```python
class TickerData(Data):
    def __init__(self, symbol, last_price, bid_price=None, ask_price=None):
        super().__init__(name="ticker", symbol=symbol)
        self.last_price = last_price
        self.bid_price = bid_price
        self.ask_price = ask_price
    
    @property
    def mid_price(self):
        if self.bid_price and self.ask_price:
            return (self.bid_price + self.ask_price) / 2
        return self.last_price
```

**C++**:
```cpp
class TickerData : public Data {
public:
    TickerData(const std::string& symbol, double last_price);
    
    void set_bid_price(double price);
    void set_ask_price(double price);
    
    std::optional<double> mid_price() const;
};
```

**主要差异**:
- C++ 使用 `std::optional` 代替 Python 的 `None`
- C++ 需要显式 setter 方法
- C++ 方法默认不可变（const）

## 🎨 代码风格对比

### 1. 类定义

**Python**:
```python
class MyStrategy(StrategyBase):
    def __init__(self, name):
        super().__init__(name)
        self.position = 0
    
    def on_ticker(self, ticker: TickerData):
        price = ticker.last_price
        if price < 50000:
            self.buy("BTC-USDT-SWAP", 0.01, price)
```

**C++**:
```cpp
class MyStrategy : public StrategyBase {
public:
    MyStrategy(const std::string& name) 
        : StrategyBase(name), position_(0) {}
    
    virtual void on_ticker(const TickerData::Ptr& ticker) override {
        double price = ticker->last_price();
        if (price < 50000) {
            buy("BTC-USDT-SWAP", 0.01, price);
        }
    }

private:
    double position_;
};
```

### 2. 事件注册

**Python**:
```python
engine.register(Order, strategy.on_order)
engine.register(TickerData, strategy.on_ticker)
```

**C++**:
```cpp
engine->register_listener(typeid(Order), 
    [this](const Event::Ptr& e) {
        on_order(std::dynamic_pointer_cast<Order>(e));
    });

engine->register_listener(typeid(TickerData),
    [this](const Event::Ptr& e) {
        on_ticker(std::dynamic_pointer_cast<TickerData>(e));
    });
```

### 3. 事件推送

**Python**:
```python
order = Order.buy_limit("BTC-USDT-SWAP", 0.01, 50000)
engine.put(order)

ticker = TickerData("BTC-USDT-SWAP", 50000)
engine.put(ticker)
```

**C++**:
```cpp
auto order = Order::buy_limit("BTC-USDT-SWAP", 0.01, 50000);
engine->put(order);

auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", 50000.0);
engine->put(ticker);
```

### 4. 枚举

**Python**:
```python
from enum import Enum, auto

class OrderType(Enum):
    LIMIT = auto()
    MARKET = auto()

# 使用
order.order_type == OrderType.LIMIT
```

**C++**:
```cpp
enum class OrderType {
    LIMIT,
    MARKET
};

// 使用
order->order_type() == OrderType::LIMIT
```

## 🔧 语言特性对比

### 1. 内存管理

**Python**:
```python
# 自动垃圾回收
order = Order(...)  # 创建对象
# 离开作用域自动回收
```

**C++**:
```cpp
// 智能指针自动管理
auto order = std::make_shared<Order>(...);  // 创建对象
// 离开作用域，引用计数归零，自动释放
```

### 2. 类型检查

**Python**:
```python
# 运行时类型检查
if isinstance(event, Order):
    print(f"订单: {event.order_id}")
```

**C++**:
```cpp
// 编译时类型检查
auto order = std::dynamic_pointer_cast<Order>(event);
if (order) {
    std::cout << "订单: " << order->order_id() << std::endl;
}
```

### 3. 可选值

**Python**:
```python
# 使用 None
bid_price = None
if bid_price is not None:
    print(bid_price)
```

**C++**:
```cpp
// 使用 std::optional
std::optional<double> bid_price;
if (bid_price) {
    std::cout << *bid_price << std::endl;
}
```

### 4. Lambda 表达式

**Python**:
```python
# Python lambda
listener = lambda event: print(event)

# 或者普通函数
def listener(event):
    print(event)
```

**C++**:
```cpp
// C++ lambda
auto listener = [](const Event::Ptr& e) {
    std::cout << e->type_name() << std::endl;
};

// 或者函数对象
void listener(const Event::Ptr& e) {
    std::cout << e->type_name() << std::endl;
}
```

## 📊 性能对比

| 特性 | Python | C++ |
|------|--------|-----|
| **执行速度** | 慢（解释执行） | 快（编译执行，10-100倍） |
| **内存占用** | 高（对象头、GC开销） | 低（紧凑的内存布局） |
| **启动时间** | 快 | 中等（编译时间） |
| **开发速度** | 快（动态类型、简洁语法） | 中等（静态类型、更多代码） |
| **类型安全** | 弱（运行时检查） | 强（编译时检查） |
| **并发** | 受限（GIL） | 强（真正的多线程） |
| **部署** | 需要Python环境 | 单一可执行文件 |

## 🎯 选择建议

### 使用 Python 版本的场景：
- ✅ 快速原型开发
- ✅ 中低频交易（分钟级）
- ✅ 复杂的数据分析和机器学习
- ✅ 团队熟悉Python
- ✅ 需要快速迭代

### 使用 C++ 版本的场景：
- ✅ 高频交易（秒级、毫秒级）
- ✅ 对延迟敏感
- ✅ 资源受限环境
- ✅ 需要极致性能
- ✅ 生产环境部署

## 🔄 迁移指南

### 从 Python 迁移到 C++

1. **类定义**：
   - 将 `__init__` 改为构造函数
   - 将公共成员改为私有成员 + getter/setter
   - 添加 `override` 关键字到虚函数

2. **事件处理**：
   - 将 `event` 改为 `event->` 或 `(*event).`
   - 添加类型转换 `std::dynamic_pointer_cast`
   - 使用 `typeid` 代替类型对象

3. **内存管理**：
   - 使用 `std::make_shared` 创建对象
   - 使用 `std::shared_ptr` 传递对象
   - 不需要手动 `del`

4. **错误处理**：
   - 使用 try-catch 代替 try-except
   - 使用 `std::exception` 代替 `Exception`

### 示例：Python → C++

**Python**:
```python
class SimpleStrategy(StrategyBase):
    def on_ticker(self, ticker):
        if ticker.last_price < 50000:
            order = self.buy("BTC-USDT-SWAP", 0.01, ticker.last_price)
            self.log_info(f"下单: {order}")
```

**C++**:
```cpp
class SimpleStrategy : public StrategyBase {
public:
    virtual void on_ticker(const TickerData::Ptr& ticker) override {
        if (ticker->last_price() < 50000) {
            auto order = buy("BTC-USDT-SWAP", 0.01, ticker->last_price());
            log_info("下单: " + order->to_string());
        }
    }
};
```

## 💡 最佳实践

### Python
- 使用类型提示（Type Hints）
- 使用 `__slots__` 减少内存
- 避免在热路径中创建对象
- 使用 `dataclasses` 简化代码

### C++
- 使用智能指针，避免裸指针
- 尽量使用 `const` 保证不可变性
- 使用 RAII 管理资源
- 优先使用 header-only 库

## 📚 相关资源

- **Python 版本**：`Real-account-trading-framework/python/`
- **C++ 版本**：`Real-account-trading-framework/cpp/`
- **架构说明**：`架构说明.md`（两个版本都有）
- **快速入门**：`QUICK_START.md`

---

**总结**：两个版本架构设计完全一致，只是语言特性不同。理解了 Python 版本，就能快速上手 C++ 版本！

