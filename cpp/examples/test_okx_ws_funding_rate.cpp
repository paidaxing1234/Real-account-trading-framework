/**
 * @file test_okx_ws_funding_rate.cpp
 * @brief OKX WebSocket 资金费率频道测试
 * 
 * 测试功能：
 * - 订阅永续合约资金费率频道
 * - 接收实时资金费率推送（30-90秒推送一次）
 * - 显示资金费率详细信息
 * 
 * 使用公共WebSocket端点 (wss://ws.okx.com:8443/ws/v5/public)
 */

#include "../adapters/okx/okx_websocket.h"
#include <iostream>
#include <iomanip>
#include <csignal>
#include <atomic>
#include <chrono>
#include <thread>
#include <ctime>

using namespace trading::okx;

// 全局退出标志
std::atomic<bool> g_running{true};

// 信号处理函数
void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
}

// 将毫秒时间戳转换为可读时间
std::string timestamp_to_string(int64_t timestamp_ms) {
    time_t timestamp_sec = timestamp_ms / 1000;
    std::tm* tm = std::gmtime(&timestamp_sec);
    
    char buffer[100];
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", tm);
    return std::string(buffer) + " UTC";
}

int main() {
    // 设置信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX WebSocket 资金费率测试" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "连接: wss://ws.okx.com:8443/ws/v5/public" << std::endl;
    std::cout << "频道: funding-rate" << std::endl;
    std::cout << "推送频率: 30-90秒" << std::endl;
    std::cout << "按 Ctrl+C 退出" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    try {
        // 创建公共频道WebSocket（不需要认证）
        auto ws = create_public_ws(false);  // false = 实盘
        
        // 设置资金费率回调
        int msg_count = 0;
        ws->set_funding_rate_callback([&msg_count](const FundingRateData::Ptr& data) {
            msg_count++;
            
            std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
            std::cout << "📊 资金费率推送 #" << msg_count << std::endl;
            std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" << std::endl;
            
            // 基本信息
            std::cout << "🔹 产品信息：" << std::endl;
            std::cout << "   产品ID:           " << data->inst_id << std::endl;
            std::cout << "   产品类型:         " << data->inst_type << std::endl;
            std::cout << "   收取逻辑:         " << data->method << std::endl;
            std::cout << "   公式类型:         " << data->formula_type << std::endl;
            
            std::cout << "\n🔹 资金费率：" << std::endl;
            std::cout << "   当前费率:         " << std::fixed << std::setprecision(8) 
                      << data->funding_rate << " (" << (data->funding_rate * 100) << "%)" << std::endl;
            
            if (data->next_funding_rate != 0.0) {
                std::cout << "   下期预测费率:     " << std::fixed << std::setprecision(8) 
                          << data->next_funding_rate << " (" << (data->next_funding_rate * 100) << "%)" << std::endl;
            }
            
            std::cout << "   费率范围:         " << std::fixed << std::setprecision(8)
                      << data->min_funding_rate << " ~ " << data->max_funding_rate << std::endl;
            
            // 时间信息
            std::cout << "\n🔹 时间信息：" << std::endl;
            std::cout << "   资金费时间:       " << timestamp_to_string(data->funding_time) << std::endl;
            std::cout << "   下期费时间:       " << timestamp_to_string(data->next_funding_time) << std::endl;
            
            // 计算收取频率
            int64_t interval_ms = data->next_funding_time - data->funding_time;
            double interval_hours = interval_ms / (1000.0 * 3600.0);
            std::cout << "   收取频率:         " << std::fixed << std::setprecision(0) 
                      << interval_hours << " 小时" << std::endl;
            
            // 结算信息
            std::cout << "\n🔹 结算信息：" << std::endl;
            std::cout << "   结算状态:         " << data->sett_state << std::endl;
            std::cout << "   结算费率:         " << std::fixed << std::setprecision(8) 
                      << data->sett_funding_rate << " (" << (data->sett_funding_rate * 100) << "%)" << std::endl;
            
            // 其他指标
            if (data->premium != 0.0) {
                std::cout << "\n🔹 其他指标：" << std::endl;
                std::cout << "   溢价指数:         " << std::fixed << std::setprecision(8) 
                          << data->premium << " (" << (data->premium * 100) << "%)" << std::endl;
            }
            
            std::cout << "\n   更新时间:         " << timestamp_to_string(data->timestamp) << std::endl;
            
            // 费率解读
            std::cout << "\n💡 费率解读：" << std::endl;
            if (data->funding_rate > 0) {
                std::cout << "   ⬆️  正费率 - 多头支付空头" << std::endl;
                std::cout << "   持有多头将支付资金费，持有空头将收到资金费" << std::endl;
            } else if (data->funding_rate < 0) {
                std::cout << "   ⬇️  负费率 - 空头支付多头" << std::endl;
                std::cout << "   持有空头将支付资金费，持有多头将收到资金费" << std::endl;
            } else {
                std::cout << "   ➡️  零费率 - 无资金费交换" << std::endl;
            }
            
            std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" << std::endl;
        });
        
        // 连接WebSocket
        std::cout << "正在连接WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功！\n" << std::endl;
        
        // 等待连接稳定
        std::this_thread::sleep_for(std::chrono::seconds(1));
        
        // 订阅多个合约的资金费率
        std::vector<std::string> instruments = {
            "BTC-USDT-SWAP",
            "ETH-USDT-SWAP",
            "BTC-USD-SWAP"
        };
        
        std::cout << "正在订阅资金费率频道..." << std::endl;
        for (const auto& inst : instruments) {
            ws->subscribe_funding_rate(inst);
            std::cout << "  ✓ " << inst << std::endl;
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        std::cout << "\n✅ 订阅成功！等待数据推送..." << std::endl;
        std::cout << "💡 提示：资金费率每30-90秒推送一次\n" << std::endl;
        
        // 主循环
        auto start_time = std::chrono::steady_clock::now();
        int last_msg_count = 0;
        
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            // 每10秒显示一次状态
            auto now = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - start_time).count();
            
            if (elapsed % 10 == 0 && msg_count == last_msg_count) {
                // 如果10秒内没有新消息，显示等待提示
                static int last_elapsed = -1;
                if (elapsed != last_elapsed) {
                    std::cout << "⏳ 运行中... 已接收 " << msg_count << " 条消息 "
                              << "(运行时间: " << elapsed << "秒)" << std::endl;
                    last_elapsed = elapsed;
                }
            }
            last_msg_count = msg_count;
        }
        
        // 清理
        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开连接" << std::endl;
        
        // 统计信息
        std::cout << "\n========================================" << std::endl;
        std::cout << "  统计信息" << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "总接收消息数: " << msg_count << std::endl;
        std::cout << "========================================" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}

