#!/bin/bash
# ===========================================
# 绑核延迟测试启动脚本
# 适用于 Linux 系统
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 默认配置
NUM_STRATEGIES=${1:-5}
COUNT=${2:-1000}

# CPU 分配（全部在 NUMA Node 0: CPU 0-11）
# Node 0: CPU 0-11, 48-59
# 避开 CPU 0（系统中断），使用 CPU 1-11
SERVER_CPU=1
STRATEGY_BASE_CPU=3

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ZeroMQ 绑核延迟测试${NC}"
echo -e "${GREEN}  Linux 高性能版本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}警告: 未使用 sudo，绑核和高优先级可能不生效${NC}"
    echo -e "${YELLOW}建议: sudo $0 $NUM_STRATEGIES $COUNT${NC}"
    echo ""
fi

# 显示配置
echo -e "${BLUE}测试配置:${NC}"
echo "  项目目录:     $PROJECT_DIR"
echo "  策略数量:     $NUM_STRATEGIES"
echo "  消息数量:     $COUNT"
echo "  服务端 CPU:   $SERVER_CPU"
echo "  策略 CPU:     $STRATEGY_BASE_CPU - $((STRATEGY_BASE_CPU + NUM_STRATEGIES - 1))"
echo ""

# Python 路径（conda 环境）
PYTHON_BIN="/home/sequencequant/miniconda3/bin/python3"

# 检查 Python 是否存在
if [ ! -x "$PYTHON_BIN" ]; then
    echo -e "${RED}错误: Python 未找到: $PYTHON_BIN${NC}"
    echo "请设置正确的 PYTHON_BIN 路径"
    exit 1
fi
echo -e "${BLUE}Python:${NC} $PYTHON_BIN"

# 检查服务端是否已编译
if [ ! -f "$PROJECT_DIR/cpp/build/trading_server" ]; then
    echo -e "${RED}错误: trading_server 未编译${NC}"
    echo ""
    echo "请先编译:"
    echo "  cd $PROJECT_DIR/cpp/build"
    echo "  cmake .."
    echo "  make trading_server -j8"
    exit 1
fi

# 检查 IPC 文件是否存在（说明服务端可能已在运行）
if [ -e "/tmp/trading_md.ipc" ]; then
    echo -e "${YELLOW}发现已存在的 IPC 文件，清理中...${NC}"
    rm -f /tmp/trading_*.ipc
fi

# 显示 CPU 信息
echo -e "${BLUE}CPU 信息:${NC}"
CPU_MODEL=$(cat /proc/cpuinfo | grep "model name" | head -1 | cut -d: -f2 | xargs)
CPU_COUNT=$(nproc)
echo "  CPU 型号:     $CPU_MODEL"
echo "  CPU 核心数:   $CPU_COUNT"
echo ""

# ========================================
# 步骤 1: 启动服务端
# ========================================
echo -e "${YELLOW}[1/3] 启动 C++ 服务端...${NC}"
cd "$PROJECT_DIR/cpp/build"

# 使用 taskset 绑定 CPU，nice 设置高优先级 (-20 是最高优先级)
if [ "$EUID" -eq 0 ]; then
    taskset -c $SERVER_CPU nice -n -20 ./trading_server &
else
    taskset -c $SERVER_CPU ./trading_server &
fi
SERVER_PID=$!

echo "  服务端 PID: $SERVER_PID (CPU $SERVER_CPU)"

# 等待服务端启动
sleep 2

# 检查服务端是否运行
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo -e "${RED}错误: 服务端启动失败${NC}"
    exit 1
fi

# 注意: ZeroMQ IPC 在某些情况下不创建文件，跳过此检查
# 服务端进程存活即认为启动成功

echo -e "${GREEN}  ✓ 服务端启动成功${NC}"
echo ""

# ========================================
# 步骤 2: 启动策略进程
# ========================================
echo -e "${YELLOW}[2/3] 启动 Python 策略进程...${NC}"
cd "$PROJECT_DIR/python/strategies"

declare -a STRATEGY_PIDS

for i in $(seq 1 $NUM_STRATEGIES); do
    CPU=$((STRATEGY_BASE_CPU + i - 1))
    
    if [ "$EUID" -eq 0 ]; then
        taskset -c $CPU nice -n -10 $PYTHON_BIN benchmark_latency.py --id $i --count $COUNT &
    else
        taskset -c $CPU $PYTHON_BIN benchmark_latency.py --id $i --count $COUNT &
    fi
    
    STRATEGY_PIDS+=($!)
    echo "  策略 $i: PID ${STRATEGY_PIDS[-1]} (CPU $CPU)"
    
    # 间隔启动，避免同时连接
    sleep 0.3
done

echo ""
echo -e "${GREEN}所有进程已启动:${NC}"
echo "  服务端:    PID $SERVER_PID (CPU $SERVER_CPU)"
for i in $(seq 1 $NUM_STRATEGIES); do
    CPU=$((STRATEGY_BASE_CPU + i - 1))
    echo "  策略 $i:    PID ${STRATEGY_PIDS[$((i-1))]} (CPU $CPU)"
done
echo ""

# ========================================
# 步骤 3: 等待测试完成
# ========================================
echo -e "${YELLOW}[3/3] 等待测试完成...${NC}"
echo "  (按 Ctrl+C 中断)"
echo ""

# 定义清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}收到中断信号，停止所有进程...${NC}"
    
    # 停止策略
    for pid in "${STRATEGY_PIDS[@]}"; do
        kill $pid 2>/dev/null
    done
    
    # 停止服务端
    kill $SERVER_PID 2>/dev/null
    
    # 清理 IPC 文件
    rm -f /tmp/trading_*.ipc
    
    echo -e "${GREEN}已停止所有进程${NC}"
    exit 0
}

# 注册信号处理
trap cleanup SIGINT SIGTERM

# 等待所有策略完成
for pid in "${STRATEGY_PIDS[@]}"; do
    wait $pid 2>/dev/null || true
done

echo ""
echo -e "${GREEN}所有策略已完成${NC}"

# 停止服务端
echo "停止服务端..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null || true

# 清理 IPC 文件
rm -f /tmp/trading_*.ipc

# ========================================
# 打印结果
# ========================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  测试完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "报告目录: $PROJECT_DIR/python/reports/"
echo ""

# 列出最新的报告文件
echo "最新报告文件:"
ls -lt "$PROJECT_DIR/python/reports/" 2>/dev/null | head -10

