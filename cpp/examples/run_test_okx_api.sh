#!/usr/bin/env bash
# Quick runner for test_okx_api
# Usage:
#   # optional: set your own credentials/proxy
#   # export API_KEY=xxx SECRET_KEY=xxx PASSPHRASE=xxx
#   # export ALL_PROXY="socks5h://127.0.0.1:7890"
#   ./run_test_okx_api.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CPP_DIR="${ROOT_DIR}/cpp"
BUILD_DIR="${CPP_DIR}/build"

echo "==> Project root: ${ROOT_DIR}"
echo "==> C++ dir     : ${CPP_DIR}"
echo "==> Build dir   : ${BUILD_DIR}"

# ----------------------------------------------------------------------
# Credentials (override with env vars if needed)
# ----------------------------------------------------------------------
: "${API_KEY:=25fc280c-9f3a-4d65-a23d-59d42eeb7d7e}"
: "${SECRET_KEY:=888CC77C745F1B49E75A992F38929992}"
: "${PASSPHRASE:=Sequence2025.}"
export API_KEY SECRET_KEY PASSPHRASE

echo "==> Using API_KEY: ${API_KEY:0:6}*** (override with env API_KEY/SECRET_KEY/PASSPHRASE if needed)"

# ----------------------------------------------------------------------
# Proxy (optional). Inherit from env if already set; otherwise leave empty.
# Supports socks5h/http. Example: export ALL_PROXY='socks5h://127.0.0.1:7890'
# ----------------------------------------------------------------------
PROXY="${ALL_PROXY:-${all_proxy:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}}"
if [[ -n "${PROXY}" ]]; then
  export ALL_PROXY="${PROXY}" HTTPS_PROXY="${PROXY}" https_proxy="${PROXY}"
  export HTTP_PROXY="${PROXY}" http_proxy="${PROXY}"
  echo "==> Using proxy : ${PROXY}"
else
  echo "==> No proxy set. If your network需要代理, export ALL_PROXY/HTTPS_PROXY first."
fi

# ----------------------------------------------------------------------
# Configure & build
# ----------------------------------------------------------------------
mkdir -p "${BUILD_DIR}"
cmake -S "${CPP_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

# Prefer nproc, fallback to sysctl on macOS
if command -v nproc >/dev/null 2>&1; then
  JOBS=$(nproc)
else
  JOBS=$(sysctl -n hw.ncpu)
fi

cmake --build "${BUILD_DIR}" --target test_okx_api -- -j"${JOBS}"

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
cd "${BUILD_DIR}"
echo "==> Running test_okx_api ..."
./test_okx_api


