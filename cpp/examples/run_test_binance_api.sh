#!/usr/bin/env bash
# Quick runner for Binance C++ examples (REST + WebSocket)
#
# What it does:
#   - Enables proxy by default (http://127.0.0.1:7890)
#   - Builds & runs:
#       - test_binance_spot
#       - test_binance_ws_market
#       - test_binance_ws_trade_testnet
#
# Optional env vars:
#   - PROXY_URL: override proxy URL, e.g. http://127.0.0.1:7890
#   - BINANCE_API_KEY / BINANCE_SECRET_KEY: used by some examples (optional)
#
set -euo pipefail

# Script lives in: <repo>/cpp/examples
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CPP_DIR="${REPO_ROOT}/cpp"
BUILD_DIR="${CPP_DIR}/build"

echo "==> Project root: ${REPO_ROOT}"
echo "==> C++ dir     : ${CPP_DIR}"
echo "==> Build dir   : ${BUILD_DIR}"

# ----------------------------------------------------------------------
# Proxy (default ON)
# ----------------------------------------------------------------------
: "${PROXY_URL:=http://127.0.0.1:7890}"
export ALL_PROXY="${PROXY_URL}" all_proxy="${PROXY_URL}"
export HTTPS_PROXY="${PROXY_URL}" https_proxy="${PROXY_URL}"
export HTTP_PROXY="${PROXY_URL}" http_proxy="${PROXY_URL}"
echo "==> Proxy (default ON): ${PROXY_URL}"

# ----------------------------------------------------------------------
# Credentials (optional, do NOT hardcode)
# ----------------------------------------------------------------------
BINANCE_API_KEY="${BINANCE_API_KEY:-}"
BINANCE_SECRET_KEY="${BINANCE_SECRET_KEY:-}"
export BINANCE_API_KEY BINANCE_SECRET_KEY

if [[ -n "${BINANCE_API_KEY}" && -n "${BINANCE_SECRET_KEY}" ]]; then
  echo "==> Binance keys: provided (BINANCE_API_KEY/BINANCE_SECRET_KEY)"
else
  echo "==> Binance keys: not provided"
fi

# ----------------------------------------------------------------------
# Configure & build
# ----------------------------------------------------------------------
mkdir -p "${BUILD_DIR}"
cmake -S "${CPP_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

if command -v nproc >/dev/null 2>&1; then
  JOBS=$(nproc)
else
  JOBS=4
fi

cmake --build "${BUILD_DIR}" --target \
  test_binance_spot \
  test_binance_ws_market \
  test_binance_ws_trade_testnet \
  -- -j"${JOBS}"

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
cd "${BUILD_DIR}"

echo
echo "==> Running: ./test_binance_spot"
./test_binance_spot

echo
echo "==> Running: ./test_binance_ws_trade_testnet  (Ctrl+C to stop or wait 30s)"
./test_binance_ws_trade_testnet

echo
echo "==> Running: ./test_binance_ws_market  (Ctrl+C to stop)"
./test_binance_ws_market


