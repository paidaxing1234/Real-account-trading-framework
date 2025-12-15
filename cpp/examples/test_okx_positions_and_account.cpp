/**
 * @file test_okx_positions_and_account.cpp
 * @brief 综合测试：同时订阅持仓频道和账户频道
 * 
 * 持仓频道：推送合约和杠杆的持仓（SWAP/FUTURES/OPTION/MARGIN）
 * 账户频道：推送账户余额变化（包括现货余额）
 * 
 * 编译：cmake --build build --target test_okx_positions_and_account
 * 运行：./build/test_okx_positions_and_account
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
std::atomic<uint64_t> g_position_update_count{0};
std::atomic<uint64_t> g_account_update_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 持仓+账户频道综合测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "\n📌 说明：" << std::endl;
    std::cout << "  - 持仓频道：推送合约和杠杆持仓（SWAP/FUTURES/OPTION/MARGIN）" << std::endl;
    std::cout << "  - 账户频道：推送账户余额变化（包括现货余额）" << std::endl;
    std::cout << "  - 现货（SPOT）买入后，余额变化在账户频道中推送" << std::endl;
    std::cout << "  - 合约开仓后，持仓变化在持仓频道中推送" << std::endl;
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
    
    // 持仓回调
    ws->set_position_callback([](const nlohmann::json& position_data) {
        g_position_update_count++;
        
        std::cout << "\n📊 [持仓更新 #" << g_position_update_count.load() << "]" << std::endl;
        
        if (!position_data.is_array() || position_data.empty()) {
            std::cout << "   ℹ️  当前没有合约/杠杆持仓" << std::endl;
            return;
        }
        
        std::cout << "   持仓数量: " << position_data.size() << " 个" << std::endl;
        
        for (size_t i = 0; i < position_data.size(); i++) {
            const auto& pos = position_data[i];
            std::cout << "\n   持仓 #" << (i + 1) << ":" << std::endl;
            
            if (pos.contains("instId")) {
                std::cout << "     产品: " << pos["instId"].get<std::string>() << std::endl;
            }
            if (pos.contains("instType")) {
                std::cout << "     类型: " << pos["instType"].get<std::string>() << std::endl;
            }
            if (pos.contains("pos")) {
                std::cout << "     持仓数量: " << pos["pos"].get<std::string>() << std::endl;
            }
            if (pos.contains("avgPx")) {
                std::cout << "     开仓均价: " << pos["avgPx"].get<std::string>() << std::endl;
            }
            if (pos.contains("upl")) {
                std::cout << "     未实现盈亏: " << pos["upl"].get<std::string>() << std::endl;
            }
        }
    });
    std::cout << "   ✅ 持仓回调已设置" << std::endl;
    
    // 账户回调
    ws->set_account_callback([](const nlohmann::json& account_data) {
        g_account_update_count++;
        
        std::cout << "\n💰 [账户更新 #" << g_account_update_count.load() << "]" << std::endl;
        
        if (account_data.is_array() && !account_data.empty()) {
            const auto& first = account_data[0];
            
            if (first.contains("totalEq")) {
                std::cout << "   总权益(USD): " << first["totalEq"].get<std::string>() << std::endl;
            }
            if (first.contains("availEq")) {
                std::cout << "   可用保证金(USD): " << first["availEq"].get<std::string>() << std::endl;
            }
            
            // 打印币种详情（现货余额）
            if (first.contains("details") && first["details"].is_array()) {
                std::cout << "   币种余额 (" << first["details"].size() << " 个币种):" << std::endl;
                for (const auto& detail : first["details"]) {
                    if (detail.contains("ccy")) {
                        std::string ccy = detail["ccy"].get<std::string>();
                        std::string eq = detail.value("eq", "0");
                        std::string avail_bal = detail.value("availBal", "0");
                        
                        // 只显示余额不为0的币种
                        if (eq != "0" || avail_bal != "0") {
                            std::cout << "     - " << ccy 
                                      << " | 总权益: " << eq
                                      << " | 可用余额: " << avail_bal << std::endl;
                        }
                    }
                }
            }
        }
    });
    std::cout << "   ✅ 账户回调已设置" << std::endl;
    
    // 原始消息回调
    ws->set_raw_message_callback([](const nlohmann::json& msg) {
        if (msg.contains("event")) {
            std::string event = msg["event"];
            if (event == "subscribe") {
                std::cout << "\n✅ [订阅成功] " << msg["arg"].dump() << std::endl;
            } else if (event == "error") {
                std::cerr << "\n❌ [错误] " << msg.value("msg", "") 
                          << " (code: " << msg.value("code", "") << ")" << std::endl;
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
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    if (!ws->is_connected()) {
        std::cerr << "❌ 连接未建立" << std::endl;
        return 1;
    }
    std::cout << "✅ 连接成功" << std::endl;
    
    // ==================== 登录 ====================
    std::cout << "\n[4] 登录认证..." << std::endl;
    ws->login();
    
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    if (!ws->is_logged_in()) {
        std::cerr << "❌ 登录失败！请检查API密钥配置" << std::endl;
        ws->disconnect();
        return 1;
    }
    std::cout << "✅ 登录成功" << std::endl;
    
    // ==================== 订阅频道 ====================
    std::cout << "\n[5] 订阅频道..." << std::endl;
    
    // 订阅持仓频道
    std::cout << "   订阅持仓频道（合约/杠杆持仓）..." << std::endl;
    ws->subscribe_positions("ANY");
    
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // 订阅账户频道
    std::cout << "   订阅账户频道（现货余额）..." << std::endl;
    ws->subscribe_account();
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待数据推送..." << std::endl;
    std::cout << "  💡 现货买入：查看账户频道（余额变化）" << std::endl;
    std::cout << "  💡 合约开仓：查看持仓频道（持仓变化）" << std::endl;
    std::cout << "  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 主循环
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "持仓更新: " << g_position_update_count.load() << " 次" << std::endl;
        std::cout << "账户更新: " << g_account_update_count.load() << " 次" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_positions("ANY");
    ws->unsubscribe_account();
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  持仓更新: " << g_position_update_count.load() << " 次" << std::endl;
    std::cout << "  账户更新: " << g_account_update_count.load() << " 次" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

