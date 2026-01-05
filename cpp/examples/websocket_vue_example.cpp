/**
 * @file websocket_vue_example.cpp
 * @brief WebSocket服务器示例 - 用于Vue前端连接
 * 
 * 功能：
 * - 启动WebSocket服务器（端口8001）
 * - 定时推送快照数据（100ms）
 * - 处理前端命令（下单、撤单、启动/停止策略）
 * - 推送实时事件（订单成交、策略状态变化）
 * 
 * 编译：
 *   g++ -std=c++17 -O3 -I./core -I./external/include \
 *       websocket_vue_example.cpp -o ws_vue_server \
 *       -lboost_system -lpthread
 * 
 * 运行：
 *   ./ws_vue_server
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include "../network/websocket_server.h"
#include "../core/event_engine.h"
#include "../trading/order.h"
#include "../core/data.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>

using namespace trading;
using json = nlohmann::json;

// 全局运行标志
std::atomic<bool> g_running{true};

// 模拟数据
struct TradingState {
    std::vector<json> orders;
    std::map<std::string, json> tickers;
    std::vector<json> strategies;
    std::vector<json> positions;
    std::vector<json> accounts;
    
    // 统计数据
    int total_orders = 0;
    int filled_orders = 0;
    double total_pnl = 0.0;
};

TradingState g_state;

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
}

// ============================================================
// 生成快照数据
// ============================================================

json generate_snapshot() {
    json snapshot;
    
    // 订单列表
    snapshot["orders"] = g_state.orders;
    
    // 行情数据
    snapshot["tickers"] = g_state.tickers;
    
    // 策略列表
    snapshot["strategies"] = g_state.strategies;
    
    // 持仓信息
    snapshot["positions"] = g_state.positions;
    
    // 账户信息
    snapshot["accounts"] = g_state.accounts;
    
    // 统计数据
    snapshot["stats"] = {
        {"total_orders", g_state.total_orders},
        {"filled_orders", g_state.filled_orders},
        {"total_pnl", g_state.total_pnl},
        {"active_strategies", g_state.strategies.size()}
    };
    
    return snapshot;
}

// ============================================================
// 处理前端命令
// ============================================================

void handle_command(int client_id, const json& message, WebSocketServer& server) {
    std::string action = message.value("action", "");
    json data = message.value("data", json::object());
    
    std::cout << "[命令] 客户端 " << client_id 
              << " | 操作: " << action << std::endl;
    
    try {
        // 下单
        if (action == "place_order") {
            std::string symbol = data.value("symbol", "BTC-USDT");
            std::string side = data.value("side", "buy");
            double price = data.value("price", 0.0);
            double quantity = data.value("quantity", 0.0);
            
            // 创建订单
            json new_order = {
                {"order_id", g_state.total_orders + 1},
                {"symbol", symbol},
                {"side", side},
                {"price", price},
                {"quantity", quantity},
                {"status", "submitted"},
                {"filled_quantity", 0.0},
                {"create_time", std::chrono::system_clock::now().time_since_epoch().count() / 1000000}
            };
            
            g_state.orders.push_back(new_order);
            g_state.total_orders++;
            
            // 发送响应
            server.send_response(client_id, true, "订单提交成功");
            
            // 推送事件
            server.send_event("order_submitted", new_order);
            
            std::cout << "[下单] " << symbol << " " << side 
                      << " @" << price << " x" << quantity << std::endl;
        }
        // 撤单
        else if (action == "cancel_order") {
            int order_id = data.value("order_id", 0);
            
            // 查找并更新订单状态
            for (auto& order : g_state.orders) {
                if (order["order_id"] == order_id) {
                    order["status"] = "cancelled";
                    
                    server.send_response(client_id, true, "订单撤销成功");
                    server.send_event("order_cancelled", order);
                    
                    std::cout << "[撤单] 订单ID: " << order_id << std::endl;
                    return;
                }
            }
            
            server.send_response(client_id, false, "订单不存在");
        }
        // 启动策略
        else if (action == "start_strategy") {
            std::string strategy_id = data.value("strategy_id", "");
            
            json strategy = {
                {"strategy_id", strategy_id},
                {"name", data.value("name", "未命名策略")},
                {"status", "running"},
                {"pnl", 0.0},
                {"trades", 0}
            };
            
            g_state.strategies.push_back(strategy);
            
            server.send_response(client_id, true, "策略启动成功");
            server.send_event("strategy_started", strategy);
            
            std::cout << "[策略] 启动: " << strategy_id << std::endl;
        }
        // 停止策略
        else if (action == "stop_strategy") {
            std::string strategy_id = data.value("strategy_id", "");
            
            for (auto& strategy : g_state.strategies) {
                if (strategy["strategy_id"] == strategy_id) {
                    strategy["status"] = "stopped";
                    
                    server.send_response(client_id, true, "策略停止成功");
                    server.send_event("strategy_stopped", strategy);
                    
                    std::cout << "[策略] 停止: " << strategy_id << std::endl;
                    return;
                }
            }
            
            server.send_response(client_id, false, "策略不存在");
        }
        // 认证（如需要）
        else if (action == "auth") {
            std::string token = data.value("token", "");
            
            // 这里可以添加真实的认证逻辑
            bool auth_success = !token.empty();
            
            if (auth_success) {
                server.send_response(client_id, true, "认证成功");
                std::cout << "[认证] 客户端 " << client_id << " 认证成功" << std::endl;
            } else {
                server.send_response(client_id, false, "认证失败");
            }
        }
        // 未知命令
        else {
            server.send_response(client_id, false, "未知命令: " + action);
            std::cout << "[警告] 未知命令: " << action << std::endl;
        }
        
    } catch (const std::exception& e) {
        server.send_response(client_id, false, std::string("处理失败: ") + e.what());
        std::cerr << "[错误] 处理命令异常: " << e.what() << std::endl;
    }
}

// ============================================================
// 模拟行情更新
// ============================================================

void simulate_market_data() {
    std::cout << "[行情线程] 启动" << std::endl;
    
    // 初始化一些行情数据
    std::vector<std::string> symbols = {
        "BTC-USDT", "ETH-USDT", "BNB-USDT", "SOL-USDT"
    };
    
    std::map<std::string, double> base_prices = {
        {"BTC-USDT", 43000.0},
        {"ETH-USDT", 2300.0},
        {"BNB-USDT", 320.0},
        {"SOL-USDT", 95.0}
    };
    
    while (g_running.load()) {
        // 更新行情
        for (const auto& symbol : symbols) {
            double base_price = base_prices[symbol];
            double delta = (rand() % 200 - 100) / 100.0;  // -1 到 +1
            double current_price = base_price + delta;
            
            g_state.tickers[symbol] = {
                {"symbol", symbol},
                {"last_price", current_price},
                {"bid_price", current_price - 0.5},
                {"ask_price", current_price + 0.5},
                {"volume_24h", 10000.0 + rand() % 5000},
                {"timestamp", std::chrono::system_clock::now().time_since_epoch().count() / 1000000}
            };
        }
        
        // 模拟订单成交
        for (auto& order : g_state.orders) {
            if (order["status"] == "submitted" && rand() % 100 < 5) {  // 5%概率成交
                order["status"] = "filled";
                order["filled_quantity"] = order["quantity"];
                g_state.filled_orders++;
                
                std::cout << "[成交] 订单 " << order["order_id"] << " 已成交" << std::endl;
            }
        }
        
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
    
    std::cout << "[行情线程] 停止" << std::endl;
}

// ============================================================
// 主函数
// ============================================================

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  WebSocket服务器 - Vue前端连接" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 创建WebSocket服务器
    WebSocketServer server;
    
    // 设置消息回调
    server.set_message_callback(
        [&server](int client_id, const json& message) {
            handle_command(client_id, message, server);
        }
    );
    
    // 设置快照生成器
    server.set_snapshot_generator([]() {
        return generate_snapshot();
    });
    
    // 设置快照推送频率（100ms）
    server.set_snapshot_interval(100);
    
    // 启动服务器
    std::string host = "0.0.0.0";  // 监听所有网卡
    uint16_t port = 8001;
    
    if (!server.start(host, port)) {
        std::cerr << "❌ 服务器启动失败" << std::endl;
        return 1;
    }
    
    std::cout << "\n✅ 服务器启动成功！" << std::endl;
    std::cout << "   监听地址: ws://" << host << ":" << port << std::endl;
    std::cout << "   按 Ctrl+C 停止服务器\n" << std::endl;
    
    // 发送启动日志
    server.send_log("info", "系统启动");
    
    // 启动行情模拟线程
    std::thread market_thread(simulate_market_data);
    
    // 初始化一些默认数据
    g_state.accounts = {
        {
            {"account_id", "main"},
            {"balance", 10000.0},
            {"available", 9500.0},
            {"frozen", 500.0}
        }
    };
    
    g_state.positions = {
        {
            {"symbol", "BTC-USDT"},
            {"quantity", 0.1},
            {"avg_price", 42000.0},
            {"unrealized_pnl", 100.0}
        }
    };
    
    // 主循环
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(5));
        
        if (g_running.load()) {
            // 打印状态
            std::cout << "[状态] 订单: " << g_state.total_orders
                      << " | 成交: " << g_state.filled_orders
                      << " | 策略: " << g_state.strategies.size()
                      << " | 客户端: " << server.get_client_count() << std::endl;
        }
    }
    
    // 停止
    std::cout << "\n正在停止服务器..." << std::endl;
    
    // 等待行情线程
    market_thread.join();
    
    // 停止服务器
    server.stop();
    
    std::cout << "✅ 服务器已停止" << std::endl;
    
    return 0;
}

