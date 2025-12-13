/**
 * @file trading_server.cpp
 * @brief 实盘交易服务器主程序
 * 
 * 功能：
 * 1. 接收 OKX WebSocket 行情并通过 ZeroMQ 分发给策略
 * 2. 接收策略的订单请求并调用 OKX REST API 下单
 * 3. 将订单执行结果返回给策略
 * 
 * 架构：
 *   OKX 交易所
 *       │
 *       │ WebSocket (行情)
 *       │ REST API (下单)
 *       ▼
 *   ┌───────────────────┐
 *   │  Trading Server   │
 *   │                   │
 *   │  ┌─────────────┐  │
 *   │  │ ZmqServer   │  │
 *   │  │ - PUB 行情  │  │
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
 *   ./trading_server
 * 
 * 环境变量（可选，也可使用默认值）：
 *   OKX_API_KEY
 *   OKX_SECRET_KEY
 *   OKX_PASSPHRASE
 * 
 * @author Sequence Team
 * @date 2024-12
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

using namespace trading;
using namespace trading::server;
using namespace trading::okx;
using namespace std::chrono;

// ============================================================
// 全局变量
// ============================================================

// 运行标志（用于优雅退出）
std::atomic<bool> g_running{true};

// 统计数据
std::atomic<uint64_t> g_ticker_count{0};    // 发送的行情数
std::atomic<uint64_t> g_order_count{0};     // 处理的订单数
std::atomic<uint64_t> g_order_success{0};   // 成功的订单数
std::atomic<uint64_t> g_order_failed{0};    // 失败的订单数

// ============================================================
// 信号处理
// ============================================================

/**
 * @brief 信号处理函数
 * 
 * 捕获 SIGINT (Ctrl+C) 和 SIGTERM，设置退出标志
 */
void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
}

// ============================================================
// 行情模拟线程
// ============================================================

/**
 * @brief 模拟行情线程
 * 
 * 在没有真实 WebSocket 连接时，生成模拟行情用于测试
 * 
 * @param server ZeroMQ 服务端引用
 * @param symbol 交易对
 * @param interval_ms 发送间隔（毫秒）
 * @param total_count 总发送数量（0 = 无限）
 * @param large_msg 是否使用大消息（8KB）
 */
void simulate_market_data(ZmqServer& server, const std::string& symbol, 
                          int interval_ms, int total_count = 0, bool large_msg = false) {
    std::cout << "[行情线程] 启动（模拟模式）\n";
    std::cout << "[行情线程] 交易对: " << symbol 
              << ", 间隔: " << interval_ms << "ms"
              << ", 总数: " << (total_count > 0 ? std::to_string(total_count) : "无限")
              << ", 大消息: " << (large_msg ? "是(8KB)" : "否") << "\n";
    
    // 初始价格
    double base_price = 43000.0;
    uint64_t seq_num = 0;
    
    while (g_running.load()) {
        // 检查是否达到目标数量
        if (total_count > 0 && g_ticker_count >= static_cast<uint64_t>(total_count)) {
            std::cout << "[行情线程] 已发送 " << total_count << " 条，停止\n";
            break;
        }
        
        // 模拟价格波动（随机游走）
        double delta = (rand() % 200 - 100) / 10.0;  // -10 到 +10
        base_price += delta;
        
        // 确保价格合理
        if (base_price < 40000) base_price = 40000;
        if (base_price > 50000) base_price = 50000;
        
        seq_num++;
        
        // 构建行情消息
        nlohmann::json ticker;
        if (large_msg) {
            // 8KB 大消息（用于延迟测试）
            ticker = make_large_ticker_msg(symbol, seq_num, base_price);
        } else {
            // 标准小消息
            ticker = make_ticker_msg(
                symbol, base_price, base_price - 0.5, base_price + 0.5,
                1.0, 1.5, 10000.0
            );
            ticker["seq_num"] = seq_num;
            ticker["send_time_ns"] = current_timestamp_ns();
        }
        
        // 发布行情
        if (server.publish_ticker(ticker)) {
            g_ticker_count++;
            
            // 每 100 条打印一次
            if (g_ticker_count % 100 == 0) {
                std::cout << "[行情] " << symbol 
                          << " | 价格: " << std::fixed << std::setprecision(2) << base_price
                          << " | 序号: " << seq_num
                          << " | 累计: " << g_ticker_count << "\n";
            }
        }
        
        // 等待
        std::this_thread::sleep_for(milliseconds(interval_ms));
    }
    
    std::cout << "[行情线程] 停止，共发送 " << g_ticker_count << " 条行情\n";
}

// ============================================================
// 订单处理
// ============================================================

/**
 * @brief 处理订单请求
 * 
 * 从策略接收订单请求，调用 OKX API 下单，返回执行结果
 * 
 * @param server ZeroMQ 服务端引用
 * @param api OKX REST API 引用
 * @param order 订单请求 JSON
 */
void process_order(ZmqServer& server, OKXRestAPI& api, const nlohmann::json& order) {
    g_order_count++;
    
    // 解析订单参数
    std::string strategy_id = order.value("strategy_id", "unknown");
    std::string client_order_id = order.value("client_order_id", "");
    std::string symbol = order.value("symbol", "BTC-USDT");
    std::string side = order.value("side", "buy");
    std::string order_type = order.value("order_type", "limit");
    double price = order.value("price", 0.0);
    double quantity = order.value("quantity", 0.0);
    
    std::cout << "[订单] 收到订单请求"
              << " | 策略: " << strategy_id
              << " | " << symbol
              << " | " << side << " " << order_type
              << " | 价格: " << std::fixed << std::setprecision(2) << price
              << " | 数量: " << quantity
              << "\n";
    
    // 解析响应
    bool success = false;
    std::string exchange_order_id;
    std::string error_msg;
    
    // ⚠️ 关键：用 try-catch 包裹 API 调用，防止网络异常导致服务器崩溃
    try {
        // 调用 OKX API 下单
        auto response = api.place_order(
            symbol,
            "cash",      // 交易模式：现货
            side,
            order_type,
            quantity,
            price,
            client_order_id
        );
        
        // 打印完整响应用于调试
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
                // 打印详细错误
                error_msg = data.value("sMsg", "Unknown error");
                std::string sCode = data.value("sCode", "");
                g_order_failed++;
                
                std::cout << "[订单] ✗ 下单失败（交易所拒绝）"
                          << " | sCode: " << sCode
                          << " | 错误: " << error_msg << "\n";
            }
        } else {
            error_msg = response.value("msg", "API error");
            g_order_failed++;
            
            std::cout << "[订单] ✗ 下单失败（API错误）"
                      << " | code: " << response.value("code", "?")
                      << " | 错误: " << error_msg << "\n";
        }
    } catch (const std::exception& e) {
        // 捕获网络异常、SSL 错误等，防止服务器崩溃
        error_msg = std::string("网络异常: ") + e.what();
        g_order_failed++;
        
        std::cout << "[订单] ✗ 下单失败（网络异常）"
                  << " | 错误: " << e.what() << "\n";
        std::cout << "[警告] API 调用异常，但服务器继续运行\n";
    }
    
    // 构建并发送回报
    nlohmann::json report = make_order_report(
        strategy_id,
        client_order_id,
        exchange_order_id,
        symbol,
        success ? "accepted" : "rejected",
        success ? price : 0.0,
        success ? quantity : 0.0,
        0.0,  // fee
        error_msg
    );
    
    server.publish_report(report);
}

// ============================================================
// 订单处理线程
// ============================================================

/**
 * @brief 订单处理线程
 * 
 * 持续轮询订单请求，处理后返回结果
 * 
 * @param server ZeroMQ 服务端引用
 * @param api OKX REST API 引用
 */
void order_thread(ZmqServer& server, OKXRestAPI& api) {
    std::cout << "[订单线程] 启动\n";
    
    while (g_running.load()) {
        // 非阻塞接收订单
        nlohmann::json order;
        while (server.recv_order_json(order)) {
            // 处理订单
            process_order(server, api, order);
        }
        
        // 短暂休眠，避免空转
        // 100μs 是一个合理的值，既不会浪费 CPU，延迟也很低
        std::this_thread::sleep_for(microseconds(100));
    }
    
    std::cout << "[订单线程] 停止"
              << " | 总计: " << g_order_count
              << " | 成功: " << g_order_success
              << " | 失败: " << g_order_failed << "\n";
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "    Sequence 实盘交易服务器\n";
    std::cout << "    ZeroMQ IPC 架构\n";
    std::cout << "========================================\n\n";
    
    // ========================================
    // 注册信号处理
    // ========================================
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // ========================================
    // 读取 API 配置
    // ========================================
    // 优先从环境变量读取，否则使用默认值（测试用）
    std::string api_key = std::getenv("OKX_API_KEY") 
        ? std::getenv("OKX_API_KEY") 
        : "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    
    std::string secret_key = std::getenv("OKX_SECRET_KEY") 
        ? std::getenv("OKX_SECRET_KEY") 
        : "888CC77C745F1B49E75A992F38929992";
    
    std::string passphrase = std::getenv("OKX_PASSPHRASE") 
        ? std::getenv("OKX_PASSPHRASE") 
        : "Sequence2025.";
    
    // 是否使用模拟盘
    bool is_testnet = true;  // 默认使用模拟盘
    
    std::cout << "[配置] 交易模式: " << (is_testnet ? "模拟盘" : "实盘") << "\n";
    
    // ========================================
    // 初始化 OKX API
    // ========================================
    OKXRestAPI api(api_key, secret_key, passphrase, is_testnet);
    std::cout << "[初始化] OKX REST API 已创建\n";
    
    // ========================================
    // 初始化 ZeroMQ 服务端
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
    
    // ========================================
    // 启动工作线程
    // ========================================
    std::cout << "\n========================================\n";
    std::cout << "  服务器启动完成！\n";
    std::cout << "  等待策略连接...\n";
    std::cout << "  按 Ctrl+C 停止\n";
    std::cout << "========================================\n\n";
    
    // 等待策略连接（给策略 5 秒启动时间）
    std::cout << "[Server] 等待 5 秒让策略连接...\n";
    std::this_thread::sleep_for(seconds(5));
    std::cout << "[Server] 开始发送行情\n";
    
    // 启动行情线程（模拟模式）
    // 配置：10ms 间隔，精确发送指定条数，8KB 大消息
    std::thread market_thread(simulate_market_data, 
                              std::ref(zmq_server), 
                              "BTC-USDT", 
                              1,     // 每 10ms 发一条（100条/秒）
                              1000,   // 精确发送 1000 条
                              true);  // 使用 8KB 大消息
    
    // 启动订单处理线程
    std::thread order_processing_thread(order_thread, 
                                        std::ref(zmq_server), 
                                        std::ref(api));
    
    // ========================================
    // 主循环：打印状态
    // ========================================
    while (g_running.load()) {
        std::this_thread::sleep_for(seconds(10));
        
        if (g_running.load()) {
            std::cout << "[状态] 行情: " << g_ticker_count
                      << " | 订单: " << g_order_count
                      << " (成功: " << g_order_success
                      << ", 失败: " << g_order_failed << ")\n";
        }
    }
    
    // ========================================
    // 停止
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    
    // 等待线程结束
    market_thread.join();
    order_processing_thread.join();
    
    // 停止 ZeroMQ
    zmq_server.stop();
    
    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "========================================\n";
    
    return 0;
}

