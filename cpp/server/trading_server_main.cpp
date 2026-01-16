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
#include "managers/redis_recorder.h"
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

    // ========================================
    // 初始化 Redis 录制器
    // ========================================
    std::cout << "\n[初始化] Redis 录制器...\n";
    g_redis_recorder = std::make_unique<RedisRecorder>();

    // 配置 Redis
    RedisConfig redis_config;
    // 从环境变量读取
    if (const char* v = std::getenv("REDIS_HOST")) redis_config.host = v;
    if (const char* v = std::getenv("REDIS_PORT")) redis_config.port = std::stoi(v);
    if (const char* v = std::getenv("REDIS_PASSWORD")) redis_config.password = v;
    if (const char* v = std::getenv("REDIS_DB")) redis_config.db = std::stoi(v);
    if (const char* v = std::getenv("REDIS_ENABLED")) {
        redis_config.enabled = (std::string(v) == "1" || std::string(v) == "true");
    }

    g_redis_recorder->set_config(redis_config);

    if (redis_config.enabled) {
        if (g_redis_recorder->start()) {
            std::cout << "[Redis] 录制器启动成功 ✓\n";
            std::cout << "[Redis] 服务器: " << redis_config.host << ":" << redis_config.port << "\n";
        } else {
            std::cerr << "[Redis] 录制器启动失败，继续运行但不录制数据\n";
        }
    } else {
        std::cout << "[Redis] 录制功能已禁用\n";
    }

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
    std::cout << "  - 行情(统一): " << IpcAddresses::MARKET_DATA << "\n";
    std::cout << "  - 行情(OKX):  " << IpcAddresses::MARKET_DATA_OKX << "\n";
    std::cout << "  - 行情(Binance): " << IpcAddresses::MARKET_DATA_BINANCE << "\n";
    std::cout << "  - 订单: " << IpcAddresses::ORDER << "\n";
    std::cout << "  - 回报: " << IpcAddresses::REPORT << "\n";
    std::cout << "  - 查询: " << IpcAddresses::QUERY << "\n";
    std::cout << "  - 订阅: " << IpcAddresses::SUBSCRIBE << "\n";

    // ========================================
    // 初始化 OKX WebSocket (只订阅公共行情)
    // ========================================
    std::cout << "\n[初始化] OKX WebSocket...\n";

    g_ws_business = create_business_ws(Config::is_testnet);
    g_ws_business->set_auto_reconnect(true);

    // 设置 OKX K线回调
    setup_websocket_callbacks(zmq_server);

    if (!g_ws_business->connect()) {
        std::cerr << "[错误] WebSocket Business 连接失败\n";
        return 1;
    }
    std::cout << "[WebSocket] OKX Business ✓\n";

    // 动态获取 OKX 所有永续合约交易对
    std::vector<std::string> okx_swap_symbols = Config::swap_symbols;

    if (okx_swap_symbols.empty() || okx_swap_symbols.size() <= 5) {
        std::cout << "[OKX] 动态获取所有永续合约交易对...\n";

        try {
            OKXRestAPI okx_api("", "", "", Config::is_testnet);
            auto instruments = okx_api.get_instruments("SWAP");

            if (instruments.contains("data") && instruments["data"].is_array()) {
                okx_swap_symbols.clear();
                for (const auto& inst : instruments["data"]) {
                    std::string inst_id = inst.value("instId", "");
                    std::string state = inst.value("state", "");
                    std::string settle_ccy = inst.value("settleCcy", "");

                    if (!inst_id.empty() && state == "live" && settle_ccy == "USDT") {
                        okx_swap_symbols.push_back(inst_id);
                    }
                }
                std::cout << "[OKX] 获取到 " << okx_swap_symbols.size() << " 个 USDT 永续合约\n";
            }
        } catch (const std::exception& e) {
            std::cerr << "[OKX] 获取交易对失败: " << e.what() << "\n";
            okx_swap_symbols = {"BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP", "DOGE-USDT-SWAP"};
            std::cout << "[OKX] 使用默认 " << okx_swap_symbols.size() << " 个币种\n";
        }
    }

    // 批量订阅 OKX K线（1m）
    const size_t okx_batch_size = 100;
    for (size_t i = 0; i < okx_swap_symbols.size(); i += okx_batch_size) {
        size_t end = std::min(i + okx_batch_size, okx_swap_symbols.size());
        std::vector<std::string> batch(okx_swap_symbols.begin() + i, okx_swap_symbols.begin() + end);
        g_ws_business->subscribe_klines_batch(batch, "1m");
        std::cout << "[订阅] OKX K线批次 " << (i / okx_batch_size + 1) << ": " << batch.size() << " 个币种\n";
    }
    for (const auto& symbol : okx_swap_symbols) {
        g_subscribed_klines[symbol].insert("1m");
    }
    std::cout << "[订阅] OKX K线(1m): " << okx_swap_symbols.size() << " 个 ✓\n";

    // ========================================
    // 初始化 Binance WebSocket
    // ========================================
    std::cout << "\n[初始化] Binance WebSocket...\n";

    // 动态获取所有交易对
    std::vector<std::string> symbols_to_subscribe = Config::binance_symbols;

    if (symbols_to_subscribe.empty()) {
        std::cout << "[Binance] 配置为空，动态获取所有永续合约交易对...\n";

        try {
            BinanceRestAPI binance_api("", "", MarketType::FUTURES, Config::binance_is_testnet);
            auto exchange_info = binance_api.get_exchange_info();

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

    // 准备小写的币种列表
    size_t subscribe_count = symbols_to_subscribe.size();
    std::vector<std::string> lower_symbols;
    lower_symbols.reserve(subscribe_count);
    for (size_t i = 0; i < subscribe_count; ++i) {
        std::string lower_symbol = symbols_to_subscribe[i];
        std::transform(lower_symbol.begin(), lower_symbol.end(), lower_symbol.begin(), ::tolower);
        lower_symbols.push_back(lower_symbol);
    }

    // 分成两组
    size_t half = lower_symbols.size() / 2;

    // ========================================
    // 只订阅 K线（1m）
    // ========================================
    std::cout << "\n[初始化] Binance K线 WebSocket (组合流URL方式)...\n";

    // 构建K线 streams
    std::vector<std::string> kline_streams;
    kline_streams.reserve(lower_symbols.size());
    for (const auto& sym : lower_symbols) {
        kline_streams.push_back(sym + "_perpetual@continuousKline_1m");
    }

    std::vector<std::string> kline_batch1(kline_streams.begin(), kline_streams.begin() + half);
    std::vector<std::string> kline_batch2(kline_streams.begin() + half, kline_streams.end());

    // K线连接1
    auto kline_ws1 = create_market_ws(MarketType::FUTURES, Config::binance_is_testnet);
    kline_ws1->set_auto_reconnect(true);
    setup_binance_kline_callback(kline_ws1.get(), zmq_server);
    if (kline_ws1->connect_with_streams(kline_batch1)) {
        std::cout << "[WebSocket] Binance K线连接1 ✓ (" << kline_batch1.size() << " streams)\n";
        g_binance_ws_klines.push_back(std::move(kline_ws1));
    } else {
        std::cerr << "[警告] Binance K线连接1 失败\n";
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // K线连接2
    auto kline_ws2 = create_market_ws(MarketType::FUTURES, Config::binance_is_testnet);
    kline_ws2->set_auto_reconnect(true);
    setup_binance_kline_callback(kline_ws2.get(), zmq_server);
    if (kline_ws2->connect_with_streams(kline_batch2)) {
        std::cout << "[WebSocket] Binance K线连接2 ✓ (" << kline_batch2.size() << " streams)\n";
        g_binance_ws_klines.push_back(std::move(kline_ws2));
    } else {
        std::cerr << "[警告] Binance K线连接2 失败\n";
    }
    std::cout << "[订阅] Binance kline(1m): " << subscribe_count << " 个币种 (通过 "
              << g_binance_ws_klines.size() << " 个连接) ✓\n";

    // ========================================
    // 启动前端 WebSocket 服务器
    // ========================================
    g_frontend_server = std::make_unique<core::WebSocketServer>();
    g_frontend_server->set_message_callback(handle_frontend_command);

    if (!g_frontend_server->start("0.0.0.0", 8002)) {
        std::cerr << "[错误] 前端WebSocket服务器启动失败\n";
        return 1;
    }

    // 设置 Logger 的 WebSocket 回调，将日志推送到前端
    Logger::instance().set_ws_callback([](const std::string& level, const std::string& source, const std::string& msg) {
        if (g_frontend_server && g_frontend_server->is_running()) {
            g_frontend_server->send_log(level, source, msg);
        }
    });

    std::cout << "[前端] WebSocket服务器已启动（端口8002）\n";
    std::cout << "[日志] 日志推送到前端已启用\n";

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
            std::stringstream ss;
            // 只显示 K线统计
            ss << "K线[OKX:" << g_okx_kline_count
               << " Binance:" << g_binance_kline_count << "]"
               << " | 订单:" << g_order_count
               << "(成功:" << g_order_success
               << " 失败:" << g_order_failed << ")"
               << " | 查询:" << g_query_count
               << " | 账户:" << get_registered_strategy_count();
            Logger::instance().info("market", ss.str());
        }
    }

    // ========================================
    // 清理
    // ========================================
    std::cout << "\n[Server] 正在停止...\n";
    LOG_INFO("服务器正在停止...");

    std::cout << "[Server] 断开 WebSocket 连接...\n";
    if (g_ws_business && g_ws_business->is_connected()) {
        g_ws_business->disconnect();
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

    // 停止 Redis 录制器
    if (g_redis_recorder) {
        std::cout << "[Server] 停止 Redis 录制器...\n";
        g_redis_recorder->stop();
        g_redis_recorder.reset();
    }

    // 显式释放全局 WebSocket 对象，避免程序退出时 double free
    std::cout << "[Server] 释放 WebSocket 对象...\n";
    g_ws_business.reset();
    g_frontend_server.reset();

    // 等待一小段时间确保所有 IO 线程完全退出
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    std::cout << "\n========================================\n";
    std::cout << "  服务器已停止\n";
    std::cout << "  K线(OKX): " << g_okx_kline_count << " 条\n";
    std::cout << "  K线(Binance): " << g_binance_kline_count << " 条\n";
    std::cout << "  订单: " << g_order_count << " 笔\n";
    std::cout << "========================================\n";

    LOG_INFO("服务器已停止 | K线(OKX):" + std::to_string(g_okx_kline_count.load()) +
             " K线(Binance):" + std::to_string(g_binance_kline_count.load()) +
             " 订单:" + std::to_string(g_order_count.load()));
    Logger::instance().shutdown();

    std::cout << "[Server] 清理完成，安全退出\n" << std::flush;

    return 0;
}
