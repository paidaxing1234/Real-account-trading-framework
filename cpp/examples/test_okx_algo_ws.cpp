/**
 * @file test_okx_algo_ws.cpp
 * @brief OKX 策略委托订单WebSocket测试程序
 * 
 * 测试两个策略委托订单频道：
 * 1. orders-algo - 策略委托订单频道（conditional, oco, trigger, chase）
 * 2. algo-advance - 高级策略委托订单频道（iceberg, twap, move_order_stop）
 * 
 * 编译运行：
 *   cd build && make test_okx_algo_ws && ./test_okx_algo_ws
 */

#include <iostream>
#include <chrono>
#include <thread>
#include <signal.h>
#include "../adapters/okx/okx_websocket.h"

using namespace trading::okx;

// 全局退出标志
volatile sig_atomic_t g_running = 1;

void signal_handler(int signum) {
    (void)signum;
    std::cout << "\n收到停止信号..." << std::endl;
    g_running = 0;
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  OKX 策略委托订单WebSocket测试\n";
    std::cout << "========================================\n";
    
    // 设置信号处理
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // API配置 (模拟盘)
    std::string api_key = "5dee6507-e02d-4bfd-9558-d81783d84cb7";
    std::string secret_key = "9B0E54A9843943331EFD0C40547179C8";
    std::string passphrase = "Wbl20041209..";
    bool is_testnet = true;
    
    std::cout << "\n配置信息:\n";
    std::cout << "  API Key: " << api_key.substr(0, 8) << "...\n";
    std::cout << "  模式: " << (is_testnet ? "模拟盘" : "实盘") << "\n\n";
    
    try {
        // 创建WebSocket客户端（使用business端点）
        OKXWebSocket ws(api_key, secret_key, passphrase, is_testnet, WsEndpointType::BUSINESS);
        
        // 设置原始消息回调
        ws.set_raw_message_callback([](const nlohmann::json& msg) {
            // 解析消息
            if (msg.contains("arg") && msg.contains("data")) {
                auto& arg = msg["arg"];
                std::string channel = arg.value("channel", "");
                
                if (channel == "orders-algo") {
                    std::cout << "\n========================================\n";
                    std::cout << "  策略委托订单更新 (orders-algo)\n";
                    std::cout << "========================================\n";
                    std::cout << msg.dump(2) << "\n";
                    
                    // 解析订单信息
                    if (msg["data"].is_array() && !msg["data"].empty()) {
                        auto& order = msg["data"][0];
                        std::cout << "\n订单详情:\n";
                        std::cout << "  algoId: " << order.value("algoId", "") << "\n";
                        std::cout << "  instId: " << order.value("instId", "") << "\n";
                        std::cout << "  ordType: " << order.value("ordType", "") << "\n";
                        std::cout << "  side: " << order.value("side", "") << "\n";
                        std::cout << "  state: " << order.value("state", "") << "\n";
                        std::cout << "  sz: " << order.value("sz", "") << "\n";
                    }
                }
                else if (channel == "algo-advance") {
                    std::cout << "\n========================================\n";
                    std::cout << "  高级策略委托订单更新 (algo-advance)\n";
                    std::cout << "========================================\n";
                    std::cout << msg.dump(2) << "\n";
                    
                    // 解析订单信息
                    if (msg["data"].is_array() && !msg["data"].empty()) {
                        auto& order = msg["data"][0];
                        std::cout << "\n订单详情:\n";
                        std::cout << "  algoId: " << order.value("algoId", "") << "\n";
                        std::cout << "  instId: " << order.value("instId", "") << "\n";
                        std::cout << "  ordType: " << order.value("ordType", "") << "\n";
                        std::cout << "  side: " << order.value("side", "") << "\n";
                        std::cout << "  state: " << order.value("state", "") << "\n";
                        std::cout << "  sz: " << order.value("sz", "") << "\n";
                    }
                }
            }
            else if (msg.contains("event")) {
                std::string event = msg.value("event", "");
                if (event == "subscribe") {
                    std::cout << "✓ 订阅成功: " << msg.dump() << "\n";
                }
                else if (event == "error") {
                    std::cout << "✗ 订阅失败: " << msg.dump() << "\n";
                }
            }
        });
        
        // 连接WebSocket
        std::cout << "连接到WebSocket...\n";
        if (!ws.connect()) {
            std::cerr << "连接失败!\n";
            return 1;
        }
        
        std::cout << "WebSocket已连接\n";
        
        // 等待连接稳定
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // 登录
        std::cout << "\n正在登录...\n";
        ws.login();
        
        // 等待登录完成
        std::this_thread::sleep_for(std::chrono::seconds(3));
        
        if (!ws.is_logged_in()) {
            std::cerr << "登录失败!\n";
            return 1;
        }
        
        std::cout << "登录成功\n";
        
        // ==================== 订阅策略委托订单频道 ====================
        std::cout << "\n========================================\n";
        std::cout << "  订阅策略委托订单频道\n";
        std::cout << "========================================\n";
        
        // 订阅SWAP的所有策略委托订单
        std::cout << "\n1. 订阅SWAP的所有策略委托订单...\n";
        ws.subscribe_orders_algo("SWAP");
        
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // 订阅BTC-USDT-SWAP的策略委托订单
        std::cout << "\n2. 订阅BTC-USDT-SWAP的策略委托订单...\n";
        ws.subscribe_orders_algo("SWAP", "BTC-USDT-SWAP");
        
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // ==================== 订阅高级策略委托订单频道 ====================
        std::cout << "\n========================================\n";
        std::cout << "  订阅高级策略委托订单频道\n";
        std::cout << "========================================\n";
        
        // 订阅SWAP的所有高级策略委托订单
        std::cout << "\n3. 订阅SWAP的所有高级策略委托订单...\n";
        ws.subscribe_algo_advance("SWAP");
        
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // 订阅BTC-USDT-SWAP的高级策略委托订单
        std::cout << "\n4. 订阅BTC-USDT-SWAP的高级策略委托订单...\n";
        ws.subscribe_algo_advance("SWAP", "BTC-USDT-SWAP");
        
        // ==================== 保持运行，监听推送 ====================
        std::cout << "\n========================================\n";
        std::cout << "  WebSocket已启动，等待推送...\n";
        std::cout << "  按Ctrl+C停止\n";
        std::cout << "========================================\n\n";
        
        std::cout << "提示:\n";
        std::cout << "  - orders-algo 首次订阅不推送，只有事件触发时推送\n";
        std::cout << "  - algo-advance 首次订阅会推送现有订单\n";
        std::cout << "  - 可以通过REST API下单/撤单来触发推送\n\n";
        
        // 保持运行
        while (g_running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        // 清理
        std::cout << "\n正在断开连接...\n";
        ws.disconnect();
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << "\n";
        return 1;
    }
    
    std::cout << "\n✅ 测试完成!\n\n";
    return 0;
}

