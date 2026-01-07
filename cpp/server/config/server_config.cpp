/**
 * @file server_config.cpp
 * @brief 交易服务器全局配置和状态实现
 */

#include "server_config.h"
#include "../../adapters/okx/okx_websocket.h"
#include "../../adapters/binance/binance_websocket.h"
#include "../../adapters/binance/binance_rest_api.h"
#include "../../trading/account_registry.h"
#include "../../network/websocket_server.h"
#include "../../network/auth_manager.h"
#include <cstdlib>
#include <iostream>

namespace trading {
namespace server {

// ============================================================
// 全局配置
// ============================================================

namespace Config {
    // OKX 配置
    std::string api_key;
    std::string secret_key;
    std::string passphrase;
    bool is_testnet = false;  // 默认主网
    std::vector<std::string> default_symbols = {};  // 空则动态获取全市场
    std::vector<std::string> spot_symbols = {};     // 空则动态获取全市场
    std::vector<std::string> swap_symbols = {};     // 空则动态获取全市场

    // Binance 配置
    std::string binance_api_key;
    std::string binance_secret_key;
    bool binance_is_testnet = false;  // 使用主网获取行情数据
    std::vector<std::string> binance_symbols = {};  // 空则动态获取全部永续合约
}

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};

// 统计
std::atomic<uint64_t> g_trade_count{0};
std::atomic<uint64_t> g_kline_count{0};
std::atomic<uint64_t> g_orderbook_count{0};
std::atomic<uint64_t> g_funding_rate_count{0};
std::atomic<uint64_t> g_order_count{0};
std::atomic<uint64_t> g_order_success{0};
std::atomic<uint64_t> g_order_failed{0};
std::atomic<uint64_t> g_query_count{0};

// 订阅管理
std::mutex g_sub_mutex;
std::set<std::string> g_subscribed_trades;
std::map<std::string, std::set<std::string>> g_subscribed_klines;
std::map<std::string, std::set<std::string>> g_subscribed_orderbooks;
std::set<std::string> g_subscribed_funding_rates;

// WebSocket 客户端指针 - OKX
std::unique_ptr<okx::OKXWebSocket> g_ws_public;
std::unique_ptr<okx::OKXWebSocket> g_ws_business;
std::unique_ptr<okx::OKXWebSocket> g_ws_private;

// WebSocket 客户端指针 - Binance
std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_market;
std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_depth;   // 深度数据专用连接
std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_user;
std::unique_ptr<binance::BinanceRestAPI> g_binance_rest_api;

// PaperTrading 状态
std::atomic<bool> g_paper_trading_running{false};
pid_t g_paper_trading_pid = -1;
std::mutex g_paper_trading_mutex;
nlohmann::json g_paper_trading_config;
int64_t g_paper_trading_start_time = 0;

// 前端 WebSocket 服务器
std::unique_ptr<core::WebSocketServer> g_frontend_server;

// 认证管理器
auth::AuthManager g_auth_manager;
std::map<int, auth::TokenInfo> g_authenticated_clients;
std::mutex g_auth_mutex;

// 账户注册管理器
AccountRegistry g_account_registry;

// ============================================================
// 工具函数
// ============================================================

void load_config() {
    // OKX 配置
    Config::api_key = std::getenv("OKX_API_KEY")
        ? std::getenv("OKX_API_KEY")
        : "5dee6507-e02d-4bfd-9558-d81783d84cb7";

    Config::secret_key = std::getenv("OKX_SECRET_KEY")
        ? std::getenv("OKX_SECRET_KEY")
        : "9B0E54A9843943331EFD0C40547179C8";

    Config::passphrase = std::getenv("OKX_PASSPHRASE")
        ? std::getenv("OKX_PASSPHRASE")
        : "Wbl20041209..";

    const char* testnet_env = std::getenv("OKX_TESTNET");
    Config::is_testnet = testnet_env ? (std::string(testnet_env) == "1") : false;  // 默认主网

    // Binance 配置
    Config::binance_api_key = std::getenv("BINANCE_API_KEY")
        ? std::getenv("BINANCE_API_KEY")
        : "";

    Config::binance_secret_key = std::getenv("BINANCE_SECRET_KEY")
        ? std::getenv("BINANCE_SECRET_KEY")
        : "";

    const char* binance_testnet_env = std::getenv("BINANCE_TESTNET");
    Config::binance_is_testnet = binance_testnet_env ? (std::string(binance_testnet_env) == "1") : false;  // 默认主网
}

} // namespace server
} // namespace trading
