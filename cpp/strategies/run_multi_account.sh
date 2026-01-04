#!/bin/bash
# 多账户启动网格策略示例

echo "=========================================="
echo "  多账户网格策略启动脚本"
echo "=========================================="
echo ""

# 账户1：使用默认账户（实盘）
echo "[账户1] 启动网格策略 - 使用默认账户"
python3 grid_strategy_cpp.py \
    --strategy-id grid_account1 \
    --symbol BTC-USDT-SWAP \
    --grid-num 10 \
    --grid-spread 0.002 \
    --order-amount 50 \
    --testnet &

ACCOUNT1_PID=$!
echo "  PID: $ACCOUNT1_PID"
echo ""

sleep 2

# 账户2：使用独立账户（实盘）
echo "[账户2] 启动网格策略 - 使用独立账户"
python3 grid_strategy_cpp.py \
    --strategy-id grid_account2 \
    --symbol ETH-USDT-SWAP \
    --grid-num 15 \
    --grid-spread 0.0015 \
    --order-amount 100 \
    --api-key "YOUR_API_KEY_2" \
    --secret-key "YOUR_SECRET_KEY_2" \
    --passphrase "YOUR_PASSPHRASE_2" \
    --testnet &

ACCOUNT2_PID=$!
echo "  PID: $ACCOUNT2_PID"
echo ""

sleep 2

# 账户3：使用另一个独立账户（模拟盘）
echo "[账户3] 启动网格策略 - 使用模拟盘账户"
python3 grid_strategy_cpp.py \
    --strategy-id grid_account3 \
    --symbol SOL-USDT-SWAP \
    --grid-num 20 \
    --grid-spread 0.001 \
    --order-amount 30 \
    --api-key "YOUR_API_KEY_3" \
    --secret-key "YOUR_SECRET_KEY_3" \
    --passphrase "YOUR_PASSPHRASE_3" \
    --testnet &

ACCOUNT3_PID=$!
echo "  PID: $ACCOUNT3_PID"
echo ""

echo "=========================================="
echo "  所有策略已启动"
echo "=========================================="
echo ""
echo "运行中的策略:"
echo "  账户1 (BTC): PID $ACCOUNT1_PID"
echo "  账户2 (ETH): PID $ACCOUNT2_PID"
echo "  账户3 (SOL): PID $ACCOUNT3_PID"
echo ""
echo "停止所有策略: kill $ACCOUNT1_PID $ACCOUNT2_PID $ACCOUNT3_PID"
echo "或按 Ctrl+C"
echo ""

# 等待所有进程
wait
