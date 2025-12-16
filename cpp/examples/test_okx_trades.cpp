/**
 * @file test_okx_trades.cpp
 * @brief 测试OKX WebSocket 交易频道（trades）
 * 
 * 获取最近的成交数据，有成交数据就推送，每次推送可能聚合多条成交数据。
 * 根据每个taker订单的不同成交价格，不同成交来源推送消息，
 * 并使用count字段表示聚合的订单匹配数量。
 * 
 * 编译：cmake --build build --target test_okx_trades
 * 运行：./build/test_okx_trades
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
std::atomic<uint64_t> g_trade_count{0};
std::atomic<uint64_t> g_total_trades{0};  // 聚合的总成交数

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 交易频道测试 (trades)" << std::endl;
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
    
    // 成交回调
    ws->set_trade_callback([](const TradeData::Ptr& trade) {
        g_trade_count++;
        
        // 获取方向的中文描述
        std::string side_str = (trade->side() == "buy") ? "买入" : "卖出";
        std::string side_emoji = (trade->side() == "buy") ? "🟢" : "🔴";
        
        std::cout << "\n" << side_emoji << " [成交 #" << g_trade_count.load() << "] " << trade->symbol() << std::endl;
        std::cout << std::fixed << std::setprecision(4);
        std::cout << "   成交ID: " << trade->trade_id() << std::endl;
        std::cout << "   价格: " << trade->price() << std::endl;
        std::cout << "   数量: " << trade->quantity() << std::endl;
        std::cout << "   方向: " << side_str << " (" << trade->side() << ")" << std::endl;
        std::cout << "   时间戳: " << trade->timestamp() << std::endl;
        
        // 打印额外信息（如果可用）
        // count字段表示聚合的订单匹配数量
        // source字段表示订单来源：0=普通订单，1=流动性增强计划订单
    });
    std::cout << "   ✅ 成交回调已设置" << std::endl;
    
    // 原始消息回调（用于显示详细的成交信息）
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
        
        // 打印成交的额外信息（count, source, seqId）
        if (msg.contains("data") && msg.contains("arg")) {
            const auto& arg = msg["arg"];
            if (arg.value("channel", "") == "trades") {
                for (const auto& trade_data : msg["data"]) {
                    std::string count = trade_data.value("count", "1");
                    std::string source = trade_data.value("source", "0");
                    
                    int count_num = std::stoi(count);
                    g_total_trades += count_num;
                    
                    if (count_num > 1) {
                        std::cout << "   [聚合] 本次推送聚合了 " << count << " 笔成交" << std::endl;
                    }
                    
                    if (source != "0") {
                        std::cout << "   [来源] 流动性增强计划订单" << std::endl;
                    }
                    
                    if (trade_data.contains("seqId")) {
                        std::cout << "   [序号] seqId: " << trade_data["seqId"] << std::endl;
                    }
                }
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
    
    // ==================== 订阅交易频道 ====================
    std::cout << "\n[4] 订阅交易频道..." << std::endl;
    
    // 订阅多个产品
    std::vector<std::string> symbols = {"BTC-USDT", "ETH-USDT"};
    
    for (const auto& symbol : symbols) {
        std::cout << "   订阅: " << symbol << std::endl;
        ws->subscribe_trades(symbol);
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
    std::cout << "  等待成交数据推送..." << std::endl;
    std::cout << "\n  交易频道说明：" << std::endl;
    std::cout << "  1. 有成交数据就推送，无成交时不推送" << std::endl;
    std::cout << "  2. 每次推送可能聚合多条成交数据" << std::endl;
    std::cout << "  3. count字段表示聚合的订单匹配数量" << std::endl;
    std::cout << "\n  推送数据包含：" << std::endl;
    std::cout << "  - tradeId: 最新成交ID" << std::endl;
    std::cout << "  - px: 成交价格" << std::endl;
    std::cout << "  - sz: 成交数量" << std::endl;
    std::cout << "  - side: 吃单方向 (buy/sell)" << std::endl;
    std::cout << "  - count: 聚合的订单数" << std::endl;
    std::cout << "  - source: 订单来源" << std::endl;
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
        std::cout << "收到成交推送: " << g_trade_count.load() << " 次" << std::endl;
        std::cout << "聚合成交总数: " << g_total_trades.load() << " 笔" << std::endl;
        if (elapsed > 0) {
            double rate = static_cast<double>(g_trade_count.load()) / elapsed;
            std::cout << "平均推送频率: " << std::fixed << std::setprecision(2) << rate << " 次/秒" << std::endl;
        }
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[5] 取消订阅并断开连接..." << std::endl;
    for (const auto& symbol : symbols) {
        ws->unsubscribe_trades(symbol);
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_trade_count.load() << " 次成交推送" << std::endl;
    std::cout << "  聚合成交: " << g_total_trades.load() << " 笔" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}
