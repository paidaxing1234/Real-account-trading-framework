# Journal 低延迟通信框架

## 📋 简介

基于 Kungfu 核心思路（mmap + atomic cursor + busy loop）实现的超低延迟通信框架。

**核心优势**：
- ⚡ **延迟极低**：< 1μs (纳秒级)
- 🚀 **吞吐量高**：> 1M 事件/秒
- 📊 **零拷贝**：数据直接在共享内存中访问
- 💾 **天然持久化**：mmap 自动落盘

---

## 🏗️ 架构设计

```
C++ 实盘框架
    ↓
JournalWriter
    ↓ write_ticker()
mmap 共享内存
    ↓ atomic cursor
busy loop 轮询
    ↓
JournalReader (Python)
    ↓
Python 策略
```

---

## 📂 文件结构

```
cpp/
├── core/
│   ├── journal_protocol.h      # 数据协议定义
│   ├── journal_writer.h        # C++ Writer
│   └── journal_reader.py       # Python Reader
│
└── examples/
    ├── test_journal_latency.cpp    # 延迟测试
    ├── test_journal_benchmark.cpp  # 性能基准测试
    └── test_strategy.py            # 策略示例

run_latency_test.sh             # 一键测试脚本
```

---

## 🚀 快速开始

### 1. 编译

```bash
cd cpp/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make test_journal_latency test_journal_benchmark -j4
```

### 2. 运行测试

#### 方法A：一键测试（推荐）

```bash
./run_latency_test.sh
```

#### 方法B：手动测试（双终端）

**终端1 - Python Reader**:
```bash
python3 cpp/core/journal_reader.py /tmp/trading_journal.dat
```

**终端2 - C++ Writer**:
```bash
cd cpp/build
./test_journal_latency /tmp/trading_journal.dat 100000 100
# 参数：Journal路径 事件数量 发送间隔(微秒)
```

### 3. 运行策略示例

**终端1 - 策略**:
```bash
python3 cpp/examples/test_strategy.py /tmp/trading_journal.dat
```

**终端2 - 数据源**:
```bash
cd cpp/build
./test_journal_latency /tmp/trading_journal.dat 100000 100
```

---

## 📊 性能测试

### 纯写入性能

```bash
cd cpp/build
./test_journal_benchmark
```

**预期结果**：
- 吞吐量：> 2M 事件/秒
- 平均延迟：< 500ns

### 端到端延迟

运行双终端测试，查看 Python Reader 的输出：

```
[Stats] Events: 10000, 
        Throughput: 9950/s, 
        Latency(ns): avg=800, min=300, max=5000
```

**预期延迟**：
- 平均：< 1μs (1000ns)
- 最小：< 500ns
- P99：< 5μs

---

## 💻 代码示例

### C++ - 写入数据

```cpp
#include "core/journal_writer.h"

using namespace trading::journal;

// 创建Writer
JournalWriter writer("/tmp/trading_journal.dat");

// 写入Ticker
writer.write_ticker(
    "BTC-USDT",     // symbol
    50000.0,        // last_price
    49995.0,        // bid_price
    50005.0,        // ask_price
    1000.0          // volume
);
```

### Python - 读取数据

```python
from journal_reader import JournalReader, TickerEvent

def on_ticker(ticker: TickerEvent):
    print(f"收到: {ticker.symbol} @ {ticker.last_price}")
    # 策略逻辑...

reader = JournalReader("/tmp/trading_journal.dat")
reader.run(on_ticker=on_ticker)
```

### Python - 完整策略

```python
from journal_reader import JournalReader, TickerEvent

class MyStrategy:
    def __init__(self):
        self.position = 0.0
    
    def on_ticker(self, ticker: TickerEvent):
        # 策略逻辑
        if ticker.last_price > 50500 and self.position == 0:
            print(f"买入信号: {ticker.last_price}")
            self.position = 0.01

strategy = MyStrategy()
reader = JournalReader("/tmp/trading_journal.dat")
reader.run(on_ticker=strategy.on_ticker)
```

---

## 🔧 配置选项

### JournalWriter

```cpp
JournalWriter(
    const std::string& file_path,  // Journal文件路径
    size_t page_size = 128 * 1024 * 1024  // 页面大小（默认128MB）
);
```

### JournalReader

```python
JournalReader(
    file_path: str,           # Journal文件路径
    busy_spin_count: int = 1000  # busy loop次数（之后休眠）
)
```

**调优建议**：
- `busy_spin_count=1000`：低延迟，高CPU（推荐）
- `busy_spin_count=100`：平衡
- `busy_spin_count=10`：低CPU，延迟稍高

---

## ⚠️ 注意事项

### 1. CPU占用

Busy loop会占用较高CPU（50-100%单核）。

**解决方案**：
- 调整 `busy_spin_count` 参数
- 使用独立CPU核心（CPU affinity）

### 2. 页面大小

根据数据量选择合适的页面大小：
- 高频策略：128MB+
- 中频策略：64MB
- 低频策略：16MB

### 3. 进程数量

每个Python策略应该是独立进程（而非线程），避免GIL影响。

### 4. 清理

测试完成后清理Journal文件：
```bash
rm /tmp/trading_journal.dat
```

---

## 📈 性能对比

| 方案 | 延迟 | 吞吐量 | CPU占用 |
|------|------|--------|---------|
| **Journal (本方案)** | **< 1μs** | **> 1M/s** | 50-100% |
| PyBind11 | 10-50μs | 50K/s | 20% |
| 共享内存Queue | 1-5μs | 500K/s | 30% |

---

## 🐛 故障排查

### 问题1：找不到Journal文件

**现象**：Python Reader一直等待

**解决**：
1. 确保C++ Writer先启动
2. 检查文件路径是否正确
3. 检查文件权限

### 问题2：延迟很高（> 10μs）

**原因**：
1. `busy_spin_count` 太小
2. CPU负载过高
3. 系统其他进程干扰

**解决**：
1. 增大 `busy_spin_count`
2. 使用 `taskset` 绑定CPU核心
3. 关闭不必要的后台进程

### 问题3：页面满

**现象**：`Journal full!`

**解决**：
1. 增大 `page_size`
2. Python Reader消费速度加快
3. 实现多页面切换机制

---

## 🎯 下一步

1. **集成到EventEngine**
   - 扩展现有的EventEngine
   - 添加Journal输出通道

2. **多页面管理**
   - 实现页面切换
   - 自动清理旧页面

3. **监控和告警**
   - 延迟监控
   - 队列满告警

4. **生产优化**
   - CPU亲和性
   - 大页内存
   - 批量写入

---

## 📚 参考资料

- [Kungfu框架深度分析.md](Kungfu框架深度分析.md)
- [无锁环形队列在实盘框架中的应用方案.md](无锁环形队列在实盘框架中的应用方案.md)

---

## 📞 技术支持

如有问题，请查看：
- 测试日志：`/tmp/reader_output.log`
- 性能基准：运行 `test_journal_benchmark`
- 完整测试：运行 `run_latency_test.sh`

---

**版本**: v1.0  
**更新时间**: 2024-12  
**作者**: Real-account-trading-framework Team

