#!/bin/bash

# Binance 市场数据测试脚本
# 用法：
#   ./run_market_data_test.sh testnet spot    # 测试网现货
#   ./run_market_data_test.sh testnet futures # 测试网合约
#   ./run_market_data_test.sh mainnet spot    # 主网现货
#   ./run_market_data_test.sh mainnet futures # 主网合约

cd "$(dirname "$0")/../build" || exit 1

NETWORK="${1:-testnet}"
MARKET="${2:-spot}"

if [ "$NETWORK" = "testnet" ]; then
    export BINANCE_TESTNET=1
    echo "🌐 使用测试网（模拟账户）"
else
    export BINANCE_TESTNET=0
    echo "🌐 使用主网（真实账户）"
fi

if [ "$MARKET" = "futures" ]; then
    export MARKET_TYPE=FUTURES
    echo "📊 测试合约市场"
else
    export MARKET_TYPE=SPOT
    echo "📊 测试现货市场"
fi

echo ""
echo "运行测试程序..."
echo ""

./test_binance_market_data_comprehensive

