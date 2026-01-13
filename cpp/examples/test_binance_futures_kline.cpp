/**
 * @file test_binance_futures_kline.cpp
 * @brief Binance 合约 WebSocket - 全币种连续合约K线测试
 *
 * 测试连续合约K线订阅: <pair>_perpetual@continuousKline_<interval>
 */

#include "../adapters/binance/binance_websocket.h"
#include "../adapters/binance/binance_rest_api.h"

#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <thread>
#include <algorithm>

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
    std::cout << "  Binance 合约 - 全币种连续合约K线测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: Binance 主网\n";
    std::cout << "市场类型: FUTURES\n";
    std::cout << "订阅格式: <symbol>_perpetual@continuousKline_1m\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "----------------------------------------\n" << std::endl;

    try {
        // 1. 先通过 REST API 获取所有永续合约交易对
        std::cout << "正在获取所有永续合约交易对..." << std::endl;
        BinanceRestAPI rest_api("", "", MarketType::FUTURES, false);
        auto exchange_info = rest_api.get_exchange_info();

        std::vector<std::string> symbols;
        if (exchange_info.contains("symbols") && exchange_info["symbols"].is_array()) {
            for (const auto& sym : exchange_info["symbols"]) {
                std::string contract_type = sym.value("contractType", "");
                std::string status = sym.value("status", "");
                std::string symbol = sym.value("symbol", "");

                if (contract_type == "PERPETUAL" && status == "TRADING" && !symbol.empty()) {
                    // 转小写
                    std::transform(symbol.begin(), symbol.end(), symbol.begin(), ::tolower);
                    symbols.push_back(symbol);
                }
            }
        }

        std::cout << "获取到 " << symbols.size() << " 个永续合约交易对\n" << std::endl;

        if (symbols.empty()) {
            std::cerr << "❌ 没有获取到交易对" << std::endl;
            return 1;
        }

        // 2. 构建 stream 列表，分成两组测试
        std::vector<std::string> streams1, streams2;
        size_t half = symbols.size() / 2;

        for (size_t i = 0; i < symbols.size(); ++i) {
            std::string stream = symbols[i] + "_perpetual@continuousKline_1m";
            if (i < half) {
                streams1.push_back(stream);
            } else {
                streams2.push_back(stream);
            }
        }

        std::cout << "分组1: " << streams1.size() << " 个streams" << std::endl;
        std::cout << "分组2: " << streams2.size() << " 个streams" << std::endl;

        // 3. 创建两个 WebSocket 连接
        std::atomic<int> kline_count{0};
        std::atomic<int> raw_count{0};

        auto setup_callbacks = [&](BinanceWebSocket& ws) {
            ws.set_raw_message_callback([&](const nlohmann::json& data) {
                int count = raw_count.fetch_add(1);
                if (count < 10) {
                    std::string preview = data.dump().substr(0, 200);
                    std::cout << "[RAW #" << count << "] " << preview << "..." << std::endl;
                }
            });

            ws.set_kline_callback([&](const nlohmann::json& k) {
                int count = kline_count.fetch_add(1);
                if (count < 10) {
                    std::string symbol = k.value("ps", k.value("s", "???"));
                    std::cout << "[KLINE #" << count << "] symbol=" << symbol << std::endl;
                }
            });
        };

        // 连接1：前半部分
        BinanceWebSocket ws1("", "", WsConnectionType::MARKET, MarketType::FUTURES, false);
        setup_callbacks(ws1);

        std::cout << "\n正在连接 WebSocket 1 (共 " << streams1.size() << " 个streams)..." << std::endl;
        if (!ws1.connect_with_streams(streams1)) {
            std::cerr << "❌ 连接1失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接1成功\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        // 连接2：后半部分
        BinanceWebSocket ws2("", "", WsConnectionType::MARKET, MarketType::FUTURES, false);
        setup_callbacks(ws2);

        std::cout << "正在连接 WebSocket 2 (共 " << streams2.size() << " 个streams)..." << std::endl;
        if (!ws2.connect_with_streams(streams2)) {
            std::cerr << "❌ 连接2失败" << std::endl;
            // 继续，只用连接1
        } else {
            std::cout << "✅ 连接2成功\n" << std::endl;
        }

        // 运行 60 秒
        std::cout << "\n等待 K线数据 (60秒)...\n" << std::endl;
        const auto start = std::chrono::steady_clock::now();
        int last_count = 0;
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(5));
            int current = kline_count.load();
            std::cout << "[状态] 已收到 " << current << " 条K线 (+" << (current - last_count) << ")" << std::endl;
            last_count = current;

            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();
            if (elapsed >= 60000000) break;
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws1.disconnect();
        ws2.disconnect();
        std::cout << "✅ 已断开\n" << std::endl;

        std::cout << "========================================\n";
        std::cout << "  测试结果\n";
        std::cout << "========================================\n";
        std::cout << "订阅币种数量: " << symbols.size() << std::endl;
        std::cout << "收到K线数量: " << kline_count.load() << std::endl;

        if (kline_count.load() == 0) {
            std::cout << "⚠️  60秒内没有收到K线推送\n";
            return 1;
        } else {
            std::cout << "✅ K线订阅正常工作\n";
        }

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}
