# Journal 框架快速开始指南

## 🚀 5分钟快速上手

### 第一步：编译（1分钟）

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp/build

# 编译测试程序
cmake .. -DCMAKE_BUILD_TYPE=Release
make test_journal_benchmark test_journal_latency -j4
```

### 第二步：性能基准测试（30秒）

```bash
# 测试纯写入性能
./test_journal_benchmark
```

**预期输出**：
```
========================================
    Journal Write Benchmark
========================================

Warming up...
Running benchmark...
  100000 events...
  200000 events...
  ...

========================================
         Benchmark Results
========================================
Total Events:      1000000
Total Time:        0.45 seconds
Throughput:        2222222 events/s
Avg Write Latency: 450 ns
                   0.45 μs
========================================
```

### 第三步：端到端延迟测试（2分钟）

**打开两个终端**：

**终端1（Python Reader）**:
```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework

python3 cpp/core/journal_reader.py /tmp/trading_journal.dat
```

**终端2（C++ Writer）**:
```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp/build

./test_journal_latency /tmp/trading_journal.dat 10000 100
# 参数说明：
#   10000 = 发送1万个事件
#   100   = 每100微秒发送一个
```

**预期输出（Python端）**：
```
[JournalReader] Starting busy loop...
[Stats] Events: 10000, Throughput: 9950/s, 
        Latency(ns): avg=800, min=350, max=4500

[JournalReader] Finished!
  Total Events: 10000
  Total Time: 1.005s
  Throughput: 9950 events/s
```

### 第四步：运行策略示例（1分钟）

**终端1（策略）**:
```bash
python3 cpp/examples/test_strategy.py /tmp/trading_journal.dat 50000
```

**终端2（数据源）**:
```bash
cd cpp/build
./test_journal_latency /tmp/trading_journal.dat 50000 100
```

---

## 📊 性能指标

### 理论性能

| 指标 | 数值 |
|------|------|
| 写入延迟 | 200-500ns |
| 读取延迟 | 100-300ns |
| 端到端延迟 | **< 1μs** |
| 吞吐量 | **> 1M 事件/秒** |

### 实测性能（预期）

| 指标 | 数值 |
|------|------|
| 平均延迟 | 500-1000ns |
| P99 延迟 | < 5μs |
| 吞吐量 | 500K-1M 事件/秒 |

---

## 🎯 一键测试脚本

### 使用自动化脚本

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework

# 运行完整测试
./run_latency_test.sh
```

**脚本会自动**：
1. 清理旧文件
2. 编译程序
3. 运行基准测试
4. 运行延迟测试
5. 显示统计结果

---

## 🔧 参数调优

### JournalReader 参数

```python
reader = JournalReader(
    file_path="/tmp/trading_journal.dat",
    busy_spin_count=1000  # 调整这个参数
)
```

| busy_spin_count | 延迟 | CPU占用 | 适用场景 |
|----------------|------|---------|---------|
| 1 | 最低 | 100% | 高频交易 |
| 100 | 很低 | 80% | 中高频 |
| 1000 | 低 | 50% | **推荐** |
| 10000 | 中等 | 20% | 低频 |

### 发送速率控制

```bash
# 快速发送（测试吞吐量）
./test_journal_latency /tmp/journal.dat 100000 0

# 中速发送（测试延迟）
./test_journal_latency /tmp/journal.dat 100000 100

# 慢速发送（模拟真实行情）
./test_journal_latency /tmp/journal.dat 100000 1000
```

---

## 📁 生成的文件

测试会生成以下文件：

```bash
/tmp/trading_journal.dat      # Journal数据文件（128MB）
/tmp/benchmark_journal.dat    # 基准测试文件
/tmp/reader_output.log        # Reader输出日志
/tmp/journal_feedback.txt     # 反馈文件
```

**清理**：
```bash
rm /tmp/trading_journal.dat /tmp/benchmark_journal.dat 
rm /tmp/reader_output.log /tmp/journal_feedback.txt
```

---

## 🐛 常见问题

### Q1: Python Reader一直等待

**现象**：`Waiting for journal file...`

**解决**：
1. 确保C++ Writer先启动
2. 检查文件路径
3. 检查文件权限

### Q2: 延迟很高（> 10μs）

**原因**：
- `busy_spin_count` 太小
- 系统负载高
- CPU频率降低（省电模式）

**解决**：
```bash
# 1. 禁用CPU省电模式
sudo cpupower frequency-set -g performance

# 2. 绑定到特定CPU核心
taskset -c 0 python3 journal_reader.py /tmp/journal.dat
taskset -c 1 ./test_journal_latency /tmp/journal.dat 10000 100

# 3. 提高进程优先级
sudo nice -n -20 python3 journal_reader.py /tmp/journal.dat
```

### Q3: 页面满

**现象**：`Journal full!`

**解决**：
1. 增大page_size（默认128MB）
2. Python Reader加快消费
3. 清理旧数据

---

## 📈 性能优化建议

### 1. CPU亲和性

```bash
# Python绑定到CPU0
taskset -c 0 python3 test_strategy.py /tmp/journal.dat &

# C++绑定到CPU1
taskset -c 1 ./test_journal_latency /tmp/journal.dat 10000 0
```

### 2. 大页内存

```bash
# 启用大页
echo 128 | sudo tee /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages

# C++端会自动使用（madvise MADV_HUGEPAGE）
```

### 3. 实时优先级

```bash
# 设置实时优先级（需要root）
sudo chrt -f 99 python3 journal_reader.py /tmp/journal.dat
```

---

## 📊 性能对比

运行所有方案的对比测试：

```bash
# 1. Journal方案
./test_journal_latency /tmp/journal.dat 10000 100

# 2. PyBind11方案（如果已实现）
./test_pybind11_latency 10000

# 3. 共享内存Queue方案（如果已实现）
./test_shm_queue_latency 10000
```

**预期对比**：
| 方案 | 延迟 | 吞吐量 |
|------|------|--------|
| Journal | < 1μs | > 1M/s |
| 共享内存Queue | 1-5μs | 500K/s |
| PyBind11 | 10-50μs | 50K/s |

---

## 🎓 下一步

1. **集成到框架**
   - 扩展 EventEngine
   - 添加 JournalWriter

2. **多策略支持**
   - 每个策略独立Journal
   - 或使用多Reader

3. **生产部署**
   - 添加监控
   - 异常处理
   - 自动重启

---

## 📞 快速命令参考

```bash
# 编译
cd cpp/build && cmake .. && make -j4

# 基准测试
./test_journal_benchmark

# 延迟测试（双终端）
# 终端1:
python3 cpp/core/journal_reader.py /tmp/trading_journal.dat

# 终端2:
./test_journal_latency /tmp/trading_journal.dat 10000 100

# 策略测试（双终端）
# 终端1:
python3 cpp/examples/test_strategy.py /tmp/trading_journal.dat

# 终端2:
./test_journal_latency /tmp/trading_journal.dat 50000 100

# 一键测试
./run_latency_test.sh

# 清理
rm /tmp/trading_journal.dat /tmp/*_journal.dat
```

---

**准备就绪！现在就可以开始测试了！** 🚀

