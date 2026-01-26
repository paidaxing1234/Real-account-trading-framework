#!/bin/bash
# 实时监控 BTC K线写入情况（包含起止时间和连续性检测）

echo "========================================="
echo "  实时监控 BTC K线数据"
echo "  按 Ctrl+C 停止"
echo "========================================="
echo ""

# 检查连续性的函数
check_continuity() {
    local key=$1
    local interval_seconds=$2

    # 获取所有时间戳
    local timestamps=$(redis-cli ZRANGE "$key" 0 -1 WITHSCORES 2>/dev/null | awk 'NR%2==0')

    if [ -z "$timestamps" ]; then
        echo "0"
        return
    fi

    # 转换为数组
    local ts_array=($timestamps)
    local gaps=0

    # 检查连续性
    for ((i=1; i<${#ts_array[@]}; i++)); do
        local prev=${ts_array[$((i-1))]}
        local curr=${ts_array[$i]}
        local expected=$((prev + interval_seconds * 1000))

        if [ $curr -gt $expected ]; then
            local gap_count=$(( (curr - expected) / (interval_seconds * 1000) ))
            gaps=$((gaps + gap_count))
        fi
    done

    echo $gaps
}

# 获取起止时间的函数
get_time_range() {
    local key=$1

    # 获取第一个和最后一个时间戳
    local first_ts=$(redis-cli ZRANGE "$key" 0 0 WITHSCORES 2>/dev/null | tail -1)
    local last_ts=$(redis-cli ZRANGE "$key" -1 -1 WITHSCORES 2>/dev/null | tail -1)

    if [ -z "$first_ts" ] || [ -z "$last_ts" ]; then
        echo "N/A ~ N/A"
        return
    fi

    # 转换为可读时间（毫秒转秒）
    local first_time=$(date -d "@$((first_ts / 1000))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "N/A")
    local last_time=$(date -d "@$((last_ts / 1000))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "N/A")

    echo "$first_time ~ $last_time"
}

while true; do
    clear
    echo "╔════════════════════════════════════════════════════════════════════════════════╗"
    echo "║                        BTC K线实时监控                                          ║"
    echo "║                    时间: $(date '+%Y-%m-%d %H:%M:%S')                          ║"
    echo "╚════════════════════════════════════════════════════════════════════════════════╝"
    echo ""

    # OKX BTC-USDT-SWAP
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📊 OKX BTC-USDT-SWAP"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for interval in 1m 5m 15m 30m 1h; do
        key="kline:okx:BTC-USDT-SWAP:${interval}"
        count=$(redis-cli ZCARD "$key" 2>/dev/null || echo "0")

        if [ "$count" -gt 0 ]; then
            # 获取时间范围
            time_range=$(get_time_range "$key")

            # 获取连续性（根据周期计算间隔秒数）
            case $interval in
                1m) interval_sec=60 ;;
                5m) interval_sec=300 ;;
                15m) interval_sec=900 ;;
                30m) interval_sec=1800 ;;
                1h) interval_sec=3600 ;;
            esac

            gaps=$(check_continuity "$key" $interval_sec)

            # 计算连续性百分比
            if [ $gaps -eq 0 ]; then
                continuity="100.00%"
                status="✓"
            else
                total=$((count + gaps))
                continuity=$(awk "BEGIN {printf \"%.2f%%\", ($count / $total) * 100}")
                if [ $gaps -lt 10 ]; then
                    status="⚠"
                else
                    status="✗"
                fi
            fi

            printf "  %-6s 数量: %-8s 缺失: %-6s 连续性: %-10s %s\n" "$interval" "$count" "$gaps" "$continuity" "$status"
            printf "         时间: %s\n" "$time_range"
        else
            printf "  %-6s 暂无数据\n" "$interval"
        fi
    done

    echo ""

    # Binance BTCUSDT
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📊 Binance BTCUSDT"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for interval in 1m 5m 15m 30m 1h; do
        key="kline:binance:BTCUSDT:${interval}"
        count=$(redis-cli ZCARD "$key" 2>/dev/null || echo "0")

        if [ "$count" -gt 0 ]; then
            # 获取时间范围
            time_range=$(get_time_range "$key")

            # 获取连续性
            case $interval in
                1m) interval_sec=60 ;;
                5m) interval_sec=300 ;;
                15m) interval_sec=900 ;;
                30m) interval_sec=1800 ;;
                1h) interval_sec=3600 ;;
            esac

            gaps=$(check_continuity "$key" $interval_sec)

            # 计算连续性百分比
            if [ $gaps -eq 0 ]; then
                continuity="100.00%"
                status="✓"
            else
                total=$((count + gaps))
                continuity=$(awk "BEGIN {printf \"%.2f%%\", ($count / $total) * 100}")
                if [ $gaps -lt 10 ]; then
                    status="⚠"
                else
                    status="✗"
                fi
            fi

            printf "  %-6s 数量: %-8s 缺失: %-6s 连续性: %-10s %s\n" "$interval" "$count" "$gaps" "$continuity" "$status"
            printf "         时间: %s\n" "$time_range"
        else
            printf "  %-6s 暂无数据\n" "$interval"
        fi
    done

    echo ""

    # 最新K线数据
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📈 最新1min K线"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # OKX 最新K线
    okx_latest=$(redis-cli ZRANGE "kline:okx:BTC-USDT-SWAP:1m" -1 -1 2>/dev/null)
    if [ -n "$okx_latest" ]; then
        echo "  OKX:"
        echo "$okx_latest" | jq -r '
            "    时间: \(.timestamp / 1000 | strftime("%Y-%m-%d %H:%M:%S"))",
            "    开: \(.open)  高: \(.high)  低: \(.low)  收: \(.close)",
            "    量: \(.volume)"
        ' 2>/dev/null || echo "    $okx_latest"
    else
        echo "  OKX: 暂无数据"
    fi

    echo ""

    # Binance 最新K线
    binance_latest=$(redis-cli ZRANGE "kline:binance:BTCUSDT:1m" -1 -1 2>/dev/null)
    if [ -n "$binance_latest" ]; then
        echo "  Binance:"
        echo "$binance_latest" | jq -r '
            "    时间: \(.timestamp / 1000 | strftime("%Y-%m-%d %H:%M:%S"))",
            "    开: \(.open)  高: \(.high)  低: \(.low)  收: \(.close)",
            "    量: \(.volume)"
        ' 2>/dev/null || echo "    $binance_latest"
    else
        echo "  Binance: 暂无数据"
    fi

    echo ""

    # 全市场统计
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  📊 全市场统计"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    total_1m_klines=0
    kline_1m_keys=$(redis-cli KEYS "kline:*:1m" 2>/dev/null)
    if [ -n "$kline_1m_keys" ]; then
        for key in $kline_1m_keys; do
            count=$(redis-cli ZCARD "$key" 2>/dev/null || echo "0")
            total_1m_klines=$((total_1m_klines + count))
        done
    fi
    echo "  全市场1min K线总数: $(printf "%'d" $total_1m_klines) 根"
    echo ""

    # data_recorder 日志
    if [ -f /tmp/data_recorder.log ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  📝 data_recorder 日志（最近3行）"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        tail -n 3 /tmp/data_recorder.log 2>/dev/null | sed 's/^/  /'
        echo ""
    fi

    echo "════════════════════════════════════════════════════════════════════════════════"
    echo "  刷新间隔: 3秒 | 图例: ✓=完全连续 ⚠=少量缺失 ✗=较多缺失"
    echo "════════════════════════════════════════════════════════════════════════════════"

    sleep 3
done
