/**
 * @file trading_server_main.cpp
 * @brief 完整实盘交易服务器 - 主入口
 *
 * 功能：
 * 1. WebSocket 行情 (trades, K线, 订单状态, 账户/持仓更新)
 * 2. REST API 交易 (下单, 批量下单, 撤单, 修改订单)
 * 3. REST API 查询 (账户余额, 持仓, 未成交订单)
 *
 * @author Sequence Team
 * @date 2025-12
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <algorithm>

#ifdef __linux__
#include <sched.h>
#include <pthread.h>
#endif

#include "config/server_config.h"
#include "managers/account_manager.h"
#include "handlers/order_processor.h"
#include "handlers/query_handler.h"
#include "managers/paper_trading_manager.h"
#include "handlers/frontend_command_handler.h"
#include "handlers/subscription_manager.h"
#include "callbacks/websocket_callbacks.h"

#include "../network/zmq_server.h"
#include "../network/frontend_handler.h"
#include "../network/websocket_server.h"
#include "../trading/config_loader.h"
#include "../trading/account_registry.h"
#include "../adapters/okx/okx_websocket.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/binance/binance_websocket.h"
#include "../adapters/binance/binance_rest_api.h"
#include "../core/logger.h"

using namespace trading;
using namespace trading::server;
using namespace trading::okx;
using namespace trading::binance;
using namespace std::chrono;

// ============================================================
// CPU 亲和性
// ============================================================

bool pin_thread_to_cpu(int cpu_id) {
#ifdef __linux__
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu_id, &cpuset);

    int result = pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    if (result == 0) {
        std::cout << "[绑核] 线程已绑定到 CPU " << cpu_id << std::endl;
        return true;
    }
    return false;
#else
    (void)cpu_id;
    return false;
#endif
}

bool set_realtime_priority(int priority = 50) {
#ifdef __linux__
    struct sched_param param;
    param.sched_priority = priority;
    return pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) == 0;
#else
    (void)priority;
    return false;
#endif
}

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
    set_curl_abort_flag(true);
    // 不在信号处理函数中调用 disconnect，让主循环处理
}

// ============================================================
// 工作线程
// ============================================================

void order_thread(ZmqServer& server) {
    std::cout << "[订单线程] 启动\n";
    pin_thread_to_cpu(2);
    set_realtime_priority(49);

    while (g_running.load()) {
        nlohmann::json order;
        while (server.recv_order_json(order)) {
            process_order_request(server, order);
        }
        std::this_thread::sleep_for(microseconds(100));
    }

    std::cout << "[订单线程] 停止\n";
}

void query_thread(ZmqServer& server) {
    std::cout << "[查询线程] 启动\n";
    pin_thread_to_cpu(3);

    server.set_query_callback([](const nlohmann::json& request) -> nlohmann::json {
        return handle_query(request);
    });

    while (g_running.load()) {
        server.poll_queries();
        std::this_thread::sleep_for(milliseconds(1));
    }

    std::cout << "[查询线程] 停止\n";
}

void subscription_thread(ZmqServer& server) {
    std::cout << "[订阅线程] 启动\n";

    server.set_subscribe_callback([](const nlohmann::json& request) {
        handle_subscription(request);
    });

    while (g_running.load()) {
        server.poll_subscriptions();
        std::this_thread::sleep_for(milliseconds(10));
    }

    std::cout << "[订阅线程] 停止\n";
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;

    using namespace trading::core;
    Logger::instance().init("logs", "trading_server", LogLevel::INFO);

    std::cout << "========================================\n";
    std::cout << "    Sequence 实盘交易服务器 (Full)\n";
    std::cout << "    支持 OKX + Binance\n";
    std::cout << "========================================\n\n";

    LOG_INFO("实盘交易服务器启动");

    load_config();

    pin_thread_to_cpu(1);
    set_realtime_priority(50);

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "[配置] OKX 交易模式: " << (Config::is_testnet ? "模拟盘" : "实盘") << "\n";
    std::cout << "[配置] Binance 交易模式: " << (Config::binance_is_testnet ? "测试网" : "主网") << "\n";

    // ========================================
    // 加载账户配置
    // ========================================
    std::cout << "\n[初始化] 加载账户配置...\n";

    try {
        load_accounts_from_config(g_account_registry, "accounts.json", true);
    } catch (const std::exception& e) {
        std::cout << "[配置] 配置文件加载失败，使用环境变量/默认值\n";

        g_account_registry.set_default_okx_account(
            Config::api_key, Config::secret_key, Config::passphrase, Config::is_testnet
        );
        std::cout << "[初始化] 默认OKX账户 ✓ (API Key: " << Config::api_key.substr(0, 8) << "...)\n";
    }

    std::cout << "[提示] 策略可通过 register_account 消息注册自己的账户\n";

    // ========================================
    // 启动前端处理器
    // ========================================
    std::cout << "\n[初始化] 启动前端处理器...\n";
    FrontendHandler frontend_handler(g_account_registry);
    if (!frontend_handler.start("tcp://*:5556")) {
        std::cerr << "[错误] 前端处理器启动失败\n";
        return 1;
    }
    std::cout << "[前端] 监听端口 5556 ✓\n";

    // ========================================
    // 初始化 ZeroMQ
    // ========================================
    ZmqServer zmq_server(0);  // mode=0: 使用 trading_*.ipc 地址，实盘和模拟策略都能连接
    if (!zmq_server.start()) {
        std::cerr << "[错误] ZeroMQ 服务启动失败\n";
        return 1;
    }

    std::cout << "[初始化] ZeroMQ 通道:\n";
    std::cout << "  - 行情: " << PaperTradingIpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 订单: " << PaperTradingIpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << PaperTradingIpcAddresses::REPORT << "\n";
    std::cout << "  - 查询: " << PaperTradingIpcAddresses::QUERY << "\n";
    std::cout << "  - 订阅: " << PaperTradingIpcAddresses::SUBSCRIBE << "\n";

    // ========================================
    // 初始化 WebSocket
    // ========================================
    std::cout << "\n[初始化] OKX WebSocket...\n";

    g_ws_public = create_public_ws(Config::is_testnet);
    g_ws_business = create_business_ws(Config::is_testnet);
    g_ws_private = create_private_ws(
        Config::api_key, Config::secret_key, Config::passphrase, Config::is_testnet
    );

    setup_websocket_callbacks(zmq_server);

    if (!g_ws_public->connect()) {
        std::cerr << "[错误] WebSocket Public 连接失败\n";
        return 1;
    }
    std::cout << "[WebSocket] Public ✓\n";

    if (!g_ws_business->connect()) {
        std::cerr << "[错误] WebSocket Business 连接失败\n";
        return 1;
    }
    std::cout << "[WebSocket] Business ✓\n";

    if (!g_ws_private->connect()) {
        std::cerr << "[警告] WebSocket Private 连接失败，私有功能不可用\n";
    } else {
        g_ws_private->login();
        std::this_thread::sleep_for(seconds(2));
        if (g_ws_private->is_logged_in()) {
            std::cout << "[WebSocket] Private ✓ (已登录)\n";

            g_ws_private->subscribe_orders("SPOT");
            g_ws_private->subscribe_orders("SWAP");
            g_ws_private->subscribe_account();
            g_ws_private->subscribe_positions("ANY");
        } else {
            std::cout << "[WebSocket] Private (登录失败)\n";
        }
    }

    // 动态获取 OKX 所有永续合约交易对
    std::vector<std::string> okx_swap_symbols = Config::swap_symbols;

    if (okx_swap_symbols.empty() || okx_swap_symbols.size() <= 5) {
        std::cout << "[OKX] 动态获取所有永续合约交易对...\n";

        try {
            // 创建临时 REST API 客户端
            OKXRestAPI temp_okx_api("", "", "", Config::is_testnet);
            auto instruments = temp_okx_api.get_instruments("SWAP");

            if (instruments.contains("data") && instruments["data"].is_array()) {
                okx_swap_symbols.clear();
                for (const auto& inst : instruments["data"]) {
                    std::string inst_id = inst.value("instId", "");
                    std::string state = inst.value("state", "");
                    std::string settle_ccy = inst.value("settleCcy", "");

                    // 只订阅 USDT 结算的永续合约且状态为 live
                    if (!inst_id.empty() && state == "live" && settle_ccy == "USDT") {
                        okx_swap_symbols.push_back(inst_id);
                    }
                }
                std::cout << "[OKX] 获取到 " << okx_swap_symbols.size() << " 个 USDT 永续合约\n";
            }
        } catch (const std::exception& e) {
            std::cerr << "[OKX] 获取交易对失败: " << e.what() << "\n";
            std::cerr << "[OKX] 请检查网络或设置代理: export https_proxy=http://127.0.0.1:7890\n";
            // 使用默认币种
            okx_swap_symbols = {"BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP", "DOGE-USDT-SWAP"};
            std::cout << "[OKX] 使用默认 " << okx_swap_symbols.size() << " 个币种\n";
        }
    }

    // 订阅合约 ticker、trades 和 K线
    // OKX 限制：每个连接最多订阅 480 个频道
    // public 端点: ticker + trades = 2 频道/币种 → 最多 240 个币种
    // business 端点: kline = 1 频道/币种 → 最多 480 个币种
    const size_t max_okx_symbols = 240;  // 受 public 端点限制
    size_t okx_subscribe_count = std::min(okx_swap_symbols.size(), max_okx_symbols);

    // 准备批量订阅的币种列表
    std::vector<std::string> okx_symbols_to_sub(okx_swap_symbols.begin(),
        okx_swap_symbols.begin() + okx_subscribe_count);

    // 分批订阅，每批100个币种
    const size_t okx_batch_size = 100;
    for (size_t i = 0; i < okx_symbols_to_sub.size(); i += okx_batch_size) {
        size_t end = std::min(i + okx_batch_size, okx_symbols_to_sub.size());
        std::vector<std::string> batch(okx_symbols_to_sub.begin() + i, okx_symbols_to_sub.begin() + end);

        // 批量订阅 Ticker 和 Trades（public 端点）
        g_ws_public->subscribe_tickers_batch(batch);
        g_ws_public->subscribe_trades_batch(batch);

        // 批量订阅 K线（business 端点）
        g_ws_business->subscribe_klines_batch(batch, "1m");

        std::cout << "[订阅] OKX 批次 " << (i / okx_batch_size + 1) << ": " << batch.size() << " 个币种\n";
    }

    // 更新订阅记录
    for (const auto& symbol : okx_symbols_to_sub) {
        g_subscribed_trades.insert(symbol);
        g_subscribed_klines[symbol].insert("1m");
    }
    std::cout << "[订阅] OKX 合约ticker+trades+kline: " << okx_subscribe_count << " 个 ✓\n";

    // ========================================
    // 初始化 Binance WebSocket
    // ========================================
    std::cout << "\n[初始化] Binance WebSocket...\n";

    // 创建 Binance 行情 WebSocket（合约测试网）
    g_binance_ws_market = create_market_ws(MarketType::FUTURES, Config::binance_is_testnet);

    // 设置 Binance 回调
    setup_binance_websocket_callbacks(zmq_server);

    // 尝试连接 Binance WebSocket，最多重试3次
    bool binance_connected = false;
    for (int retry = 0; retry < 3 && !binance_connected; ++retry) {
        if (retry > 0) {
            std::cout << "[Binance] 重试连接 (" << retry << "/3)...\n";
            std::this_thread::sleep_for(std::chrono::seconds(2));
        }
        binance_connected = g_binance_ws_market->connect();
    }

    if (!binance_connected) {
        std::cerr << "[警告] Binance WebSocket Market 连接失败（已重试3次）\n";
    } else {
        std::cout << "[WebSocket] Binance Market ✓\n";

        // 使用全市场订阅，避免订阅太多单独频道导致限流
        g_binance_ws_market->subscribe_mini_ticker();  // !miniTicker@arr - 全市场精简ticker
        std::cout << "[订阅] Binance 全市场精简Ticker ✓\n";
        std::this_thread::sleep_for(std::chrono::milliseconds(500));  // 延迟避免限流

        g_binance_ws_market->subscribe_all_mark_prices();  // !markPrice@arr - 全市场标记价格
        std::cout << "[订阅] Binance 全市场标记价格 ✓\n";
        std::this_thread::sleep_for(std::chrono::milliseconds(500));

        // 动态获取所有交易对并订阅（如果配置为空）
        std::vector<std::string> symbols_to_subscribe = Config::binance_symbols;

        if (symbols_to_subscribe.empty()) {
            std::cout << "[Binance] 配置为空，动态获取所有永续合约交易对...\n";

            try {
                // 创建临时 REST API 客户端获取交易对信息
                BinanceRestAPI temp_api("", "", MarketType::FUTURES, Config::binance_is_testnet);
                auto exchange_info = temp_api.get_exchange_info();

                if (exchange_info.contains("symbols") && exchange_info["symbols"].is_array()) {
                    for (const auto& sym : exchange_info["symbols"]) {
                        // 只订阅永续合约且状态为 TRADING 的交易对
                        std::string contract_type = sym.value("contractType", "");
                        std::string status = sym.value("status", "");
                        std::string symbol = sym.value("symbol", "");

                        if (contract_type == "PERPETUAL" && status == "TRADING" && !symbol.empty()) {
                            symbols_to_subscribe.push_back(symbol);
                        }
                    }
                    std::cout << "[Binance] 获取到 " << symbols_to_subscribe.size() << " 个永续合约交易对\n";
                }
            } catch (const std::exception& e) {
                std::cerr << "[Binance] ❌ 获取交易对失败: " << e.what() << "\n";
                std::cerr << "[Binance] 使用默认主流币种列表...\n";
                // 使用默认主流币种作为后备
                symbols_to_subscribe = {
                    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
                    "MATICUSDT", "LTCUSDT", "TRXUSDT", "ATOMUSDT", "UNIUSDT"
                };
            }
        }

        // 订阅 trades 和 K线（单连接最多1024个streams，预留2个给全市场订阅）
        const size_t max_symbols = 500;  // 每个symbol订阅2个stream，最多1000个 + 2个全市场 = 1002个
        size_t subscribe_count = std::min(symbols_to_subscribe.size(), max_symbols);

        // 准备小写的币种列表
        std::vector<std::string> lower_symbols;
        lower_symbols.reserve(subscribe_count);
        for (size_t i = 0; i < subscribe_count; ++i) {
            std::string lower_symbol = symbols_to_subscribe[i];
            std::transform(lower_symbol.begin(), lower_symbol.end(), lower_symbol.begin(), ::tolower);
            lower_symbols.push_back(lower_symbol);
        }

        // 分批订阅，每批100个币种（Binance 限制每秒10个订阅消息，但批量订阅算1个消息）
        const size_t binance_batch_size = 100;
        for (size_t i = 0; i < lower_symbols.size(); i += binance_batch_size) {
            size_t end = std::min(i + binance_batch_size, lower_symbols.size());
            std::vector<std::string> batch(lower_symbols.begin() + i, lower_symbols.begin() + end);

            g_binance_ws_market->subscribe_trades_batch(batch);
            g_binance_ws_market->subscribe_klines_batch(batch, "1m");

            std::cout << "[订阅] Binance 批次 " << (i / binance_batch_size + 1) << ": " << batch.size() << " 个币种\n";
        }
        std::cout << "[订阅] Binance trades+kline: " << subscribe_count << " 个币种 ✓\n";

        // ========================================
        // 创建第二个 WebSocket 连接用于深度数据
        // ========================================
        std::cout << "\n[初始化] Binance 深度数据 WebSocket...\n";
        g_binance_ws_depth = create_market_ws(MarketType::FUTURES, Config::binance_is_testnet);

        // 设置深度数据回调（复用 g_binance_ws_market 的回调逻辑）
        // 主流币种列表（只有这些发送给前端）
        static const std::set<std::string> main_symbols = {
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
        };

        g_binance_ws_depth->set_orderbook_callback([&zmq_server](const OrderBookData::Ptr& orderbook) {
            g_orderbook_count++;

            nlohmann::json bids = nlohmann::json::array();
            nlohmann::json asks = nlohmann::json::array();

            for (const auto& bid : orderbook->bids()) {
                bids.push_back({bid.first, bid.second});
            }
            for (const auto& ask : orderbook->asks()) {
                asks.push_back({ask.first, ask.second});
            }

            nlohmann::json msg = {
                {"type", "orderbook"},
                {"exchange", "binance"},
                {"symbol", orderbook->symbol()},
                {"bids", bids},
                {"asks", asks},
                {"timestamp", orderbook->timestamp()},
                {"timestamp_ns", current_timestamp_ns()}
            };

            auto best_bid = orderbook->best_bid();
            auto best_ask = orderbook->best_ask();
            if (best_bid) {
                msg["best_bid_price"] = best_bid->first;
                msg["best_bid_size"] = best_bid->second;
            }
            if (best_ask) {
                msg["best_ask_price"] = best_ask->first;
                msg["best_ask_size"] = best_ask->second;
            }

            auto mid_price = orderbook->mid_price();
            if (mid_price) {
                msg["mid_price"] = *mid_price;
            }
            auto spread = orderbook->spread();
            if (spread) {
                msg["spread"] = *spread;
            }

            // 所有深度数据都发给后端策略
            zmq_server.publish_depth(msg);

            // 只有主流币种发送给前端
            if (g_frontend_server && main_symbols.count(orderbook->symbol())) {
                g_frontend_server->send_event("orderbook", msg);
            }
        });

        // 连接深度数据 WebSocket
        bool depth_connected = false;
        for (int retry = 0; retry < 3 && !depth_connected; ++retry) {
            if (retry > 0) {
                std::cout << "[Binance Depth] 重试连接 (" << retry << "/3)...\n";
                std::this_thread::sleep_for(std::chrono::seconds(2));
            }
            depth_connected = g_binance_ws_depth->connect();
        }

        if (!depth_connected) {
            std::cerr << "[警告] Binance WebSocket Depth 连接失败\n";
        } else {
            std::cout << "[WebSocket] Binance Depth ✓\n";

            // 分批订阅深度数据
            for (size_t i = 0; i < lower_symbols.size(); i += binance_batch_size) {
                size_t end = std::min(i + binance_batch_size, lower_symbols.size());
                std::vector<std::string> batch(lower_symbols.begin() + i, lower_symbols.begin() + end);

                g_binance_ws_depth->subscribe_depths_batch(batch, 20, 100);  // 20档，100ms更新
            }
            std::cout << "[订阅] Binance depth: " << subscribe_count << " 个币种 ✓\n";
        }
    }

    // 如果有 Binance API Key，创建用户数据流
    if (!Config::binance_api_key.empty()) {
        g_binance_rest_api = std::make_unique<BinanceRestAPI>(
            Config::binance_api_key, Config::binance_secret_key,
            MarketType::FUTURES, Config::binance_is_testnet
        );

        // 获取 listenKey
        auto listen_key_result = g_binance_rest_api->create_listen_key();
        if (listen_key_result.contains("listenKey")) {
            std::string listen_key = listen_key_result["listenKey"];
            std::cout << "[Binance] ListenKey: " << listen_key.substr(0, 20) << "...\n";

            // 创建用户数据流 WebSocket
            g_binance_ws_user = create_user_ws(Config::binance_api_key, MarketType::FUTURES, Config::binance_is_testnet);
            if (g_binance_ws_user->connect_user_stream(listen_key)) {
                std::cout << "[WebSocket] Binance User Stream ✓\n";
                // 启动自动刷新 listenKey
                g_binance_ws_user->start_auto_refresh_listen_key(g_binance_rest_api.get());
            } else {
                std::cerr << "[警告] Binance User Stream 连接失败\n";
            }
        } else {
            std::cerr << "[警告] 获取 Binance ListenKey 失败\n";
        }
    } else {
        std::cout << "[Binance] 未配置 API Key，跳过用户数据流\n";
    }

    // ========================================
    // 启动前端 WebSocket 服务器
    // ========================================
    g_frontend_server = std::make_unique<core::WebSocketServer>();
    g_frontend_server->set_message_callback(handle_frontend_command);

    if (!g_frontend_server->start("0.0.0.0", 8002)) {
        std::cerr << "[错误] 前端WebSocket服务器启动失败\n";
        return 1;
    }

    std::cout << "[前端] WebSocket服务器已启动（端口8002）\n";

    // ========================================
    // 启动工作线程
    // ========================================
    std::thread order_worker(order_thread, std::ref(zmq_server));
    std::thread query_worker(query_thread, std::ref(zmq_server));
    std::thread sub_worker(subscription_thread, std::ref(zmq_server));

    // ========================================
    // 主循环
    // ========================================
    std::cout << "\n========================================\n";
    std::cout << "  服务器启动完成！\n";
    std::cout << "  等待策略连接...\n";
    std::cout << "  按 Ctrl+C 停止\n";
    std::cout << "========================================\n\n";

    int status_counter = 0;
    while (g_running.load()) {
        std::this_thread::sleep_for(milliseconds(100));
        status_counter++;

        if (status_counter >= 100 && g_running.load()) {
            status_counter = 0;
            std::cout << "[状态] Trades: " << g_trade_count
                      << " | K线: " << g_kline_count
                      << " | 深度: " << g_orderbook_count
                      << " | 资金费率: " << g_funding_rate_count
                      << " | 订单: " << g_order_count
                      << " (成功: " << g_order_success
                      << ", 失败: " << g_order_failed << ")"
                      << " | 查询: " << g_query_count
                      << " | 注册账户: " << get_registered_strategy_count() << "\n";
        }
    }

    // ========================================
    // 清理
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    LOG_INFO("服务器正在停止...");

    std::cout << "[Server] 断开 WebSocket 连接...\n";
    // OKX
    if (g_ws_public && g_ws_public->is_connected()) {
        g_ws_public->disconnect();
    }
    if (g_ws_business && g_ws_business->is_connected()) {
        g_ws_business->disconnect();
    }
    if (g_ws_private && g_ws_private->is_connected()) {
        g_ws_private->disconnect();
    }
    // Binance
    if (g_binance_ws_market && g_binance_ws_market->is_connected()) {
        g_binance_ws_market->disconnect();
    }
    if (g_binance_ws_depth && g_binance_ws_depth->is_connected()) {
        g_binance_ws_depth->disconnect();
    }
    if (g_binance_ws_user) {
        g_binance_ws_user->stop_auto_refresh_listen_key();
        if (g_binance_ws_user->is_connected()) {
            g_binance_ws_user->disconnect();
        }
    }

    std::cout << "[Server] 等待工作线程退出...\n";
    if (order_worker.joinable()) order_worker.join();
    std::cout << "[Server] 订单线程已退出\n";
    if (query_worker.joinable()) query_worker.join();
    std::cout << "[Server] 查询线程已退出\n";
    if (sub_worker.joinable()) sub_worker.join();
    std::cout << "[Server] 订阅线程已退出\n";

    if (g_frontend_server) {
        std::cout << "[Server] 停止前端WebSocket服务器...\n";
        g_frontend_server->stop();
    }

    std::cout << "[Server] 停止 ZeroMQ...\n";
    zmq_server.stop();

    std::cout << "[Server] 停止前端处理器...\n";
    frontend_handler.stop();

    std::cout << "[Server] 清理账户注册器...\n";
    g_account_registry.clear();

    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "  Trades: " << g_trade_count << " 条\n";
    std::cout << "  K线: " << g_kline_count << " 条\n";
    std::cout << "  深度: " << g_orderbook_count << " 条\n";
    std::cout << "  资金费率: " << g_funding_rate_count << " 条\n";
    std::cout << "  订单: " << g_order_count << " 笔\n";
    std::cout << "========================================\n";

    LOG_INFO("服务器已停止 | Trades:" + std::to_string(g_trade_count.load()) +
             " K线:" + std::to_string(g_kline_count.load()) +
             " 订单:" + std::to_string(g_order_count.load()));
    Logger::instance().shutdown();

    return 0;
}
