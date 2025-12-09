#!/bin/bash

# ============================================
# Web服务启动脚本（Linux）
# ============================================

set -e

echo "=========================================="
echo "  实盘交易管理系统 - Web服务启动"
echo "=========================================="
echo ""

# 激活虚拟环境（如果存在）
if [ -d "venv" ]; then
    echo "激活虚拟环境..."
    source venv/bin/activate
fi

# 检查依赖
echo "[1/3] 检查Python依赖..."
pip list | grep fastapi > /dev/null || {
    echo "未安装依赖，正在安装..."
    pip install -r requirements.txt
}

# 创建日志目录
echo "[2/3] 创建日志目录..."
mkdir -p logs

# 启动服务
echo "[3/3] 启动FastAPI服务..."
echo ""
echo "访问地址: http://localhost:8000"
echo "API文档: http://localhost:8000/docs"
echo "SSE测试: http://localhost:8000/events/stream"
echo ""
echo "按Ctrl+C停止服务"
echo ""

python start.py

