/**
 * @file test_okx_ws_order.cpp
 * @brief 测试OKX WebSocket下单接口
 * 
 * 功能测试：
 * - WebSocket连接和登录
 * - 单笔下单
 * - 批量下单
 * - 订单状态订阅
 */

#include "adapters/okx/okx_websocket.h"
#include "trading/order.h"
#include <iostream>
#include <vector>
#include <thread>
#include <chrono>
#include <condition_variable>
#include <atomic>

using namespace trading;
using namespace trading::okx;

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket下单测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // ==================== API密钥配置 ====================
    // 请在此处填入您的OKX API密钥
    std::string api_key = "5dee6507-e02d-4bfd-9558-d81783d84cb7";           // 替换为您的 API Key
    std::string secret_key = "9B0E54A9843943331EFD0C40547179C8";     // 替换为您的 Secret Key
    std::string passphrase = "Wbl20041209..";     // 替换为您的 Passphrase
    
    // 检查是否已配置API密钥
    if (api_key == "YOUR_API_KEY" || secret_key == "YOUR_SECRET_KEY" || passphrase == "YOUR_PASSPHRASE") {
        std::cerr << "❌ 请先在代码中配置您的API密钥" << std::endl;
        std::cerr << "   修改文件: test_okx_ws_order.cpp" << std::endl;
        std::cerr << "   在main()函数开头填入您的API Key、Secret Key和Passphrase" << std::endl;
        return 1;
    }
    
    std::cout << "✅ API密钥已配置" << std::endl;
    std::cout << "   API Key: " << api_key.substr(0, 10) << "..." << std::endl;
    
    // ==================== 步骤1：创建WebSocket客户端并连接 ====================
    
    std::cout << "\n[1] 创建WebSocket客户端（私有频道）..." << std::endl;
    
    // 使用模拟盘
    OKXWebSocket ws(api_key, secret_key, passphrase, true, WsEndpointType::PRIVATE);
    
    // 设置下单响应回调
    std::atomic<int> order_response_count{0};
    std::mutex order_mtx;
    std::condition_variable order_cv;
    
    ws.set_place_order_callback([&](const nlohmann::json& response) {
        std::cout << "\n[下单响应回调]" << std::endl;
        std::cout << "  请求ID: " << response.value("id", "") << std::endl;
        std::cout << "  操作: " << response.value("op", "") << std::endl;
        std::cout << "  响应码: " << response.value("code", "") << std::endl;
        std::cout << "  消息: " << response.value("msg", "") << std::endl;
        
        if (response.contains("data") && !response["data"].empty()) {
            std::cout << "  订单数据:" << std::endl;
            for (const auto& order : response["data"]) {
                std::cout << "    - ordId: " << order.value("ordId", "") << std::endl;
                std::cout << "      clOrdId: " << order.value("clOrdId", "") << std::endl;
                std::cout << "      sCode: " << order.value("sCode", "") << std::endl;
                std::cout << "      sMsg: " << order.value("sMsg", "") << std::endl;
            }
        }
        
        order_response_count++;
        order_cv.notify_one();
    });
    
    // 设置订单更新回调
    ws.set_order_callback([](const Order::Ptr& order) {
        std::cout << "\n[订单更新回调]" << std::endl;
        std::cout << "  订单ID: " << order->order_id() << std::endl;
        std::cout << "  产品: " << order->symbol() << std::endl;
        std::cout << "  方向: " << (order->side() == OrderSide::BUY ? "买入" : "卖出") << std::endl;
        std::cout << "  状态: " << static_cast<int>(order->state()) << std::endl;
        std::cout << "  价格: " << order->price() << std::endl;
        std::cout << "  数量: " << order->quantity() << std::endl;
    });
    
    // 连接WebSocket
    std::cout << "\n[2] 连接到WebSocket服务器..." << std::endl;
    if (!ws.connect()) {
        std::cerr << "❌ 连接失败" << std::endl;
        return 1;
    }
    
    std::cout << "✅ 连接成功" << std::endl;
    
    // 等待连接稳定
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 步骤2：登录 ====================
    
    std::cout << "\n[3] 执行登录..." << std::endl;
    ws.login();
    
    // 等待登录完成
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    if (!ws.is_logged_in()) {
        std::cerr << "❌ 登录失败" << std::endl;
        return 1;
    }
    
    std::cout << "✅ 登录成功" << std::endl;
    
    // ==================== 步骤3：订阅订单频道 ====================
    
    std::cout << "\n[4] 订阅订单频道..." << std::endl;
    ws.subscribe_orders("SPOT");
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 步骤4：单笔下单测试 ====================
    
    std::cout << "\n[5] 测试单笔下单..." << std::endl;
    std::cout << "    产品: BTC-USDT" << std::endl;
    std::cout << "    方向: 买入 (buy)" << std::endl;
    std::cout << "    类型: 限价单 (limit)" << std::endl;
    std::cout << "    数量: 0.001" << std::endl;
    std::cout << "    价格: 40000 (设置低价，避免立即成交)" << std::endl;
    
    std::string req_id1 = ws.place_order_ws(
        "BTC-USDT",           // inst_id
        "cash",               // td_mode
        "buy",                // side
        "limit",              // ord_type
        "0.001",              // sz
        "40000",              // px
        "",                   // ccy
        "wstestorder1",       // cl_ord_id (只能包含字母和数字)
        "testtag"             // tag
    );
    
    if (req_id1.empty()) {
        std::cerr << "❌ 发送下单请求失败" << std::endl;
    } else {
        std::cout << "✅ 下单请求已发送，请求ID: " << req_id1 << std::endl;
    }
    
    // 等待下单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return order_response_count.load() >= 1; });
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 步骤5：市价单测试 ====================
    
    std::cout << "\n[6] 测试市价单下单..." << std::endl;
    std::cout << "    产品: BTC-USDT" << std::endl;
    std::cout << "    方向: 买入 (buy)" << std::endl;
    std::cout << "    类型: 市价单 (market)" << std::endl;
    std::cout << "    数量: 10 USDT" << std::endl;
    
    std::string req_id2 = ws.place_order_ws(
        "BTC-USDT",           // inst_id
        "cash",               // td_mode
        "buy",                // side
        "market",             // ord_type
        "10",                 // sz (10 USDT)
        "",                   // px (市价单不需要价格)
        "",                   // ccy
        "wstestorder2",       // cl_ord_id (只能包含字母和数字)
        "markettest",         // tag
        "",                   // pos_side
        false,                // reduce_only
        "quote_ccy"           // tgt_ccy (使用计价货币)
    );
    
    if (req_id2.empty()) {
        std::cerr << "❌ 发送市价单请求失败" << std::endl;
    } else {
        std::cout << "✅ 市价单请求已发送，请求ID: " << req_id2 << std::endl;
    }
    
    // 等待下单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return order_response_count.load() >= 2; });
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 步骤6：批量下单测试 ====================
    
    std::cout << "\n[7] 测试批量下单..." << std::endl;
    
    std::vector<nlohmann::json> batch_orders;
    
    // 订单1：BTC-USDT限价买单
    nlohmann::json order1 = {
        {"instId", "BTC-USDT"},
        {"tdMode", "cash"},
        {"side", "buy"},
        {"ordType", "limit"},
        {"sz", "0.001"},
        {"px", "41000"},
        {"clOrdId", "wsbatch1"},    // 只能包含字母和数字
        {"tag", "batchtest"}
    };
    batch_orders.push_back(order1);
    
    // 订单2：ETH-USDT限价买单
    nlohmann::json order2 = {
        {"instId", "ETH-USDT"},
        {"tdMode", "cash"},
        {"side", "buy"},
        {"ordType", "limit"},
        {"sz", "0.01"},
        {"px", "2000"},
        {"clOrdId", "wsbatch2"},    // 只能包含字母和数字
        {"tag", "batchtest"}
    };
    batch_orders.push_back(order2);
    
    std::cout << "    订单1: BTC-USDT, 买入, 限价 41000, 数量 0.001" << std::endl;
    std::cout << "    订单2: ETH-USDT, 买入, 限价 2000, 数量 0.01" << std::endl;
    
    std::string req_id3 = ws.place_batch_orders_ws(batch_orders, "batchreq1");  // 只能包含字母和数字
    
    if (req_id3.empty()) {
        std::cerr << "❌ 发送批量下单请求失败" << std::endl;
    } else {
        std::cout << "✅ 批量下单请求已发送，请求ID: " << req_id3 << std::endl;
    }
    
    // 等待批量下单响应
    {
        std::unique_lock<std::mutex> lock(order_mtx);
        order_cv.wait_for(lock, std::chrono::seconds(5), [&]{ return order_response_count.load() >= 3; });
    }
    
    // ==================== 等待订单更新 ====================
    
    std::cout << "\n[8] 等待订单更新推送（10秒）..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(10));
    
    // ==================== 清理 ====================
    
    std::cout << "\n[9] 断开连接..." << std::endl;
    ws.disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  收到下单响应数: " << order_response_count.load() << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

