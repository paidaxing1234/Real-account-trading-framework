# ZeroMQ 多策略延迟测试指南

本指南说明如何运行多策略并发延迟测试，评估 ZeroMQ 框架的性能。

## 测试架构

```
                    ┌──────────────────────────────────────┐
                    │        C++ Trading Server            │
                    │  - 发布行情 (PUB, 500ms/条)          │
                    │  - 接收订单 (PULL)                   │
                    │  - 发布回报 (PUB)                    │
                    └──────────┬───────────────────────────┘
                               │
              IPC (ipc:///tmp/trading_*.ipc)
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
    │策略 1   │          │策略 2   │          │策略 3   │
    │ Python  │          │ Python  │          │ Python  │
    └─────────┘          └─────────┘          └─────────┘
```

## 测量指标

| 指标 | 说明 | 预期值 |
|------|------|--------|
| 行情推送延迟 | 服务端发送 → 策略接收 | 30-100 μs |
| 订单往返延迟 | 策略发送 → 收到回报 | 取决于 API 调用 |

**注意**：订单往返延迟包含 OKX API 调用时间（网络延迟），实际 ZeroMQ 通信延迟很小。

## 运行测试

### 1. 编译 C++ 服务端

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp/build
make trading_server -j4
```

### 2. 启动服务端（终端 1）

```bash
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp/build
./trading_server
```

服务端会输出：
```
========================================
  服务器启动完成！
  等待策略连接...
========================================
```

### 3. 运行多策略测试（终端 2）

```bash
conda activate sequence
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/python/strategies

# 方式一：运行多策略并发测试（推荐）
python run_multi_strategy_test.py --num-strategies 3 --orders 30 --interval 20

# 方式二：单独运行一个延迟测试策略
python latency_test_strategy.py --id 1 --orders 50 --interval 10
```

### 参数说明

**run_multi_strategy_test.py**:
- `--num-strategies, -n`: 策略数量（默认 3）
- `--orders, -o`: 每个策略发送的订单数（默认 50）
- `--interval, -i`: 每 N 条行情发一个订单（默认 20）

**latency_test_strategy.py**:
- `--id`: 策略编号
- `--orders`: 订单数量
- `--interval`: 订单间隔

## 测试报告

测试完成后，会在 `python/reports/` 目录生成 JSON 报告：

```
python/reports/
├── latency_report_latency_test_1_1702xxx.json  # 单策略报告
├── latency_report_latency_test_2_1702xxx.json
├── latency_report_latency_test_3_1702xxx.json
└── summary_report_1702xxx.json                  # 汇总报告
```

### 报告内容示例

```
========================================
  汇总报告
========================================

--- 行情推送延迟 (服务端 -> 策略) ---
策略ID               样本数     平均(μs)     P50(μs)      P90(μs)      P99(μs)     
------------------------------------------------------------------------------
latency_test_1       1000       45.32        42.00        65.00        120.00      
latency_test_2       1000       48.15        44.00        68.00        125.00      
latency_test_3       1000       46.88        43.00        66.00        118.00      

--- 订单往返延迟 (策略 -> 服务端 -> 策略) ---
策略ID               样本数     平均(μs)     P50(μs)      P90(μs)      P99(μs)     
------------------------------------------------------------------------------
latency_test_1       50         50000.00     ...          ...          ...
(注: 包含 OKX API 网络延迟)
```

## 评级标准

### 行情延迟评级

| 评级 | 延迟 | 说明 |
|------|------|------|
| ⭐⭐⭐⭐⭐ 极佳 | < 100μs | 高频交易级别 |
| ⭐⭐⭐⭐ 优秀 | < 500μs | 专业量化级别 |
| ⭐⭐⭐ 良好 | < 1ms | 普通量化 |
| ⭐⭐ 一般 | > 1ms | 需要优化 |

### 纯 ZeroMQ IPC 延迟参考

| 场景 | 延迟 |
|------|------|
| 单进程内调用 | ~1 μs |
| IPC (同机器) | 30-100 μs |
| TCP localhost | 100-300 μs |

## 常见问题

### Q: 订单往返延迟很高（>100ms）正常吗？

是的，因为订单往返延迟 = ZeroMQ 延迟 + OKX API 调用延迟。
- ZeroMQ IPC 延迟: ~50 μs
- OKX API 延迟: 50-200 ms（取决于网络和代理）

如果想测试纯 ZeroMQ 延迟，可以在服务端禁用真实 API 调用。

### Q: 行情延迟不稳定怎么办？

1. 确保测试期间没有其他高 CPU 负载任务
2. 尝试增加行情发送间隔
3. 检查是否有 GC 暂停（Python 端）

### Q: 如何进一步降低延迟？

1. **C++ 策略**: 用 C++ 直接编写策略，避免 Python 开销
2. **共享内存**: 使用共享内存替代 ZeroMQ IPC（开发更复杂）
3. **绑核**: 将服务端和策略绑定到特定 CPU 核心
4. **Busy Polling**: 使用忙等待替代阻塞 IO

## 停止测试

- 按 `Ctrl+C` 停止策略进程
- 按 `Ctrl+C` 停止服务端

## 完整测试命令汇总

```bash
# 终端 1: 启动服务端
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/cpp/build
./trading_server

# 终端 2: 运行测试
conda activate sequence
cd /Users/wuyh/Desktop/Sequence/Real-account-trading-framework/python/strategies

# 快速测试 (2 个策略，每个 20 订单)
python run_multi_strategy_test.py -n 2 -o 20 -i 10

# 标准测试 (3 个策略，每个 50 订单)
python run_multi_strategy_test.py -n 3 -o 50 -i 20

# 压力测试 (5 个策略，每个 100 订单)
python run_multi_strategy_test.py -n 5 -o 100 -i 5
```

