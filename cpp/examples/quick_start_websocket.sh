#!/bin/bash

###############################################################################
# WebSocket服务器一键启动脚本
# 
# 功能：自动编译并启动WebSocket服务器
###############################################################################

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║        WebSocket服务器一键启动                                ║
║                                                              ║
║        连接地址: ws://localhost:8001                         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPP_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_BIN="$SCRIPT_DIR/ws_vue_server"

# 检查是否已编译
if [ ! -f "$SERVER_BIN" ]; then
    echo -e "${YELLOW}未找到可执行文件，正在编译...${NC}"
    bash "$SCRIPT_DIR/build_websocket_server.sh"
else
    echo -e "${GREEN}✓ 找到可执行文件${NC}"
fi

# 检查端口是否被占用
if netstat -tuln 2>/dev/null | grep -q ":8001 "; then
    echo -e "${RED}错误: 端口8001已被占用！${NC}"
    echo "请停止占用该端口的进程，或修改服务器端口"
    echo ""
    echo "查看占用进程："
    echo "  netstat -tulnp | grep :8001"
    exit 1
fi

echo ""
echo -e "${GREEN}启动服务器...${NC}"
echo ""
echo "提示："
echo "  - 按 Ctrl+C 停止服务器"
echo "  - 或在后台运行: nohup $SERVER_BIN > ws_server.log 2>&1 &"
echo ""

# 启动服务器
exec "$SERVER_BIN"

