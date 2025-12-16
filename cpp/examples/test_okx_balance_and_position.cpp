/**
 * @file test_okx_balance_and_position.cpp
 * @brief 测试OKX WebSocket 账户余额和持仓频道（balance_and_position）
 * 
 * 该频道获取账户余额和持仓信息，首次订阅按照订阅维度推送数据，
 * 此外，当成交、资金划转等事件触发时，推送数据。
 * 适用于尽快获取账户现金余额和仓位资产变化的信息。
 * 
 * 事件类型（eventType）：
 *   - snapshot: 首推快照
 *   - delivered: 交割
 *   - exercised: 行权
 *   - transferred: 划转
 *   - filled: 成交
 *   - liquidation: 强平
 *   - claw_back: 穿仓补偿
 *   - adl: ADL自动减仓
 *   - funding_fee: 资金费
 *   - adjust_margin: 调整保证金
 *   - set_leverage: 设置杠杆
 *   - interest_deduction: 扣息
 *   - settlement: 交割结算
 * 
 * 编译：cmake --build build --target test_okx_balance_and_position
 * 运行：./build/test_okx_balance_and_position
 */

#include "adapters/okx/okx_websocket.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include <iomanip>

using namespace trading;
using namespace trading::okx;

// 运行标志
std::atomic<bool> g_running{true};
std::atomic<uint64_t> g_update_count{0};

// 信号处理
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在停止..." << std::endl;
    g_running.store(false);
}

// 获取事件类型的中文描述
std::string get_event_type_desc(const std::string& event_type) {
    if (event_type == "snapshot") return "首推快照";
    if (event_type == "delivered") return "交割";
    if (event_type == "exercised") return "行权";
    if (event_type == "transferred") return "划转";
    if (event_type == "filled") return "成交";
    if (event_type == "liquidation") return "强平";
    if (event_type == "claw_back") return "穿仓补偿";
    if (event_type == "adl") return "ADL自动减仓";
    if (event_type == "funding_fee") return "资金费";
    if (event_type == "adjust_margin") return "调整保证金";
    if (event_type == "set_leverage") return "设置杠杆";
    if (event_type == "interest_deduction") return "扣息";
    if (event_type == "settlement") return "交割结算";
    return "未知类型";
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 账户余额和持仓频道测试" << std::endl;
    std::cout << "  (balance_and_position)" << std::endl;
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
    
    // 账户余额和持仓回调
    ws->set_balance_and_position_callback([](const nlohmann::json& data) {
        g_update_count++;
        
        std::cout << "\n💰📊 [余额+持仓更新 #" << g_update_count.load() << "]" << std::endl;
        
        // 解析事件类型
        std::string p_time = data.value("pTime", "");
        std::string event_type = data.value("eventType", "");
        std::string event_desc = get_event_type_desc(event_type);
        
        std::cout << "   事件类型: " << event_type << " (" << event_desc << ")" << std::endl;
        if (!p_time.empty()) {
            std::cout << "   推送时间: " << p_time << std::endl;
        }
        
        // 打印余额数据
        if (data.contains("balData") && data["balData"].is_array()) {
            std::cout << "   📌 余额数据 (" << data["balData"].size() << " 个币种):" << std::endl;
            for (const auto& bal : data["balData"]) {
                std::string ccy = bal.value("ccy", "");
                std::string cash_bal = bal.value("cashBal", "");
                std::string u_time = bal.value("uTime", "");
                std::cout << "      - " << std::setw(6) << ccy << ": " << cash_bal;
                if (!u_time.empty()) {
                    std::cout << " (更新时间: " << u_time << ")";
                }
                std::cout << std::endl;
            }
        }
        
        // 打印持仓数据
        if (data.contains("posData") && data["posData"].is_array() && !data["posData"].empty()) {
            std::cout << "   📌 持仓数据 (" << data["posData"].size() << " 个仓位):" << std::endl;
            for (const auto& pos : data["posData"]) {
                std::string pos_id = pos.value("posId", "");
                std::string inst_id = pos.value("instId", "");
                std::string inst_type = pos.value("instType", "");
                std::string mgn_mode = pos.value("mgnMode", "");
                std::string pos_side = pos.value("posSide", "");
                std::string pos_amt = pos.value("pos", "");
                std::string avg_px = pos.value("avgPx", "");
                std::string ccy = pos.value("ccy", "");
                
                std::cout << "      - " << inst_id << " (" << inst_type << ")" << std::endl;
                std::cout << "        持仓ID: " << pos_id << std::endl;
                std::cout << "        模式: " << mgn_mode << " | 方向: " << pos_side << std::endl;
                std::cout << "        数量: " << pos_amt << " | 均价: " << avg_px << std::endl;
                if (!ccy.empty()) {
                    std::cout << "        保证金币种: " << ccy << std::endl;
                }
            }
        }
        
        // 打印成交数据
        if (data.contains("trades") && data["trades"].is_array() && !data["trades"].empty()) {
            std::cout << "   📌 成交数据 (" << data["trades"].size() << " 笔):" << std::endl;
            for (const auto& trade : data["trades"]) {
                std::string inst_id = trade.value("instId", "");
                std::string trade_id = trade.value("tradeId", "");
                std::cout << "      - " << inst_id << " | 成交ID: " << trade_id << std::endl;
            }
        }
        
        std::cout << "   ----------------------------------------" << std::endl;
    });
    std::cout << "   ✅ 账户余额和持仓回调已设置" << std::endl;
    
    // 原始消息回调（打印订阅和错误消息）
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
    
    // ==================== 订阅频道 ====================
    std::cout << "\n[5] 订阅账户余额和持仓频道..." << std::endl;
    ws->subscribe_balance_and_position();
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // 显示已订阅的频道
    auto channels = ws->get_subscribed_channels();
    std::cout << "\n   已订阅频道:" << std::endl;
    for (const auto& ch : channels) {
        std::cout << "     - " << ch << std::endl;
    }
    
    // ==================== 等待推送 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  等待账户余额和持仓数据推送..." << std::endl;
    std::cout << "\n  📌 balance_and_position 频道说明：" << std::endl;
    std::cout << "  1. 首次订阅：推送快照数据（snapshot）" << std::endl;
    std::cout << "  2. 事件触发：成交、划转、强平等操作会触发推送" << std::endl;
    std::cout << "  3. 数据内容：同时包含余额（balData）和持仓（posData）" << std::endl;
    std::cout << "  4. 增量推送：只推送变化的币种余额和持仓" << std::endl;
    std::cout << "\n  💡 提示：" << std::endl;
    std::cout << "  - 您可以在OKX模拟盘下单测试推送" << std::endl;
    std::cout << "  - 划转资金也会触发推送" << std::endl;
    std::cout << "\n  按 Ctrl+C 停止" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 主循环
    auto start_time = std::chrono::steady_clock::now();
    
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(30));
        
        // 每30秒打印统计
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time).count();
        
        std::cout << "\n--- 统计 (运行 " << elapsed << " 秒) ---" << std::endl;
        std::cout << "收到余额+持仓更新: " << g_update_count.load() << " 次" << std::endl;
        std::cout << "----------------------------\n" << std::endl;
    }
    
    // ==================== 清理 ====================
    std::cout << "\n[6] 取消订阅并断开连接..." << std::endl;
    ws->unsubscribe_balance_and_position();
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    ws->disconnect();
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "  总计收到: " << g_update_count.load() << " 次更新" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

