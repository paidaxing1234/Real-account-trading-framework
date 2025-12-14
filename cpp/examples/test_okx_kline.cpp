/**
 * @file test_okx_kline.cpp
 * @brief 测试OKX WebSocket K线订阅
 * 
 * 功能：
 * 1. 连接OKX WebSocket (business端点)
 * 2. 订阅BTC-USDT 1分钟K线
 * 3. 打印接收到的K线数据
 * 
 * 编译：
 *   cd build && cmake .. && make test_okx_kline
 * 
 * 运行：
 *   ./test_okx_kline
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>

#include "adapters/okx/okx_websocket.h"

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket K线订阅测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 创建WebSocket客户端（使用business端点）
    // K线数据必须使用 WsEndpointType::BUSINESS 端点
    auto ws = create_business_ws(true);  // true = 使用模拟盘
    
    std::cout << "\n[1] WebSocket URL: " << ws->get_url() << std::endl;
    
    // 设置K线回调
    ws->set_kline_callback([](const KlineData::Ptr& kline) {
        std::cout << "\n📊 [K线] " << kline->symbol() 
                  << " | " << kline->interval()
                  << " | O:" << kline->open()
                  << " H:" << kline->high()
                  << " L:" << kline->low()
                  << " C:" << kline->close()
                  << " V:" << kline->volume()
                  << " | ts:" << kline->timestamp()
                  << std::endl;
    });
    
    // 设置原始消息回调（调试用）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        // 只打印部分信息，避免刷屏
        if (msg.contains("event")) {
            std::cout << "[RAW] Event: " << msg.dump() << std::endl;
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
    
    // 订阅K线
    std::cout << "\n[3] 订阅K线..." << std::endl;
    
    // 订阅多个时间周期
    ws->subscribe_kline("BTC-USDT", KlineInterval::MINUTE_1);  // 1分钟
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    ws->subscribe_kline("BTC-USDT", "5m");  // 5分钟（字符串版本）
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    ws->subscribe_kline("ETH-USDT", KlineInterval::MINUTE_1);  // ETH 1分钟
    
    std::cout << "\n[4] 已订阅频道:" << std::endl;
    for (const auto& channel : ws->get_subscribed_channels()) {
        std::cout << "  - " << channel << std::endl;
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待K线数据..." << std::endl;
    std::cout << "  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 主循环
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    
    // 取消订阅
    std::cout << "\n[5] 取消订阅..." << std::endl;
    ws->unsubscribe_kline("BTC-USDT", KlineInterval::MINUTE_1);
    ws->unsubscribe_kline("BTC-USDT", "5m");
    ws->unsubscribe_kline("ETH-USDT", KlineInterval::MINUTE_1);
    
    // 断开连接
    std::cout << "\n[6] 断开连接..." << std::endl;
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

