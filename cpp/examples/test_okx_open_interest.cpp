/**
 * @file test_okx_open_interest.cpp
 * @brief 测试OKX WebSocket 持仓总量频道
 * 
 * 持仓总量频道用于获取永续/交割合约的总持仓量
 * 推送频率：每3秒有数据更新时推送
 * 
 * 编译：cmake --build build --target test_okx_open_interest
 * 运行：./build/test_okx_open_interest
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <vector>
#include <iomanip>

#include "adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_oi_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 持仓总量频道测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 要订阅的永续合约列表
    std::vector<std::string> swap_pairs = {
        "BTC-USDT-SWAP",
        "ETH-USDT-SWAP",
        "SOL-USDT-SWAP",
        "XRP-USDT-SWAP",
        "DOGE-USDT-SWAP",
        "LTC-USD-SWAP",
        "BTC-USD-SWAP",
        "ETH-USD-SWAP"
    };
    
    // 创建公共频道WebSocket
    auto ws = create_public_ws(true);  // true = 模拟盘
    
    std::cout << "\n[1] WebSocket URL: " << ws->get_url() << std::endl;
    
    // 设置持仓总量回调
    ws->set_open_interest_callback([](const OpenInterestData::Ptr& oi) {
        g_oi_count++;
        
        // 格式化输出
        std::cout << "📊 [OI] " << std::left << std::setw(16) << oi->inst_id
                  << " | 类型: " << std::setw(6) << oi->inst_type
                  << " | 持仓(张): " << std::right << std::setw(15) << std::fixed << std::setprecision(2) << oi->oi
                  << " | 持仓(币): " << std::setw(12) << std::setprecision(4) << oi->oi_ccy
                  << " | 持仓(USD): $" << std::setw(15) << std::setprecision(2) << oi->oi_usd
                  << std::endl;
    });
    
    // 设置原始消息回调（调试用）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "✅ 订阅成功: " << msg["arg"].dump() << std::endl;
            } else if (event == "error") {
                std::cerr << "❌ 错误: " << msg["msg"].get<std::string>() << std::endl;
            }
        }
    });
    
    // 连接
    std::cout << "\n[2] 正在连接..." << std::endl;
    if (!ws->connect()) {
        std::cerr << "❌ 连接失败" << std::endl;
        return 1;
    }
    
    // 等待连接稳定
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 订阅持仓总量
    std::cout << "\n[3] 订阅持仓总量频道..." << std::endl;
    
    for (const auto& pair : swap_pairs) {
        std::cout << "   订阅: " << pair << std::endl;
        ws->subscribe_open_interest(pair);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待持仓总量数据 (每3秒更新)..." << std::endl;
    std::cout << "  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 主循环
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        
        // 每10秒打印统计
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "收到持仓总量更新: " << g_oi_count.load() << " 条" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // 取消订阅
    std::cout << "\n[4] 取消订阅..." << std::endl;
    for (const auto& pair : swap_pairs) {
        ws->unsubscribe_open_interest(pair);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    
    // 断开连接
    std::cout << "\n[5] 断开连接..." << std::endl;
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_oi_count.load() << " 条持仓总量数据" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

