/**
 * @file test_okx_ticker.cpp
 * @brief 测试OKX WebSocket 行情频道（tickers）
 * 
 * 获取产品的最新成交价、买一价、卖一价和24小时交易量等信息。
 * 最快100ms推送一次，没有触发事件时不推送，
 * 触发推送的事件有：成交、买一卖一发生变动。
 * 
 * 编译：cmake --build build --target test_okx_ticker
 * 运行：./build/test_okx_ticker
 */

#include "adapters/okx/okx_websocket.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <iomanip>

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_ticker_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 行情频道测试 (tickers)" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // ==================== 创建公共频道WebSocket ====================
    std::cout << "\n[1] 创建公共频道WebSocket..." << std::endl;
    auto ws = create_public_ws(true);  // true = 模拟盘
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    std::cout << "\n[2] 设置回调函数..." << std::endl;
    
    // 行情回调
    ws->set_ticker_callback([](const TickerData::Ptr& ticker) {
        g_ticker_count++;
        
        std::cout << "\n📊 [行情 #" << g_ticker_count.load() << "] " << ticker->symbol() << std::endl;
        std::cout << std::fixed << std::setprecision(2);
        std::cout << "   最新价: " << ticker->last_price() << std::endl;
        std::cout << "   买一价: " << ticker->bid_price() << " (量: " << ticker->bid_size() << ")" << std::endl;
        std::cout << "   卖一价: " << ticker->ask_price() << " (量: " << ticker->ask_size() << ")" << std::endl;
        std::cout << "   价差: " << ticker->spread() << " (" << std::setprecision(2) << ticker->spread_bps() << " bps)" << std::endl;
        std::cout << "   24h成交量: " << ticker->volume_24h() << std::endl;
        std::cout << "   时间戳: " << ticker->timestamp() << std::endl;
    });
    std::cout << "   ✅ 行情回调已设置" << std::endl;
    
    // 原始消息回调（打印订阅和错误消息）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "\n✅ [订阅成功] " << msg["arg"].dump() << std::endl;
            } else if (event == "unsubscribe") {
                std::cout << "\n✅ [取消订阅] " << msg["arg"].dump() << std::endl;
            } else if (event == "error") {
                std::cerr << "\n❌ [错误] " << msg.value("msg", "") 
                          << " (code: " << msg.value("code", "") << ")" << std::endl;
            }
        }
    });
    std::cout << "   ✅ 原始消息回调已设置" << std::endl;
    
    // ==================== 连接 ====================
    std::cout << "\n[3] 建立连接..." << std::endl;
    if (!ws->connect()) {
        std::cerr << "❌ 连接失败" << std::endl;
        return 1;
    }
    
    // 等待连接稳定
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    if (!ws->is_connected()) {
        std::cerr << "❌ 连接未建立" << std::endl;
        return 1;
    }
    std::cout << "✅ 连接成功" << std::endl;
    
    // ==================== 订阅行情频道 ====================
    std::cout << "\n[4] 订阅行情频道..." << std::endl;
    
    // 订阅多个产品
    std::vector<std::string> symbols = {"BTC-USDT", "ETH-USDT"};
    
    for (const auto& symbol : symbols) {
        std::cout << "   订阅: " << symbol << std::endl;
        ws->subscribe_ticker(symbol);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "     - " << ch << std::endl;
    }
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待行情数据推送..." << std::endl;
    std::cout << "\n  行情频道说明：" << std::endl;
    std::cout << "  1. 最快100ms推送一次" << std::endl;
    std::cout << "  2. 没有触发事件时不推送" << std::endl;
    std::cout << "  3. 触发推送的事件：成交、买一卖一发生变动" << std::endl;
    std::cout << "\n  推送数据包含：" << std::endl;
    std::cout << "  - 最新成交价 (last)" << std::endl;
    std::cout << "  - 买一价/卖一价 (bidPx/askPx)" << std::endl;
    std::cout << "  - 24小时成交量 (vol24h)" << std::endl;
    std::cout << "  - 24小时最高/最低价 (high24h/low24h)" << std::endl;
    std::cout << "\n  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 主循环
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(30));
        
        // 每30秒打印统计
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "收到行情更新: " << g_ticker_count.load() << " 次" << std::endl;
        if (elapsed > 0) {
            double rate = static_cast<double>(g_ticker_count.load()) / elapsed;
            std::cout << "平均推送频率: " << std::fixed << std::setprecision(2) << rate << " 次/秒" << std::endl;
        }
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[5] 取消订阅并断开连接..." << std::endl;
    for (const auto& symbol : symbols) {
        ws->unsubscribe_ticker(symbol);
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_ticker_count.load() << " 次行情更新" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

