/**
 * @file test_okx_account.cpp
 * @brief 测试OKX WebSocket 账户频道
 * 
 * 账户频道：首次订阅按照订阅维度推送数据，此外，当下单、撤单、成交等事件触发时，推送数据
 * 以及按照订阅维度定时推送数据
 * 
 * 编译：cmake --build build --target test_okx_account
 * 运行：./build/test_okx_account
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
std::atomic<uint64_t> g_account_update_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 账户频道测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // API凭证
    const std::string api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string secret_key = "888CC77C745F1B49E75A992F38929992";
    const std::string passphrase = "Sequence2025.";
    
    // ==================== 创建私有频道WebSocket ====================
    std::cout << "\n[1] 创建私有频道WebSocket..." << std::endl;
    auto ws = create_private_ws(api_key, secret_key, passphrase, true);  // true = 模拟盘
    std::cout << "   URL: " << ws->get_url() << std::endl;
    
    // ==================== 设置回调 ====================
    std::cout << "\n[2] 设置回调函数..." << std::endl;
    
    // 账户回调
    ws->set_account_callback([](const nlohmann::json& account_data) {
        g_account_update_count++;
        
        std::cout << "\n💰 [账户更新 #" << g_account_update_count.load() << "]" << std::endl;
        
        // 打印账户数据摘要
        if (account_data.is_array() && !account_data.empty()) {
            const auto& first = account_data[0];
            
            if (first.contains("totalEq")) {
                std::cout << "   总权益(USD): " << first["totalEq"].get<std::string>() << std::endl;
            }
            if (first.contains("availEq")) {
                std::cout << "   可用保证金(USD): " << first["availEq"].get<std::string>() << std::endl;
            }
            if (first.contains("uTime")) {
                std::cout << "   更新时间: " << first["uTime"].get<std::string>() << std::endl;
            }
            
            // 打印币种详情
            if (first.contains("details") && first["details"].is_array()) {
                std::cout << "   币种详情 (" << first["details"].size() << " 个币种):" << std::endl;
                for (const auto& detail : first["details"]) {
                    if (detail.contains("ccy")) {
                        std::cout << "     - " << detail["ccy"].get<std::string>();
                        if (detail.contains("eq")) {
                            std::cout << " | 总权益: " << detail["eq"].get<std::string>();
                        }
                        if (detail.contains("availBal")) {
                            std::cout << " | 可用余额: " << detail["availBal"].get<std::string>();
                        }
                        std::cout << std::endl;
                    }
                }
            }
        }
    });
    std::cout << "   ✅ 账户回调已设置" << std::endl;
    
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
        
        // 打印账户数据推送（完整JSON）
        if (msg.contains("data") && msg.contains("arg")) {
            const auto& arg = msg["arg"];
            if (arg.value("channel", "") == "account") {
                std::cout << "\n📥 [账户数据推送] " << msg.dump(2) << std::endl;
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
    
    // ==================== 订阅账户频道 ====================
    std::cout << "\n[5] 订阅账户频道..." << std::endl;
    std::cout << "   方式1: 订阅所有币种（定时推送 + 事件推送）" << std::endl;
    ws->subscribe_account();  // 订阅所有币种
    
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // 方式2: 订阅指定币种
    // std::cout << "   方式2: 订阅BTC币种..." << std::endl;
    // ws->subscribe_account("BTC");
    
    // 方式3: 仅事件推送（不定时推送）
    // std::cout << "   方式3: 订阅所有币种（仅事件推送）..." << std::endl;
    // ws->subscribe_account("", 0);  // update_interval = 0
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "     - " << ch << std::endl;
    }
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待账户数据推送..." << std::endl;
    std::cout << "  💡 提示：首次订阅会立即推送快照数据" << std::endl;
    std::cout << "  💡 提示：下单、撤单、成交等事件会触发推送" << std::endl;
    std::cout << "  💡 提示：系统会定时推送账户更新" << std::endl;
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
        std::cout << "收到账户更新: " << g_account_update_count.load() << " 次" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_account();
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_account_update_count.load() << " 次账户更新" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

