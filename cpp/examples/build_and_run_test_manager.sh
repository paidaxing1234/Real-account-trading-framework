#!/bin/bash

# 账户管理器测试快速编译运行脚本

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  账户管理器测试 - 快速编译运行"
echo "=========================================="
echo ""

# 进入cpp目录
cd "$(dirname "$0")/.."

# 检查是否已经有build目录
if [ ! -d "build" ]; then
    echo "创建build目录..."
    mkdir build
fi

cd build

# 配置CMake（每次都重新配置以确保最新）
echo "配置CMake..."
cmake ..
echo ""

# 编译test_manager
echo "编译 test_manager..."
make test_manager -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
echo ""

# 运行测试
echo "=========================================="
echo "  运行测试"
echo "=========================================="
echo ""

./test_manager

echo ""
echo "=========================================="
echo "  测试完成"
echo "=========================================="
