/**
 * @file test_binance_ws_trading.cpp
 * @brief Binance WebSocket 交易API测试（示例）
 *
 * 说明：
 * - 需要 BINANCE_API_KEY / BINANCE_SECRET_KEY
 * - 可用 BINANCE_TESTNET=1 走测试网（模拟）
 * - 本示例默认不做真实下单，只演示连接 + 回调打印
 */

#include "../adapters/binance/binance_websocket.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <string>
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

static std::string getenv_or_empty(const char* k) {
    const char* v = std::getenv(k);
    return (v && *v) ? std::string(v) : std::string();
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    const bool is_testnet = env_truthy("BINANCE_TESTNET");
    const std::string api_key = getenv_or_empty("BINANCE_API_KEY");
    const std::string secret_key = getenv_or_empty("BINANCE_SECRET_KEY");

    std::cout << "========================================\n";
    std::cout << "  Binance WebSocket 交易API测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: " << (is_testnet ? "TESTNET(模拟)" : "MAINNET(实盘)") << "\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "========================================\n\n";

    if (api_key.empty() || secret_key.empty()) {
        std::cerr << "❌ 请先设置环境变量 BINANCE_API_KEY / BINANCE_SECRET_KEY\n";
        return 1;
    }

    try {
        auto ws = create_trading_ws(api_key, secret_key, MarketType::SPOT, is_testnet);

        ws->set_order_response_callback([](const nlohmann::json& resp) {
            std::cout << "\n[ws-response] " << resp.dump() << "\n" << std::endl;
        });

        std::cout << "正在连接WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功" << std::endl;

        std::cout << "\n⚠️ 本示例默认不下单。需要下单请自行调用 ws->place_order_ws(...)\n";
        std::cout << "按 Ctrl+C 退出...\n" << std::endl;

        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开" << std::endl;

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}


