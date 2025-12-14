/**
 * @file test_okx_private.cpp
 * @brief OKX WebSocket 私有频道测试
 * 
 * 测试私有频道的订阅功能：
 * - 登录认证
 * - 订单频道 (orders)
 * - 持仓频道 (positions)
 * - 账户频道 (account)
 * 
 * 编译: cmake --build build --target test_okx_private
 * 运行: ./build/test_okx_private
 */

#include "adapters/okx/okx_websocket.h"
#include "core/order.h"
#include <iostream>
#include <thread>
#include <chrono>

int main() {
    using namespace trading;
    using namespace trading::okx;
    
    std::cout << "========================================" << std::endl;
    std::cout << "   OKX WebSocket 私有频道测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // ==================== 配置API凭证 ====================
    // 请替换为您的OKX模拟盘API密钥
    const std::string api_key = "your_api_key";
    const std::string secret_key = "your_secret_key";
    const std::string passphrase = "your_passphrase";
    
    // 检查是否已配置
    if (api_key == "your_api_key") {
        std::cerr << "\n❌ 请先配置您的API密钥！" << std::endl;
        std::cerr << "   编辑文件: examples/test_okx_private.cpp" << std::endl;
        std::cerr << "   修改 api_key, secret_key, passphrase" << std::endl;
        return 1;
    }
    
    // ==================== 创建私有频道WebSocket ====================
    std::cout << "\n1️⃣  创建私有频道WebSocket..." << std::endl;
    auto ws = create_private_ws(api_key, secret_key, passphrase, true);  // true = 模拟盘
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    std::cout << "\n2️⃣  设置回调函数..." << std::endl;
    
    // 订单回调
    ws->set_order_callback([](const Order::Ptr& order) {
        std::cout << "\n📦 [订单更新]" << std::endl;
        std::cout << "   订单ID: " << order->exchange_order_id() << std::endl;
        std::cout << "   客户端ID: " << order->client_order_id() << std::endl;
        std::cout << "   产品: " << order->symbol() << std::endl;
        std::cout << "   方向: " << (order->side() == OrderSide::BUY ? "买入" : "卖出") << std::endl;
        std::cout << "   类型: " << order_type_to_string(order->order_type()) << std::endl;
        std::cout << "   价格: " << order->price() << std::endl;
        std::cout << "   数量: " << order->quantity() << std::endl;
        std::cout << "   状态: " << order_state_to_string(order->state()) << std::endl;
        std::cout << "   已成交: " << order->filled_quantity() << std::endl;
        if (order->filled_price() > 0) {
            std::cout << "   成交价: " << order->filled_price() << std::endl;
        }
    });
    
    // 持仓回调
    ws->set_position_callback([](const nlohmann::json& pos) {
        std::cout << "\n📊 [持仓更新]" << std::endl;
        std::cout << "   产品: " << pos.value("instId", "N/A") << std::endl;
        std::cout << "   方向: " << pos.value("posSide", "N/A") << std::endl;
        std::cout << "   数量: " << pos.value("pos", "0") << std::endl;
        std::cout << "   可用: " << pos.value("availPos", "0") << std::endl;
        std::cout << "   开仓均价: " << pos.value("avgPx", "0") << std::endl;
        std::cout << "   未实现盈亏: " << pos.value("upl", "0") << std::endl;
        std::cout << "   杠杆: " << pos.value("lever", "N/A") << std::endl;
    });
    
    // 账户回调
    ws->set_account_callback([](const nlohmann::json& acc) {
        std::cout << "\n💰 [账户更新]" << std::endl;
        std::cout << "   总权益(USD): " << acc.value("totalEq", "N/A") << std::endl;
        std::cout << "   有效保证金: " << acc.value("adjEq", "N/A") << std::endl;
        std::cout << "   保证金率: " << acc.value("mgnRatio", "N/A") << std::endl;
        
        // 显示各币种详情
        if (acc.contains("details") && acc["details"].is_array()) {
            for (const auto& detail : acc["details"]) {
                std::cout << "   [" << detail.value("ccy", "?") << "] "
                          << "余额: " << detail.value("cashBal", "0")
                          << ", 可用: " << detail.value("availBal", "0")
                          << std::endl;
            }
        }
    });
    
    // 原始消息回调（调试用）
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        // 取消注释以查看所有原始消息
        // std::cout << "[RAW] " << msg.dump(2) << std::endl;
    });
    
    // ==================== 连接 ====================
    std::cout << "\n3️⃣  建立连接..." << std::endl;
    if (!ws->connect()) {
        std::cerr << "❌ 连接失败！" << std::endl;
        return 1;
    }
    std::cout << "✅ 连接成功" << std::endl;
    
    // ==================== 登录 ====================
    std::cout << "\n4️⃣  登录认证..." << std::endl;
    ws->login();
    
    // 等待登录完成
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    if (!ws->is_logged_in()) {
        std::cerr << "❌ 登录失败！请检查API密钥配置" << std::endl;
        ws->disconnect();
        return 1;
    }
    std::cout << "✅ 登录成功" << std::endl;
    
    // ==================== 订阅私有频道 ====================
    std::cout << "\n5️⃣  订阅私有频道..." << std::endl;
    
    // 订阅现货订单
    std::cout << "   订阅现货订单..." << std::endl;
    ws->subscribe_orders("SPOT");
    
    // 订阅合约订单
    std::cout << "   订阅合约订单..." << std::endl;
    ws->subscribe_orders("SWAP");
    
    // 订阅合约持仓
    std::cout << "   订阅合约持仓..." << std::endl;
    ws->subscribe_positions("SWAP");
    
    // 订阅账户更新
    std::cout << "   订阅账户更新..." << std::endl;
    ws->subscribe_account();
    
    // ==================== 等待数据 ====================
    std::cout << "\n6️⃣  等待推送数据 (60秒)..." << std::endl;
    std::cout << "   💡 提示: 请在OKX模拟盘手动下单或修改持仓来触发推送" << std::endl;
    std::cout << "   📝 按 Ctrl+C 可提前退出" << std::endl;
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "   - " << ch << std::endl;
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(60));
    
    // ==================== 清理 ====================
    std::cout << "\n7️⃣  取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_orders("SPOT");
    ws->unsubscribe_orders("SWAP");
    ws->unsubscribe_positions("SWAP");
    ws->unsubscribe_account();
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n✅ 测试完成！" << std::endl;
    
    return 0;
}

