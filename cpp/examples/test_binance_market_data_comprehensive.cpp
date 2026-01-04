/**
 * @file test_binance_market_data_comprehensive.cpp
 * @brief Binance 市场数据全面测试（模拟账户和真实账户）
 * 
 * 测试内容：
 * - 现货市场：K线、深度、成交、Ticker
 * - 合约市场：K线、深度、成交、标记价格、全市场标记价格
 * - 支持测试网（模拟）和主网（真实）
 * 
 * 使用方法：
 *   export BINANCE_TESTNET=1  # 测试网（模拟账户）
 *   export BINANCE_TESTNET=0  # 主网（真实账户，默认）
 *   export MARKET_TYPE=SPOT   # 现货市场（默认）
 *   export MARKET_TYPE=FUTURES # 合约市场
 *   ./test_binance_market_data_comprehensive
 */

#include "../adapters/binance/binance_websocket.h"
#include "../core/data.h"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
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

static bool env_truthy(const char* key) {
    const char* v = std::getenv(key);
    if (!v) return false;
    std::string s(v);
    for (auto& c : s) c = (char)std::tolower((unsigned char)c);
    return (s == "1" || s == "true" || s == "yes" || s == "on");
}

static std::string getenv_str(const char* key, const std::string& default_val = "") {
    const char* v = std::getenv(key);
    return v ? std::string(v) : default_val;
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
    const std::string market_type_str = getenv_str("MARKET_TYPE", "SPOT");
    
    MarketType market_type = MarketType::SPOT;
    if (market_type_str == "FUTURES" || market_type_str == "futures") {
        market_type = MarketType::FUTURES;
    } else if (market_type_str == "COIN_FUTURES" || market_type_str == "coin_futures") {
        market_type = MarketType::COIN_FUTURES;
    }

    std::cout << "========================================\n";
    std::cout << "  Binance 市场数据全面测试\n";
    std::cout << "========================================\n";
    std::cout << "网络: " << (is_testnet ? "TESTNET(模拟账户)" : "MAINNET(真实账户)") << "\n";
    std::cout << "市场: ";
    if (market_type == MarketType::SPOT) {
        std::cout << "SPOT(现货)";
    } else if (market_type == MarketType::FUTURES) {
        std::cout << "FUTURES(USDT合约)";
    } else {
        std::cout << "COIN_FUTURES(币本位合约)";
    }
    std::cout << "\n";
    std::cout << "提示: WebSocket 默认启用 HTTP 代理 127.0.0.1:7890\n";
    std::cout << "按 Ctrl+C 退出\n";
    std::cout << "========================================\n" << std::endl;

    try {
        auto ws = create_market_ws(market_type, is_testnet);

        std::atomic<int> trade_count{0};
        std::atomic<int> kline_count{0};
        std::atomic<int> ticker_count{0};
        std::atomic<int> depth_count{0};
        std::atomic<int> mark_price_count{0};
        std::atomic<int> all_mark_price_count{0};

        // 成交回调
        ws->set_trade_callback([&](const TradeData::Ptr& trade) {
            trade_count.fetch_add(1);
            if (trade_count.load() % 10 == 0) {  // 每10条打印1条
                std::cout << "[成交] " << trade->symbol()
                          << " px=" << std::fixed << std::setprecision(2) << trade->price()
                          << " qty=" << std::setprecision(6) << trade->quantity()
                          << " side=" << trade->side().value_or("?")
                          << " t=" << ts_to_time(trade->timestamp())
                          << std::endl;
            }
        });

        // K线回调
        ws->set_kline_callback([&](const KlineData::Ptr& kline) {
            kline_count.fetch_add(1);
            std::cout << "[K线] " << kline->symbol()
                      << " " << kline->interval()
                      << " O=" << std::fixed << std::setprecision(2) << kline->open()
                      << " H=" << kline->high()
                      << " L=" << kline->low()
                      << " C=" << kline->close()
                      << " V=" << std::setprecision(4) << kline->volume()
                      << " closed=" << (kline->is_confirmed() ? "✅" : "⏳")
                      << " t=" << ts_to_time(kline->timestamp())
                      << std::endl;
        });

        // Ticker回调
        ws->set_ticker_callback([&](const TickerData::Ptr& ticker) {
            ticker_count.fetch_add(1);
            if (ticker_count.load() % 5 == 0) {  // 每5条打印1条
                std::cout << "[Ticker] " << ticker->symbol()
                          << " last=" << std::fixed << std::setprecision(2) << ticker->last_price()
                          << " bid=" << ticker->bid_price().value_or(0.0)
                          << " ask=" << ticker->ask_price().value_or(0.0)
                          << std::endl;
            }
        });

        // 深度回调
        ws->set_orderbook_callback([&](const OrderBookData::Ptr& ob) {
            depth_count.fetch_add(1);
            if (depth_count.load() % 20 == 0) {  // 每20条打印1条
                auto bb = ob->best_bid();
                auto ba = ob->best_ask();
                std::cout << "[深度] " << ob->symbol()
                          << " best_bid=" << (bb ? bb->first : 0.0)
                          << " best_ask=" << (ba ? ba->first : 0.0)
                          << " bids=" << ob->bids().size()
                          << " asks=" << ob->asks().size()
                          << std::endl;
            }
        });

        // 标记价格回调（仅合约）
        if (market_type != MarketType::SPOT) {
            ws->set_mark_price_callback([&](const MarkPriceData::Ptr& mp) {
                mark_price_count.fetch_add(1);
                std::cout << "[标记价格] " << mp->symbol
                          << " mark=" << std::fixed << std::setprecision(2) << mp->mark_price
                          << " index=" << mp->index_price
                          << " funding=" << mp->funding_rate
                          << std::endl;
            });
        }

        // 原始消息回调（用于检测全市场标记价格）
        ws->set_raw_message_callback([&](const nlohmann::json& msg) {
            if (msg.is_array()) {
                // 全市场标记价格是数组格式
                for (const auto& item : msg) {
                    if (item.is_object() && item.contains("e") && 
                        item["e"] == "markPriceUpdate") {
                        all_mark_price_count.fetch_add(1);
                        if (all_mark_price_count.load() % 10 == 0) {
                            std::cout << "[全市场标记价格] 收到 " 
                                      << all_mark_price_count.load() 
                                      << " 条更新" << std::endl;
                        }
                    }
                }
            }
        });

        std::cout << "正在连接 WebSocket..." << std::endl;
        if (!ws->connect()) {
            std::cerr << "❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "✅ 连接成功！\n" << std::endl;

        std::this_thread::sleep_for(std::chrono::seconds(1));

        // 选择测试的交易对
        std::string symbol = "btcusdt";
        if (market_type == MarketType::FUTURES || market_type == MarketType::COIN_FUTURES) {
            symbol = "BTCUSDT";
        }

        std::cout << "正在订阅数据流（交易对: " << symbol << "）..." << std::endl;
        
        // 订阅基础数据
        ws->subscribe_trade(symbol);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        std::cout << "  ✓ 成交流" << std::endl;

        ws->subscribe_kline(symbol, "1m");
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        std::cout << "  ✓ K线流 (1m)" << std::endl;

        ws->subscribe_ticker(symbol);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        std::cout << "  ✓ Ticker流" << std::endl;

        ws->subscribe_depth(symbol, 20, 100);
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        std::cout << "  ✓ 深度流 (20档@100ms)" << std::endl;

        // 合约市场特有
        if (market_type == MarketType::FUTURES || market_type == MarketType::COIN_FUTURES) {
            ws->subscribe_mark_price(symbol);
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            std::cout << "  ✓ 标记价格流" << std::endl;

            ws->subscribe_all_mark_prices();
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            std::cout << "  ✓ 全市场标记价格流" << std::endl;
        }

        std::cout << "\n✅ 订阅完成！等待数据推送...\n" << std::endl;

        // 主循环
        auto start = std::chrono::steady_clock::now();
        while (g_running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));

            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - start
            ).count();

            // 每10秒显示统计
            if (elapsed > 0 && elapsed % 10 == 0) {
                static int last = -1;
                if (last != (int)elapsed) {
                    last = (int)elapsed;
                    std::cout << "\n[统计] " << elapsed << "秒"
                              << " | 成交: " << trade_count.load()
                              << " | K线: " << kline_count.load()
                              << " | Ticker: " << ticker_count.load()
                              << " | 深度: " << depth_count.load();
                    if (market_type != MarketType::SPOT) {
                        std::cout << " | 标记价格: " << mark_price_count.load()
                                  << " | 全市场标记价格: " << all_mark_price_count.load();
                    }
                    std::cout << "\n" << std::endl;
                }
            }

            // 运行60秒
            if (elapsed >= 60) break;
        }

        std::cout << "\n正在断开连接..." << std::endl;
        ws->disconnect();
        std::cout << "✅ 已断开连接\n" << std::endl;

        // 最终统计
        std::cout << "========================================\n";
        std::cout << "  最终统计\n";
        std::cout << "========================================\n";
        std::cout << "成交数: " << trade_count.load() << "\n";
        std::cout << "K线数: " << kline_count.load() << "\n";
        std::cout << "Ticker数: " << ticker_count.load() << "\n";
        std::cout << "深度数: " << depth_count.load() << "\n";
        if (market_type != MarketType::SPOT) {
            std::cout << "标记价格数: " << mark_price_count.load() << "\n";
            std::cout << "全市场标记价格数: " << all_mark_price_count.load() << "\n";
        }
        std::cout << "========================================\n";

        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}

