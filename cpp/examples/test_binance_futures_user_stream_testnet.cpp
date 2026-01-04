#include "../adapters/binance/binance_rest_api.h"
#include "../adapters/binance/binance_websocket.h"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <future>
#include <iostream>
#include <string>
#include <thread>

using namespace trading::binance;

static std::string getenv_str(const char* key) {
    const char* v = std::getenv(key);
    return v ? std::string(v) : std::string();
}

static int getenv_int(const char* key, int default_val) {
    const char* v = std::getenv(key);
    if (!v || !*v) return default_val;
    try {
        return std::stoi(v);
    } catch (...) {
        return default_val;
    }
}

static void ensure_proxy_env() {
    const bool has_proxy =
        std::getenv("https_proxy") || std::getenv("HTTPS_PROXY") ||
        std::getenv("all_proxy") || std::getenv("ALL_PROXY") ||
        std::getenv("http_proxy") || std::getenv("HTTP_PROXY");
    if (has_proxy) return;
    setenv("https_proxy", "http://127.0.0.1:7890", 1);
    setenv("http_proxy", "http://127.0.0.1:7890", 1);
    setenv("all_proxy", "http://127.0.0.1:7890", 1);
}

static void print_account_update_summary(const nlohmann::json& msg) {
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "📨 [ACCOUNT_UPDATE]\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  E: " << msg.value("E", 0LL) << "\n";
    std::cout << "  T: " << msg.value("T", 0LL) << "\n";
    if (!msg.contains("a") || !msg["a"].is_object()) {
        std::cout << "  raw: " << msg.dump() << "\n";
        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        return;
    }
    const auto& a = msg["a"];
    std::cout << "  m: " << a.value("m", "") << "\n";
    if (a.contains("B") && a["B"].is_array()) {
        std::cout << "  B:\n";
        for (const auto& b : a["B"]) {
            if (!b.is_object()) continue;
            std::cout << "    " << b.value("a", "") << " wb=" << b.value("wb", "")
                      << " cw=" << b.value("cw", "") << " bc=" << b.value("bc", "") << "\n";
        }
    }
    if (a.contains("P") && a["P"].is_array()) {
        std::cout << "  P:\n";
        for (const auto& p : a["P"]) {
            if (!p.is_object()) continue;
            std::cout << "    " << p.value("s", "") << " ps=" << p.value("ps", "")
                      << " pa=" << p.value("pa", "") << " ep=" << p.value("ep", "")
                      << " up=" << p.value("up", "") << " mt=" << p.value("mt", "")
                      << " iw=" << p.value("iw", "") << "\n";
        }
    }
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
}

static void print_order_trade_update_summary(const nlohmann::json& msg) {
    std::cout << "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "📨 [ORDER_TRADE_UPDATE]\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    std::cout << "  E: " << msg.value("E", 0LL) << " (事件时间)\n";
    std::cout << "  T: " << msg.value("T", 0LL) << " (撮合时间)\n";
    
    if (!msg.contains("o") || !msg["o"].is_object()) {
        std::cout << "  raw: " << msg.dump() << "\n";
        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
        return;
    }
    
    const auto& o = msg["o"];
    std::cout << "  订单信息:\n";
    std::cout << "    symbol: " << o.value("s", "") << "\n";
    std::cout << "    clientOrderId: " << o.value("c", "") << "\n";
    std::cout << "    side: " << o.value("S", "") << "\n";
    std::cout << "    type: " << o.value("o", "") << "\n";
    std::cout << "    status: " << o.value("X", "") << " (订单状态)\n";
    std::cout << "    execType: " << o.value("x", "") << " (执行类型)\n";
    std::cout << "    orderId: " << o.value("i", 0LL) << "\n";
    std::cout << "    price: " << o.value("p", "") << "\n";
    std::cout << "    avgPrice: " << o.value("ap", "") << "\n";
    std::cout << "    origQty: " << o.value("q", "") << "\n";
    std::cout << "    executedQty: " << o.value("z", "") << "\n";
    std::cout << "    lastExecutedQty: " << o.value("l", "") << "\n";
    std::cout << "    lastExecutedPrice: " << o.value("L", "") << "\n";
    std::cout << "    commission: " << o.value("n", "") << " " << o.value("N", "") << "\n";
    std::cout << "    realizedPnl: " << o.value("rp", "") << "\n";
    std::cout << "    positionSide: " << o.value("ps", "") << "\n";
    std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  Binance FUTURES USER_STREAM 测试(Testnet)\n";
    std::cout << "========================================\n";

    ensure_proxy_env();

    const std::string api_key = getenv_str("BINANCE_API_KEY");
    const std::string secret_key = getenv_str("BINANCE_SECRET_KEY");

    if (api_key.empty() || secret_key.empty()) {
        std::cerr << "❌ 缺少环境变量 BINANCE_API_KEY / BINANCE_SECRET_KEY\n";
        return 1;
    }

    const std::string mode = getenv_str("USER_STREAM_MODE").empty() ? "rest" : getenv_str("USER_STREAM_MODE");
    const int run_seconds = getenv_int("USER_STREAM_RUN_SECONDS", 120);
    const int keepalive_seconds = getenv_int("USER_STREAM_KEEPALIVE_SECONDS", 1800);

    std::cout << "  API Key: " << api_key.substr(0, 8) << "...\n";
    std::cout << "  REST: https://demo-fapi.binance.com\n";
    std::cout << "  WS:   wss://fstream.binancefuture.com/ws/<listenKey>\n";
    std::cout << "  mode: " << mode << "\n";
    std::cout << "  run:  " << run_seconds << "s\n";
    std::cout << "  keepalive: " << keepalive_seconds << "s\n";

    try {
        BinanceRestAPI rest(api_key, secret_key, MarketType::FUTURES, true);

        std::string listen_key;
        std::unique_ptr<BinanceWebSocket> ws_trading;
        std::unique_ptr<BinanceWebSocket> ws_user;

        if (mode == "ws") {
            ws_trading = create_trading_ws(api_key, secret_key, MarketType::FUTURES, true);
            std::promise<std::string> lk_promise;
            std::future<std::string> lk_future = lk_promise.get_future();
            std::atomic<bool> lk_done{false};

            ws_trading->set_order_response_callback([&](const nlohmann::json& response) {
                if (lk_done.load()) return;
                if (response.value("status", 0) != 200) return;
                if (!response.contains("result") || !response["result"].is_object()) return;
                const auto& result = response["result"];
                if (!result.contains("listenKey")) return;
                lk_done.store(true);
                lk_promise.set_value(result["listenKey"].get<std::string>());
            });

            if (!ws_trading->connect()) {
                std::cerr << "❌ Trading WS 连接失败\n";
                return 1;
            }

            const std::string req_id = ws_trading->start_user_data_stream_ws();
            if (req_id.empty()) {
                std::cerr << "❌ userDataStream.start 发送失败\n";
                return 1;
            }

            if (lk_future.wait_for(std::chrono::seconds(10)) != std::future_status::ready) {
                std::cerr << "❌ 等待 listenKey 超时\n";
                return 1;
            }
            listen_key = lk_future.get();
        } else {
            std::cout << "[测试] 正在创建 listenKey (REST API)...\n";
            try {
                auto lk_resp = rest.create_listen_key();
                std::cout << "[测试] listenKey 响应: " << lk_resp.dump() << "\n";
                if (!lk_resp.contains("listenKey")) {
                    std::cerr << "❌ listenKey 响应中没有 listenKey 字段\n";
                    return 1;
                }
                listen_key = lk_resp.at("listenKey").get<std::string>();
            } catch (const std::exception& e) {
                std::cerr << "❌ 创建 listenKey 失败: " << e.what() << "\n";
                return 1;
            }
        }

        std::cout << "✅ listenKey: " << listen_key << "\n";

        std::cout << "[测试] 创建用户数据流 WebSocket...\n";
        ws_user = create_user_ws(api_key, MarketType::FUTURES, true);
        ws_user->set_account_update_callback([&](const nlohmann::json& msg) {
            print_account_update_summary(msg);
        });
        ws_user->set_order_trade_update_callback([&](const nlohmann::json& msg) {
            print_order_trade_update_summary(msg);
        });
        ws_user->set_raw_message_callback([&](const nlohmann::json& msg) {
            if (!msg.is_object()) return;
            if (!msg.contains("e")) return;
            const std::string e = msg.value("e", "");
            if (e == "ACCOUNT_UPDATE" || e == "ORDER_TRADE_UPDATE") return;
            std::cout << "\n[USER_STREAM] " << e << ": " << msg.dump() << "\n";
        });

        std::cout << "[测试] 连接用户数据流...\n";
        if (!ws_user->connect_user_stream(listen_key)) {
            std::cerr << "❌ USER_STREAM 连接失败\n";
            return 1;
        }
        std::cout << "[测试] ✅ 用户数据流连接成功\n";

        // 启动自动刷新 listenKey（每50分钟刷新一次，避免60分钟过期）
        std::cout << "\n[自动刷新] 启动 listenKey 自动刷新（间隔: " << keepalive_seconds << "秒）\n";
        ws_user->start_auto_refresh_listen_key(&rest, keepalive_seconds);

        std::cout << "\n✅ 准备就绪，等待推送中...\n";
        std::cout << "提示：\n";
        std::cout << "  - ORDER_TRADE_UPDATE: 订单创建、成交、状态变化时触发\n";
        std::cout << "  - ACCOUNT_UPDATE: 账户余额或持仓实际变化时触发\n";
        std::cout << "  - 请在测试网下单或平仓以触发事件\n";
        std::cout << "  - 程序将运行 " << run_seconds << " 秒\n\n";
        
        // 每5秒打印一次状态，确认程序还在运行
        auto start_time = std::chrono::steady_clock::now();
        int check_count = 0;
        while (true) {
            auto elapsed = std::chrono::steady_clock::now() - start_time;
            auto elapsed_seconds = std::chrono::duration_cast<std::chrono::seconds>(elapsed).count();
            
            if (elapsed_seconds >= run_seconds) {
                break;
            }
            
            // 每5秒打印一次状态
            if (elapsed_seconds > 0 && elapsed_seconds % 5 == 0 && check_count < elapsed_seconds / 5) {
                check_count = elapsed_seconds / 5;
                std::cout << "[状态] 运行中... (" << elapsed_seconds << "/" << run_seconds << "秒) ";
                if (ws_user->is_connected()) {
                    std::cout << "✅ WebSocket 已连接\n";
                } else {
                    std::cout << "❌ WebSocket 未连接\n";
                }
            }
            
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }

        // 停止自动刷新
        ws_user->stop_auto_refresh_listen_key();

        if (ws_user) ws_user->disconnect();
        if (ws_trading) ws_trading->disconnect();

        std::cout << "\n✅ 结束\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "❌ 异常: " << e.what() << "\n";
        return 1;
    }
}
