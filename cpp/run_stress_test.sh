#!/bin/bash
# ============================================================
# 压力测试客户端长期运行脚本
# 在后台持续运行压力测试并记录状态
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"

STRESS_SCRIPT="${SCRIPT_DIR}/stress_test_client.py"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
STRESS_LOG="${LOG_DIR}/stress_test_${TIMESTAMP}.log"
PID_FILE="${LOG_DIR}/stress_test.pid"

# 默认参数
RATE=100
ACCOUNTS=4
STRATEGIES=2
INTERVAL=10

# 启动压力测试
start_stress() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p $OLD_PID > /dev/null 2>&1; then
            echo "压力测试已在运行 (PID: $OLD_PID)"
            return 1
        fi
    fi

    echo "启动压力测试..."
    echo "  速率: ${RATE}/s | 账户: ${ACCOUNTS} | 策略: ${STRATEGIES}"
    nohup python3 -u "$STRESS_SCRIPT" --continuous \
        --rate $RATE \
        --accounts $ACCOUNTS \
        --strategies $STRATEGIES \
        --interval $INTERVAL \
        > "$STRESS_LOG" 2>&1 &
    STRESS_PID=$!
    echo $STRESS_PID > "$PID_FILE"
    echo "压力测试已启动 (PID: $STRESS_PID)"
    echo "日志文件: $STRESS_LOG"
    sleep 2
}

# 检查状态
check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            MEM=$(ps -o rss= -p $PID 2>/dev/null | awk '{printf "%.1f", $1/1024}')
            UPTIME=$(ps -o etime= -p $PID 2>/dev/null | tr -d ' ')
            echo "状态: 运行中 | PID: $PID | 内存: ${MEM}MB | 运行时间: $UPTIME"

            # 显示最新统计
            LATEST_LOG=$(ls -t ${LOG_DIR}/stress_test_*.log 2>/dev/null | head -1)
            if [ -n "$LATEST_LOG" ]; then
                echo ""
                echo "最新状态:"
                tail -3 "$LATEST_LOG" | grep -E "订单|行情" | head -2
            fi
            return 0
        fi
    fi
    echo "状态: 未运行"
    return 1
}

# 停止压力测试
stop_stress() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "停止压力测试 (PID: $PID)..."
            kill $PID 2>/dev/null
            sleep 2
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID 2>/dev/null
            fi
        fi
        rm -f "$PID_FILE"
        echo "压力测试已停止"
    else
        echo "压力测试未运行"
    fi
}

# 查看日志
view_log() {
    LATEST_LOG=$(ls -t ${LOG_DIR}/stress_test_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "日志文件: $LATEST_LOG"
        echo "----------------------------------------"
        tail -50 "$LATEST_LOG"
    else
        echo "没有找到日志文件"
    fi
}

# 实时查看日志
follow_log() {
    LATEST_LOG=$(ls -t ${LOG_DIR}/stress_test_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "实时查看日志 (Ctrl+C 退出): $LATEST_LOG"
        echo "----------------------------------------"
        tail -f "$LATEST_LOG"
    else
        echo "没有找到日志文件"
    fi
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --rate|-r)
            RATE="$2"
            shift 2
            ;;
        --accounts|-a)
            ACCOUNTS="$2"
            shift 2
            ;;
        --strategies|-s)
            STRATEGIES="$2"
            shift 2
            ;;
        --interval|-i)
            INTERVAL="$2"
            shift 2
            ;;
        start|stop|status|log|follow|restart)
            CMD="$1"
            shift
            ;;
        *)
            CMD="$1"
            shift
            ;;
    esac
done

case "$CMD" in
    start)
        start_stress
        ;;
    stop)
        stop_stress
        ;;
    status)
        check_status
        ;;
    log)
        view_log
        ;;
    follow)
        follow_log
        ;;
    restart)
        stop_stress
        sleep 1
        start_stress
        ;;
    *)
        echo "用法: $0 {start|stop|status|log|follow|restart} [选项]"
        echo ""
        echo "命令:"
        echo "  start   - 启动压力测试（后台运行）"
        echo "  stop    - 停止压力测试"
        echo "  status  - 查看运行状态"
        echo "  log     - 查看最新日志"
        echo "  follow  - 实时查看日志"
        echo "  restart - 重启压力测试"
        echo ""
        echo "选项:"
        echo "  --rate, -r      每秒订单数 (默认: 100)"
        echo "  --accounts, -a  账户数量 (默认: 4)"
        echo "  --strategies, -s 每账户策略数 (默认: 2)"
        echo "  --interval, -i  状态报告间隔秒数 (默认: 10)"
        echo ""
        echo "示例:"
        echo "  $0 start --rate 200 --accounts 8"
        echo "  $0 status"
        echo "  $0 follow"
        ;;
esac
