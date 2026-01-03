/**
 * @file test_binance_ws_mark_price_testnet.cpp
 * @brief Binance 全市场标记价格+资金费率测试（合约测试网）
 * 
 * 订阅：!markPrice@arr@1s
 * 用途：全市场扫描资金费率（适合做资金费套利策略）
 */

#include "../adapters/binance/binance_websocket.h"
#include <iostream>
#include <iomanip>
#include <csignal>
#include <atomic>
#include <chrono>
#include <thread>
#include <map>

using namespace trading::binance;

static std::atomic<bool> g_running{true};

static void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "========================================\n";
    std::cout << "  Binance 全市场标记价格+资金费率测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: FUTURES Testnet (合约测试网)\n";
    std::cout << "订阅: !markPrice@arr@1s\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "用途: 全市场资金费率扫描（适合套利策略）\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "========================================\n" << std::endl;

    try {
        // 创建 FUTURES 行情 WS（测试网）
        auto ws = create_market_ws(MarketType::FUTURES, true);

        std::atomic<int> update_count{0};
        std::map<std::string, MarkPriceData::Ptr> latest_prices;

        ws->set_mark_price_callback([&](const MarkPriceData::Ptr& mp) {
            update_count.fetch_add(1);
            latest_prices[mp->symbol] = mp;
        });

        std::cout << "正在连接 WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        std::cout << "发送订阅: !markPrice@arr@1s（全市场，1秒更新）" << std::endl;
        ws->subscribe_all_mark_prices(1000);

        // 每 5 秒打印一次统计 + 前 10 个交易对
        auto last_print = std::chrono::steady_clock::now();
        
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            
            auto now = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - last_print).count();
            
            if (elapsed >= 5) {
                last_print = now;
                
                std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
                std::cout << "📊 统计: 收到 " << update_count.load() << " 条更新"
                          << " | 交易对数: " << latest_prices.size() << "\n";
                std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
                
                // 显示前 10 个交易对（按资金费率排序，从高到低）
                std::vector<std::pair<std::string, MarkPriceData::Ptr>> sorted;
                for (const auto& kv : latest_prices) {
                    sorted.push_back(kv);
                }
                
                // 按资金费率降序排序
                std::sort(sorted.begin(), sorted.end(), 
                    [](const auto& a, const auto& b) {
                        return a.second->funding_rate > b.second->funding_rate;
                    });
                
                std::cout << "\n前 10 个交易对（按资金费率排序）：\n";
                std::cout << std::string(90, '-') << "\n";
                std::cout << std::setw(12) << std::left << "交易对"
                          << std::setw(14) << "标记价格"
                          << std::setw(14) << "指数价格"
                          << std::setw(16) << "资金费率(%)"
                          << "下次资金时间\n";
                std::cout << std::string(90, '-') << "\n";
                
                int count = 0;
                for (const auto& kv : sorted) {
                    if (count >= 10) break;
                    
                    const auto& mp = kv.second;
                    
                    // 转换时间戳为可读格式
                    time_t next_funding_t = mp->next_funding_time / 1000;
                    char time_buf[32];
                    strftime(time_buf, sizeof(time_buf), "%H:%M", gmtime(&next_funding_t));
                    
                    std::cout << std::setw(12) << std::left << mp->symbol
                              << std::setw(14) << std::fixed << std::setprecision(2) << mp->mark_price
                              << std::setw(14) << mp->index_price
                              << std::setw(16) << std::setprecision(4) << (mp->funding_rate * 100)
                              << time_buf << "\n";
                    
                    count++;
                }
                std::cout << std::string(90, '-') << "\n";
            }
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开\n" << std::endl;
        
        std::cout << "最终统计：收到 " << update_count.load() << " 条更新"
                  << "，共 " << latest_prices.size() << " 个交易对\n";

    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}

