#!/bin/bash
# OKX WebSocket Debug 日志查看脚本

LOG_FILE="/tmp/okx_websocket_debug.log"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        OKX WebSocket Debug 日志查看器                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "日志文件: $LOG_FILE"
echo ""

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ 日志文件不存在"
    echo "请先启动 trading_server，日志会自动创建"
    exit 1
fi

echo "选择查看模式:"
echo "  1) 实时跟踪 (tail -f)"
echo "  2) 查看最近100行"
echo "  3) 查看最近500行"
echo "  4) 查看全部"
echo "  5) 搜索关键词"
echo "  6) 查看统计信息"
echo ""
read -p "请选择 [1-6]: " choice

case $choice in
    1)
        echo "实时跟踪日志 (按 Ctrl+C 退出)..."
        tail -f "$LOG_FILE"
        ;;
    2)
        tail -100 "$LOG_FILE"
        ;;
    3)
        tail -500 "$LOG_FILE"
        ;;
    4)
        cat "$LOG_FILE"
        ;;
    5)
        read -p "输入搜索关键词: " keyword
        grep -i "$keyword" "$LOG_FILE" | tail -100
        ;;
    6)
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "统计信息"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "总行数: $(wc -l < "$LOG_FILE")"
        echo ""
        echo "ping 发送次数: $(grep -c "发送 ping" "$LOG_FILE")"
        echo "pong 接收次数: $(grep -c "收到 pong" "$LOG_FILE")"
        echo ""
        echo "连接断开次数: $(grep -c "连接断开" "$LOG_FILE")"
        echo "连接失败次数: $(grep -c "连接失败" "$LOG_FILE")"
        echo ""
        echo "最后一次 ping: $(grep "发送 ping" "$LOG_FILE" | tail -1)"
        echo "最后一次 pong: $(grep "收到 pong" "$LOG_FILE" | tail -1)"
        echo ""
        echo "最后一次断开: $(grep "连接断开\|连接失败" "$LOG_FILE" | tail -1)"
        echo ""
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
