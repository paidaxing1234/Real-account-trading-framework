#!/bin/bash
# 重新编译并重启trading_server

echo "=========================================="
echo "重新编译trading_server（添加调试日志）"
echo "=========================================="
echo

cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/build

echo "[1/4] 编译服务器..."
make trading_server_full -j4

if [ $? -ne 0 ]; then
    echo "✗ 编译失败"
    exit 1
fi

echo "✓ 编译成功"
echo

echo "[2/4] 停止旧的服务器进程..."
pkill -9 trading_server_full
sleep 2

echo "[3/4] 启动新的服务器..."
nohup ./trading_server_full > /tmp/trading_server.log 2>&1 &
SERVER_PID=$!

echo "✓ 服务器已启动，PID: $SERVER_PID"
echo

echo "[4/4] 等待服务器初始化..."
sleep 3

echo
echo "=========================================="
echo "服务器已重启，日志文件："
echo "  /tmp/trading_server.log"
echo "=========================================="
echo
echo "查看实时日志："
echo "  tail -f /tmp/trading_server.log"
echo
echo "测试账户查询："
echo "  cd /home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/strategies/GNN_model/trading/GNNstr"
echo "  python3 test_account_detail.py"
