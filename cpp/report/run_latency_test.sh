#!/bin/bash

echo "=========================================="
echo "  Journal 延迟测试 - 完整测试流程"
echo "=========================================="

# 设置路径
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$PROJECT_DIR/cpp/build"
JOURNAL_FILE="/tmp/trading_journal.dat"

# 清理旧的Journal文件
echo ""
echo "[1] 清理旧的Journal文件..."
rm -f "$JOURNAL_FILE"
echo "    完成"

# 编译
echo ""
echo "[2] 编译测试程序..."
if [ ! -d "$BUILD_DIR" ]; then
    mkdir -p "$BUILD_DIR"
fi

cd "$BUILD_DIR"
cmake .. -DCMAKE_BUILD_TYPE=Release
make test_journal_latency test_journal_benchmark -j4

if [ $? -ne 0 ]; then
    echo "    编译失败！"
    exit 1
fi
echo "    编译完成"

# 纯写入性能测试
echo ""
echo "[3] 运行纯写入性能测试..."
./test_journal_benchmark
echo "    测试完成"

# 清理
rm -f /tmp/benchmark_journal.dat

# 延迟测试说明
echo ""
echo "=========================================="
echo "[4] 延迟测试（需要两个终端）"
echo "=========================================="
echo ""
echo "终端1（Python Reader）："
echo "  cd $PROJECT_DIR"
echo "  python3 cpp/core/journal_reader.py $JOURNAL_FILE"
echo ""
echo "终端2（C++ Writer）："
echo "  cd $BUILD_DIR"
echo "  ./test_journal_latency $JOURNAL_FILE 100000 100"
echo ""
echo "参数说明："
echo "  100000 = 发送10万个事件"
echo "  100    = 每100微秒发送一个（可调整）"
echo ""
echo "=========================================="
echo ""

read -p "按Enter键继续运行自动化测试（单终端）..."

# 自动化测试
echo ""
echo "[5] 运行自动化测试..."

# 清理
rm -f "$JOURNAL_FILE"

# 后台启动Python Reader
echo "    启动Python Reader（后台）..."
cd "$PROJECT_DIR"
python3 cpp/core/journal_reader.py "$JOURNAL_FILE" > /tmp/reader_output.log 2>&1 &
READER_PID=$!

sleep 1

# 启动C++ Writer
echo "    启动C++ Writer..."
cd "$BUILD_DIR"
./test_journal_latency "$JOURNAL_FILE" 10000 100 < /dev/null

# 等待一会儿让Reader处理完
sleep 2

# 停止Python Reader
echo "    停止Python Reader..."
kill $READER_PID 2>/dev/null

# 显示Reader输出
echo ""
echo "=========================================="
echo "  Python Reader 输出："
echo "=========================================="
cat /tmp/reader_output.log

echo ""
echo "=========================================="
echo "  测试完成！"
echo "=========================================="
echo ""
echo "查看完整日志："
echo "  cat /tmp/reader_output.log"
echo ""

