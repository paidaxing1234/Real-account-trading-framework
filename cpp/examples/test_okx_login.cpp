/**
 * @file test_okx_login.cpp
 * @brief 测试OKX WebSocket 登录功能
 * 
 * 编译：cmake --build build --target test_okx_login
 * 运行：./build/test_okx_login
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

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 登录测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // API凭证
    const std::string api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string secret_key = "888CC77C745F1B49E75A992F38929992";
    const std::string passphrase = "Sequence2025.";
    
    // 创建私有频道WebSocket
    std::cout << "\n[1] 创建私有频道WebSocket..." << std::endl;
    auto ws = create_private_ws(api_key, secret_key, passphrase, true);  // true = 模拟盘
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // 设置原始消息回调（查看所有消息）
    bool login_success = false;
    ws->set_raw_message_callback([&login_success](const nlohmann::json& msg) {
        std::cout << "\n[RAW] " << msg.dump(2) << std::endl;
        
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "login") {
                if (msg.value("code", "") == "0") {
                    login_success = true;
                    std::cout << "\n✅ 登录成功！连接ID: " << msg.value("connId", "") << std::endl;
                } else {
                    std::cerr << "\n❌ 登录失败: " << msg.value("msg", "") 
                              << " (code: " << msg.value("code", "") << ")" << std::endl;
                }
            } else if (event == "error") {
                std::cerr << "\n❌ 错误: " << msg.value("msg", "") 
                          << " (code: " << msg.value("code", "") << ")" << std::endl;
            }
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
    
    if (!ws->is_connected()) {
        std::cerr << "❌ 连接未建立" << std::endl;
        return 1;
    }
    
    std::cout << "✅ 连接成功" << std::endl;
    
    // 登录
    std::cout << "\n[3] 发送登录请求..." << std::endl;
    ws->login();
    
    // 等待登录响应
    std::cout << "\n[4] 等待登录响应（5秒）..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(5));
    
    // 检查登录状态
    if (login_success || ws->is_logged_in()) {
        std::cout << "\n✅ 登录测试成功！" << std::endl;
        std::cout << "\n[5] 保持连接10秒..." << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(10));
    } else {
        std::cerr << "\n❌ 登录测试失败" << std::endl;
    }
    
    // 断开连接
    std::cout << "\n[6] 断开连接..." << std::endl;
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return login_success ? 0 : 1;
}

