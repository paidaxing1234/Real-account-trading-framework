/**
 * @file test_okx_order_fills.cpp
 * @brief 测试OKX WebSocket 普通订单成交推送
 * 
 * ⚠️ 重要说明：
 * - Spread成交数据频道（sprd-trades）只推送Spread订单的成交，不推送普通订单的成交
 * - 普通订单的成交需要通过订单频道（orders）来获取
 * - 订单频道会推送订单状态变化，包括：live（等待成交）、partially_filled（部分成交）、filled（完全成交）
 * 
 * 编译：cmake --build build --target test_okx_order_fills
 * 运行：./build/test_okx_order_fills
 */

#include "adapters/okx/okx_websocket.h"
#include "core/order.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_order_count{0};
std::atomic<uint64_t> g_filled_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 普通订单成交推送测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "\n⚠️  重要说明：" << std::endl;
    std::cout << "  - Spread成交数据频道（sprd-trades）只推送Spread订单的成交" << std::endl;
    std::cout << "  - 普通订单的成交需要通过订单频道（orders）来获取" << std::endl;
    std::cout << "  - 订单频道会推送订单状态变化，包括成交信息" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // API凭证
    const std::string api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string secret_key = "888CC77C745F1B49E75A992F38929992";
    const std::string passphrase = "Sequence2025.";
    
    // ==================== 创建私有频道WebSocket ====================
    std::cout << "[1] 创建私有频道WebSocket..." << std::endl;
    auto ws = create_private_ws(api_key, secret_key, passphrase, true);  // true = 模拟盘
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    std::cout << "\n[2] 设置回调函数..." << std::endl;
    
    // 订单回调（接收所有订单状态变化，包括成交）
    ws->set_order_callback([](const Order::Ptr& order) {
        g_order_count++;
        
        std::cout << "\n📦 [订单更新 #" << g_order_count.load() << "]" << std::endl;
        std::cout << "   产品: " << order->symbol() << std::endl;
        std::cout << "   订单ID: " << order->exchange_order_id() << std::endl;
        std::cout << "   客户端ID: " << order->client_order_id() << std::endl;
        std::cout << "   方向: " << (order->side() == OrderSide::BUY ? "买入" : "卖出") << std::endl;
        std::cout << "   类型: " << order_type_to_string(order->order_type()) << std::endl;
        std::cout << "   价格: " << order->price() << std::endl;
        std::cout << "   数量: " << order->quantity() << std::endl;
        std::cout << "   状态: " << order_state_to_string(order->state()) << std::endl;
        std::cout << "   已成交: " << order->filled_quantity() << " / " << order->quantity() << std::endl;
        
        // 检查是否成交
        if (order->filled_price() > 0) {
            std::cout << "   ✅ 成交价: " << order->filled_price() << std::endl;
            g_filled_count++;
            std::cout << "   🎉 订单已成交！" << std::endl;
        }
        
        if (order->state() == OrderState::FILLED) {
            std::cout << "   ✅ 订单完全成交！" << std::endl;
        } else if (order->state() == OrderState::PARTIALLY_FILLED) {
            std::cout << "   ⚠️  订单部分成交" << std::endl;
        }
    });
    std::cout << "   ✅ 订单回调已设置" << std::endl;
    
    // 原始消息回调（打印所有消息）
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
        
        // 打印订单数据推送（完整JSON，用于调试）
        if (msg.contains("data") && msg.contains("arg")) {
            const auto& arg = msg["arg"];
            if (arg.value("channel", "") == "orders") {
                std::cout << "\n📥 [订单数据推送] " << msg.dump(2) << std::endl;
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
    
    // ==================== 订阅订单频道 ====================
    std::cout << "\n[5] 订阅订单频道..." << std::endl;
    std::cout << "   订阅现货订单（SPOT）..." << std::endl;
    ws->subscribe_orders("SPOT");
    
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    std::cout << "   订阅合约订单（SWAP）..." << std::endl;
    ws->subscribe_orders("SWAP");
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "     - " << ch << std::endl;
    }
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待订单推送..." << std::endl;
    std::cout << "  💡 提示：请在OKX模拟盘手动下单测试" << std::endl;
    std::cout << "  💡 提示：订单频道会推送订单状态变化" << std::endl;
    std::cout << "  💡 提示：包括 live -> partially_filled -> filled" << std::endl;
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
        std::cout << "收到订单更新: " << g_order_count.load() << " 次" << std::endl;
        std::cout << "订单成交次数: " << g_filled_count.load() << " 次" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_orders("SPOT");
    ws->unsubscribe_orders("SWAP");
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_order_count.load() << " 次订单更新" << std::endl;
    std::cout << "  订单成交: " << g_filled_count.load() << " 次" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

