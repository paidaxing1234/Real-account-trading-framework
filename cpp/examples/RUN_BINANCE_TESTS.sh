#!/usr/bin/env bash
# 一键运行所有已验证通过的 Binance 测试
# 包含：REST 市场数据 + WebSocket 行情推送（测试网）

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CPP_DIR="${REPO_ROOT}/cpp"
BUILD_DIR="${CPP_DIR}/build"

echo "========================================" echo "  Binance 接口测试（已验证）"
echo "========================================"
echo "==> Build dir: ${BUILD_DIR}"

# 代理（默认启用）
: "${PROXY_URL:=http://127.0.0.1:7890}"
export ALL_PROXY="${PROXY_URL}" all_proxy="${PROXY_URL}"
export HTTPS_PROXY="${PROXY_URL}" https_proxy="${PROXY_URL}"
export HTTP_PROXY="${PROXY_URL}" http_proxy="${PROXY_URL}"
echo "==> Proxy: ${PROXY_URL}"

# 配置 + 编译
mkdir -p "${BUILD_DIR}"
cmake -S "${CPP_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

JOBS=$(nproc 2>/dev/null || echo 4)
cmake --build "${BUILD_DIR}" --target \
  test_binance_spot \
  test_binance_ws_trade_testnet \
  test_binance_ws_kline_testnet \
  test_binance_ws_all_market_testnet \
  -- -j"${JOBS}"

cd "${BUILD_DIR}"

echo
echo "========================================" echo "  1️⃣  REST 市场数据测试（无需密钥）"
echo "========================================"
./test_binance_spot

echo
echo "========================================"
echo "  2️⃣  WS 逐笔成交（测试网，30秒）"
echo "========================================"
timeout 30 ./test_binance_ws_trade_testnet || true

echo
echo "========================================"
echo "  3️⃣  WS K线（测试网，70秒）"
echo "========================================"
timeout 70 ./test_binance_ws_kline_testnet || true

echo
echo "========================================"
echo "  4️⃣  WS 全量行情推送（测试网，60秒）"
echo "========================================"
timeout 60 ./test_binance_ws_all_market_testnet || true

echo
echo "========================================"
echo "  ✅ 所有测试完成"
echo "========================================"

