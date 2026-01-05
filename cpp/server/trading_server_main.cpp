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

    // OKX WebSocket
    if (g_ws_public) {
        g_ws_public->disconnect();
    }
    if (g_ws_business) {
        g_ws_business->disconnect();
    }
    if (g_ws_private) {
        g_ws_private->disconnect();
    }

    // Binance WebSocket
    if (g_binance_ws_market) {
        g_binance_ws_market->disconnect();
    }
    if (g_binance_ws_user) {
        g_binance_ws_user->stop_auto_refresh_listen_key();
        g_binance_ws_user->disconnect();
    }
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
    ZmqServer zmq_server(2);
    if (!zmq_server.start()) {
        std::cerr << "[错误] ZeroMQ 服务启动失败\n";
        return 1;
    }

    std::cout << "[初始化] ZeroMQ 通道:\n";
    std::cout << "  - 行情: " << WebSocketServerIpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 订单: " << WebSocketServerIpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << WebSocketServerIpcAddresses::REPORT << "\n";
    std::cout << "  - 查询: " << WebSocketServerIpcAddresses::QUERY << "\n";
    std::cout << "  - 订阅: " << WebSocketServerIpcAddresses::SUBSCRIBE << "\n";

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

    for (const auto& symbol : Config::default_symbols) {
        g_ws_public->subscribe_trades(symbol);
        g_subscribed_trades.insert(symbol);
        std::cout << "[订阅] OKX trades: " << symbol << "\n";
    }

    // ========================================
    // 初始化 Binance WebSocket
    // ========================================
    std::cout << "\n[初始化] Binance WebSocket...\n";

    // 创建 Binance 行情 WebSocket（合约测试网）
    g_binance_ws_market = create_market_ws(MarketType::FUTURES, Config::binance_is_testnet);

    // 设置 Binance 回调
    setup_binance_websocket_callbacks(zmq_server);

    if (!g_binance_ws_market->connect()) {
        std::cerr << "[警告] Binance WebSocket Market 连接失败\n";
    } else {
        std::cout << "[WebSocket] Binance Market ✓\n";

        // 订阅默认交易对
        for (const auto& symbol : Config::binance_symbols) {
            std::string lower_symbol = symbol;
            std::transform(lower_symbol.begin(), lower_symbol.end(), lower_symbol.begin(), ::tolower);
            g_binance_ws_market->subscribe_trade(lower_symbol);
            std::cout << "[订阅] Binance trades: " << symbol << "\n";
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
