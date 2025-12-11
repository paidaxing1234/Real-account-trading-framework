# Disruptor 环形总线架构

## 📊 性能指标

| 指标 | 数值 | 说明 |
|------|------|------|
| **写入延迟** | 23.5 ns | 单事件写入 |
| **端到端延迟** | 42-46 ns | 生产者到消费者 |
| **P99延迟** | 42 ns | 99%请求 |
| **吞吐量** | 42.5M events/s | 4250万事件/秒 |
| **队列写入** | 15.8 ns | MPSC队列 |
| **队列读取** | 3.0 ns | MPSC队列 |

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Ring Bus Architecture                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│   Core 0: OS/SSH (垃圾回收站)                                 │
│                                                               │
│   Core 1: MD Thread (水源)                                    │
│      └── 收行情 → 归一化 → 写总线                              │
│                        ↓                                      │
│   ┌────────────────────────────────────────┐                 │
│   │      Market Data Bus (RingBuffer)      │                 │
│   │           SPMC 行情总线                  │                 │
│   │        容量: 64K事件 (4MB内存)            │                 │
│   └────────────────────────────────────────┘                 │
│          ↓               ↓              ↓                    │
│   Core 2: Strat A    Core 3: Strat B   Core 5: Logger        │
│      └── 策略1~10       └── 策略11~20     └── 写磁盘          │
│          ↓                   ↓                               │
│   ┌────────────────────────────────────────┐                 │
│   │        Order Bus (MPSC Queue)          │                 │
│   │           指令总线 (4K容量)              │                 │
│   └────────────────────────────────────────┘                 │
│                        ↓                                      │
│   Core 4: OEMS Thread (手脚)                                  │
│      └── 收指令 → 风控 → 路由 → TCP发单                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 文件结构

```
cpp/core/disruptor/
├── ring_buffer.h        # 无锁环形缓冲区（SPMC）
├── mpsc_queue.h         # 多生产者单消费者队列
├── events.h             # 固定大小事件结构体
├── market_data_bus.h    # 行情数据总线
├── workers.h            # 工作线程（策略、OEMS、日志）
├── disruptor_engine.h   # 整合引擎
└── README.md            # 本文档
```

---

## 🔧 核心组件

### 1. RingBuffer (ring_buffer.h)

```cpp
template<typename T, size_t CAPACITY = 65536>
class RingBuffer {
    // 预分配内存
    alignas(64) T events_[CAPACITY];
    
    // 原子游标
    alignas(64) std::atomic<int64_t> cursor_;
    
    // 写入
    T& get(int64_t seq) { return events_[seq & MASK]; }
    void publish(int64_t seq) { cursor_.store(seq, release); }
    
    // 读取
    int64_t cursor() const { return cursor_.load(acquire); }
};
```

### 2. MarketEvent (events.h)

```cpp
struct alignas(64) MarketEvent {
    int64_t timestamp_ns;    // 8: 纳秒时间戳
    EventType type;          // 1: 事件类型
    uint8_t exchange_id;     // 1: 交易所ID
    uint16_t symbol_id;      // 2: 交易对ID
    uint32_t sequence;       // 4: 序列号
    double last_price;       // 8: 最新价
    double bid_price;        // 8: 买一价
    double ask_price;        // 8: 卖一价
    double volume;           // 8: 成交量
    double bid_size;         // 8: 买一量
    char padding[8];         // 8: 填充到64字节
};
// sizeof = 64 bytes (1个缓存行)
```

### 3. MPSC Queue (mpsc_queue.h)

```cpp
template<typename T, size_t CAPACITY = 4096>
class MPSCQueue {
    // 多生产者入队（CAS）
    bool try_push(const T& item);
    
    // 单消费者出队
    bool try_pop(T& item);
};
```

---

## 💻 使用示例

### 基本用法

```cpp
#include "disruptor/disruptor_engine.h"

using namespace trading::disruptor;

int main() {
    // 创建引擎
    ThreadConfig config;
    config.enable_cpu_pinning = true;
    
    DisruptorEngine<65536, 4096> engine(config);
    
    // 添加策略
    engine.add_strategy_group_a(std::make_unique<MyStrategy>());
    
    // 启动
    engine.start();
    
    // 发布行情
    engine.publish_ticker(
        SymbolMapper::BTC_USDT,  // symbol_id
        50000.0,                  // last_price
        49995.0,                  // bid_price
        50005.0,                  // ask_price
        1000.0                    // volume
    );
    
    // 停止
    engine.stop();
}
```

### 自定义策略

```cpp
class MyStrategy : public IStrategy {
public:
    uint32_t strategy_id() const override { return 1; }
    
    bool on_market_event(const MarketEvent& event) override {
        // 处理行情
        if (event.last_price > threshold_) {
            // 产生订单
            pending_order_ = true;
            return true;
        }
        return false;
    }
    
    bool get_pending_order(OrderRequest& req) override {
        if (pending_order_) {
            req.clear();
            req.side = Side::BUY;
            req.price = 50000.0;
            req.quantity = 0.01;
            pending_order_ = false;
            return true;
        }
        return false;
    }
};
```

---

## ⚡ 性能优化技巧

### 1. CPU绑核

```cpp
ThreadConfig config;
config.md_thread_cpu = 1;         // 行情线程
config.strategy_group_a_cpu = 2;  // 策略组A
config.strategy_group_b_cpu = 3;  // 策略组B
config.oems_thread_cpu = 4;       // OEMS线程
config.logger_thread_cpu = 5;     // 日志线程
config.enable_cpu_pinning = true;
```

### 2. 缓存行对齐

所有关键数据结构都对齐到64字节：
- `MarketEvent`: 64 bytes
- `OrderRequest`: 128 bytes
- 原子游标: 独占缓存行

### 3. 零拷贝

```cpp
// 直接在RingBuffer中填充数据
auto& event = ring_buffer.get(seq);
event.last_price = price;  // 直接写入
ring_buffer.publish(seq);  // 原子发布
```

### 4. Busy Spin

```cpp
while (cursor < target) {
    #if defined(__x86_64__)
    __builtin_ia32_pause();  // 降低功耗
    #elif defined(__aarch64__)
    asm volatile("yield" ::: "memory");
    #endif
}
```

---

## 🧪 测试程序

### 编译

```bash
cd cpp/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make test_disruptor_perf test_ringbuffer_simple -j4
```

### 运行

```bash
# 简单测试
./test_ringbuffer_simple

# 完整性能测试
./test_disruptor_perf
```

### 预期输出

```
========================================
  Test 1: Write Performance
========================================
  Events:      1000000
  Time:        23.524 ms
  Throughput:  42.51 M events/s
  Latency:     23.5 ns/event

========================================
  Test 2: End-to-End Latency
========================================
  Min:         41 ns
  Avg:         46 ns
  P50:         42 ns
  P99:         42 ns
```

---

## 📈 与其他方案对比

| 方案 | 写入延迟 | 端到端延迟 | 吞吐量 | 适用场景 |
|------|----------|------------|--------|----------|
| **Disruptor** | **23.5ns** | **42ns** | **42.5M/s** | 高频交易 |
| Journal | 105ns | ~800ns | 9.5M/s | 中频策略 |
| EventEngine | ~1μs | ~5μs | 0.5M/s | 低频策略 |
| ZeroMQ | ~50μs | ~100μs | 10K/s | 分布式 |

---

## ⚠️ 注意事项

### 1. 容量规划

- RingBuffer容量必须是2的幂
- 默认64K事件 ≈ 4MB内存
- 根据行情频率调整容量

### 2. 消费者速度

- 消费者必须跟上生产者
- 否则会覆盖未消费的数据
- 使用Logger监控落后情况

### 3. CPU占用

- Busy Spin会占用100% CPU
- 建议绑定到独立核心
- 生产环境确保有足够的核心

### 4. 内存屏障

- 使用正确的memory_order
- 生产者: release
- 消费者: acquire

---

## 🔮 未来优化

1. **NUMA感知** - 多CPU插槽场景优化
2. **大页内存** - 减少TLB miss
3. **io_uring** - 异步日志写入
4. **Kernel Bypass** - DPDK/AF_XDP直接收包

---

## 📚 参考资料

- [LMAX Disruptor](https://lmax-exchange.github.io/disruptor/)
- [Mechanical Sympathy](https://mechanical-sympathy.blogspot.com/)
- [False Sharing](https://en.wikipedia.org/wiki/False_sharing)

---

**版本**: v1.0  
**性能**: 42.5M events/s, 23.5ns延迟  
**状态**: ✅ 生产就绪

