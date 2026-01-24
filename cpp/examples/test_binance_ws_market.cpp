/**
 * @file test_binance_ws_market.cpp
 * @brief Binance WebSocket 行情推送测试
 *
 * 说明：
 * - 可通过环境变量 BINANCE_TESTNET=1 切换到测试网（模拟）。
 * - 本项目 WebSocket 默认启用 HTTP 代理 127.0.0.1:7890。
 */

#include "../adapters/binance/binance_websocket.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <thread>

using namespace trading::binance;

static std::atomic<bool> g_running{true};

static void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
}

static bool env_truthy(const char* key) {
    const char* v = std::getenv(key);
    if (!v) return false;
    std::string s(v);
    for (auto& c : s) c = (char)std::tolower((unsigned char)c);
    return (s == "1" || s == "true" || s == "yes" || s == "on");
}

static std::string ts_to_time(int64_t timestamp_ms) {
    std::time_t t = static_cast<std::time_t>(timestamp_ms / 1000);
    std::tm* tm = std::gmtime(&t);
    if (!tm) return "";
    char buf[32];
    std::strftime(buf, sizeof(buf), "%H:%M:%S", tm);
    return std::string(buf);
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    const bool is_testnet = env_truthy("BINANCE_TESTNET");

    std::cout << "========================================\n";
    std::cout << "  Binance WebSocket 行情推送测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: " << (is_testnet ? "TESTNET(模拟)" : "MAINNET(实盘)") << "\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "========================================\n" << std::endl;

    try {
        // 行情推送无需密钥
        auto ws = create_market_ws(MarketType::SPOT, is_testnet);

        std::atomic<int> trade_count{0};
        std::atomic<int> kline_count{0};
        std::atomic<int> ticker_count{0};

        ws->set_trade_callback([&](const nlohmann::json& trade) {
            trade_count.fetch_add(1);
            std::cout << "[trade] " << trade.value("s", "")
                      << " px=" << std::fixed << std::setprecision(2) << std::stod(trade.value("p", "0"))
                      << " qty=" << std::setprecision(6) << std::stod(trade.value("q", "0"))
                      << " t=" << ts_to_time(trade.value("T", 0LL))
                      << std::endl;
        });

        ws->set_kline_callback([&](const nlohmann::json& data) {
            kline_count.fetch_add(1);
            auto k = data.value("k", nlohmann::json::object());
            std::cout << "[kline] " << k.value("s", "")
                      << " O=" << std::fixed << std::setprecision(2) << std::stod(k.value("o", "0"))
                      << " H=" << std::stod(k.value("h", "0"))
                      << " L=" << std::stod(k.value("l", "0"))
                      << " C=" << std::stod(k.value("c", "0"))
                      << " V=" << std::setprecision(4) << std::stod(k.value("v", "0"))
                      << " t=" << ts_to_time(k.value("t", 0LL))
                      << std::endl;
        });

        ws->set_ticker_callback([&](const nlohmann::json& ticker) {
            ticker_count.fetch_add(1);
            std::cout << "[ticker] " << ticker.value("s", "")
                      << " last=" << std::fixed << std::setprecision(2) << std::stod(ticker.value("c", "0"))
                      << " bid=" << std::stod(ticker.value("b", "0"))
                      << " ask=" << std::stod(ticker.value("a", "0"))
                      << std::endl;
        });

        std::cout << "正在连接WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功！\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        std::cout << "正在订阅数据流..." << std::endl;
        ws->subscribe_trade("btcusdt");
        ws->subscribe_kline("btcusdt", "1m");
        ws->subscribe_ticker("btcusdt");
        std::cout << "  ✓ btcusdt (trade + kline + ticker)\n" << std::endl;

        auto start = std::chrono::steady_clock::now();
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));

            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();

            if (elapsed > 0 && elapsed % 10 == 0) {
                static int last = -1;
                if (last != (int)elapsed) {
                    last = (int)elapsed;
                    std::cout << "\n[stats] " << elapsed << "s"
                              << " trade=" << trade_count.load()
                              << " kline=" << kline_count.load()
                              << " ticker=" << ticker_count.load()
                              << "\n"
                              << std::endl;
                }
            }
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开连接" << std::endl;

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
}
