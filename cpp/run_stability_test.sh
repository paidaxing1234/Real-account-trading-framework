#!/bin/bash
# ============================================================
# run_stability_test.sh
# 稳定性浸泡测试脚本
#
# 功能：
# 1. 启动服务器（可选 ASan 模式）
# 2. 多轮压力测试
# 3. 监控内存使用
# 4. 检测崩溃和内存泄漏
# ============================================================

set -u

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${ROOT_DIR}/build"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# 默认参数
ROUNDS=${1:-5}              # 测试轮数
ORDERS_PER_ROUND=${2:-1000} # 每轮订单数
RATE=${3:-300}              # 每秒订单数
SERVER_TYPE=${4:-full}      # full 或 paper

# 日志文件
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_LOG="${LOG_DIR}/stability_${TIMESTAMP}.log"
SERVER_LOG="${LOG_DIR}/server_stability_${TIMESTAMP}.log"

log() {
    echo -e "$1" | tee -a "${TEST_LOG}"
}

log_header() {
    log ""
    log "${CYAN}============================================================${NC}"
    log "${CYAN}$1${NC}"
    log "${CYAN}============================================================${NC}"
}

# 获取进程内存使用 (MB)
get_memory_mb() {
    local pid=$1
    if ps -p $pid > /dev/null 2>&1; then
        ps -o rss= -p $pid 2>/dev/null | awk '{printf "%.1f", $1/1024}'
    else
        echo "N/A"
    fi
}

# 检查服务器是否存活
check_server() {
    local pid=$1
    if ps -p $pid > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 清理 IPC 文件
cleanup_ipc() {
    rm -f /tmp/seq_*.ipc /tmp/paper_*.ipc /tmp/trading_*.ipc 2>/dev/null || true
}

# ============================================================
# 主流程
# ============================================================

log_header "       稳定性测试 - $(date)"

log "配置:"
log "  测试轮数: ${ROUNDS}"
log "  每轮订单: ${ORDERS_PER_ROUND}"
log "  发送速率: ${RATE} 订单/秒"
log "  服务器类型: ${SERVER_TYPE}"
log "  日志文件: ${TEST_LOG}"
log ""

# 1. 检查服务器可执行文件
if [ "${SERVER_TYPE}" = "paper" ]; then
    SERVER_BIN="${BUILD_DIR}/papertrading_server"
else
    SERVER_BIN="${BUILD_DIR}/trading_server_full"
fi

if [ ! -f "${SERVER_BIN}" ]; then
    log "${RED}错误: 服务器不存在: ${SERVER_BIN}${NC}"
    log "请先编译: cd build && cmake .. && make trading_server_full"
    exit 1
fi

log "${GREEN}✓ 服务器可执行文件: ${SERVER_BIN}${NC}"

# 2. 清理环境
log ""
log "清理残留 IPC 文件..."
cleanup_ipc

# 3. 启动服务器
log_header "       启动服务器"

"${SERVER_BIN}" --testnet > "${SERVER_LOG}" 2>&1 &
SERVER_PID=$!
log "服务器 PID: ${SERVER_PID}"

# 等待服务器启动
log -n "等待服务器初始化"
for i in {1..15}; do
    if [ -e "/tmp/seq_order.ipc" ]; then
        log " ${GREEN}✓${NC}"
        break
    fi
    log -n "."
    sleep 0.5
done

sleep 1

# 检查服务器是否存活
if ! check_server ${SERVER_PID}; then
    log "${RED}错误: 服务器启动失败！${NC}"
    log "查看日志: ${SERVER_LOG}"
    tail -30 "${SERVER_LOG}"
    exit 1
fi

INITIAL_MEM=$(get_memory_mb ${SERVER_PID})
log "服务器初始内存: ${INITIAL_MEM} MB"
log ""

# 4. 运行多轮压力测试
log_header "       开始压力测试 (${ROUNDS} 轮)"

PASSED_ROUNDS=0
FAILED_ROUNDS=0
MEM_READINGS=()

for ((round=1; round<=ROUNDS; round++)); do
    log ""
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${YELLOW}  第 ${round}/${ROUNDS} 轮${NC}"
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # 检查服务器状态
    if ! check_server ${SERVER_PID}; then
        log "${RED}!!! 严重错误: 服务器在第 ${round} 轮前已崩溃 !!!${NC}"
        log "查看日志: ${SERVER_LOG}"
        tail -50 "${SERVER_LOG}" | tee -a "${TEST_LOG}"
        break
    fi

    # 运行压力测试
    if python3 "${ROOT_DIR}/stress_test_client.py" \
        --orders ${ORDERS_PER_ROUND} \
        --rate ${RATE} 2>&1 | tee -a "${TEST_LOG}"; then
        log "${GREEN}第 ${round} 轮: 通过${NC}"
        ((PASSED_ROUNDS++))
    else
        log "${RED}第 ${round} 轮: 失败${NC}"
        ((FAILED_ROUNDS++))
    fi

    # 检查服务器是否还活着
    if ! check_server ${SERVER_PID}; then
        log "${RED}!!! 严重错误: 服务器在第 ${round} 轮后崩溃 !!!${NC}"
        log "查看日志尾部:"
        tail -50 "${SERVER_LOG}" | tee -a "${TEST_LOG}"
        break
    fi

    # 记录内存使用
    CURRENT_MEM=$(get_memory_mb ${SERVER_PID})
    MEM_READINGS+=("$CURRENT_MEM")
    log "当前内存占用: ${CURRENT_MEM} MB"

    # 检测内存增长趋势
    if [ ${#MEM_READINGS[@]} -ge 3 ]; then
        FIRST_MEM=${MEM_READINGS[0]}
        if (( $(echo "$CURRENT_MEM > $FIRST_MEM * 2" | bc -l 2>/dev/null || echo 0) )); then
            log "${YELLOW}警告: 内存增长较快 (初始: ${FIRST_MEM} MB -> 当前: ${CURRENT_MEM} MB)${NC}"
        fi
    fi

    # 休息一下
    sleep 2
done

# 5. 停止服务器
log_header "       停止服务器"

if check_server ${SERVER_PID}; then
    log "发送 SIGTERM..."
    kill ${SERVER_PID} 2>/dev/null

    # 等待优雅退出
    for i in {1..10}; do
        if ! check_server ${SERVER_PID}; then
            log "${GREEN}服务器已正常退出${NC}"
            break
        fi
        sleep 0.5
    done

    # 强制终止
    if check_server ${SERVER_PID}; then
        log "${YELLOW}强制终止服务器...${NC}"
        kill -9 ${SERVER_PID} 2>/dev/null
    fi
else
    log "${RED}服务器在测试期间崩溃${NC}"
fi

# 清理 IPC
cleanup_ipc

# 6. 检查 ASan 报告
log_header "       检查 AddressSanitizer 报告"

if grep -q "AddressSanitizer" "${SERVER_LOG}"; then
    log "${RED}!!! 发现 AddressSanitizer 错误 !!!${NC}"
    log ""
    grep -A 50 "AddressSanitizer" "${SERVER_LOG}" | head -60 | tee -a "${TEST_LOG}"
    ASAN_ERROR=1
else
    log "${GREEN}✓ 未发现 AddressSanitizer 错误${NC}"
    ASAN_ERROR=0
fi

# 检查其他崩溃信号
if grep -qE "(Segmentation fault|SIGABRT|SIGSEGV|double free|corrupted|free\(\): invalid|malloc\(\)|heap-buffer)" "${SERVER_LOG}"; then
    log "${RED}!!! 发现崩溃信号 !!!${NC}"
    grep -E "(Segmentation fault|SIGABRT|SIGSEGV|double free|corrupted|free\(\): invalid|malloc\(\)|heap-buffer)" "${SERVER_LOG}" | tee -a "${TEST_LOG}"
    CRASH_DETECTED=1
else
    log "${GREEN}✓ 未发现崩溃信号${NC}"
    CRASH_DETECTED=0
fi

# 7. 汇总结果
log_header "       测试结果汇总"

log "测试轮数: ${ROUNDS}"
log "通过轮数: ${PASSED_ROUNDS}"
log "失败轮数: ${FAILED_ROUNDS}"
log ""
log "内存使用:"
log "  初始: ${INITIAL_MEM} MB"
if [ ${#MEM_READINGS[@]} -gt 0 ]; then
    FINAL_MEM=${MEM_READINGS[-1]}
    log "  最终: ${FINAL_MEM} MB"

    # 计算内存增长
    if command -v bc &> /dev/null && [ "$INITIAL_MEM" != "N/A" ] && [ "$FINAL_MEM" != "N/A" ]; then
        MEM_GROWTH=$(echo "scale=1; $FINAL_MEM - $INITIAL_MEM" | bc 2>/dev/null || echo "N/A")
        log "  增长: ${MEM_GROWTH} MB"
    fi
fi
log ""
log "ASan 错误: $([ $ASAN_ERROR -eq 0 ] && echo '无' || echo '有')"
log "崩溃检测: $([ $CRASH_DETECTED -eq 0 ] && echo '无' || echo '有')"
log ""

# 最终判定
if [ $PASSED_ROUNDS -eq $ROUNDS ] && [ $ASAN_ERROR -eq 0 ] && [ $CRASH_DETECTED -eq 0 ]; then
    log "${GREEN}============================================================${NC}"
    log "${GREEN}[SUCCESS] 稳定性测试全部通过！${NC}"
    log "${GREEN}============================================================${NC}"
    EXIT_CODE=0
elif [ $PASSED_ROUNDS -gt 0 ] && [ $CRASH_DETECTED -eq 0 ]; then
    log "${YELLOW}============================================================${NC}"
    log "${YELLOW}[PARTIAL] 稳定性测试部分通过${NC}"
    log "${YELLOW}============================================================${NC}"
    EXIT_CODE=1
else
    log "${RED}============================================================${NC}"
    log "${RED}[FAILED] 稳定性测试失败${NC}"
    log "${RED}============================================================${NC}"
    EXIT_CODE=1
fi

log ""
log "详细日志:"
log "  测试日志: ${TEST_LOG}"
log "  服务器日志: ${SERVER_LOG}"

exit ${EXIT_CODE}
