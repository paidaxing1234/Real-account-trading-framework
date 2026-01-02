#!/bin/bash
#
# 快速编译模拟交易服务器
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="${CPP_DIR}/build"

echo "=========================================="
echo "  编译模拟交易服务器"
echo "=========================================="
echo ""

# 检查依赖
echo "[1/4] 检查依赖..."

# 检查CMake
if ! command -v cmake &> /dev/null; then
    echo "  ✗ cmake 未安装"
    echo "    安装: sudo apt install cmake (Ubuntu) / brew install cmake (macOS)"
    exit 1
fi
echo "  ✓ cmake $(cmake --version | head -1 | awk '{print $3}')"

# 检查编译器
if ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
    echo "  ✗ C++编译器未安装"
    echo "    安装: sudo apt install build-essential (Ubuntu) / xcode-select --install (macOS)"
    exit 1
fi
echo "  ✓ C++编译器"

echo ""

# 创建构建目录
echo "[2/4] 创建构建目录..."
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"
echo "  ✓ ${BUILD_DIR}"
echo ""

# 运行CMake
echo "[3/4] 运行CMake..."
if [ ! -f "CMakeCache.txt" ]; then
    cmake .. -DCMAKE_BUILD_TYPE=Release
else
    echo "  (使用现有CMake配置)"
fi
echo ""

# 编译
echo "[4/4] 编译..."
CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "4")
make papertrading_server -j${CORES}
echo ""

# 检查可执行文件
if [ -f "papertrading_server" ]; then
    echo "=========================================="
    echo "  ✓ 编译成功！"
    echo "=========================================="
    echo ""
    echo "可执行文件: ${BUILD_DIR}/papertrading_server"
    echo ""
    echo "运行方法:"
    echo "  cd ${BUILD_DIR}"
    echo "  ./papertrading_server"
    echo ""
    echo "或指定配置文件:"
    echo "  ./papertrading_server --config ${SCRIPT_DIR}/papertrading_config.json"
    echo ""
else
    echo "=========================================="
    echo "  ✗ 编译失败"
    echo "=========================================="
    exit 1
fi

