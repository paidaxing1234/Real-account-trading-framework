/**
 * @file test_okx_positions.cpp
 * @brief 测试OKX WebSocket 持仓频道
 * 
 * 持仓频道：首次订阅按照订阅维度推送数据，此外，当下单、撤单等事件触发时，推送数据
 * 以及按照订阅维度定时推送数据
 * 
 * 编译：cmake --build build --target test_okx_positions
 * 运行：./build/test_okx_positions
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

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 持仓频道测试" << std::endl;
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
    
    // 持仓回调
    ws->set_position_callback([](const nlohmann::json& position_data) {
        g_position_update_count++;
        
        std::cout << "\n📊 [持仓更新 #" << g_position_update_count.load() << "]" << std::endl;
        
        // 检查数据是否为空
        if (!position_data.is_array()) {
            std::cerr << "   ⚠️ 持仓数据格式错误（不是数组）" << std::endl;
            return;
        }
        
        if (position_data.empty()) {
            std::cout << "   ℹ️  当前没有持仓（空数组）" << std::endl;
            std::cout << "   💡 提示：持仓频道只推送有持仓的情况" << std::endl;
            std::cout << "   💡 提示：如果下单后没有持仓，可能不会推送" << std::endl;
            return;
        }
        
        // 打印持仓数据摘要
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
            if (pos.contains("posSide")) {
                std::cout << "     方向: " << pos["posSide"].get<std::string>() << std::endl;
            }
            if (pos.contains("pos")) {
                std::cout << "     持仓数量: " << pos["pos"].get<std::string>() << std::endl;
            }
            if (pos.contains("availPos")) {
                std::cout << "     可平仓数量: " << pos["availPos"].get<std::string>() << std::endl;
            }
            if (pos.contains("avgPx")) {
                std::cout << "     开仓均价: " << pos["avgPx"].get<std::string>() << std::endl;
            }
            if (pos.contains("markPx")) {
                std::cout << "     标记价格: " << pos["markPx"].get<std::string>() << std::endl;
            }
            if (pos.contains("last")) {
                std::cout << "     最新成交价: " << pos["last"].get<std::string>() << std::endl;
            }
            if (pos.contains("upl")) {
                std::cout << "     未实现盈亏: " << pos["upl"].get<std::string>() << std::endl;
            }
            if (pos.contains("uplRatio")) {
                std::cout << "     未实现收益率: " << pos["uplRatio"].get<std::string>() << std::endl;
            }
            if (pos.contains("realizedPnl")) {
                std::cout << "     已实现收益: " << pos["realizedPnl"].get<std::string>() << std::endl;
            }
            if (pos.contains("lever")) {
                std::cout << "     杠杆倍数: " << pos["lever"].get<std::string>() << std::endl;
            }
            if (pos.contains("mgnMode")) {
                std::cout << "     保证金模式: " << pos["mgnMode"].get<std::string>() << std::endl;
            }
            if (pos.contains("margin")) {
                std::cout << "     保证金余额: " << pos["margin"].get<std::string>() << std::endl;
            }
            if (pos.contains("liqPx")) {
                std::cout << "     预估强平价: " << pos["liqPx"].get<std::string>() << std::endl;
            }
        }
    });
    std::cout << "   ✅ 持仓回调已设置" << std::endl;
    
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
        
        // 打印持仓数据推送（完整JSON，用于调试）
        if (msg.contains("data") && msg.contains("arg")) {
            const auto& arg = msg["arg"];
            if (arg.value("channel", "") == "positions") {
                std::string event_type = msg.value("eventType", "");
                std::cout << "\n📥 [持仓数据推送] 事件类型: " << event_type;
                if (msg.contains("curPage") && msg.contains("lastPage")) {
                    std::cout << " | 页码: " << msg["curPage"].get<int>() 
                              << "/" << (msg["lastPage"].get<bool>() ? "最后" : "更多") << std::endl;
                } else {
                    std::cout << std::endl;
                }
                // 打印完整数据（可选，如果数据量大可以注释掉）
                // std::cout << msg.dump(2) << std::endl;
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
    
    // ==================== 订阅持仓频道 ====================
    std::cout << "\n[5] 订阅持仓频道..." << std::endl;
    std::cout << "   方式1: 订阅所有类型持仓（定时推送 + 事件推送）" << std::endl;
    ws->subscribe_positions("ANY");  // 订阅所有类型
    
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // 方式2: 订阅指定类型
    // std::cout << "   方式2: 订阅永续合约持仓..." << std::endl;
    // ws->subscribe_positions("SWAP");
    
    // 方式3: 订阅指定交易品种
    // std::cout << "   方式3: 订阅BTC-USD交易品种..." << std::endl;
    // ws->subscribe_positions("FUTURES", "", "BTC-USD");
    
    // 方式4: 仅事件推送（不定时推送）
    // std::cout << "   方式4: 订阅所有类型持仓（仅事件推送）..." << std::endl;
    // ws->subscribe_positions("ANY", "", "", 0);  // update_interval = 0
    
    // 方式5: 自定义定时推送间隔（2000ms）
    // std::cout << "   方式5: 订阅所有类型持仓（事件推送 + 2秒定时推送）..." << std::endl;
    // ws->subscribe_positions("ANY", "", "", 2000);  // update_interval = 2000
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "     - " << ch << std::endl;
    }
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待持仓数据推送..." << std::endl;
    std::cout << "  💡 提示：首次订阅会立即推送快照数据" << std::endl;
    std::cout << "  💡 提示：下单、撤单等事件会触发推送" << std::endl;
    std::cout << "  💡 提示：系统会定时推送持仓更新" << std::endl;
    std::cout << "\n  ⚠️  重要说明：" << std::endl;
    std::cout << "  - 持仓频道只推送有持仓的情况" << std::endl;
    std::cout << "  - 如果下单后没有持仓（如立即平仓），可能不会推送" << std::endl;
    std::cout << "  - 现货（SPOT）持仓：买入后持有BTC/USDT等资产" << std::endl;
    std::cout << "  - 合约持仓：开仓后持有合约仓位" << std::endl;
    std::cout << "  - 如果数据为空数组，说明当前没有持仓" << std::endl;
    std::cout << "\n  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 主循环
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        
        // 每10秒打印统计
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "收到持仓更新: " << g_position_update_count.load() << " 次" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_positions("ANY");
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_position_update_count.load() << " 次持仓更新" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

