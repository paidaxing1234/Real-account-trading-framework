# Linux 绑核延迟测试指南

## 系统信息

```
CPU: AMD EPYC 9475F 48-Core Processor (96 线程)
OS: Linux
```

## 第一步：安装依赖

```bash
# 安装编译工具和依赖
sudo apt update
sudo apt install -y cmake build-essential

# 安装 ZeroMQ
sudo apt install -y libzmq3-dev

# 安装 cppzmq (C++ 绑定)
sudo apt install -y cppzmq-dev

# 安装其他依赖
sudo apt install -y libcurl4-openssl-dev libssl-dev nlohmann-json3-dev

# 安装 Python 依赖
pip install pyzmq
```

## 第二步：编译 C++ 服务端

```bash
cd /home/sequencequant/Real-account-trading-framework/cpp/build

# 清理并重新编译
rm -rf CMakeCache.txt CMakeFiles/
cmake ..
make trading_server -j8
```

## 第三步：CPU 绑核配置

### 96 核服务器的 CPU 分配策略

你的系统 NUMA 拓扑：
```
Node 0: CPU 0-11, 48-59  (192GB)
Node 1: CPU 12-23, 60-71 (193GB)
Node 2: CPU 24-35, 72-83 (193GB)
Node 3: CPU 36-47, 84-95 (193GB)
```

**推荐方案：所有进程绑定到 NUMA Node 0（CPU 1-11）**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  NUMA Node 0 (CPU 0-11, 48-59) - 所有测试进程放这里                      │
├─────────────────────────────────────────────────────────────────────────┤
│  CPU 0:     系统/中断（避免使用）                                        │
│  CPU 1:     C++ Trading Server（主线程）                                │
│  CPU 2:     C++ Trading Server（订单线程，如需要）                       │
├─────────────────────────────────────────────────────────────────────────┤
│  CPU 3:     Python 策略 1                                               │
│  CPU 4:     Python 策略 2                                               │
│  CPU 5:     Python 策略 3                                               │
│  CPU 6:     Python 策略 4                                               │
│  CPU 7:     Python 策略 5                                               │
├─────────────────────────────────────────────────────────────────────────┤
│  CPU 8-11:  备用                                                        │
│  CPU 48-59: 超线程对应核心（可选用于更多策略）                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### NUMA 架构说明

⚠️ **重要**：跨 NUMA 节点通信会增加 ~20% 延迟！务必将服务端和策略放在同一节点。

```bash
# 查看 NUMA 拓扑
numactl --hardware

# 你的系统有 4 个 NUMA 节点，节点间距离为 12（同节点为 10）
# node distances:
# node   0   1   2   3 
#   0:  10  12  12  12   <- 同节点最快
#   1:  12  10  12  12 
#   2:  12  12  10  12 
#   3:  12  12  12  10 
```

## 第四步：运行绑核测试

### 方式一：使用启动脚本（推荐）

创建启动脚本 `run_latency_test_pinned.sh`：

```bash
#!/bin/bash

# ===========================================
# 绑核延迟测试启动脚本
# ===========================================

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ZeroMQ 绑核延迟测试${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}警告: 未使用 sudo，绑核可能不生效${NC}"
fi

# 设置变量
PROJECT_DIR="/home/sequencequant/Real-account-trading-framework"
NUM_STRATEGIES=${1:-5}
COUNT=${2:-1000}

# CPU 分配（全部在 NUMA Node 0）
SERVER_CPU=1
STRATEGY_BASE_CPU=3

echo ""
echo "配置:"
echo "  策略数量: $NUM_STRATEGIES"
echo "  消息数量: $COUNT"
echo "  服务端 CPU: $SERVER_CPU"
echo "  策略起始 CPU: $STRATEGY_BASE_CPU"
echo ""

# 步骤 1: 启动服务端（绑核到 CPU 8-9）
echo -e "${YELLOW}[1/2] 启动 C++ 服务端 (绑定到 CPU $SERVER_CPU)...${NC}"
cd $PROJECT_DIR/cpp/build

# 使用 taskset 绑定 CPU，使用 nice 设置高优先级
taskset -c $SERVER_CPU nice -n -20 ./trading_server &
SERVER_PID=$!

echo "  服务端 PID: $SERVER_PID"

# 等待服务端启动
sleep 3

# 检查服务端是否运行
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo -e "${RED}错误: 服务端启动失败${NC}"
    exit 1
fi

# 步骤 2: 启动策略（每个绑定到不同 CPU）
echo -e "${YELLOW}[2/2] 启动 Python 策略...${NC}"
cd $PROJECT_DIR/python/strategies

STRATEGY_PIDS=()
for i in $(seq 1 $NUM_STRATEGIES); do
    CPU=$((STRATEGY_BASE_CPU + i - 1))
    echo "  启动策略 $i (绑定到 CPU $CPU)..."
    
    taskset -c $CPU nice -n -10 python benchmark_latency.py --id $i --count $COUNT &
    STRATEGY_PIDS+=($!)
    
    sleep 0.3
done

echo ""
echo -e "${GREEN}所有进程已启动:${NC}"
echo "  服务端: PID $SERVER_PID (CPU $SERVER_CPU)"
for i in $(seq 1 $NUM_STRATEGIES); do
    CPU=$((STRATEGY_BASE_CPU + i - 1))
    echo "  策略 $i: PID ${STRATEGY_PIDS[$((i-1))]} (CPU $CPU)"
done

echo ""
echo "等待测试完成... (按 Ctrl+C 中断)"

# 等待所有策略完成
wait ${STRATEGY_PIDS[@]}

echo ""
echo -e "${GREEN}所有策略已完成，停止服务端...${NC}"
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  测试完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "报告目录: $PROJECT_DIR/python/reports/"
```

### 方式二：手动分步执行

#### 终端 1：启动服务端（绑核）

```bash
cd /home/sequencequant/Real-account-trading-framework/cpp/build

# 使用 taskset 绑定到 CPU 1（NUMA Node 0），nice 设置高优先级
sudo taskset -c 1 nice -n -20 ./trading_server
```

#### 终端 2：运行策略（绑核）

```bash
cd /home/sequencequant/Real-account-trading-framework/python/strategies

# 方式 A：使用绑核脚本
sudo python run_benchmark_pinned.py --num-strategies 5 --count 1000

# 方式 B：手动绑核每个策略（全部在 NUMA Node 0: CPU 3-7）
sudo taskset -c 3 nice -n -10 python benchmark_latency.py --id 1 --count 1000 &
sudo taskset -c 4 nice -n -10 python benchmark_latency.py --id 2 --count 1000 &
sudo taskset -c 5 nice -n -10 python benchmark_latency.py --id 3 --count 1000 &
sudo taskset -c 6 nice -n -10 python benchmark_latency.py --id 4 --count 1000 &
sudo taskset -c 7 nice -n -10 python benchmark_latency.py --id 5 --count 1000 &
```

## 第五步：高级优化（可选）

### 1. 禁用 CPU 频率调节（关闭节能）

```bash
# 设置性能模式
sudo cpupower frequency-set -g performance

# 或者直接写入
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance | sudo tee $cpu
done
```

### 2. 避免超线程干扰

AMD EPYC 的超线程配对：CPU 0-47 与 CPU 48-95 一一对应。
例如：CPU 1 和 CPU 49 共享同一物理核心。

```bash
# 查看 CPU 拓扑
lscpu -e

# 推荐：只使用 CPU 1-11（物理核心的第一个线程）
# 避免使用对应的 CPU 49-59（超线程对）
taskset -c 1,3,4,5,6,7 ...
```

### 3. 设置实时调度优先级

```bash
# 使用 SCHED_FIFO 实时调度
sudo chrt -f 99 taskset -c 8 ./trading_server
```

### 4. 隔离 CPU 核心（需要重启）

编辑 `/etc/default/grub`：

```
GRUB_CMDLINE_LINUX="isolcpus=1-11 nohz_full=1-11 rcu_nocbs=1-11"
```

然后：

```bash
sudo update-grub
sudo reboot
```

### 5. 禁用透明大页

```bash
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
echo never | sudo tee /sys/kernel/mm/transparent_hugepage/defrag
```

## 延迟评估标准

| 评级 | 延迟 | 说明 |
|------|------|------|
| ⭐⭐⭐⭐⭐ 极佳 | < 50μs | 高频交易级别 |
| ⭐⭐⭐⭐ 优秀 | < 100μs | 专业量化级别 |
| ⭐⭐⭐ 良好 | < 500μs | 良好的实盘框架 |
| ⭐⭐ 一般 | < 1ms | 普通量化 |
| ⭐ 差 | > 1ms | 需要优化 |

## 常见问题

### Q: taskset: failed to set pid's affinity: Operation not permitted

需要使用 `sudo` 运行。

### Q: nice: cannot set niceness: Permission denied

需要使用 `sudo` 运行，或者给用户添加 CAP_SYS_NICE 权限。

### Q: 延迟仍然不稳定

1. 检查是否有其他进程在使用绑定的 CPU
2. 使用 `htop` 查看 CPU 使用情况
3. 考虑使用 isolcpus 完全隔离 CPU

## 快速测试命令汇总

```bash
# 1. 安装依赖
sudo apt install -y cmake build-essential libzmq3-dev cppzmq-dev \
    libcurl4-openssl-dev libssl-dev nlohmann-json3-dev

# 2. 编译服务端
cd /home/sequencequant/Real-account-trading-framework/cpp/build
rm -rf CMakeCache.txt CMakeFiles/
cmake ..
make trading_server -j8

# 3. 安装 Python 依赖
pip install pyzmq

# 4. 运行绑核测试
cd /home/sequencequant/Real-account-trading-framework
chmod +x run_latency_test_pinned.sh
sudo ./run_latency_test_pinned.sh 5 1000
```

