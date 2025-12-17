#!/bin/bash
#
# Sequence 实盘交易系统启动脚本
#
# 功能：
# 1. 启动实盘服务器（绑定到 CPU 1-2）
# 2. 启动策略进程（绑定到 CPU 4-11）
#
# CPU 分配（NUMA Node 0）：
#   CPU 0: 系统中断（保留）
#   CPU 1: 实盘服务器主线程（WebSocket + ZMQ）
#   CPU 2: 实盘服务器订单线程
#   CPU 3: 备用
#   CPU 4-11: 策略进程（最多8个策略）
#
# 使用方法：
#   ./run_trading_system.sh server    # 启动服务器
#   ./run_trading_system.sh strategy  # 启动策略（默认编号0，CPU 4）
#   ./run_trading_system.sh strategy 1 # 启动策略编号1（CPU 5）
#   ./run_trading_system.sh all       # 启动服务器 + 1个策略
#
# 环境要求：
#   - Linux (支持 sched_setaffinity)
#   - libnuma-dev (可选，用于 NUMA 绑定)
#   - sudo 权限（用于实时调度）
#

set -e

# ============================================================
# 配置
# ============================================================

# 目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$CPP_DIR/build"
EXAMPLES_DIR="$CPP_DIR/examples"

# CPU 配置
SERVER_CPU=1
ORDER_CPU=2
STRATEGY_START_CPU=4

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================
# 辅助函数
# ============================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_cpu_layout() {
    echo ""
    echo "============================================================"
    echo "  CPU 分配（NUMA Node 0）"
    echo "============================================================"
    echo "  CPU 0:     系统中断（保留）"
    echo "  CPU 1:     实盘服务器主线程"
    echo "  CPU 2:     实盘服务器订单线程"
    echo "  CPU 3:     备用"
    echo "  CPU 4-11:  策略进程（最多8个）"
    echo "============================================================"
    echo ""
}

check_server_binary() {
    if [[ ! -f "$BUILD_DIR/trading_server_live" ]]; then
        log_error "未找到 trading_server_live"
        log_info "请先编译: cd $BUILD_DIR && make trading_server_live"
        exit 1
    fi
}

check_strategy_script() {
    if [[ ! -f "$EXAMPLES_DIR/zmq_strategy_client.py" ]]; then
        log_error "未找到 zmq_strategy_client.py"
        exit 1
    fi
}

# ============================================================
# 启动函数
# ============================================================

start_server() {
    log_info "启动实盘服务器..."
    check_server_binary
    
    # 使用 taskset 绑定 CPU（备用方案，程序内部也会绑定）
    # 使用 numactl 绑定 NUMA 节点
    if command -v numactl &> /dev/null; then
        log_info "使用 numactl 绑定到 NUMA Node 0"
        numactl --cpunodebind=0 --membind=0 "$BUILD_DIR/trading_server_live"
    else
        log_warn "numactl 未安装，使用 taskset"
        taskset -c $SERVER_CPU "$BUILD_DIR/trading_server_live"
    fi
}

start_server_sudo() {
    log_info "启动实盘服务器（实时调度）..."
    check_server_binary
    
    # 使用 sudo + chrt 设置实时调度
    if command -v numactl &> /dev/null; then
        sudo numactl --cpunodebind=0 --membind=0 \
            chrt -f 50 "$BUILD_DIR/trading_server_live"
    else
        sudo taskset -c $SERVER_CPU \
            chrt -f 50 "$BUILD_DIR/trading_server_live"
    fi
}

start_strategy() {
    local strategy_index=${1:-0}
    local cpu=$((STRATEGY_START_CPU + strategy_index))
    
    log_info "启动策略 #$strategy_index (CPU $cpu)..."
    check_strategy_script
    
    cd "$EXAMPLES_DIR"
    python3 zmq_strategy_client.py \
        --strategy-id "strategy_$strategy_index" \
        --strategy-index "$strategy_index" \
        --cpu "$cpu"
}

start_strategy_sudo() {
    local strategy_index=${1:-0}
    local cpu=$((STRATEGY_START_CPU + strategy_index))
    
    log_info "启动策略 #$strategy_index (CPU $cpu, 实时调度)..."
    check_strategy_script
    
    cd "$EXAMPLES_DIR"
    sudo taskset -c "$cpu" \
        chrt -f 48 \
        python3 zmq_strategy_client.py \
            --strategy-id "strategy_$strategy_index" \
            --strategy-index "$strategy_index" \
            --realtime
}

start_all() {
    log_info "启动完整交易系统..."
    
    # 后台启动服务器
    start_server &
    SERVER_PID=$!
    log_info "服务器 PID: $SERVER_PID"
    
    # 等待服务器启动
    sleep 3
    
    # 启动策略
    start_strategy 0
}

# ============================================================
# 主函数
# ============================================================

show_usage() {
    echo "用法: $0 <command> [args]"
    echo ""
    echo "命令:"
    echo "  server          启动实盘服务器"
    echo "  server-rt       启动实盘服务器（实时调度，需要 sudo）"
    echo "  strategy [n]    启动策略 #n（默认 n=0）"
    echo "  strategy-rt [n] 启动策略 #n（实时调度，需要 sudo）"
    echo "  all             启动服务器 + 策略 0"
    echo "  cpu             显示 CPU 分配"
    echo ""
    echo "示例:"
    echo "  $0 server           # 启动服务器"
    echo "  $0 strategy 0       # 启动策略 0（CPU 4）"
    echo "  $0 strategy 1       # 启动策略 1（CPU 5）"
    echo ""
    print_cpu_layout
}

main() {
    local command=${1:-help}
    
    case "$command" in
        server)
            print_cpu_layout
            start_server
            ;;
        server-rt)
            print_cpu_layout
            start_server_sudo
            ;;
        strategy)
            start_strategy "${2:-0}"
            ;;
        strategy-rt)
            start_strategy_sudo "${2:-0}"
            ;;
        all)
            print_cpu_layout
            start_all
            ;;
        cpu)
            print_cpu_layout
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            log_error "未知命令: $command"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"

