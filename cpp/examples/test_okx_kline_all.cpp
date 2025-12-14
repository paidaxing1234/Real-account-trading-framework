/**
 * @file test_okx_kline_all.cpp
 * @brief 测试OKX WebSocket K线订阅 - 多币种版本
 * 
 * 订阅主流交易对的K线数据
 * 
 * 编译：cmake --build build --target test_okx_kline_all
 * 运行：./build/test_okx_kline_all
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <vector>
#include <map>
#include <iomanip>

#include "adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_kline_count{0};

// 每个币种的最新K线
std::map<std::string, KlineData::Ptr> g_latest_klines;
std::mutex g_klines_mutex;

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main(int argc, char* argv[]) {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket K线订阅测试 (多币种)" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // ==================== 配置订阅的币种 ====================
    // 现货交易对
    std::vector<std::string> spot_pairs = {
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
        "ADA-USDT", "AVAX-USDT", "DOT-USDT", "MATIC-USDT", "LINK-USDT",
        "UNI-USDT", "ATOM-USDT", "LTC-USDT", "BCH-USDT", "ETC-USDT",
        "FIL-USDT", "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT"
    };
    
    // 永续合约
    std::vector<std::string> swap_pairs = {
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", 
        "XRP-USDT-SWAP", "DOGE-USDT-SWAP"
    };
    
    // 选择订阅哪些
    std::vector<std::string> pairs_to_subscribe;
    
    // 默认订阅现货
    std::string mode = "spot";
    if (argc > 1) {
        mode = argv[1];
    }
    
    if (mode == "swap") {
        pairs_to_subscribe = swap_pairs;
        std::cout << "\n模式: 永续合约" << std::endl;
    } else if (mode == "all") {
        pairs_to_subscribe = spot_pairs;
        pairs_to_subscribe.insert(pairs_to_subscribe.end(), swap_pairs.begin(), swap_pairs.end());
        std::cout << "\n模式: 全部（现货+永续）" << std::endl;
    } else {
        pairs_to_subscribe = spot_pairs;
        std::cout << "\n模式: 现货" << std::endl;
    }
    
    std::cout << "订阅币种数: " << pairs_to_subscribe.size() << std::endl;
    
    // ==================== K线周期选择 ====================
    std::string interval = "1m";
    if (argc > 2) {
        interval = argv[2];
    }
    std::cout << "K线周期: " << interval << std::endl;
    
    // ==================== 创建WebSocket ====================
    auto ws = create_business_ws(true);  // true = 模拟盘
    std::cout << "\nWebSocket URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    ws->set_kline_callback([](const KlineData::Ptr& kline) {
        g_kline_count++;
        
        // 保存最新K线
        {
            std::lock_guard<std::mutex> lock(g_klines_mutex);
            g_latest_klines[kline->symbol()] = kline;
        }
        
        // 打印K线数据
        std::cout << "📊 " << std::left << std::setw(15) << kline->symbol()
                  << " | " << kline->interval()
                  << " | O:" << std::fixed << std::setprecision(2) << std::setw(10) << kline->open()
                  << " H:" << std::setw(10) << kline->high()
                  << " L:" << std::setw(10) << kline->low()
                  << " C:" << std::setw(10) << kline->close()
                  << " V:" << std::setprecision(4) << kline->volume()
                  << std::endl;
    });
    
    // 订阅响应回调
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "✅ 订阅成功: " << msg["arg"]["channel"].get<std::string>() 
                          << " - " << msg["arg"]["instId"].get<std::string>() << std::endl;
            } else if (event == "error") {
                std::cerr << "❌ 错误: " << msg["msg"].get<std::string>() << std::endl;
            }
        }
    });
    
    // ==================== 连接 ====================
    std::cout << "\n正在连接..." << std::endl;
    if (!ws->connect()) {
        std::cerr << "❌ 连接失败" << std::endl;
        return 1;
    }
    std::cout << "✅ 连接成功" << std::endl;
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 批量订阅 ====================
    std::cout << "\n开始订阅K线..." << std::endl;
    
    for (const auto& pair : pairs_to_subscribe) {
        ws->subscribe_kline(pair, interval);
        // 避免发送太快
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  订阅完成，等待K线数据..." << std::endl;
    std::cout << "  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // ==================== 主循环 ====================
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        
        // 每10秒打印统计
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::lock_guard<std::mutex> lock(g_klines_mutex);
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "收到K线数: " << g_kline_count.load() << std::endl;
        std::cout << "活跃币种: " << g_latest_klines.size() << "/" << pairs_to_subscribe.size() << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n取消订阅..." << std::endl;
    for (const auto& pair : pairs_to_subscribe) {
        ws->unsubscribe_kline(pair, interval);
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    
    ws->disconnect();
    
    // ==================== 最终统计 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到K线: " << g_kline_count.load() << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

