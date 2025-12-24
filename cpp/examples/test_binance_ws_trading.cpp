/**
 * @file test_binance_ws_trading.cpp
 * @brief Binance WebSocket 交易API测试
 * 
 * 测试通过WebSocket进行低延迟交易
 * 
 * 功能：
 * - WebSocket下单（比REST API快5-10倍）
 * - WebSocket撤单
 * - WebSocket查询订单
 * 
 * 参考: https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/websocket-api/trading-requests
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

using namespace trading::binance;

// 全局退出标志
std::atomic<bool> g_running{true};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
}

int main() {
    // 设置信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    std::cout << "========================================" << std::endl;
    std::cout << "  Binance WebSocket 交易API测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "连接: wss://ws-api.binance.com/ws-api/v3" << std::endl;
    std::cout << "功能: 低延迟交易（比REST API快5-10倍）" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // API密钥（请替换为你的密钥）
    const std::string API_KEY = "YOUR_API_KEY";
    const std::string SECRET_KEY = "YOUR_SECRET_KEY";
    
    if (API_KEY == "YOUR_API_KEY") {
        std::cout << "⚠️  警告：请设置你的API密钥！" << std::endl;
        std::cout << "     在代码中将 YOUR_API_KEY 和 YOUR_SECRET_KEY 替换为实际值\n" << std::endl;
        std::cout << "💡 提示：API密钥可在币安官网申请" << std::endl;
        std::cout << "     主网: https://www.binance.com" << std::endl;
        std::cout << "     测试网: https://testnet.binance.vision/\n" << std::endl;
        return 1;
    }
    
    try {
        // 创建WebSocket交易API客户端
        auto ws = create_trading_ws(API_KEY, SECRET_KEY, MarketType::SPOT, false);
        
        // 设置订单响应回调
        int response_count = 0;
        ws->set_order_response_callback([&response_count](const nlohmann::json& response) {
            response_count++;
            
            std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
            std::cout << "📨 收到响应 #" << response_count << std::endl;
            std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" << std::endl;
            
            std::cout << "请求ID: " << response["id"] << std::endl;
            std::cout << "状态码: " << response["status"] << std::endl;
            
            if (response["status"] == 200) {
                auto result = response["result"];
                std::cout << "\n✅ 操作成功！\n" << std::endl;
                std::cout << "交易对:       " << result.value("symbol", "") << std::endl;
                std::cout << "订单ID:       " << result.value("orderId", 0) << std::endl;
                std::cout << "客户订单ID:   " << result.value("clientOrderId", "") << std::endl;
                std::cout << "订单状态:     " << result.value("status", "") << std::endl;
                std::cout << "订单类型:     " << result.value("type", "") << std::endl;
                std::cout << "方向:         " << result.value("side", "") << std::endl;
                std::cout << "价格:         " << result.value("price", "") << std::endl;
                std::cout << "数量:         " << result.value("origQty", "") << std::endl;
                std::cout << "已成交数量:   " << result.value("executedQty", "") << std::endl;
                
            } else {
                std::cout << "\n❌ 操作失败！\n" << std::endl;
                if (response.contains("error")) {
                    auto error = response["error"];
                    std::cout << "错误码: " << error.value("code", 0) << std::endl;
                    std::cout << "错误信息: " << error.value("msg", "") << std::endl;
                }
            }
            
            std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" << std::endl;
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
        
        // 测试1：查询服务器时间（测试连接）
        std::cout << "1️⃣  测试：查询服务器时间" << std::endl;
        // TODO: 实现time.get请求
        
        // 测试2：WebSocket限价下单（演示）
        std::cout << "\n2️⃣  测试：WebSocket限价下单（演示）" << std::endl;
        std::cout << "   ⚠️  注意：这是一个真实下单示例" << std::endl;
        std::cout << "   为了安全，默认不执行" << std::endl;
        std::cout << "   如需测试下单，请取消注释以下代码\n" << std::endl;
        
        /*
        // 取消注释以下代码来测试下单
        std::string req_id = ws->place_order_ws(
            "BTCUSDT",
            OrderSide::BUY,
            OrderType::LIMIT,
            "0.001",     // 数量
            "20000"      // 价格（远低于市价，不会成交）
        );
        
        std::cout << "下单请求已发送，请求ID: " << req_id << std::endl;
        std::cout << "等待响应..." << std::endl;
        
        // 等待响应
        std::this_thread::sleep_for(std::chrono::seconds(3));
        */
        
        // 测试3：查询挂单
        std::cout << "3️⃣  测试：查询当前挂单" << std::endl;
        std::cout << "   TODO: 实现openOrders.status请求\n" << std::endl;
        
        // 提示信息
        std::cout << "========================================" << std::endl;
        std::cout << "  测试连接信息" << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "连接类型: 交易API (低延迟)" << std::endl;
        std::cout << "市场类型: 现货" << std::endl;
        std::cout << "总响应数: " << response_count << std::endl;
        std::cout << "========================================" << std::endl;
        
        std::cout << "\n💡 WebSocket交易API优势：" << std::endl;
        std::cout << "   ✅ 延迟更低：10-50ms（REST API: 100-300ms）" << std::endl;
        std::cout << "   ✅ 保持长连接：无需频繁建立HTTP连接" << std::endl;
        std::cout << "   ✅ 适合高频交易：算法交易、做市商" << std::endl;
        std::cout << "   ✅ 实时响应：立即收到订单状态更新" << std::endl;
        
        std::cout << "\n按 Ctrl+C 退出..." << std::endl;
        
        // 保持运行
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        // 清理
        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开连接" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}

