/**
 * @file trading_server_full.cpp
 * @brief 完整实盘交易服务器 - 支持所有OKX接口
 * 
 * 功能：
 * 1. WebSocket 行情
 *    - trades (多币种)
 *    - K线 (多币种、多周期)
 *    - 订单状态推送
 *    - 账户/持仓更新推送
 * 
 * 2. REST API 交易
 *    - 下单（现货/合约）
 *    - 批量下单
 *    - 撤单/批量撤单
 *    - 修改订单
 * 
 * 3. REST API 查询
 *    - 账户余额
 *    - 持仓信息
 *    - 未成交订单
 * 
 * 架构：
 *   OKX 交易所
 *       │
 *       │ WebSocket (行情/订单推送)
 *       │ REST API (交易/查询)
 *       ▼
 *   ┌───────────────────────────────────┐
 *   │      Trading Server (C++)         │
 *   │  ┌─────────────────────────────┐  │
 *   │  │ WebSocket Client            │  │
 *   │  │ - Public (trades)           │  │
 *   │  │ - Business (K线)            │  │
 *   │  │ - Private (订单/账户)        │  │
 *   │  └─────────────────────────────┘  │
 *   │  ┌─────────────────────────────┐  │
 *   │  │ ZmqServer                   │  │
 *   │  │ - PUB 行情 (trades/K线)     │  │
 *   │  │ - PULL 订单请求             │  │
 *   │  │ - PUB 订单回报              │  │
 *   │  │ - REP 查询响应              │  │
 *   │  │ - PULL 订阅管理             │  │
 *   │  └─────────────────────────────┘  │
 *   └───────────────────────────────────┘
 *       │
 *       │ IPC (Unix Socket, 30-100μs)
 *       ▼
 *   策略进程 (Python)
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include <iostream>
#include <thread>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iomanip>
#include <cstring>
#include <mutex>
#include <set>
#include <map>

// Linux CPU 亲和性
#ifdef __linux__
#include <sched.h>
#include <pthread.h>
#if __has_include(<numa.h>)
#include <numa.h>
#define HAS_NUMA 1
#else
#define HAS_NUMA 0
#endif
#endif

#include "zmq_server.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::server;
using namespace trading::okx;
using namespace std::chrono;

// ============================================================
// 全局配置
// ============================================================

namespace Config {
    // API 凭证（可通过环境变量覆盖）
    std::string api_key;
    std::string secret_key;
    std::string passphrase;
    bool is_testnet = true;  // 默认模拟盘
    
    // 初始订阅的交易对
    std::vector<std::string> default_symbols = {"BTC-USDT", "ETH-USDT"};
    
    // 合约交易对
    std::vector<std::string> swap_symbols = {"BTC-USDT-SWAP", "ETH-USDT-SWAP"};
}

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};

// 统计
std::atomic<uint64_t> g_trade_count{0};
std::atomic<uint64_t> g_kline_count{0};
std::atomic<uint64_t> g_order_count{0};
std::atomic<uint64_t> g_order_success{0};
std::atomic<uint64_t> g_order_failed{0};
std::atomic<uint64_t> g_query_count{0};

// 订阅管理
std::mutex g_sub_mutex;
std::set<std::string> g_subscribed_trades;  // 已订阅的 trades 交易对
std::map<std::string, std::set<std::string>> g_subscribed_klines;  // 已订阅的 K线 {symbol: {intervals}}

// WebSocket 客户端指针
std::unique_ptr<OKXWebSocket> g_ws_public;
std::unique_ptr<OKXWebSocket> g_ws_business;
std::unique_ptr<OKXWebSocket> g_ws_private;

// ============================================================
// 多账户管理
// ============================================================

/**
 * @brief 账户信息结构
 */
struct AccountInfo {
    std::string api_key;
    std::string secret_key;
    std::string passphrase;
    bool is_testnet;
    std::unique_ptr<OKXRestAPI> api;  // 该账户的 REST API 客户端
    int64_t register_time;            // 注册时间
    
    AccountInfo() : is_testnet(true), register_time(0) {}
    
    AccountInfo(const std::string& key, const std::string& secret, 
                const std::string& pass, bool testnet)
        : api_key(key), secret_key(secret), passphrase(pass), is_testnet(testnet) {
        register_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        // 创建 API 客户端
        api = std::make_unique<OKXRestAPI>(api_key, secret_key, passphrase, is_testnet);
    }
};

// 策略账户映射：strategy_id -> AccountInfo
std::mutex g_accounts_mutex;
std::map<std::string, std::shared_ptr<AccountInfo>> g_strategy_accounts;

// 默认账户（用于未注册账户的策略）
std::shared_ptr<AccountInfo> g_default_account;

/**
 * @brief 获取策略对应的 API 客户端
 * 
 * @param strategy_id 策略ID
 * @return OKXRestAPI* 对应的 API 客户端，如果策略未注册则返回默认账户的 API
 */
OKXRestAPI* get_api_for_strategy(const std::string& strategy_id) {
    std::lock_guard<std::mutex> lock(g_accounts_mutex);
    
    auto it = g_strategy_accounts.find(strategy_id);
    if (it != g_strategy_accounts.end() && it->second && it->second->api) {
        return it->second->api.get();
    }
    
    // 使用默认账户
    if (g_default_account && g_default_account->api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册账户，使用默认账户\n";
        return g_default_account->api.get();
    }
    
    return nullptr;
}

/**
 * @brief 注册策略账户
 * 
 * @param strategy_id 策略ID
 * @param api_key API Key
 * @param secret_key Secret Key
 * @param passphrase Passphrase
 * @param is_testnet 是否模拟盘
 * @return bool 注册成功返回 true
 */
bool register_strategy_account(const std::string& strategy_id,
                                const std::string& api_key,
                                const std::string& secret_key,
                                const std::string& passphrase,
                                bool is_testnet) {
    std::lock_guard<std::mutex> lock(g_accounts_mutex);
    
    // 检查是否已注册
    auto it = g_strategy_accounts.find(strategy_id);
    if (it != g_strategy_accounts.end()) {
        std::cout << "[账户] 策略 " << strategy_id << " 已注册，更新账户信息\n";
    }
    
    // 创建新的账户信息
    auto account = std::make_shared<AccountInfo>(api_key, secret_key, passphrase, is_testnet);
    g_strategy_accounts[strategy_id] = account;
    
    std::cout << "[账户] ✓ 策略 " << strategy_id << " 注册成功"
              << " | 模式: " << (is_testnet ? "模拟盘" : "实盘")
              << " | API Key: " << api_key.substr(0, 8) << "..."
              << "\n";
    
    return true;
}

/**
 * @brief 注销策略账户
 */
bool unregister_strategy_account(const std::string& strategy_id) {
    std::lock_guard<std::mutex> lock(g_accounts_mutex);
    
    auto it = g_strategy_accounts.find(strategy_id);
    if (it != g_strategy_accounts.end()) {
        g_strategy_accounts.erase(it);
        std::cout << "[账户] ✓ 策略 " << strategy_id << " 已注销\n";
        return true;
    }
    
    std::cout << "[账户] 策略 " << strategy_id << " 未找到\n";
    return false;
}

/**
 * @brief 获取已注册的策略数量
 */
size_t get_registered_strategy_count() {
    std::lock_guard<std::mutex> lock(g_accounts_mutex);
    return g_strategy_accounts.size();
}

// ============================================================
// CPU 亲和性
// ============================================================

bool pin_thread_to_cpu(int cpu_id) {
#ifdef __linux__
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu_id, &cpuset);
    
    int result = pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    if (result == 0) {
        std::cout << "[绑核] 线程已绑定到 CPU " << cpu_id << std::endl;
        return true;
    }
    return false;
#else
    return false;
#endif
}

bool set_realtime_priority(int priority = 50) {
#ifdef __linux__
    struct sched_param param;
    param.sched_priority = priority;
    return pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) == 0;
#else
    return false;
#endif
}

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
    
    // ⚠️ 关键1：设置 CURL 中断标志，中断所有正在进行的 HTTP 请求
    set_curl_abort_flag(true);
    
    // ⚠️ 关键2：断开 WebSocket 连接，中断 ASIO 事件循环
    if (g_ws_public) {
        g_ws_public->disconnect();
    }
    if (g_ws_business) {
        g_ws_business->disconnect();
    }
    if (g_ws_private) {
        g_ws_private->disconnect();
    }
}

// ============================================================
// 订单处理
// ============================================================

void process_place_order(ZmqServer& server, const nlohmann::json& order) {
    g_order_count++;
    
    // 记录接收时间
    auto recv_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    
    std::string strategy_id = order.value("strategy_id", "unknown");
    std::string client_order_id = order.value("client_order_id", "");
    std::string symbol = order.value("symbol", "BTC-USDT");
    std::string side = order.value("side", "buy");
    std::string order_type = order.value("order_type", "limit");
    double price = order.value("price", 0.0);
    double quantity = order.value("quantity", 0.0);
    std::string td_mode = order.value("td_mode", "cash");
    std::string pos_side = order.value("pos_side", "");
    std::string tgt_ccy = order.value("tgt_ccy", "");
    
<<<<<<< HEAD
=======
    std::cout << "[下单] " << strategy_id << " | " << symbol 
              << " | " << side << " " << order_type
              << " | 数量: " << quantity << "\n";
    
    // 🔑 关键：获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        std::string error_msg = "策略 " + strategy_id + " 未注册账户，且无默认账户";
        std::cout << "[下单] ✗ " << error_msg << "\n";
        g_order_failed++;
        
        nlohmann::json report = make_order_report(
            strategy_id, client_order_id, "", symbol,
            "rejected", price, quantity, 0.0, error_msg
        );
        server.publish_report(report);
        return;
    }
    
>>>>>>> a0dfaf1ceeb7cfff3e133dc759230552393f69f6
    bool success = false;
    std::string exchange_order_id;
    std::string error_msg;
    
    try {
        PlaceOrderRequest req;
        req.inst_id = symbol;
        req.td_mode = td_mode;
        req.side = side;
        req.ord_type = order_type;
        req.sz = std::to_string(quantity);
        if (price > 0) req.px = std::to_string(price);
        if (!pos_side.empty()) req.pos_side = pos_side;
        if (!tgt_ccy.empty()) req.tgt_ccy = tgt_ccy;
        if (!client_order_id.empty()) req.cl_ord_id = client_order_id;
        
<<<<<<< HEAD
        // 记录发送给OKX的时间
        auto send_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        std::cout << "[服务器→OKX] 时间戳: " << send_ns << " ns | 订单ID: " << client_order_id 
                  << " | 延迟: " << (send_ns - recv_ns) / 1000 << " μs\n";
        
        auto response = api.place_order_advanced(req);
=======
        auto response = api->place_order_advanced(req);
>>>>>>> a0dfaf1ceeb7cfff3e133dc759230552393f69f6
        
        // 记录收到OKX响应的时间
        auto resp_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        
        if (response.is_success()) {
            success = true;
            exchange_order_id = response.ord_id;
            g_order_success++;
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id 
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✓\n";
        } else {
            error_msg = response.s_msg.empty() ? response.msg : response.s_msg;
            g_order_failed++;
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id 
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✗ " << error_msg << "\n";
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
        g_order_failed++;
    }
    
    nlohmann::json report = make_order_report(
        strategy_id, client_order_id, exchange_order_id, symbol,
        success ? "accepted" : "rejected",
        price, quantity, 0.0, error_msg
    );
    server.publish_report(report);
}

void process_batch_orders(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string batch_id = request.value("batch_id", "");
    
    std::cout << "[批量下单] " << strategy_id << " | " << batch_id << "\n";
    
    // 获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", "策略未注册账户"}, {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }
    
    if (!request.contains("orders") || !request["orders"].is_array()) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", "无效的订单数组"}, {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }
    
    std::vector<PlaceOrderRequest> orders;
    for (const auto& ord : request["orders"]) {
        PlaceOrderRequest req;
        req.inst_id = ord.value("symbol", "BTC-USDT-SWAP");
        req.td_mode = ord.value("td_mode", "cross");
        req.side = ord.value("side", "buy");
        req.ord_type = ord.value("order_type", "limit");
        req.sz = std::to_string(ord.value("quantity", 0.0));
        
        double px = ord.value("price", 0.0);
        if (px > 0) req.px = std::to_string(px);
        
        req.pos_side = ord.value("pos_side", "");
        req.cl_ord_id = ord.value("client_order_id", "");
        orders.push_back(req);
    }
    
    try {
        auto response = api->place_batch_orders(orders);
        
        int success_count = 0, fail_count = 0;
        nlohmann::json results = nlohmann::json::array();
        
        if (response.contains("data") && response["data"].is_array()) {
            for (const auto& data : response["data"]) {
                bool ok = data["sCode"] == "0";
                if (ok) success_count++; else fail_count++;
                
                results.push_back({
                    {"client_order_id", data.value("clOrdId", "")},
                    {"exchange_order_id", data.value("ordId", "")},
                    {"status", ok ? "accepted" : "rejected"},
                    {"error_msg", data.value("sMsg", "")}
                });
            }
        }
        
        g_order_count += orders.size();
        g_order_success += success_count;
        g_order_failed += fail_count;
        
        std::cout << "[批量下单] 成功: " << success_count << " 失败: " << fail_count << "\n";
        
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id},
            {"status", fail_count == 0 ? "accepted" : (success_count > 0 ? "partial" : "rejected")},
            {"results", results}, {"success_count", success_count}, {"fail_count", fail_count},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        
    } catch (const std::exception& e) {
        nlohmann::json report = {
            {"type", "batch_report"}, {"strategy_id", strategy_id},
            {"batch_id", batch_id}, {"status", "rejected"},
            {"error_msg", std::string("异常: ") + e.what()},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
    }
}

void process_cancel_order(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string symbol = request.value("symbol", "");
    std::string order_id = request.value("order_id", "");
    std::string client_order_id = request.value("client_order_id", "");
    
    std::cout << "[撤单] " << strategy_id << " | " << symbol 
              << " | " << (order_id.empty() ? client_order_id : order_id) << "\n";
    
    // 获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "cancel_report"}, {"strategy_id", strategy_id},
            {"order_id", order_id}, {"client_order_id", client_order_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }
    
    bool success = false;
    std::string error_msg;
    
    try {
        auto response = api->cancel_order(symbol, order_id, client_order_id);
        
        if (response["code"] == "0" && response.contains("data") && !response["data"].empty()) {
            auto& data = response["data"][0];
            if (data["sCode"] == "0") {
                success = true;
                std::cout << "[撤单] ✓ 成功\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
            }
        } else {
            error_msg = response.value("msg", "API error");
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
    }
    
    if (!success) std::cout << "[撤单] ✗ " << error_msg << "\n";
    
    nlohmann::json report = {
        {"type", "cancel_report"}, {"strategy_id", strategy_id},
        {"order_id", order_id}, {"client_order_id", client_order_id},
        {"status", success ? "cancelled" : "rejected"},
        {"error_msg", error_msg}, {"timestamp", current_timestamp_ms()}
    };
    server.publish_report(report);
}

void process_batch_cancel(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string symbol = request.value("symbol", "");
    
    // 获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }
    
    std::vector<std::string> order_ids;
    if (request.contains("order_ids") && request["order_ids"].is_array()) {
        for (const auto& id : request["order_ids"]) {
            order_ids.push_back(id.get<std::string>());
        }
    }
    
    std::cout << "[批量撤单] " << strategy_id << " | " << symbol 
              << " | " << order_ids.size() << "个订单\n";
    
    try {
        auto response = api->cancel_batch_orders(order_ids, symbol);
        
        int success_count = 0, fail_count = 0;
        nlohmann::json results = nlohmann::json::array();
        
        if (response.contains("data") && response["data"].is_array()) {
            for (const auto& data : response["data"]) {
                bool ok = data["sCode"] == "0";
                if (ok) success_count++; else fail_count++;
                
                results.push_back({
                    {"order_id", data.value("ordId", "")},
                    {"status", ok ? "cancelled" : "rejected"},
                    {"error_msg", data.value("sMsg", "")}
                });
            }
        }
        
        std::cout << "[批量撤单] 成功: " << success_count << " 失败: " << fail_count << "\n";
        
        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"symbol", symbol}, {"results", results},
            {"success_count", success_count}, {"fail_count", fail_count},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        
    } catch (const std::exception& e) {
        nlohmann::json report = {
            {"type", "batch_cancel_report"}, {"strategy_id", strategy_id},
            {"status", "rejected"}, {"error_msg", std::string("异常: ") + e.what()},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
    }
}

void process_amend_order(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string symbol = request.value("symbol", "");
    std::string order_id = request.value("order_id", "");
    std::string client_order_id = request.value("client_order_id", "");
    std::string new_px = request.value("new_price", "");
    std::string new_sz = request.value("new_quantity", "");
    
    std::cout << "[修改订单] " << strategy_id << " | " << symbol << "\n";
    
    // 获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        nlohmann::json report = {
            {"type", "amend_report"}, {"strategy_id", strategy_id},
            {"order_id", order_id}, {"client_order_id", client_order_id},
            {"status", "rejected"}, {"error_msg", "策略未注册账户"},
            {"timestamp", current_timestamp_ms()}
        };
        server.publish_report(report);
        return;
    }
    
    bool success = false;
    std::string error_msg;
    
    try {
        auto response = api->amend_order(symbol, order_id, client_order_id, new_sz, new_px);
        
        if (response["code"] == "0" && response.contains("data") && !response["data"].empty()) {
            auto& data = response["data"][0];
            if (data["sCode"] == "0") {
                success = true;
                std::cout << "[修改订单] ✓ 成功\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
            }
        } else {
            error_msg = response.value("msg", "API error");
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
    }
    
    if (!success) std::cout << "[修改订单] ✗ " << error_msg << "\n";
    
    nlohmann::json report = {
        {"type", "amend_report"}, {"strategy_id", strategy_id},
        {"order_id", order_id}, {"client_order_id", client_order_id},
        {"status", success ? "amended" : "rejected"},
        {"error_msg", error_msg}, {"timestamp", current_timestamp_ms()}
    };
    server.publish_report(report);
}

/**
 * @brief 处理账户注册请求
 */
void process_register_account(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "");
    std::string api_key = request.value("api_key", "");
    std::string secret_key = request.value("secret_key", "");
    std::string passphrase = request.value("passphrase", "");
    bool is_testnet = request.value("is_testnet", true);
    
    std::cout << "[账户注册] 策略: " << strategy_id << "\n";
    
    nlohmann::json report;
    report["type"] = "register_report";
    report["strategy_id"] = strategy_id;
    report["timestamp"] = current_timestamp_ms();
    
    if (strategy_id.empty() || api_key.empty() || secret_key.empty() || passphrase.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少必要参数 (strategy_id, api_key, secret_key, passphrase)";
        std::cout << "[账户注册] ✗ 参数不完整\n";
    } else {
        bool success = register_strategy_account(strategy_id, api_key, secret_key, passphrase, is_testnet);
        if (success) {
            report["status"] = "registered";
            report["error_msg"] = "";
        } else {
            report["status"] = "rejected";
            report["error_msg"] = "注册失败";
        }
    }
    
    server.publish_report(report);
}

/**
 * @brief 处理账户注销请求
 */
void process_unregister_account(ZmqServer& server, const nlohmann::json& request) {
    std::string strategy_id = request.value("strategy_id", "");
    
    std::cout << "[账户注销] 策略: " << strategy_id << "\n";
    
    nlohmann::json report;
    report["type"] = "unregister_report";
    report["strategy_id"] = strategy_id;
    report["timestamp"] = current_timestamp_ms();
    
    if (strategy_id.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少 strategy_id";
    } else {
        bool success = unregister_strategy_account(strategy_id);
        report["status"] = success ? "unregistered" : "rejected";
        report["error_msg"] = success ? "" : "策略未找到";
    }
    
    server.publish_report(report);
}

// 订单请求路由
void process_order_request(ZmqServer& server, const nlohmann::json& request) {
    std::string type = request.value("type", "order_request");
    
    if (type == "order_request") {
        process_place_order(server, request);
    } else if (type == "batch_order_request") {
        process_batch_orders(server, request);
    } else if (type == "cancel_request") {
        process_cancel_order(server, request);
    } else if (type == "batch_cancel_request") {
        process_batch_cancel(server, request);
    } else if (type == "amend_request") {
        process_amend_order(server, request);
    } else if (type == "register_account") {
        process_register_account(server, request);
    } else if (type == "unregister_account") {
        process_unregister_account(server, request);
    } else {
        std::cout << "[订单] 未知请求类型: " << type << "\n";
    }
}

// ============================================================
// 查询处理
// ============================================================

nlohmann::json handle_query(const nlohmann::json& request) {
    g_query_count++;
    
    std::string strategy_id = request.value("strategy_id", "unknown");
    std::string query_type = request.value("query_type", "");
    auto params = request.value("params", nlohmann::json::object());
    
    std::cout << "[查询] 策略: " << strategy_id << " | 类型: " << query_type << "\n";
    
    // 获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        return {{"code", -1}, {"error", "策略 " + strategy_id + " 未注册账户"}};
    }
    
    try {
        if (query_type == "account" || query_type == "balance") {
            // 账户余额查询
            std::string ccy = params.value("currency", "");
            auto result = api->get_account_balance(ccy);
            return {{"code", 0}, {"query_type", query_type}, {"data", result}};
        }
        else if (query_type == "positions") {
            // 持仓查询
            std::string inst_type = params.value("inst_type", "SWAP");
            std::string symbol = params.value("symbol", "");
            auto result = api->get_positions(inst_type, symbol);
            return {{"code", 0}, {"query_type", query_type}, {"data", result}};
        }
        else if (query_type == "pending_orders" || query_type == "orders") {
            // 未成交订单查询
            std::string inst_type = params.value("inst_type", "SPOT");
            std::string symbol = params.value("symbol", "");
            auto result = api->get_pending_orders(inst_type, symbol);
            return {{"code", 0}, {"query_type", query_type}, {"data", result}};
        }
        else if (query_type == "order") {
            // 单个订单查询
            std::string symbol = params.value("symbol", "");
            std::string order_id = params.value("order_id", "");
            std::string client_order_id = params.value("client_order_id", "");
            auto result = api->get_order(symbol, order_id, client_order_id);
            return {{"code", 0}, {"query_type", query_type}, {"data", result}};
        }
        else if (query_type == "instruments") {
            // 产品信息查询
            std::string inst_type = params.value("inst_type", "SPOT");
            auto result = api->get_account_instruments(inst_type);
            return {{"code", 0}, {"query_type", query_type}, {"data", result}};
        }
        else if (query_type == "registered_accounts") {
            // 查询已注册的策略数量
            return {{"code", 0}, {"query_type", query_type}, 
                    {"count", get_registered_strategy_count()}};
        }
        else {
            return {{"code", -1}, {"error", "未知查询类型: " + query_type}};
        }
    } catch (const std::exception& e) {
        return {{"code", -1}, {"error", std::string("查询异常: ") + e.what()}};
    }
}

// ============================================================
// 订阅管理
// ============================================================

void handle_subscription(const nlohmann::json& request) {
    std::string action = request.value("action", "subscribe");
    std::string channel = request.value("channel", "");
    std::string symbol = request.value("symbol", "");
    std::string interval = request.value("interval", "1m");
    
    std::cout << "[订阅] " << action << " | " << channel << " | " << symbol << "\n";
    
    std::lock_guard<std::mutex> lock(g_sub_mutex);
    
    if (channel == "trades") {
        if (action == "subscribe" && g_ws_public) {
            if (g_subscribed_trades.find(symbol) == g_subscribed_trades.end()) {
                g_ws_public->subscribe_trades(symbol);
                g_subscribed_trades.insert(symbol);
                std::cout << "[订阅] trades: " << symbol << " ✓\n";
            }
        } else if (action == "unsubscribe" && g_ws_public) {
            if (g_subscribed_trades.find(symbol) != g_subscribed_trades.end()) {
                g_ws_public->unsubscribe_trades(symbol);
                g_subscribed_trades.erase(symbol);
                std::cout << "[取消订阅] trades: " << symbol << " ✓\n";
            }
        }
    }
    else if (channel == "kline" || channel == "candle") {
        if (action == "subscribe" && g_ws_business) {
            g_ws_business->subscribe_kline(symbol, interval);
            g_subscribed_klines[symbol].insert(interval);
            std::cout << "[订阅] K线: " << symbol << " " << interval << " ✓\n";
        } else if (action == "unsubscribe" && g_ws_business) {
            g_ws_business->unsubscribe_kline(symbol, interval);
            g_subscribed_klines[symbol].erase(interval);
            std::cout << "[取消订阅] K线: " << symbol << " " << interval << " ✓\n";
        }
    }
}

// ============================================================
// WebSocket 回调设置
// ============================================================

void setup_websocket_callbacks(ZmqServer& zmq_server) {
    // Trades 回调（公共频道）
    if (g_ws_public) {
        g_ws_public->set_trade_callback([&zmq_server](const TradeData::Ptr& trade) {
            g_trade_count++;
            
            nlohmann::json msg = {
                {"type", "trade"},
                {"symbol", trade->symbol()},
                {"trade_id", trade->trade_id()},
                {"price", trade->price()},
                {"quantity", trade->quantity()},
                {"side", trade->side().value_or("")},
                {"timestamp", trade->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };
            
            zmq_server.publish_ticker(msg);
        });
    }
    
    // K线回调（业务频道）
    if (g_ws_business) {
        g_ws_business->set_kline_callback([&zmq_server](const KlineData::Ptr& kline) {
            g_kline_count++;
            
            nlohmann::json msg = {
                {"type", "kline"},
                {"symbol", kline->symbol()},
                {"interval", kline->interval()},
                {"open", kline->open()},
                {"high", kline->high()},
                {"low", kline->low()},
                {"close", kline->close()},
                {"volume", kline->volume()},
                {"timestamp", kline->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };
            
            zmq_server.publish_kline(msg);
        });
    }
    
    // 订单推送回调（私有频道）
    if (g_ws_private) {
        g_ws_private->set_order_callback([&zmq_server](const Order::Ptr& order) {
            nlohmann::json msg = {
                {"type", "order_update"},
                {"symbol", order->symbol()},
                {"exchange_order_id", order->exchange_order_id()},
                {"client_order_id", order->client_order_id()},
                {"side", order->side() == OrderSide::BUY ? "buy" : "sell"},
                {"order_type", order->order_type() == OrderType::MARKET ? "market" : "limit"},
                {"price", order->price()},
                {"quantity", order->quantity()},
                {"filled_quantity", order->filled_quantity()},
                {"status", order_state_to_string(order->state())},
                {"timestamp", current_timestamp_ms()},
                {"timestamp_ns", current_timestamp_ns()}
            };
            
            zmq_server.publish_report(msg);
        });
        
        // 账户更新回调
        g_ws_private->set_account_callback([&zmq_server](const nlohmann::json& acc) {
            nlohmann::json msg = {
                {"type", "account_update"},
                {"data", acc},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);
        });
        
        // 持仓更新回调
        g_ws_private->set_position_callback([&zmq_server](const nlohmann::json& pos) {
            nlohmann::json msg = {
                {"type", "position_update"},
                {"data", pos},
                {"timestamp", current_timestamp_ms()}
            };
            zmq_server.publish_report(msg);
        });
    }
}

// ============================================================
// 订单处理线程
// ============================================================

void order_thread(ZmqServer& server) {
    std::cout << "[订单线程] 启动\n";
    pin_thread_to_cpu(2);
    set_realtime_priority(49);
    
    while (g_running.load()) {
        nlohmann::json order;
        while (server.recv_order_json(order)) {
            process_order_request(server, order);
        }
        std::this_thread::sleep_for(microseconds(100));
    }
    
    std::cout << "[订单线程] 停止\n";
}

// ============================================================
// 查询处理线程
// ============================================================

void query_thread(ZmqServer& server) {
    std::cout << "[查询线程] 启动\n";
    pin_thread_to_cpu(3);
    
    server.set_query_callback([](const nlohmann::json& request) -> nlohmann::json {
        return handle_query(request);
    });
    
    while (g_running.load()) {
        server.poll_queries();
        std::this_thread::sleep_for(milliseconds(1));
    }
    
    std::cout << "[查询线程] 停止\n";
}

// ============================================================
// 订阅管理线程
// ============================================================

void subscription_thread(ZmqServer& server) {
    std::cout << "[订阅线程] 启动\n";
    
    server.set_subscribe_callback([](const nlohmann::json& request) {
        handle_subscription(request);
    });
    
    while (g_running.load()) {
        server.poll_subscriptions();
        std::this_thread::sleep_for(milliseconds(10));
    }
    
    std::cout << "[订阅线程] 停止\n";
}

// ============================================================
// 加载配置
// ============================================================

void load_config() {
    // 从环境变量读取
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
    Config::is_testnet = testnet_env ? (std::string(testnet_env) == "1") : true;
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "    Sequence 实盘交易服务器 (Full)\n";
    std::cout << "    支持所有OKX接口\n";
    std::cout << "========================================\n\n";
    
    // 加载配置
    load_config();
    
    // CPU 绑核
    pin_thread_to_cpu(1);
    set_realtime_priority(50);
    
    // 信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    std::cout << "[配置] 交易模式: " << (Config::is_testnet ? "模拟盘" : "实盘") << "\n";
    
    // ========================================
    // 初始化默认账户（用于未注册策略）
    // ========================================
    g_default_account = std::make_shared<AccountInfo>(
        Config::api_key, Config::secret_key, Config::passphrase, Config::is_testnet
    );
    std::cout << "[初始化] 默认账户 ✓ (API Key: " << Config::api_key.substr(0, 8) << "...)\n";
    std::cout << "[提示] 策略可通过 register_account 消息注册自己的账户\n";
    
    // ========================================
    // 初始化 ZeroMQ
    // ========================================
    ZmqServer zmq_server;
    if (!zmq_server.start()) {
        std::cerr << "[错误] ZeroMQ 服务启动失败\n";
        return 1;
    }
    
    std::cout << "[初始化] ZeroMQ 通道:\n";
    std::cout << "  - 行情: " << IpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 订单: " << IpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << IpcAddresses::REPORT << "\n";
    std::cout << "  - 查询: " << IpcAddresses::QUERY << "\n";
    std::cout << "  - 订阅: " << IpcAddresses::SUBSCRIBE << "\n";
    
    // ========================================
    // 初始化 WebSocket
    // ========================================
    std::cout << "\n[初始化] OKX WebSocket...\n";
    
    // 公共频道 (trades)
    g_ws_public = create_public_ws(Config::is_testnet);
    
    // 业务频道 (K线)
    g_ws_business = create_business_ws(Config::is_testnet);
    
    // 私有频道 (订单/账户/持仓)
    g_ws_private = create_private_ws(
        Config::api_key, Config::secret_key, Config::passphrase, Config::is_testnet
    );
    
    // 设置回调
    setup_websocket_callbacks(zmq_server);
    
    // 连接
    if (!g_ws_public->connect()) {
        std::cerr << "[错误] WebSocket Public 连接失败\n";
        return 1;
    }
    std::cout << "[WebSocket] Public ✓\n";
    
    if (!g_ws_business->connect()) {
        std::cerr << "[错误] WebSocket Business 连接失败\n";
        return 1;
    }
    std::cout << "[WebSocket] Business ✓\n";
    
    if (!g_ws_private->connect()) {
        std::cerr << "[警告] WebSocket Private 连接失败，私有功能不可用\n";
    } else {
        g_ws_private->login();
        std::this_thread::sleep_for(seconds(2));
        if (g_ws_private->is_logged_in()) {
            std::cout << "[WebSocket] Private ✓ (已登录)\n";
            
            // 订阅私有频道
            g_ws_private->subscribe_orders("SPOT");
            g_ws_private->subscribe_orders("SWAP");
            g_ws_private->subscribe_account();
            g_ws_private->subscribe_positions("ANY");
        } else {
            std::cout << "[WebSocket] Private (登录失败)\n";
        }
    }
    
    // 订阅默认交易对
    for (const auto& symbol : Config::default_symbols) {
        g_ws_public->subscribe_trades(symbol);
        g_subscribed_trades.insert(symbol);
        std::cout << "[订阅] trades: " << symbol << "\n";
    }
    
    // ========================================
    // 启动工作线程
    // ========================================
    std::thread order_worker(order_thread, std::ref(zmq_server));
    std::thread query_worker(query_thread, std::ref(zmq_server));
    std::thread sub_worker(subscription_thread, std::ref(zmq_server));
    
    // ========================================
    // 主循环
    // ========================================
    std::cout << "\n========================================\n";
    std::cout << "  服务器启动完成！\n";
    std::cout << "  等待策略连接...\n";
    std::cout << "  按 Ctrl+C 停止\n";
    std::cout << "========================================\n\n";
    
    // 主循环：使用更短的 sleep 间隔，以便更快响应 Ctrl+C
    int status_counter = 0;
    while (g_running.load()) {
<<<<<<< HEAD
        std::this_thread::sleep_for(seconds(10));
        // 状态打印已关闭
=======
        std::this_thread::sleep_for(milliseconds(100));
        status_counter++;
        
        // 每 10 秒打印一次状态 (100 * 100ms = 10s)
        if (status_counter >= 100 && g_running.load()) {
            status_counter = 0;
            std::cout << "[状态] Trades: " << g_trade_count
                      << " | K线: " << g_kline_count
                      << " | 订单: " << g_order_count
                      << " (成功: " << g_order_success
                      << ", 失败: " << g_order_failed << ")"
                      << " | 查询: " << g_query_count
                      << " | 注册账户: " << get_registered_strategy_count() << "\n";
        }
>>>>>>> a0dfaf1ceeb7cfff3e133dc759230552393f69f6
    }
    
    // ========================================
    // 清理
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    
    // ⚠️ 注意：WebSocket 已在信号处理器中断开
    // 这里检查并确保断开，以防信号处理器未触发
    std::cout << "[Server] 断开 WebSocket 连接...\n";
    if (g_ws_public && g_ws_public->is_connected()) {
        g_ws_public->disconnect();
    }
    if (g_ws_business && g_ws_business->is_connected()) {
        g_ws_business->disconnect();
    }
    if (g_ws_private && g_ws_private->is_connected()) {
        g_ws_private->disconnect();
    }
    
    // 等待工作线程（现在应该能快速退出，因为 g_running = false）
    std::cout << "[Server] 等待工作线程退出...\n";
    if (order_worker.joinable()) order_worker.join();
    std::cout << "[Server] 订单线程已退出\n";
    if (query_worker.joinable()) query_worker.join();
    std::cout << "[Server] 查询线程已退出\n";
    if (sub_worker.joinable()) sub_worker.join();
    std::cout << "[Server] 订阅线程已退出\n";
    
    // 停止 ZeroMQ
    std::cout << "[Server] 停止 ZeroMQ...\n";
    zmq_server.stop();
    
    // 清理账户
    {
        std::lock_guard<std::mutex> lock(g_accounts_mutex);
        g_strategy_accounts.clear();
        g_default_account.reset();
    }
    
    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "  Trades: " << g_trade_count << " 条\n";
    std::cout << "  K线: " << g_kline_count << " 条\n";
    std::cout << "  订单: " << g_order_count << " 笔\n";
    std::cout << "========================================\n";
    
    return 0;
}

