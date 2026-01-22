/**
 * @file test_binance_ws_all_market_testnet.cpp
 * @brief Binance WebSocket 测试网(模拟) - 行情推送全量订阅一把测完
 *
 * 覆盖（MARKET连接）：
 * - subscribe_trade
 * - subscribe_kline
 * - subscribe_ticker
 * - subscribe_mini_ticker
 * - subscribe_depth
 * - subscribe_book_ticker
 *
 * 注意：
 * - WebSocket 默认启用 HTTP 代理 127.0.0.1:7890
 * - 输出做了限频（避免刷屏）
 */

#include "../adapters/binance/binance_websocket.h"
#include "../core/data.h"

#include <atomic>
#include <chrono>
#include <csignal>
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

static bool should_print_every(std::atomic<uint64_t>& counter, uint64_t every) {
    const uint64_t n = counter.fetch_add(1) + 1;
    return (n % every) == 0;
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "========================================\n";
    std::cout << "  Binance WS Testnet - 行情推送全量订阅测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: Binance 测试网 (模拟)\n";
    std::cout << "连接类型: MARKET\n";
    std::cout << "交易对: btcusdt\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "----------------------------------------\n" << std::endl;

    try {
        BinanceWebSocket ws("", "", WsConnectionType::MARKET, MarketType::SPOT, true);

        std::atomic<uint64_t> trade_n{0};
        std::atomic<uint64_t> kline_n{0};
        std::atomic<uint64_t> ticker_n{0};
        std::atomic<uint64_t> depth_n{0};
        std::atomic<uint64_t> book_n{0};

        // trade：每 10 条打印 1 条
        ws.set_trade_callback([&](const nlohmann::json& t) {
            if (!should_print_every(trade_n, 10)) return;
            std::cout << "[trade] px=" << std::fixed << std::setprecision(2) << std::stod(t.value("p", "0"))
                      << " qty=" << std::setprecision(6) << std::stod(t.value("q", "0"))
                      << std::endl;
        });

        // kline：每 1 条都打印（频率低）
        ws.set_kline_callback([&](const nlohmann::json& data) {
            kline_n.fetch_add(1);
            auto k = data.value("k", nlohmann::json::object());
            std::cout << "[kline] " << k.value("i", "")
                      << " O=" << std::fixed << std::setprecision(2) << std::stod(k.value("o", "0"))
                      << " H=" << std::stod(k.value("h", "0"))
                      << " L=" << std::stod(k.value("l", "0"))
                      << " C=" << std::stod(k.value("c", "0"))
                      << " V=" << std::setprecision(6) << std::stod(k.value("v", "0"))
                      << std::endl;
        });

        // ticker：每 5 条打印 1 条
        ws.set_ticker_callback([&](const nlohmann::json& tk) {
            if (!should_print_every(ticker_n, 5)) return;
            std::cout << "[ticker] last=" << std::fixed << std::setprecision(2) << std::stod(tk.value("c", "0"))
                      << " bid=" << std::stod(tk.value("b", "0"))
                      << " ask=" << std::stod(tk.value("a", "0"))
                      << std::endl;
        });

        // depth：每 20 条打印 1 条（只看最优价）
        ws.set_orderbook_callback([&](const nlohmann::json& ob) {
            if (!should_print_every(depth_n, 20)) return;
            std::cout << "[depth] data received" << std::endl;
        });

        // bookTicker：复用 ticker_callback（parse_book_ticker -> ticker_callback）
        // 这里额外计数，用 raw_callback 识别 e=bookTicker
        ws.set_raw_message_callback([&](const nlohmann::json& j) {
            if (j.is_object() && j.contains("e") && j["e"] == "bookTicker") {
                book_n.fetch_add(1);
            }
        });

        std::cout << "正在连接 WebSocket..." << std::endl;
        if (!ws.connect()) {
            std::cerr << "❌ 连接失败（检查代理/网络/websocketpp 依赖）" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        // 全量订阅
        const std::string sym = "btcusdt";
        // Binance WS 对客户端发送消息有频率限制（常见：<= 5 msg/s）。
        // 这里做节流，避免 "Too many requests" 被服务端踢下线。
        ws.subscribe_trade(sym);
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        ws.subscribe_kline(sym, "1m");
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        ws.subscribe_ticker(sym);          // 24hrTicker
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        ws.subscribe_mini_ticker(sym);     // 24hrMiniTicker
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        ws.subscribe_depth(sym, 20, 100);  // depth20@100ms（快照/可能无e，代码已兼容）
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        ws.subscribe_book_ticker(sym);     // bookTicker

        std::cout << "\n✅ 已发送订阅请求，运行 60 秒...\n" << std::endl;

        const auto start = std::chrono::steady_clock::now();
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();

            if (elapsed > 0 && elapsed % 10 == 0) {
                static int last = -1;
                if (last != (int)elapsed) {
                    last = (int)elapsed;
                    std::cout << "\n[stats] " << elapsed << "s"
                              << " trade=" << trade_n.load()
                              << " kline=" << kline_n.load()
                              << " ticker=" << ticker_n.load()
                              << " depth=" << depth_n.load()
                              << " bookTicker(raw)=" << book_n.load()
                              << "\n"
                              << std::endl;
                }
            }

            if (elapsed >= 60) break;
        }

        std::cout << "正在断开连接..." << std::endl;
        ws.disconnect();
        std::cout << "✅ 已断开\n" << std::endl;

        std::cout << "[final] trade=" << trade_n.load()
                  << " kline=" << kline_n.load()
                  << " ticker=" << ticker_n.load()
                  << " depth=" << depth_n.load()
                  << " bookTicker(raw)=" << book_n.load()
                  << std::endl;

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}


