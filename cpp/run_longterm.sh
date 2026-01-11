#!/bin/bash
# ============================================================
# 长期稳定性测试脚本
# 在后台运行服务器，定期发送测试订单并记录状态
# ============================================================

LOG_DIR="$(pwd)/logs"
mkdir -p "$LOG_DIR"

SERVER_BIN="$(pwd)/build/trading_server_full"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SERVER_LOG="${LOG_DIR}/longterm_server_${TIMESTAMP}.log"
MONITOR_LOG="${LOG_DIR}/longterm_monitor_${TIMESTAMP}.log"
PID_FILE="${LOG_DIR}/server.pid"

# 启动服务器
start_server() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p $OLD_PID > /dev/null 2>&1; then
            echo "服务器已在运行 (PID: $OLD_PID)"
            return 1
        fi
    fi
    
    echo "启动服务器..."
    nohup "$SERVER_BIN" --testnet > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"
    echo "服务器已启动 (PID: $SERVER_PID)"
    echo "日志文件: $SERVER_LOG"
    sleep 3
}

# 检查状态
check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            MEM=$(ps -o rss= -p $PID 2>/dev/null | awk '{printf "%.1f", $1/1024}')
            UPTIME=$(ps -o etime= -p $PID 2>/dev/null | tr -d ' ')
            echo "状态: 运行中 | PID: $PID | 内存: ${MEM}MB | 运行时间: $UPTIME"
            return 0
        fi
    fi
    echo "状态: 未运行"
    return 1
}

# 停止服务器
stop_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "停止服务器 (PID: $PID)..."
            kill $PID 2>/dev/null
            sleep 2
            if ps -p $PID > /dev/null 2>&1; then
                kill -9 $PID 2>/dev/null
            fi
        fi
        rm -f "$PID_FILE"
        echo "服务器已停止"
    else
        echo "服务器未运行"
    fi
}

# 查看日志
view_log() {
    LATEST_LOG=$(ls -t ${LOG_DIR}/longterm_server_*.log 2>/dev/null | head -1)
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
    LATEST_LOG=$(ls -t ${LOG_DIR}/longterm_server_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "实时查看日志 (Ctrl+C 退出): $LATEST_LOG"
        echo "----------------------------------------"
        tail -f "$LATEST_LOG"
    else
        echo "没有找到日志文件"
    fi
}

case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
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
        stop_server
        sleep 1
        start_server
        ;;
    *)
        echo "用法: $0 {start|stop|status|log|follow|restart}"
        echo ""
        echo "命令:"
        echo "  start   - 启动服务器（后台运行）"
        echo "  stop    - 停止服务器"
        echo "  status  - 查看运行状态"
        echo "  log     - 查看最新日志"
        echo "  follow  - 实时查看日志"
        echo "  restart - 重启服务器"
        ;;
esac
