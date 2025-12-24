/**
 * @file test_binance_ws_market.cpp
 * @brief Binance WebSocket 行情推送测试
 * 
 * 测试实时行情数据订阅：
 * - 逐笔成交流
 * - K线数据流
 * - Ticker行情流
 * - 深度数据流
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "../adapters/binance/binance_websocket.h"
#include <iostream>
#include <iomanip>
#include <csignal>
#include <atomic>
#include <chrono>
#include <thread>
#include <ctime>

using namespace trading::binance;

// 全局退出标志
std::atomic<bool> g_running{true};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
}

// 时间戳转字符串
std::string timestamp_to_string(int64_t timestamp_ms) {
    time_t t = timestamp_ms / 1000;
    std::tm* tm = std::gmtime(&t);
    
    char buffer[100];
    std::strftime(buffer, sizeof(buffer), "%H:%M:%S", tm);
    return std::string(buffer);
}

int main() {
    // 设置信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    std::cout << "========================================" << std::endl;
    std::cout << "  Binance WebSocket 行情推送测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "连接: wss://stream.binance.com:9443/ws" << std::endl;
    std::cout << "功能: 实时行情数据订阅" << std::endl;
    std::cout << "按 Ctrl+C 退出" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    try {
        // 创建行情WebSocket客户端（无需API密钥）
        auto ws = create_market_ws(MarketType::SPOT, false);
        
        // 统计变量
        int trade_count = 0;
        int kline_count = 0;
        int ticker_count = 0;
        
        // 设置逐笔成交回调
        ws->set_trade_callback([&trade_count](const TradeData::Ptr& trade) {
            trade_count++;
            std::cout << "🔸 [成交] " << trade->symbol()
                      << " | 价格: $" << std::fixed << std::setprecision(2) << trade->price()
                      << " | 数量: " << std::setprecision(4) << trade->quantity()
                      << " | " << (trade->side() == ::trading::OrderSide::BUY ? "买入" : "卖出")
                      << " | " << timestamp_to_string(trade->timestamp())
                      << std::endl;
        });
        
        // 设置K线回调
        ws->set_kline_callback([&kline_count](const KlineData::Ptr& kline) {
            kline_count++;
            std::cout << "📊 [K线] " << kline->symbol()
                      << " | O:" << std::fixed << std::setprecision(2) << kline->open()
                      << " H:" << kline->high()
                      << " L:" << kline->low()
                      << " C:" << kline->close()
                      << " | V:" << std::setprecision(4) << kline->volume()
                      << " | " << timestamp_to_string(kline->timestamp())
                      << std::endl;
        });
        
        // 设置Ticker回调
        ws->set_ticker_callback([&ticker_count](const TickerData::Ptr& ticker) {
            ticker_count++;
            std::cout << "📈 [Ticker] " << ticker->symbol()
                      << " | 价格: $" << std::fixed << std::setprecision(2) << ticker->last_price()
                      << " | 买: $" << ticker->bid_price()
                      << " | 卖: $" << ticker->ask_price()
                      << " | 24h量: " << std::setprecision(2) << ticker->volume_24h()
                      << std::endl;
        });
        
        // 连接WebSocket
        std::cout << "正在连接WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功！\n" << std::endl;
        
        // 等待连接稳定
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // 订阅多个数据流
        std::cout << "正在订阅数据流..." << std::endl;
        
        // 订阅BTC和ETH的行情
        std::vector<std::string> symbols = {"btcusdt", "ethusdt"};
        
        for (const auto& symbol : symbols) {
            ws->subscribe_trade(symbol);        // 逐笔成交
            ws->subscribe_kline(symbol, "1m");  // 1分钟K线
            ws->subscribe_ticker(symbol);       // Ticker行情
            
            std::cout << "  ✓ " << symbol << " (成交+K线+Ticker)" << std::endl;
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }
        
        // 订阅深度（前20档）
        ws->subscribe_depth("btcusdt", 20, 1000);
        std::cout << "  ✓ btcusdt depth@20" << std::endl;
        
        std::cout << "\n✅ 订阅成功！等待数据推送...\n" << std::endl;
        
        // 主循环
        auto start_time = std::chrono::steady_clock::now();
        
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            // 每10秒显示一次统计
            auto now = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - start_time).count();
            
            if (elapsed % 10 == 0) {
                static int last_elapsed = -1;
                if (elapsed != last_elapsed && elapsed > 0) {
                    std::cout << "\n📊 [统计] 运行: " << elapsed << "秒 "
                              << "| 成交: " << trade_count 
                              << " | K线: " << kline_count
                              << " | Ticker: " << ticker_count << "\n" << std::endl;
                    last_elapsed = elapsed;
                }
            }
        }
        
        // 清理
        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开连接" << std::endl;
        
        // 最终统计
        std::cout << "\n========================================" << std::endl;
        std::cout << "  最终统计" << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "总成交数: " << trade_count << std::endl;
        std::cout << "总K线数: " << kline_count << std::endl;
        std::cout << "总Ticker数: " << ticker_count << std::endl;
        std::cout << "========================================" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}

