/**
 * @file test_okx_sprd_trades.cpp
 * @brief 测试OKX WebSocket Spread成交数据频道
 * 
 * Spread成交数据频道：通过订阅 sprd-trades 频道接收与用户成交信息相关的更新
 * 已成交（filled）和被拒绝（rejected）的交易都会通过此频道推送更新
 * 
 * ⚠️ 重要说明：
 * - 此频道只推送Spread订单的成交数据，不推送普通订单的成交
 * - 普通订单的成交需要通过订单频道（orders）来获取，请使用 test_okx_order_fills 测试
 * - 需要使用 business 端点并登录
 * 
 * 编译：cmake --build build --target test_okx_sprd_trades
 * 运行：./build/test_okx_sprd_trades
 */

#include "adapters/okx/okx_websocket.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_trade_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket Spread成交数据频道测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "\n⚠️  重要说明：" << std::endl;
    std::cout << "  - 此频道只推送Spread订单的成交数据" << std::endl;
    std::cout << "  - 普通订单（如BTC-USDT市价单）的成交不在此频道推送" << std::endl;
    std::cout << "  - 普通订单的成交请使用订单频道（orders），运行 test_okx_order_fills" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // API凭证
    const std::string api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string secret_key = "888CC77C745F1B49E75A992F38929992";
    const std::string passphrase = "Sequence2025.";
    
    // ==================== 创建WebSocket（business端点） ====================
    std::cout << "\n[1] 创建Spread成交数据WebSocket（business端点）..." << std::endl;
    auto ws = std::make_unique<OKXWebSocket>(
        api_key, secret_key, passphrase, true, WsEndpointType::BUSINESS
    );
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    std::cout << "\n[2] 设置回调函数..." << std::endl;
    
    // Spread成交数据回调
    ws->set_spread_trade_callback([](const SpreadTradeData::Ptr& trade) {
        g_trade_count++;
        
        std::cout << "\n💹 [Spread成交 #" << g_trade_count.load() << "]" << std::endl;
        std::cout << "   Spread ID: " << trade->sprd_id << std::endl;
        std::cout << "   交易ID: " << trade->trade_id << std::endl;
        std::cout << "   订单ID: " << trade->ord_id << std::endl;
        std::cout << "   客户端ID: " << trade->cl_ord_id << std::endl;
        std::cout << "   标签: " << trade->tag << std::endl;
        std::cout << "   方向: " << trade->side << std::endl;
        std::cout << "   状态: " << trade->state << std::endl;
        std::cout << "   执行类型: " << trade->exec_type << std::endl;
        std::cout << "   成交价: " << trade->fill_px << std::endl;
        std::cout << "   成交数量: " << trade->fill_sz << std::endl;
        std::cout << "   时间戳: " << trade->timestamp << std::endl;
        std::cout << "   交易腿数: " << trade->legs.size() << std::endl;
        
        // 打印每个腿的详情
        for (size_t i = 0; i < trade->legs.size(); i++) {
            const auto& leg = trade->legs[i];
            std::cout << "   腿 #" << (i + 1) << ":" << std::endl;
            std::cout << "     产品: " << leg.inst_id << std::endl;
            std::cout << "     价格: " << leg.px << std::endl;
            std::cout << "     数量: " << leg.sz << std::endl;
            std::cout << "     合约数量: " << leg.sz_cont << std::endl;
            std::cout << "     方向: " << leg.side << std::endl;
            if (leg.fill_pnl != 0.0) {
                std::cout << "     成交收益: " << leg.fill_pnl << std::endl;
            }
            if (leg.fee != 0.0) {
                std::cout << "     手续费: " << leg.fee << " " << leg.fee_ccy << std::endl;
            }
            std::cout << "     交易ID: " << leg.trade_id << std::endl;
        }
    });
    std::cout << "   ✅ Spread成交数据回调已设置" << std::endl;
    
    // 原始消息回调（查看所有消息）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "\n✅ [订阅成功] " << msg["arg"].dump() << std::endl;
            } else if (event == "error") {
                std::cerr << "\n❌ [错误] " << msg.value("msg", "") 
                          << " (code: " << msg.value("code", "") << ")" << std::endl;
            } else if (event == "login") {
                if (msg.value("code", "") == "0") {
                    std::cout << "\n✅ [登录成功] 连接ID: " << msg.value("connId", "") << std::endl;
                } else {
                    std::cerr << "\n❌ [登录失败] " << msg.value("msg", "") << std::endl;
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
    
    // ==================== 登录 ====================
    std::cout << "\n[4] 登录认证..." << std::endl;
    ws->login();
    
    // 等待登录完成
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    if (!ws->is_logged_in()) {
        std::cerr << "❌ 登录失败！请检查API密钥配置" << std::endl;
        ws->disconnect();
        return 1;
    }
    std::cout << "✅ 登录成功" << std::endl;
    
    // ==================== 订阅Spread成交数据频道 ====================
    std::cout << "\n[5] 订阅Spread成交数据频道..." << std::endl;
    std::cout << "   💡 提示：可以订阅所有Spread成交，或指定Spread ID" << std::endl;
    
    // 方式1：订阅所有Spread成交数据
    std::cout << "   订阅所有Spread成交数据..." << std::endl;
    ws->subscribe_sprd_trades();  // 不传参数表示订阅所有
    
    // 方式2：订阅指定Spread ID（示例）
    // std::string sprd_id = "BTC-USDT_BTC-USDT-SWAP";
    // std::cout << "   订阅Spread ID: " << sprd_id << std::endl;
    // ws->subscribe_sprd_trades(sprd_id);
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待Spread成交数据推送..." << std::endl;
    std::cout << "  💡 提示：请在OKX模拟盘创建Spread订单并成交来触发推送" << std::endl;
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
        std::cout << "收到Spread成交推送: " << g_trade_count.load() << " 条" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_sprd_trades();
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_trade_count.load() << " 条Spread成交推送" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

