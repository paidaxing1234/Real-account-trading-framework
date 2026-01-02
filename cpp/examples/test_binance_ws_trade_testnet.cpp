/**
 * @file test_binance_ws_trade_testnet.cpp
 * @brief Binance WebSocket 测试网(模拟) - 订阅逐笔成交流（单项测试）
 *
 * 目标：只测试一件事 —— 订阅逐笔成交（trade stream），并打印收到的数据。
 *
 * 说明：
 * - 行情订阅本身不需要 API_KEY，但你要求“用模拟账户”，这里会连接 Binance 测试网：
 *   wss://testnet.binance.vision/ws
 * - 本项目的 WebSocket 实现默认启用 HTTP 代理 127.0.0.1:7890（见 binance_websocket.cpp）。
 *   如果你的环境没有该代理，请先启动代理服务，否则连接会失败。
 *
 * 可选环境变量（不写死在代码里）：
 *   BINANCE_API_KEY=xxx
 *   BINANCE_SECRET_KEY=yyy
 *
 * 编译运行：
 *   cd /home/llx/Real-account-trading-framework/cpp/build
 *   cmake .. -DCMAKE_BUILD_TYPE=Release
 *   make test_binance_ws_trade_testnet -j$(nproc)
 *   ./test_binance_ws_trade_testnet
 */

#include "../adapters/binance/binance_websocket.h"
#include "../core/data.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
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

static std::string getenv_or_empty(const char* k) {
    const char* v = std::getenv(k);
    return (v && *v) ? std::string(v) : std::string();
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    const std::string api_key = getenv_or_empty("BINANCE_API_KEY");
    const std::string secret_key = getenv_or_empty("BINANCE_SECRET_KEY");

    std::cout << "========================================\n";
    std::cout << "  Binance WS Testnet - 订阅逐笔成交测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: Binance 测试网 (模拟)\n";
    std::cout << "连接类型: MARKET\n";
    std::cout << "订阅: btcusdt@trade\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    if (!api_key.empty()) {
        std::cout << "密钥: 已提供 BINANCE_API_KEY（行情订阅无需密钥）\n";
    } else {
        std::cout << "密钥: 未提供（行情订阅无需密钥）\n";
    }
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "----------------------------------------\n" << std::endl;

    try {
        // 使用测试网（模拟）
        BinanceWebSocket ws(api_key, secret_key, WsConnectionType::MARKET, MarketType::SPOT, true);

        std::atomic<int> trade_count{0};

        ws.set_trade_callback([&](const TradeData::Ptr& trade) {
            trade_count.fetch_add(1);
            const std::string side = trade->side().value_or("?");
            std::cout << "[trade] " << trade->symbol()
                      << " px=" << std::fixed << std::setprecision(2) << trade->price()
                      << " qty=" << std::setprecision(6) << trade->quantity()
                      << " side=" << side
                      << " t=" << ts_to_time(trade->timestamp())
                      << std::endl;
        });

        std::cout << "正在连接 WebSocket..." << std::endl;
        if (!ws.connect()) {
            std::cerr << "❌ 连接失败（检查代理/网络/websocketpp 依赖）" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功\n" << std::endl;

        // 等连接稳定再订阅
        std::this_thread::sleep_for(std::chrono::seconds(1));

        std::cout << "发送订阅: btcusdt@trade" << std::endl;
        ws.subscribe_trade("btcusdt");

        // 运行 30 秒或 Ctrl+C 退出
        const auto start = std::chrono::steady_clock::now();
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            if (elapsed >= 30) break;
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws.disconnect();
        std::cout << "✅ 已断开\n" << std::endl;

        std::cout << "收到逐笔成交数量: " << trade_count.load() << std::endl;

        if (trade_count.load() == 0) {
            std::cout << "⚠️  30秒内没有收到成交推送：可能是网络/代理/订阅未成功，或测试网流量较少。\n";
        }

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}


