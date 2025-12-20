#!/bin/bash
#
# 编译 strategy_base Python 模块
#
# 使用方法:
#   ./build_strategy_base.sh
#
# 依赖:
#   - Python 3.8+
#   - pybind11: pip install pybind11
#   - ZeroMQ: brew install zeromq cppzmq (macOS) / apt install libzmq3-dev (Ubuntu)
#   - nlohmann_json: brew install nlohmann-json (macOS) / apt install nlohmann-json3-dev (Ubuntu)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

echo "╔════════════════════════════════════════════╗"
echo "║  编译 strategy_base Python 模块           ║"
echo "╚════════════════════════════════════════════╝"
echo

# 检查依赖
echo "[1/4] 检查依赖..."

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "  ✓ ${PYTHON_VERSION}"

# 检查 pybind11
if ! python3 -c "import pybind11" 2>/dev/null; then
    echo "  ✗ pybind11 未安装"
    echo "    安装: pip install pybind11"
    exit 1
fi
echo "  ✓ pybind11"

# 检查 cmake
if ! command -v cmake &> /dev/null; then
    echo "  ✗ cmake 未安装"
    echo "    安装: brew install cmake (macOS) / apt install cmake (Ubuntu)"
    exit 1
fi
echo "  ✓ cmake $(cmake --version | head -1 | awk '{print $3}')"

echo

# 创建构建目录
echo "[2/4] 创建构建目录..."
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"
echo "  ✓ ${BUILD_DIR}"
echo

# 运行 cmake
echo "[3/4] 运行 cmake..."
cmake .. -DCMAKE_BUILD_TYPE=Release
echo

# 编译
echo "[4/4] 编译..."
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)
echo

# 完成
echo "════════════════════════════════════════════"
echo "  编译完成!"
echo "════════════════════════════════════════════"
echo
echo "生成的模块: ${BUILD_DIR}/strategy_base.cpython-*.so"
echo
echo "使用方法:"
echo "  cd ${BUILD_DIR}"
echo "  python3 -c \"from strategy_base import StrategyBase; print('OK')\""
echo
echo "或者将模块复制到策略目录:"
echo "  cp ${BUILD_DIR}/strategy_base.cpython-*.so ${SCRIPT_DIR}/"
echo
echo "然后运行示例策略:"
echo "  cd ${SCRIPT_DIR}"
echo "  python3 example_strategy.py"

