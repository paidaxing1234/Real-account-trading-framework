#!/bin/bash
# 实时监控 BTC 1min K线写入情况

echo "========================================="
echo "  实时监控 BTC 1min K线写入"
echo "  按 Ctrl+C 停止"
echo "========================================="
echo ""

while true; do
    clear
    echo "========================================="
    echo "  BTC 1min K线实时监控"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================="
    echo ""

    # 全市场1min K线总数统计
    echo "【全市场1min K线总数】"
    total_1m_klines=0
    kline_1m_keys=$(redis-cli KEYS "kline:*:1m" 2>/dev/null)
    if [ -n "$kline_1m_keys" ]; then
        for key in $kline_1m_keys; do
            count=$(redis-cli ZCARD "$key" 2>/dev/null || echo "0")
            total_1m_klines=$((total_1m_klines + count))
        done
    fi
    echo "  总计: $total_1m_klines 根1min K线"
    echo ""

    # OKX BTC-USDT-SWAP
    echo "【OKX BTC-USDT-SWAP】"
    okx_count=$(redis-cli ZCARD "kline:okx:BTC-USDT-SWAP:1m" 2>/dev/null || echo "0")
    echo "  1min K线数量: $okx_count"

    if [ "$okx_count" -gt 0 ]; then
        echo "  最新K线:"
        redis-cli ZRANGE "kline:okx:BTC-USDT-SWAP:1m" -1 -1 2>/dev/null | jq -r '. | "    时间: \(.timestamp / 1000 | strftime("%Y-%m-%d %H:%M:%S"))\n    开: \(.open) 高: \(.high) 低: \(.low) 收: \(.close)\n    量: \(.volume)"' 2>/dev/null || redis-cli ZRANGE "kline:okx:BTC-USDT-SWAP:1m" -1 -1
    else
        echo "  暂无数据"
    fi
    echo ""

    # Binance BTCUSDT
    echo "【Binance BTCUSDT】"
    binance_count=$(redis-cli ZCARD "kline:binance:BTCUSDT:1m" 2>/dev/null || echo "0")
    echo "  1min K线数量: $binance_count"

    if [ "$binance_count" -gt 0 ]; then
        echo "  最新K线:"
        redis-cli ZRANGE "kline:binance:BTCUSDT:1m" -1 -1 2>/dev/null | jq -r '. | "    时间: \(.timestamp / 1000 | strftime("%Y-%m-%d %H:%M:%S"))\n    开: \(.open) 高: \(.high) 低: \(.low) 收: \(.close)\n    量: \(.volume)"' 2>/dev/null || redis-cli ZRANGE "kline:binance:BTCUSDT:1m" -1 -1
    else
        echo "  暂无数据"
    fi
    echo ""

    # 聚合K线统计
    echo "【聚合K线统计】"
    for interval in 5m 15m 30m 1h; do
        okx_agg=$(redis-cli ZCARD "kline:okx:BTC-USDT-SWAP:${interval}" 2>/dev/null || echo "0")
        binance_agg=$(redis-cli ZCARD "kline:binance:BTCUSDT:${interval}" 2>/dev/null || echo "0")
        echo "  ${interval}: OKX=$okx_agg, Binance=$binance_agg"
    done
    echo ""

    # data_recorder 日志最后几行
    echo "【data_recorder 日志】"
    tail -n 3 /tmp/data_recorder.log 2>/dev/null || echo "  日志文件不存在"
    echo ""

    echo "========================================="
    echo "  刷新间隔: 2秒"
    echo "========================================="

    sleep 2
done
