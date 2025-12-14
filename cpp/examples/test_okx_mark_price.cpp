/**
 * @file test_okx_mark_price.cpp
 * @brief 测试OKX WebSocket 标记价格频道
 * 
 * 标记价格有变化时每200ms推送，没变化时每10s推送
 * 
 * 编译：cmake --build build --target test_okx_mark_price
 * 运行：./build/test_okx_mark_price
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <vector>
#include <iomanip>
#include <map>

#include "adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_mp_count{0};

// 最新标记价格
std::map<std::string, double> g_latest_prices;
std::mutex g_prices_mutex;

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 标记价格频道测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 要订阅的产品列表（现货、永续合约）
    std::vector<std::string> pairs = {
        // 现货/杠杆
        "BTC-USDT",
        "ETH-USDT",
        "SOL-USDT",
        // 永续合约
        "BTC-USDT-SWAP",
        "ETH-USDT-SWAP",
        "SOL-USDT-SWAP"
    };
    
    // 创建公共频道WebSocket
    auto ws = create_public_ws(true);  // true = 模拟盘
    
    std::cout << "\n[1] WebSocket URL: " << ws->get_url() << std::endl;
    
    // 设置标记价格回调
    ws->set_mark_price_callback([](const MarkPriceData::Ptr& mp) {
        g_mp_count++;
        
        // 保存最新价格
        {
            std::lock_guard<std::mutex> lock(g_prices_mutex);
            g_latest_prices[mp->inst_id] = mp->mark_px;
        }
        
        // 格式化输出
        std::cout << "📈 [MarkPrice] " << std::left << std::setw(16) << mp->inst_id
                  << " | 类型: " << std::setw(8) << mp->inst_type
                  << " | 标记价格: $" << std::right << std::fixed << std::setprecision(2) << std::setw(12) << mp->mark_px
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
    
    // 订阅标记价格
    std::cout << "\n[3] 订阅标记价格频道..." << std::endl;
    
    for (const auto& pair : pairs) {
        std::cout << "   订阅: " << pair << std::endl;
        ws->subscribe_mark_price(pair);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待标记价格数据..." << std::endl;
    std::cout << "  (有变化时200ms推送，无变化时10s推送)" << std::endl;
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
        std::cout << "收到标记价格更新: " << g_mp_count.load() << " 条" << std::endl;
        
        // 显示所有最新价格
        std::lock_guard<std::mutex> lock(g_prices_mutex);
        std::cout << "最新标记价格:" << std::endl;
        for (const auto& [inst_id, price] : g_latest_prices) {
            std::cout << "  " << std::left << std::setw(16) << inst_id 
                      << ": $" << std::fixed << std::setprecision(2) << price << std::endl;
        }
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // 取消订阅
    std::cout << "\n[4] 取消订阅..." << std::endl;
    for (const auto& pair : pairs) {
        ws->unsubscribe_mark_price(pair);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    
    // 断开连接
    std::cout << "\n[5] 断开连接..." << std::endl;
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_mp_count.load() << " 条标记价格数据" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

