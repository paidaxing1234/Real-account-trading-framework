#!/bin/bash
# Sequence API 文档服务器启动脚本

PORT=8000
DOCS_DIR="/home/llx/Real-account-trading-framework/cpp/docs"

echo "========================================"
echo "  Sequence API 文档服务器"
echo "========================================"
echo ""

# 检查端口是否被占用
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "[错误] 端口 $PORT 已被占用"
    echo "占用进程："
    lsof -Pi :$PORT -sTCP:LISTEN
    echo ""
    echo "执行以下命令停止旧进程："
    echo "  kill -9 \$(lsof -t -i:$PORT)"
    exit 1
fi

# 获取本机 IP 地址
IP_ADDR=$(hostname -I | awk '{print $1}')

echo "[信息] 服务器配置："
echo "  - 文档目录: $DOCS_DIR"
echo "  - 监听端口: $PORT"
echo "  - 本机IP: $IP_ADDR"
echo ""

echo "[访问地址]"
echo "  本机访问: http://localhost:$PORT/api-reference.html"
echo "  局域网访问: http://$IP_ADDR:$PORT/api-reference.html"
echo ""

# 检查防火墙
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(sudo ufw status 2>/dev/null | grep -w "$PORT" | grep ALLOW)
    if [ -z "$UFW_STATUS" ]; then
        echo "[提示] 端口 $PORT 未在防火墙中放行"
        echo "  执行以下命令放行端口："
        echo "    sudo ufw allow $PORT/tcp"
        echo ""
    fi
fi

echo "========================================"
echo "  服务器启动中..."
echo "  按 Ctrl+C 停止服务器"
echo "========================================"
echo ""

# 启动 HTTP 服务器
cd "$DOCS_DIR"
python3 -m http.server $PORT --bind 0.0.0.0
