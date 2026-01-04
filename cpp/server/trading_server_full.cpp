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
#include <sys/wait.h>
#include <unistd.h>

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
#include "frontend_handler.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/okx/okx_websocket.h"
#include "../core/account_registry.h"
#include "../core/config_loader.h"
#include "../core/websocket_server.h"
#include "../core/logger.h"

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
std::atomic<uint64_t> g_orderbook_count{0};
std::atomic<uint64_t> g_funding_rate_count{0};
std::atomic<uint64_t> g_order_count{0};
std::atomic<uint64_t> g_order_success{0};
std::atomic<uint64_t> g_order_failed{0};
std::atomic<uint64_t> g_query_count{0};

// 订阅管理
std::mutex g_sub_mutex;
std::set<std::string> g_subscribed_trades;  // 已订阅的 trades 交易对
std::map<std::string, std::set<std::string>> g_subscribed_klines;  // 已订阅的 K线 {symbol: {intervals}}
std::map<std::string, std::set<std::string>> g_subscribed_orderbooks;  // 已订阅的深度 {symbol: {channels}}
std::set<std::string> g_subscribed_funding_rates;  // 已订阅的资金费率交易对

// WebSocket 客户端指针
std::unique_ptr<OKXWebSocket> g_ws_public;
std::unique_ptr<OKXWebSocket> g_ws_business;
std::unique_ptr<OKXWebSocket> g_ws_private;

// PaperTrading 状态
std::atomic<bool> g_paper_trading_running{false};
pid_t g_paper_trading_pid = -1;
std::mutex g_paper_trading_mutex;
nlohmann::json g_paper_trading_config;
int64_t g_paper_trading_start_time = 0;

// 前端 WebSocket 服务器
std::unique_ptr<core::WebSocketServer> g_frontend_server;

// PaperTrading 函数声明
nlohmann::json process_start_paper_strategy(const nlohmann::json& request);
nlohmann::json process_stop_paper_strategy(const nlohmann::json& request);
nlohmann::json process_get_paper_strategy_status(const nlohmann::json& request);

// ============================================================
// 账户注册管理器（使用新的 AccountRegistry）
// ============================================================

AccountRegistry g_account_registry;

/**
 * @brief 获取策略对应的 API 客户端
 */
OKXRestAPI* get_api_for_strategy(const std::string& strategy_id) {
    OKXRestAPI* api = g_account_registry.get_okx_api(strategy_id);
    if (!api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册账户，且无默认账户\n";
    }
    return api;
}

/**
 * @brief 注册策略账户
 */
bool register_strategy_account(const std::string& strategy_id,
                                const std::string& api_key,
                                const std::string& secret_key,
                                const std::string& passphrase,
                                bool is_testnet) {
    bool success = g_account_registry.register_okx_account(
        strategy_id, api_key, secret_key, passphrase, is_testnet
    );

    if (success) {
        std::cout << "[账户] ✓ 策略 " << strategy_id << " 注册成功"
                  << " | 模式: " << (is_testnet ? "模拟盘" : "实盘")
                  << " | API Key: " << api_key.substr(0, 8) << "...\n";
    }

    return success;
}

/**
 * @brief 注销策略账户
 */
bool unregister_strategy_account(const std::string& strategy_id) {
    bool success = g_account_registry.unregister_account(strategy_id, ExchangeType::OKX);

    if (success) {
        std::cout << "[账户] ✓ 策略 " << strategy_id << " 已注销\n";
    } else {
        std::cout << "[账户] 策略 " << strategy_id << " 未找到\n";
    }

    return success;
}

/**
 * @brief 获取已注册的策略数量
 */
size_t get_registered_strategy_count() {
    return g_account_registry.count();
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

    // 订单生命周期日志 - 接收
    LOG_ORDER(client_order_id, "RECEIVED", "strategy=" + strategy_id + " symbol=" + symbol + " side=" + side + " qty=" + std::to_string(quantity));
    LOG_AUDIT("ORDER_SUBMIT", "strategy=" + strategy_id + " order_id=" + client_order_id + " symbol=" + symbol);

    std::cout << "[下单] " << strategy_id << " | " << symbol
              << " | " << side << " " << order_type
              << " | 数量: " << quantity << "\n";
    
    // 🔑 关键：获取该策略对应的 API 客户端
    OKXRestAPI* api = get_api_for_strategy(strategy_id);
    if (!api) {
        std::string error_msg = "策略 " + strategy_id + " 未注册账户，且无默认账户";
        std::cout << "[下单] ✗ " << error_msg << "\n";
        LOG_ORDER(client_order_id, "REJECTED", "reason=" + error_msg);
        g_order_failed++;
        
        nlohmann::json report = make_order_report(
            strategy_id, client_order_id, "", symbol,
            "rejected", price, quantity, 0.0, error_msg
        );
        server.publish_report(report);
        return;
    }
    
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
        
        // 处理订单标签
        if (order.contains("tag") && !order["tag"].is_null()) {
            req.tag = order["tag"].get<std::string>();
        }
        
        // 处理止盈止损参数
        if (order.contains("attach_algo_ords") && order["attach_algo_ords"].is_array()) {
            for (const auto& algo_json : order["attach_algo_ords"]) {
                AttachAlgoOrder algo;
                if (algo_json.contains("tp_trigger_px") && !algo_json["tp_trigger_px"].is_null()) {
                    algo.tp_trigger_px = algo_json["tp_trigger_px"].get<std::string>();
                    algo.tp_ord_px = algo_json.value("tp_ord_px", "-1");
                    algo.tp_trigger_px_type = algo_json.value("tp_trigger_px_type", "last");
                }
                if (algo_json.contains("sl_trigger_px") && !algo_json["sl_trigger_px"].is_null()) {
                    algo.sl_trigger_px = algo_json["sl_trigger_px"].get<std::string>();
                    algo.sl_ord_px = algo_json.value("sl_ord_px", "-1");
                    algo.sl_trigger_px_type = algo_json.value("sl_trigger_px_type", "last");
                }
                if (!algo.tp_trigger_px.empty() || !algo.sl_trigger_px.empty()) {
                    req.attach_algo_ords.push_back(algo);
                }
            }
        }
        
        // 记录发送到OKX的时间
        auto send_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        
        auto response = api->place_order_advanced(req);
        
        // 记录收到OKX响应的时间
        auto resp_ns = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        
        if (response.is_success()) {
            success = true;
            exchange_order_id = response.ord_id;
            g_order_success++;
            LOG_ORDER(client_order_id, "ACCEPTED", "exchange_id=" + exchange_order_id);
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✓\n";
        } else {
            error_msg = response.s_msg.empty() ? response.msg : response.s_msg;
            g_order_failed++;
            LOG_ORDER(client_order_id, "REJECTED", "error=" + error_msg);
            std::cout << "[OKX响应] 时间戳: " << resp_ns << " ns | 订单ID: " << client_order_id
                      << " | 往返: " << (resp_ns - send_ns) / 1000000 << " ms | ✗ " << error_msg << "\n";
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
        g_order_failed++;
        LOG_ORDER(client_order_id, "ERROR", error_msg);
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
        
        // 处理订单标签
        if (ord.contains("tag") && !ord["tag"].is_null()) {
            req.tag = ord["tag"].get<std::string>();
        }
        
        // 处理止盈止损参数
        if (ord.contains("attach_algo_ords") && ord["attach_algo_ords"].is_array()) {
            for (const auto& algo_json : ord["attach_algo_ords"]) {
                AttachAlgoOrder algo;
                if (algo_json.contains("tp_trigger_px") && !algo_json["tp_trigger_px"].is_null()) {
                    algo.tp_trigger_px = algo_json["tp_trigger_px"].get<std::string>();
                    algo.tp_ord_px = algo_json.value("tp_ord_px", "-1");
                    algo.tp_trigger_px_type = algo_json.value("tp_trigger_px_type", "last");
                }
                if (algo_json.contains("sl_trigger_px") && !algo_json["sl_trigger_px"].is_null()) {
                    algo.sl_trigger_px = algo_json["sl_trigger_px"].get<std::string>();
                    algo.sl_ord_px = algo_json.value("sl_ord_px", "-1");
                    algo.sl_trigger_px_type = algo_json.value("sl_trigger_px_type", "last");
                }
                if (!algo.tp_trigger_px.empty() || !algo.sl_trigger_px.empty()) {
                    req.attach_algo_ords.push_back(algo);
                }
            }
        }
        
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

    std::string cancel_id = order_id.empty() ? client_order_id : order_id;
    LOG_ORDER(cancel_id, "CANCEL_REQUEST", "strategy=" + strategy_id + " symbol=" + symbol);
    LOG_AUDIT("ORDER_CANCEL", "strategy=" + strategy_id + " order_id=" + cancel_id);

    std::cout << "[撤单] " << strategy_id << " | " << symbol
              << " | " << cancel_id << "\n";
    
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
                LOG_ORDER(cancel_id, "CANCELLED", "success");
                std::cout << "[撤单] ✓ 成功\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
                LOG_ORDER(cancel_id, "CANCEL_FAILED", "error=" + error_msg);
            }
        } else {
            error_msg = response.value("msg", "API error");
            LOG_ORDER(cancel_id, "CANCEL_FAILED", "error=" + error_msg);
        }
    } catch (const std::exception& e) {
        error_msg = std::string("异常: ") + e.what();
        LOG_ORDER(cancel_id, "CANCEL_ERROR", error_msg);
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
    std::string exchange = request.value("exchange", "okx");
    std::string api_key = request.value("api_key", "");
    std::string secret_key = request.value("secret_key", "");
    std::string passphrase = request.value("passphrase", "");
    bool is_testnet = request.value("is_testnet", true);

    LOG_AUDIT("ACCOUNT_REGISTER", "strategy=" + strategy_id + " exchange=" + exchange + " testnet=" + (is_testnet ? "true" : "false"));
    std::cout << "[账户注册] 策略: " << strategy_id << " | 交易所: " << exchange << "\n";

    nlohmann::json report;
    report["type"] = "register_report";
    report["strategy_id"] = strategy_id;
    report["exchange"] = exchange;
    report["timestamp"] = current_timestamp_ms();

    if (api_key.empty() || secret_key.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少必要参数 (api_key, secret_key)";
        std::cout << "[账户注册] ✗ 参数不完整\n";
    } else {
        ExchangeType ex_type = string_to_exchange_type(exchange);
        bool success = false;

        if (strategy_id.empty()) {
            // 注册为默认账户
            if (ex_type == ExchangeType::OKX) {
                g_account_registry.set_default_okx_account(api_key, secret_key, passphrase, is_testnet);
                success = true;
            } else if (ex_type == ExchangeType::BINANCE) {
                g_account_registry.set_default_binance_account(api_key, secret_key, is_testnet);
                success = true;
            }
            std::cout << "[账户注册] ✓ 默认账户注册成功\n";
        } else {
            // 注册策略账户
            success = g_account_registry.register_account(
                strategy_id, ex_type, api_key, secret_key, passphrase, is_testnet
            );
            if (success) {
                std::cout << "[账户注册] ✓ 策略 " << strategy_id << " 注册成功\n";
            }
        }

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
    std::string exchange = request.value("exchange", "okx");

    std::cout << "[账户注销] 策略: " << strategy_id << " | 交易所: " << exchange << "\n";

    nlohmann::json report;
    report["type"] = "unregister_report";
    report["strategy_id"] = strategy_id;
    report["exchange"] = exchange;
    report["timestamp"] = current_timestamp_ms();

    if (strategy_id.empty()) {
        report["status"] = "rejected";
        report["error_msg"] = "缺少 strategy_id";
    } else {
        ExchangeType ex_type = string_to_exchange_type(exchange);
        bool success = g_account_registry.unregister_account(strategy_id, ex_type);
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

    // PaperTrading 相关请求（不需要 API 认证）
    if (query_type == "start_paper_strategy") {
        return process_start_paper_strategy(request);
    }
    else if (query_type == "stop_paper_strategy") {
        return process_stop_paper_strategy(request);
    }
    else if (query_type == "get_paper_strategy_status") {
        return process_get_paper_strategy_status(request);
    }

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
// PaperTrading 管理
// ============================================================

nlohmann::json process_start_paper_strategy(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    if (g_paper_trading_running) {
        return {{"success", false}, {"message", "模拟交易已在运行中"}};
    }

    // 保存配置
    g_paper_trading_config = request;

    // 构建启动命令
    std::string cmd = "cd /home/llx/Real-account-trading-framework/cpp/build && ./papertrading_server > /tmp/papertrading.log 2>&1 &";

    // 启动进程
    int ret = system(cmd.c_str());
    if (ret != 0) {
        return {{"success", false}, {"message", "启动失败"}};
    }

    // 等待进程启动
    sleep(2);

    // 获取进程 PID (简化实现，实际应该从 pidfile 读取)
    FILE* fp = popen("pgrep -f papertrading_server", "r");
    if (fp) {
        char pid_str[32];
        if (fgets(pid_str, sizeof(pid_str), fp)) {
            g_paper_trading_pid = atoi(pid_str);
        }
        pclose(fp);
    }

    g_paper_trading_running = true;
    g_paper_trading_start_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();

    std::cout << "[PaperTrading] 已启动 (PID: " << g_paper_trading_pid << ")\n";

    return {
        {"success", true},
        {"message", "模拟交易已启动"},
        {"data", {
            {"strategyId", "paper_trading"},
            {"startTime", g_paper_trading_start_time}
        }}
    };
}

nlohmann::json process_stop_paper_strategy(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    if (!g_paper_trading_running) {
        return {{"success", false}, {"message", "模拟交易未运行"}};
    }

    // 停止进程
    if (g_paper_trading_pid > 0) {
        kill(g_paper_trading_pid, SIGTERM);

        // 等待进程退出
        int status;
        waitpid(g_paper_trading_pid, &status, WNOHANG);

        std::cout << "[PaperTrading] 已停止 (PID: " << g_paper_trading_pid << ")\n";
        g_paper_trading_pid = -1;
    }

    g_paper_trading_running = false;
    g_paper_trading_config.clear();

    return {{"success", true}, {"message", "模拟交易已停止"}};
}

nlohmann::json process_get_paper_strategy_status(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    return {
        {"success", true},
        {"data", {
            {"isRunning", g_paper_trading_running.load()},
            {"config", g_paper_trading_config},
            {"startTime", g_paper_trading_start_time},
            {"pid", g_paper_trading_pid}
        }}
    };
}
// ============================================================
// 前端 WebSocket 命令处理
// ============================================================

void handle_frontend_command(int client_id, const nlohmann::json& message) {
    try {
        std::string action = message.value("action", "");
        nlohmann::json data = message.value("data", nlohmann::json::object());
        std::string request_id = data.value("requestId", "");

        std::cout << "[前端] 收到命令: " << action << " (客户端: " << client_id << ")\n";

        nlohmann::json response;

        if (action == "start_paper_strategy") {
            response = process_start_paper_strategy(data);
        }
        else if (action == "stop_paper_strategy") {
            response = process_stop_paper_strategy(data);
        }
        else if (action == "get_paper_strategy_status") {
            response = process_get_paper_strategy_status(data);
        }
        else {
            response = {{"success", false}, {"message", "未知命令: " + action}};
        }

        // 添加 requestId 到响应
        if (!request_id.empty()) {
            response["requestId"] = request_id;
        }

        // 发送响应
        g_frontend_server->send_response(client_id, response["success"],
                                        response.value("message", ""), response);

    } catch (const std::exception& e) {
        std::cerr << "[前端] 处理命令异常: " << e.what() << "\n";
        g_frontend_server->send_response(client_id, false,
                                        std::string("处理命令异常: ") + e.what(), {});
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
    else if (channel == "orderbook" || channel == "books" || channel == "books5" || 
             channel == "bbo-tbt" || channel == "books-l2-tbt" || 
             channel == "books50-l2-tbt" || channel == "books-elp") {
        // 深度频道订阅
        std::string depth_channel = channel == "orderbook" ? "books5" : channel;
        
        if (action == "subscribe" && g_ws_public) {
            g_ws_public->subscribe_orderbook(symbol, depth_channel);
            g_subscribed_orderbooks[symbol].insert(depth_channel);
            std::cout << "[订阅] 深度: " << symbol << " " << depth_channel << " ✓\n";
        } else if (action == "unsubscribe" && g_ws_public) {
            g_ws_public->unsubscribe_orderbook(symbol, depth_channel);
            g_subscribed_orderbooks[symbol].erase(depth_channel);
            std::cout << "[取消订阅] 深度: " << symbol << " " << depth_channel << " ✓\n";
        }
    }
    else if (channel == "funding_rate" || channel == "funding-rate") {
        // 资金费率订阅
        if (action == "subscribe" && g_ws_public) {
            if (g_subscribed_funding_rates.find(symbol) == g_subscribed_funding_rates.end()) {
                g_ws_public->subscribe_funding_rate(symbol);
                g_subscribed_funding_rates.insert(symbol);
                std::cout << "[订阅] 资金费率: " << symbol << " ✓\n";
            }
        } else if (action == "unsubscribe" && g_ws_public) {
            if (g_subscribed_funding_rates.find(symbol) != g_subscribed_funding_rates.end()) {
                g_ws_public->unsubscribe_funding_rate(symbol);
                g_subscribed_funding_rates.erase(symbol);
                std::cout << "[取消订阅] 资金费率: " << symbol << " ✓\n";
            }
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
        
        // 深度数据回调（公共频道）
        g_ws_public->set_orderbook_callback([&zmq_server](const OrderBookData::Ptr& orderbook) {
            g_orderbook_count++;
            
            // 构建 bids 和 asks 数组
            nlohmann::json bids = nlohmann::json::array();
            nlohmann::json asks = nlohmann::json::array();
            
            for (const auto& bid : orderbook->bids()) {
                bids.push_back({bid.first, bid.second});  // [price, size]
            }
            
            for (const auto& ask : orderbook->asks()) {
                asks.push_back({ask.first, ask.second});  // [price, size]
            }
            
            // 根据 symbol 查找订阅的 channel（默认使用第一个）
            std::string channel = "books5";  // 默认值
            {
                std::lock_guard<std::mutex> lock(g_sub_mutex);
                auto it = g_subscribed_orderbooks.find(orderbook->symbol());
                if (it != g_subscribed_orderbooks.end() && !it->second.empty()) {
                    channel = *it->second.begin();  // 使用第一个订阅的 channel
                }
            }
            
            nlohmann::json msg = {
                {"type", "orderbook"},
                {"symbol", orderbook->symbol()},
                {"channel", channel},
                {"bids", bids},
                {"asks", asks},
                {"timestamp", orderbook->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };
            
            // 添加最优买卖价
            auto best_bid = orderbook->best_bid();
            auto best_ask = orderbook->best_ask();
            if (best_bid) {
                msg["best_bid_price"] = best_bid->first;
                msg["best_bid_size"] = best_bid->second;
            }
            if (best_ask) {
                msg["best_ask_price"] = best_ask->first;
                msg["best_ask_size"] = best_ask->second;
            }
            
            // 添加中间价和价差
            auto mid_price = orderbook->mid_price();
            if (mid_price) {
                msg["mid_price"] = *mid_price;
            }
            auto spread = orderbook->spread();
            if (spread) {
                msg["spread"] = *spread;
            }
            
            zmq_server.publish_depth(msg);
        });
        
        // 资金费率回调（公共频道）
        g_ws_public->set_funding_rate_callback([&zmq_server](const FundingRateData::Ptr& fr) {
            g_funding_rate_count++;
            
            nlohmann::json msg = {
                {"type", "funding_rate"},
                {"symbol", fr->inst_id},
                {"inst_type", fr->inst_type},
                {"funding_rate", fr->funding_rate},
                {"next_funding_rate", fr->next_funding_rate},
                {"funding_time", fr->funding_time},
                {"next_funding_time", fr->next_funding_time},
                {"min_funding_rate", fr->min_funding_rate},
                {"max_funding_rate", fr->max_funding_rate},
                {"interest_rate", fr->interest_rate},
                {"impact_value", fr->impact_value},
                {"premium", fr->premium},
                {"sett_state", fr->sett_state},
                {"sett_funding_rate", fr->sett_funding_rate},
                {"method", fr->method},
                {"formula_type", fr->formula_type},
                {"timestamp", fr->timestamp},
                {"timestamp_ns", current_timestamp_ns()}
            };
            
            zmq_server.publish_ticker(msg);
        });
    }
    
    // K线回调（业务频道）
    // 只推送已完结的K线（confirm=1），未完结的不推送
    if (g_ws_business) {
        g_ws_business->set_kline_callback([&zmq_server](const KlineData::Ptr& kline) {
            // 过滤：只推送已完结的K线
            if (!kline->is_confirmed()) {
                return;  // 跳过未完结的K线
            }
            
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
    (void)argc;  // 消除未使用警告
    (void)argv;  // 消除未使用警告

    // 初始化日志系统
    using namespace trading::core;
    Logger::instance().init("logs", "trading_server", LogLevel::INFO);

    std::cout << "========================================\n";
    std::cout << "    Sequence 实盘交易服务器 (Full)\n";
    std::cout << "    支持所有OKX接口\n";
    std::cout << "========================================\n\n";

    LOG_INFO("实盘交易服务器启动");
    
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
    // 加载账户配置（使用新的 AccountRegistry）
    // ========================================
    std::cout << "\n[初始化] 加载账户配置...\n";

    // 尝试从配置文件加载
    try {
        load_accounts_from_config(g_account_registry, "accounts.json", true);
    } catch (const std::exception& e) {
        std::cout << "[配置] 配置文件加载失败，使用环境变量/默认值\n";

        // 使用环境变量或默认值设置默认账户
        g_account_registry.set_default_okx_account(
            Config::api_key, Config::secret_key, Config::passphrase, Config::is_testnet
        );
        std::cout << "[初始化] 默认OKX账户 ✓ (API Key: " << Config::api_key.substr(0, 8) << "...)\n";
    }

    std::cout << "[提示] 策略可通过 register_account 消息注册自己的账户\n";

    // ========================================
    // 启动前端处理器（独立线程，非阻塞）
    // ========================================
    std::cout << "\n[初始化] 启动前端处理器...\n";
    FrontendHandler frontend_handler(g_account_registry);
    if (!frontend_handler.start("tcp://*:5556")) {
        std::cerr << "[错误] 前端处理器启动失败\n";
        return 1;
    }
    std::cout << "[前端] 监听端口 5556 ✓\n";

    // ========================================
    // 初始化 ZeroMQ (使用 WebSocket 服务器模式)
    // ========================================
    ZmqServer zmq_server(2);  // 模式 2 = WebSocket服务器地址
    if (!zmq_server.start()) {
        std::cerr << "[错误] ZeroMQ 服务启动失败\n";
        return 1;
    }

    std::cout << "[初始化] ZeroMQ 通道:\n";
    std::cout << "  - 行情: " << WebSocketServerIpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 订单: " << WebSocketServerIpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << WebSocketServerIpcAddresses::REPORT << "\n";
    std::cout << "  - 查询: " << WebSocketServerIpcAddresses::QUERY << "\n";
    std::cout << "  - 订阅: " << WebSocketServerIpcAddresses::SUBSCRIBE << "\n";
    
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
    // 启动前端 WebSocket 服务器
    // ========================================
    g_frontend_server = std::make_unique<core::WebSocketServer>();
    g_frontend_server->set_message_callback(handle_frontend_command);

    if (!g_frontend_server->start("0.0.0.0", 8002)) {
        std::cerr << "[错误] 前端WebSocket服务器启动失败\n";
        return 1;
    }

    std::cout << "[前端] WebSocket服务器已启动（端口8002）\n";

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
        std::this_thread::sleep_for(milliseconds(100));
        status_counter++;
        
        // 每 10 秒打印一次状态 (100 * 100ms = 10s)
        if (status_counter >= 100 && g_running.load()) {
            status_counter = 0;
            std::cout << "[状态] Trades: " << g_trade_count
                      << " | K线: " << g_kline_count
                      << " | 深度: " << g_orderbook_count
                      << " | 资金费率: " << g_funding_rate_count
                      << " | 订单: " << g_order_count
                      << " (成功: " << g_order_success
                      << ", 失败: " << g_order_failed << ")"
                      << " | 查询: " << g_query_count
                      << " | 注册账户: " << get_registered_strategy_count() << "\n";
        }
    }
    
    // ========================================
    // 清理
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    LOG_INFO("服务器正在停止...");
    
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

    // 停止前端 WebSocket 服务器
    if (g_frontend_server) {
        std::cout << "[Server] 停止前端WebSocket服务器...\n";
        g_frontend_server->stop();
    }

    // 停止 ZeroMQ
    std::cout << "[Server] 停止 ZeroMQ...\n";
    zmq_server.stop();

    // 停止前端处理器
    std::cout << "[Server] 停止前端处理器...\n";
    frontend_handler.stop();

    // 清理账户（使用新的 AccountRegistry）
    std::cout << "[Server] 清理账户注册器...\n";
    g_account_registry.clear();
    
    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "  Trades: " << g_trade_count << " 条\n";
    std::cout << "  K线: " << g_kline_count << " 条\n";
    std::cout << "  深度: " << g_orderbook_count << " 条\n";
    std::cout << "  资金费率: " << g_funding_rate_count << " 条\n";
    std::cout << "  订单: " << g_order_count << " 笔\n";
    std::cout << "========================================\n";

    LOG_INFO("服务器已停止 | Trades:" + std::to_string(g_trade_count.load()) +
             " K线:" + std::to_string(g_kline_count.load()) +
             " 订单:" + std::to_string(g_order_count.load()));
    Logger::instance().shutdown();

    return 0;
}

