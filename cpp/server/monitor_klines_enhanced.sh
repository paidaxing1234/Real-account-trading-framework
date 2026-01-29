#!/bin/bash
# K线数据实时监控脚本（增强版 - 检测连续性）

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        K线数据实时监控（增强版）                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

TEST_SYMBOL="BTC-USDT-SWAP"
EXCHANGE="okx"  # 添加交易所字段

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检查Python脚本是否存在
if [ ! -f "$SCRIPT_DIR/check_kline_continuity.py" ]; then
    echo "错误: 找不到 check_kline_continuity.py"
    echo "请确保该脚本在 $SCRIPT_DIR 目录下"
    exit 1
fi

while true; do
    clear
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║        K线数据实时监控 - $TEST_SYMBOL"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    date
    echo ""

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "原始K线（从交易所获取）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for interval in "1m"; do
        count=$(redis-cli ZCARD "kline:$EXCHANGE:$TEST_SYMBOL:$interval" 2>/dev/null || echo "0")
        printf "  %-4s: %6d 根\n" "$interval" "$count"
    done

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "聚合K线（本地计算）"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for interval in "5m" "15m" "30m" "1h"; do
        count=$(redis-cli ZCARD "kline:$EXCHANGE:$TEST_SYMBOL:$interval" 2>/dev/null || echo "0")
        if [ "$count" -gt 0 ]; then
            printf "  \033[0;32m%-4s: %6d 根 ✓\033[0m\n" "$interval" "$count"
        else
            printf "  \033[1;33m%-4s: %6d 根 (等待中...)\033[0m\n" "$interval" "$count"
        fi
    done

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "聚合进度与连续性检查"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 调用Python脚本检查连续性
    python3 "$SCRIPT_DIR/check_kline_continuity.py" "$TEST_SYMBOL" "$EXCHANGE"

    echo ""
    echo "按 Ctrl+C 停止监控"
    echo ""

    sleep 5
done
