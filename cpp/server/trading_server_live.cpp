/**
 * @file trading_server_live.cpp
 * @brief 实盘交易服务器 - OKX WebSocket实时行情版本
 * 
 * 功能：
 * 1. 连接 OKX WebSocket 获取实时 trades 数据
 * 2. 通过 ZeroMQ 将 trades 数据分发给策略
 * 3. 接收策略的订单请求并调用 OKX REST API 下单
 * 4. 将订单执行结果返回给策略
 * 
 * 架构：
 *   OKX 交易所
 *       │
 *       │ WebSocket (trades实时数据)
 *       │ REST API (下单)
 *       ▼
 *   ┌───────────────────┐
 *   │  Trading Server   │
 *   │                   │
 *   │  ┌─────────────┐  │
 *   │  │ ZmqServer   │  │
 *   │  │ - PUB trades│  │
 *   │  │ - PULL 订单 │  │
 *   │  │ - PUB 回报  │  │
 *   │  └─────────────┘  │
 *   └───────────────────┘
 *       │
 *       │ IPC (Unix Socket)
 *       ▼
 *   策略进程 (Python)
 * 
 * 运行方式：
 *   ./trading_server_live
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

#include "zmq_server.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::server;
using namespace trading::okx;
using namespace std::chrono;

// ============================================================
// 全局变量
// ============================================================

std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_trade_count{0};     // 收到的trades数
std::atomic<uint64_t> g_publish_count{0};   // 发布的trades数
std::atomic<uint64_t> g_order_count{0};     // 处理的订单数
std::atomic<uint64_t> g_order_success{0};
std::atomic<uint64_t> g_order_failed{0};

// ZeroMQ服务器指针（用于WebSocket回调）
ZmqServer* g_zmq_server = nullptr;

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
}

// ============================================================
// 订单处理
// ============================================================

void process_order(ZmqServer& server, OKXRestAPI& api, const nlohmann::json& order) {
    g_order_count++;
    
    std::string strategy_id = order.value("strategy_id", "unknown");
    std::string client_order_id = order.value("client_order_id", "");
    std::string symbol = order.value("symbol", "BTC-USDT");
    std::string side = order.value("side", "buy");
    std::string order_type = order.value("order_type", "limit");
    double price = order.value("price", 0.0);
    double quantity = order.value("quantity", 0.0);
    std::string td_mode = order.value("td_mode", "cash");  // cash=现货, cross=全仓
    
    std::cout << "[订单] 收到订单请求"
              << " | 策略: " << strategy_id
              << " | " << symbol
              << " | " << side << " " << order_type
              << " | 价格: " << std::fixed << std::setprecision(2) << price
              << " | 数量: " << quantity
              << "\n";
    
    bool success = false;
    std::string exchange_order_id;
    std::string error_msg;
    
    try {
        auto response = api.place_order(
            symbol,
            td_mode,
            side,
            order_type,
            quantity,
            price,
            client_order_id
        );
        
        std::cout << "[DEBUG] API Response: " << response.dump() << "\n";
        
        if (response["code"] == "0" && response.contains("data") && !response["data"].empty()) {
            auto& data = response["data"][0];
            if (data["sCode"] == "0") {
                success = true;
                exchange_order_id = data.value("ordId", "");
                g_order_success++;
                
                std::cout << "[订单] ✓ 下单成功"
                          << " | 交易所ID: " << exchange_order_id << "\n";
            } else {
                error_msg = data.value("sMsg", "Unknown error");
                g_order_failed++;
                std::cout << "[订单] ✗ 下单失败: " << error_msg << "\n";
            }
        } else {
            error_msg = response.value("msg", "API error");
            g_order_failed++;
            std::cout << "[订单] ✗ 下单失败: " << error_msg << "\n";
        }
    } catch (const std::exception& e) {
        error_msg = std::string("网络异常: ") + e.what();
        g_order_failed++;
        std::cout << "[订单] ✗ 下单异常: " << e.what() << "\n";
    }
    
    // 发布订单回报
    nlohmann::json report = make_order_report(
        strategy_id,
        client_order_id,
        exchange_order_id,
        symbol,
        success ? "accepted" : "rejected",
        success ? price : 0.0,
        success ? quantity : 0.0,
        0.0,
        error_msg
    );
    
    server.publish_report(report);
}

// ============================================================
// 订单处理线程
// ============================================================

void order_thread(ZmqServer& server, OKXRestAPI& api) {
    std::cout << "[订单线程] 启动\n";
    
    while (g_running.load()) {
        nlohmann::json order;
        while (server.recv_order_json(order)) {
            process_order(server, api, order);
        }
        std::this_thread::sleep_for(microseconds(100));
    }
    
    std::cout << "[订单线程] 停止\n";
}

// ============================================================
// 主函数
// ============================================================

int main() {
    std::cout << "========================================\n";
    std::cout << "    Sequence 实盘交易服务器 (Live)\n";
    std::cout << "    OKX WebSocket + ZeroMQ\n";
    std::cout << "========================================\n\n";
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // ========================================
    // API 配置
    // ========================================
    std::string api_key = std::getenv("OKX_API_KEY") 
        ? std::getenv("OKX_API_KEY") 
        : "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    
    std::string secret_key = std::getenv("OKX_SECRET_KEY") 
        ? std::getenv("OKX_SECRET_KEY") 
        : "888CC77C745F1B49E75A992F38929992";
    
    std::string passphrase = std::getenv("OKX_PASSPHRASE") 
        ? std::getenv("OKX_PASSPHRASE") 
        : "Sequence2025.";
    
    bool is_testnet = true;  // 模拟盘
    
    std::cout << "[配置] 交易模式: " << (is_testnet ? "模拟盘" : "实盘") << "\n";
    
    // ========================================
    // 初始化 OKX REST API
    // ========================================
    OKXRestAPI api(api_key, secret_key, passphrase, is_testnet);
    std::cout << "[初始化] OKX REST API 已创建\n";
    
    // ========================================
    // 初始化 ZeroMQ 服务端
    // ========================================
    ZmqServer zmq_server;
    g_zmq_server = &zmq_server;
    
    if (!zmq_server.start()) {
        std::cerr << "[错误] ZeroMQ 服务启动失败\n";
        return 1;
    }
    
    std::cout << "[初始化] ZeroMQ 通道:\n";
    std::cout << "  - 行情: " << IpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 订单: " << IpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << IpcAddresses::REPORT << "\n";
    
    // ========================================
    // 初始化 OKX WebSocket (公共频道)
    // ========================================
    std::cout << "\n[初始化] 创建 OKX WebSocket...\n";
    auto ws = create_public_ws(is_testnet);
    
    // 设置 trades 回调
    ws->set_trade_callback([&zmq_server](const TradeData::Ptr& trade) {
        g_trade_count++;
        
        // 构建 trades 消息
        nlohmann::json trade_msg = {
            {"type", "trade"},
            {"symbol", trade->symbol()},
            {"trade_id", trade->trade_id()},
            {"price", trade->price()},
            {"quantity", trade->quantity()},
            {"side", trade->side().value_or("")},
            {"timestamp", trade->timestamp()},
            {"timestamp_ns", current_timestamp_ns()}
        };
        
        // 通过 ZeroMQ 发布
        if (zmq_server.publish_ticker(trade_msg)) {
            g_publish_count++;
            
            // 每 100 条打印一次
            if (g_publish_count % 100 == 0) {
                std::cout << "[Trades] " << trade->symbol() 
                          << " | " << trade->side().value_or("?")
                          << " | 价格: " << std::fixed << std::setprecision(2) << trade->price()
                          << " | 数量: " << trade->quantity()
                          << " | 累计: " << g_publish_count << "\n";
            }
        }
    });
    
    // 设置原始消息回调（调试用）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "[WebSocket] ✓ 订阅成功: " << msg["arg"].dump() << "\n";
            } else if (event == "error") {
                std::cerr << "[WebSocket] ✗ 错误: " << msg.value("msg", "") << "\n";
            }
        }
    });
    
    // ========================================
    // 连接 WebSocket
    // ========================================
    std::cout << "\n[WebSocket] 连接中...\n";
    if (!ws->connect()) {
        std::cerr << "[错误] WebSocket 连接失败\n";
        return 1;
    }
    
    std::this_thread::sleep_for(seconds(2));
    
    if (!ws->is_connected()) {
        std::cerr << "[错误] WebSocket 连接未建立\n";
        return 1;
    }
    std::cout << "[WebSocket] ✓ 连接成功\n";
    
    // ========================================
    // 订阅 trades 频道
    // ========================================
    std::cout << "\n[WebSocket] 订阅 trades 频道...\n";
    ws->subscribe_trades("BTC-USDT");
    std::this_thread::sleep_for(milliseconds(500));
    ws->subscribe_trades("ETH-USDT");
    
    std::cout << "[WebSocket] 已订阅: BTC-USDT, ETH-USDT\n";
    
    // ========================================
    // 启动订单处理线程
    // ========================================
    std::thread order_processing_thread(order_thread, 
                                        std::ref(zmq_server), 
                                        std::ref(api));
    
    // ========================================
    // 启动完成
    // ========================================
    std::cout << "\n========================================\n";
    std::cout << "  服务器启动完成！\n";
    std::cout << "  等待策略连接...\n";
    std::cout << "  按 Ctrl+C 停止\n";
    std::cout << "========================================\n\n";
    
    // ========================================
    // 主循环：打印状态
    // ========================================
    while (g_running.load()) {
        std::this_thread::sleep_for(seconds(10));
        
        if (g_running.load()) {
            std::cout << "[状态] Trades收到: " << g_trade_count
                      << " | 发布: " << g_publish_count
                      << " | 订单: " << g_order_count
                      << " (成功: " << g_order_success
                      << ", 失败: " << g_order_failed << ")\n";
        }
    }
    
    // ========================================
    // 停止
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    
    // 断开 WebSocket
    ws->unsubscribe_trades("BTC-USDT");
    ws->unsubscribe_trades("ETH-USDT");
    ws->disconnect();
    
    // 等待线程结束
    order_processing_thread.join();
    
    // 停止 ZeroMQ
    zmq_server.stop();
    
    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "  Trades: " << g_trade_count << " 条\n";
    std::cout << "  订单: " << g_order_count << " 笔\n";
    std::cout << "========================================\n";
    
    return 0;
}

