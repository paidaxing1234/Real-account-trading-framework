/**
 * @file test_binance_ws_kline_testnet.cpp
 * @brief Binance WebSocket 测试网(模拟) - 订阅K线流（单项测试）
 *
 * 目标：只测试一件事 —— 订阅K线（kline stream），并打印收到的数据。
 *
 * 说明：
 * - 连接 Binance 测试网行情 WS：wss://stream.testnet.binance.vision/ws
 * - 本项目 WebSocket 默认启用 HTTP 代理 127.0.0.1:7890（见 binance_websocket.cpp）
 *
 * 编译运行：
 *   cd /home/llx/Real-account-trading-framework/cpp/build
 *   cmake .. -DCMAKE_BUILD_TYPE=Release
 *   make test_binance_ws_kline_testnet -j$(nproc)
 *   ./test_binance_ws_kline_testnet
 */

#include "../adapters/binance/binance_websocket.h"
#include "../core/data.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <thread>

using namespace trading::binance;
using namespace trading;

static std::atomic<bool> g_running{true};

static void signal_handler(int signum) {
    std::cout << "\n收到信号 " << signum << "，正在退出..." << std::endl;
    g_running.store(false);
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

    std::cout << "========================================\n";
    std::cout << "  Binance WS Testnet - 订阅K线测试(1m)\n";
    std::cout << "========================================\n";
    std::cout << "网络: Binance 测试网 (模拟)\n";
    std::cout << "连接类型: MARKET\n";
    std::cout << "订阅: btcusdt@kline_1m\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "----------------------------------------\n" << std::endl;

    try {
        BinanceWebSocket ws("", "", WsConnectionType::MARKET, MarketType::SPOT, true);

        std::atomic<int> kline_count{0};

        ws.set_kline_callback([&](const nlohmann::json& data) {
            kline_count.fetch_add(1);
            auto k = data.value("k", nlohmann::json::object());
            std::cout << "[kline] " << k.value("s", "")
                      << " interval=" << k.value("i", "")
                      << " O=" << std::fixed << std::setprecision(2) << std::stod(k.value("o", "0"))
                      << " H=" << std::stod(k.value("h", "0"))
                      << " L=" << std::stod(k.value("l", "0"))
                      << " C=" << std::stod(k.value("c", "0"))
                      << " V=" << std::setprecision(6) << std::stod(k.value("v", "0"))
                      << " closed=" << (k.value("x", false) ? "✅" : "⏳")
                      << " t=" << ts_to_time(k.value("t", 0LL))
                      << std::endl;
        });

        std::cout << "正在连接 WebSocket..." << std::endl;
        if (!ws.connect()) {
            std::cerr << "❌ 连接失败（检查代理/网络/websocketpp 依赖）" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        std::cout << "发送订阅: btcusdt@kline_1m" << std::endl;
        ws.subscribe_kline("btcusdt", "1m");

        // 运行 70 秒，保证至少看到 1 分钟K线的推送（或者 Ctrl+C 退出）
        const auto start = std::chrono::steady_clock::now();
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            if (elapsed >= 70) break;
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws.disconnect();
        std::cout << "✅ 已断开\n" << std::endl;

        std::cout << "收到K线数量: " << kline_count.load() << std::endl;
        if (kline_count.load() == 0) {
            std::cout << "⚠️  70秒内没有收到K线推送：可能订阅未成功或测试网推送较少。\n";
        }

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}


