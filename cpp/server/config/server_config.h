/**
 * @file server_config.h
 * @brief 交易服务器全局配置和状态
 */

#pragma once

#include <atomic>
#include <mutex>
#include <set>
#include <map>
#include <string>
#include <vector>
#include <memory>

#include <sys/types.h>
#include <nlohmann/json.hpp>

// 前向声明
namespace trading {
namespace okx {
class OKXWebSocket;
}
namespace binance {
class BinanceWebSocket;
class BinanceRestAPI;
}
namespace core {
class WebSocketServer;
}
namespace auth {
class AuthManager;
struct TokenInfo;
}
class AccountRegistry;
}

namespace trading {
namespace server {

// ============================================================
// 全局配置
// ============================================================

namespace Config {
    // OKX 配置
    extern std::string api_key;
    extern std::string secret_key;
    extern std::string passphrase;
    extern bool is_testnet;
    extern std::vector<std::string> default_symbols;
    extern std::vector<std::string> spot_symbols;
    extern std::vector<std::string> swap_symbols;

    // Binance 配置
    extern std::string binance_api_key;
    extern std::string binance_secret_key;
    extern bool binance_is_testnet;
    extern std::vector<std::string> binance_symbols;
}

// ============================================================
// 全局状态
// ============================================================

extern std::atomic<bool> g_running;

// 统计
extern std::atomic<uint64_t> g_trade_count;
extern std::atomic<uint64_t> g_kline_count;
extern std::atomic<uint64_t> g_orderbook_count;
extern std::atomic<uint64_t> g_funding_rate_count;
extern std::atomic<uint64_t> g_order_count;
extern std::atomic<uint64_t> g_order_success;
extern std::atomic<uint64_t> g_order_failed;
extern std::atomic<uint64_t> g_query_count;

// 订阅管理
extern std::mutex g_sub_mutex;
extern std::set<std::string> g_subscribed_trades;
extern std::map<std::string, std::set<std::string>> g_subscribed_klines;
extern std::map<std::string, std::set<std::string>> g_subscribed_orderbooks;
extern std::set<std::string> g_subscribed_funding_rates;

// WebSocket 客户端指针 - OKX
extern std::unique_ptr<okx::OKXWebSocket> g_ws_public;
extern std::unique_ptr<okx::OKXWebSocket> g_ws_business;
extern std::unique_ptr<okx::OKXWebSocket> g_ws_private;

// WebSocket 客户端指针 - Binance
extern std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_market;
extern std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_depth;   // 深度数据专用连接
extern std::unique_ptr<binance::BinanceWebSocket> g_binance_ws_user;
extern std::unique_ptr<binance::BinanceRestAPI> g_binance_rest_api;

// PaperTrading 状态
extern std::atomic<bool> g_paper_trading_running;
extern pid_t g_paper_trading_pid;
extern std::mutex g_paper_trading_mutex;
extern nlohmann::json g_paper_trading_config;
extern int64_t g_paper_trading_start_time;

// 前端 WebSocket 服务器
extern std::unique_ptr<core::WebSocketServer> g_frontend_server;

// 认证管理器
extern auth::AuthManager g_auth_manager;
extern std::map<int, auth::TokenInfo> g_authenticated_clients;
extern std::mutex g_auth_mutex;

// 账户注册管理器
extern AccountRegistry g_account_registry;

// ============================================================
// 工具函数
// ============================================================

void load_config();

} // namespace server
} // namespace trading
