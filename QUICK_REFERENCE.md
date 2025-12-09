# 快速参考卡片

## 🚀 快速启动（30秒上手）

### 1. 编译C++
```bash
cd cpp && mkdir build && cd build
cmake .. && make -j4
```

### 2. 启动系统
```bash
# 清理旧共享内存
rm -f /dev/shm/trading_*

# 启动C++框架（后台）
./trading_engine &

# 启动Python策略
python3 momentum_strategy.py &
python3 mean_revert_strategy.py &
```

### 3. 监控
```bash
# 查看共享内存
ls -lh /dev/shm/trading_*

# 查看日志
tail -f trading.log
```

---

## 📊 性能速查表

| 指标 | 数值 |
|------|------|
| **单次延迟** | < 1μs |
| **端到端延迟** | < 200μs |
| **吞吐量** | 500K 事件/秒 |
| **内存/策略** | ~2MB |
| **最大策略数** | 20+ |

---

## 🔑 关键数据结构

### TickerEvent (64字节)
```cpp
struct TickerEvent {
    EventType type;        // 1 byte
    char symbol[16];       // 16 bytes
    int64_t timestamp;     // 8 bytes
    double last_price;     // 8 bytes
    double bid_price;      // 8 bytes
    double ask_price;      // 8 bytes
    double volume;         // 8 bytes
    uint8_t padding[7];    // 7 bytes
};
```

### OrderEvent (128字节)
```cpp
struct OrderEvent {
    EventType type;             // 1 byte
    char symbol[16];            // 16 bytes
    int64_t timestamp;          // 8 bytes
    int64_t order_id;           // 8 bytes
    uint8_t order_type, side, state;  // 3 bytes
    double price, quantity;     // 16 bytes
    double filled_quantity, filled_price; // 16 bytes
    char client_order_id[32];   // 32 bytes
    uint8_t padding[23];        // 23 bytes
};
```

---

## 💻 核心API

### C++ - 广播事件
```cpp
StrategyManager manager;
manager.register_strategy("strategy1");

Event event;
event.type = EventType::TICKER_DATA;
// ... 填充数据

manager.broadcast_event(event);
```

### C++ - 接收订单
```cpp
manager.receive_orders([](const std::string& id, const OrderEvent& order) {
    std::cout << "收到订单: " << id << " " << order.symbol << "\n";
    // 提交到交易所...
});
```

### Python - 策略框架
```python
from base_strategy import BaseStrategy, TickerEvent

class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("my_strategy")
        self.position = 0.0
    
    def on_ticker(self, ticker: TickerEvent):
        # 策略逻辑
        if ticker.last_price > 50000:
            self.send_order(ticker.symbol, 0, 0.01, ticker.last_price)

if __name__ == "__main__":
    strategy = MyStrategy()
    strategy.run()
```

---

## ⚡ 性能优化清单

- [x] 使用固定大小结构体（避免序列化）
- [x] 缓存行对齐（避免伪共享）
- [x] SPSC无锁队列（最快）
- [x] Memory order优化（reduce barriers）
- [x] 零拷贝（直接在共享内存操作）
- [ ] 批量处理（可选）
- [ ] CPU亲和性绑定（可选）
- [ ] 大页内存（可选）

---

## 🐛 常见问题

### Q1: 队列满了怎么办？
```cpp
void* ptr = queue->try_push();
if (ptr == nullptr) {
    // 选项1: 丢弃（高频场景）
    dropped_events_++;
    
    // 选项2: 阻塞等待（低频场景）
    while ((ptr = queue->try_push()) == nullptr) {
        std::this_thread::sleep_for(std::chrono::microseconds(1));
    }
}
```

### Q2: 如何调试共享内存？
```bash
# 查看共享内存
ls -lh /dev/shm/trading_*

# 清理
rm -f /dev/shm/trading_*

# 十六进制查看
xxd /dev/shm/trading_c2p_strategy1 | head -20
```

### Q3: Python进程崩溃了怎么办？
答：C++主框架不受影响，只需重启对应的Python策略即可。

### Q4: 如何动态添加策略？
```cpp
// C++端
manager.register_strategy("new_strategy");

// 启动Python进程
system("python3 new_strategy.py &");
```

---

## 📝 命名规范

### 共享内存名称
- C++ → Python: `/trading_c2p_{strategy_id}`
- Python → C++: `/trading_p2c_{strategy_id}`

### 策略ID规范
- 小写字母+下划线
- 示例: `momentum_strategy`, `mean_revert_btc`

---

## 🔧 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Python连接失败 | C++未启动 | 先启动C++主程序 |
| 队列满 | 策略处理太慢 | 优化策略代码，增加队列容量 |
| 数据解析错误 | 结构体不一致 | 检查C++和Python的结构体定义 |
| 内存泄漏 | 未清理共享内存 | 程序退出时调用`shm_unlink` |

---

## 📚 文件清单

```
cpp/
├── shared_memory_protocol.h   # 数据协议
├── lock_free_queue.h          # 无锁队列
├── strategy_manager.h         # 策略管理器
└── main.cpp                   # 主程序

python/
├── base_strategy.py           # 策略基类
├── momentum_strategy.py       # 示例策略1
├── mean_revert_strategy.py    # 示例策略2
└── arbitrage_strategy.py      # 示例策略3
```

---

## 🎯 下一步

1. ✅ 阅读完整文档：`C++实盘框架与多策略低延迟通信方案.md`
2. ✅ 运行示例代码
3. ✅ 实现自己的策略
4. ⭐ 性能测试和调优
5. ⭐ 部署到生产环境

---

**祝交易顺利！** 🚀

