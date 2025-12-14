#!/bin/bash

###############################################################################
# WebSocket服务器编译脚本（WSL/Linux）
# 
# 功能：
# - 自动检查并安装依赖
# - 编译WebSocket服务器
# - 运行服务器
###############################################################################

set -e  # 遇到错误立即退出

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║       WebSocket服务器编译脚本（Vue前端连接）                  ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 检查是否在WSL/Linux环境
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}错误: 此脚本需要在WSL或Linux环境中运行${NC}"
    exit 1
fi

# 切换到cpp目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_DIR="$(dirname "$SCRIPT_DIR")"
cd "$CPP_DIR"

echo -e "${YELLOW}[1/5] 检查依赖...${NC}"

# 检查编译器
if ! command -v g++ &> /dev/null; then
    echo -e "${RED}错误: 未找到 g++ 编译器${NC}"
    echo "请运行: sudo apt update && sudo apt install build-essential"
    exit 1
fi

GCC_VERSION=$(g++ --version | head -n1)
echo "✓ 编译器: $GCC_VERSION"

# 检查Boost库
if ! ldconfig -p | grep -q libboost_system; then
    echo -e "${YELLOW}未找到Boost库，正在安装...${NC}"
    sudo apt update
    sudo apt install -y libboost-all-dev
fi

BOOST_VERSION=$(dpkg -s libboost-dev 2>/dev/null | grep Version || echo "未知版本")
echo "✓ Boost: $BOOST_VERSION"

# 检查nlohmann/json
if [ ! -f "external/include/nlohmann/json.hpp" ]; then
    echo -e "${YELLOW}未找到nlohmann/json，正在下载...${NC}"
    mkdir -p external/include/nlohmann
    wget -q https://github.com/nlohmann/json/releases/download/v3.11.3/json.hpp \
         -O external/include/nlohmann/json.hpp
    echo "✓ nlohmann/json 已下载"
else
    echo "✓ nlohmann/json 已存在"
fi

echo ""
echo -e "${YELLOW}[2/5] 编译WebSocket服务器...${NC}"

# 编译选项
CXX="g++"
CXXFLAGS="-std=c++17 -O3 -Wall -Wextra"
INCLUDES="-I./core -I./external/include -I/usr/include"
LIBS="-lboost_system -lpthread"
SOURCE="examples/websocket_vue_example.cpp"
OUTPUT="examples/ws_vue_server"

# 编译命令
echo "编译命令:"
echo "$CXX $CXXFLAGS $INCLUDES $SOURCE -o $OUTPUT $LIBS"
echo ""

$CXX $CXXFLAGS $INCLUDES $SOURCE -o $OUTPUT $LIBS

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 编译成功！${NC}"
else
    echo -e "${RED}✗ 编译失败${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[3/5] 检查可执行文件...${NC}"
ls -lh $OUTPUT
file $OUTPUT

echo ""
echo -e "${YELLOW}[4/5] 测试运行（3秒）...${NC}"
timeout 3s $OUTPUT || true
echo ""

echo -e "${GREEN}[5/5] 完成！${NC}"
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  编译完成                                                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  可执行文件: $OUTPUT"
echo "║                                                              ║"
echo "║  启动服务器:                                                 ║"
echo "║    $OUTPUT"
echo "║                                                              ║"
echo "║  或在后台运行:                                               ║"
echo "║    nohup $OUTPUT > ws_server.log 2>&1 &"
echo "║                                                              ║"
echo "║  前端连接地址:                                               ║"
echo "║    ws://localhost:8001                                      ║"
echo "║                                                              ║"
echo "║  如果在WSL中，Windows浏览器需要用:                           ║"
echo "║    ws://$(hostname -I | awk '{print $1}'):8001"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${YELLOW}提示: 按任意键启动服务器，或按 Ctrl+C 退出${NC}"
read -n 1 -s

echo ""
echo -e "${GREEN}启动服务器...${NC}"
$OUTPUT

