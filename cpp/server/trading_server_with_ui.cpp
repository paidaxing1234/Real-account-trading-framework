/**
 * @file trading_server_with_ui.cpp
 * @brief 带前端界面的实盘交易服务器
 * 
 * 功能：
 * 1. OKX交易所连接（REST API + WebSocket）
 * 2. WebSocket服务器（连接Vue前端）
 * 3. 策略管理（启动/停止/监控）
 * 4. 实时数据推送（行情、订单、持仓）
 * 
 * 架构：
 *   OKX交易所 ←→ 交易服务器 ←→ WebSocket ←→ Vue前端
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include "websocket_server.h"
#include "adapters/okx/okx_rest_api.h"
#include "adapters/okx/okx_websocket.h"
#include "core/event_engine.h"
#include "core/order.h"
#include "core/data.h"
#include "strategies/strategy_base.h"
#include "utils/account_manager.h"
#include <iostream>
#include <thread>
#include <csignal>
#include <atomic>
#include <map>
#include <mutex>

using namespace trading;
using namespace trading::okx;
using json = nlohmann::json;

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};

struct ServerState {
    std::mutex mutex;
    
    // 引擎
    std::unique_ptr<EventEngine> event_engine;
    std::unique_ptr<AccountManager> account_manager;
    
    // OKX连接
    std::unique_ptr<OKXRestAPI> okx_rest;
    std::unique_ptr<OKXWebSocket> okx_ws_public;
    std::unique_ptr<OKXWebSocket> okx_ws_private;
    
    // WebSocket服务器（前端）
    std::unique_ptr<WebSocketServer> frontend_server;
    
    // 策略
    std::map<std::string, std::unique_ptr<StrategyBase>> strategies;
    
    // 数据缓存
    std::map<std::string, json> tickers;
    std::vector<json> orders;
    std::map<std::string, json> positions;
    json account_info;
    
    // 统计
    int total_orders = 0;
    int filled_orders = 0;
    double total_pnl = 0.0;
};

ServerState g_state;

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Server] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
}

// ============================================================
// 生成快照数据（发送给前端）
// ============================================================

json generate_snapshot() {
    std::lock_guard<std::mutex> lock(g_state.mutex);
    
    json snapshot;
    
    // 订单列表
    snapshot["orders"] = g_state.orders;
    
    // 行情数据
    snapshot["tickers"] = g_state.tickers;
    
    // 策略列表
    json strategies_json = json::array();
    for (const auto& [id, strategy] : g_state.strategies) {
        strategies_json.push_back({
            {"strategy_id", id},
            {"name", strategy->name()},
            {"status", strategy->is_running() ? "running" : "stopped"}
        });
    }
    snapshot["strategies"] = strategies_json;
    
    // 持仓信息
    json positions_json = json::array();
    for (const auto& [symbol, pos] : g_state.positions) {
        positions_json.push_back(pos);
    }
    snapshot["positions"] = positions_json;
    
    // 账户信息
    snapshot["accounts"] = json::array({g_state.account_info});
    
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

void handle_frontend_command(int client_id, const json& message) {
    std::string action = message.value("action", "");
    json data = message.value("data", json::object());
    
    std::cout << "[前端命令] 客户端 " << client_id 
              << " | 操作: " << action << std::endl;
    
    try {
        // 下单
        if (action == "place_order") {
            std::string symbol = data.value("symbol", "BTC-USDT");
            std::string side = data.value("side", "buy");
            std::string ord_type = data.value("order_type", "limit");
            double price = data.value("price", 0.0);
            double quantity = data.value("quantity", 0.0);
            
            // 调用OKX REST API下单
            auto response = g_state.okx_rest->place_order(
                symbol,
                "cash",  // 现货交易模式
                side,
                ord_type,
                quantity,
                price
            );
            
            // 检查响应
            if (response["code"] == "0" && !response["data"].empty()) {
                auto& order_data = response["data"][0];
                if (order_data["sCode"] == "0") {
                    g_state.frontend_server->send_response(client_id, true, "下单成功");
                    g_state.frontend_server->send_log("info", "下单成功: " + symbol);
                    
                    std::cout << "[下单] 成功 | " << symbol << " " << side 
                              << " @" << price << " x" << quantity << std::endl;
                } else {
                    std::string error = order_data.value("sMsg", "未知错误");
                    g_state.frontend_server->send_response(client_id, false, "下单失败: " + error);
                }
            } else {
                std::string error = response.value("msg", "API错误");
                g_state.frontend_server->send_response(client_id, false, "下单失败: " + error);
            }
        }
        // 撤单
        else if (action == "cancel_order") {
            std::string symbol = data.value("symbol", "BTC-USDT");
            std::string order_id = data.value("order_id", "");
            
            auto response = g_state.okx_rest->cancel_order(symbol, order_id);
            
            if (response["code"] == "0") {
                g_state.frontend_server->send_response(client_id, true, "撤单成功");
                g_state.frontend_server->send_log("info", "撤单成功: " + order_id);
                
                std::cout << "[撤单] 成功 | 订单ID: " << order_id << std::endl;
            } else {
                std::string error = response.value("msg", "未知错误");
                g_state.frontend_server->send_response(client_id, false, "撤单失败: " + error);
            }
        }
        // 启动策略
        else if (action == "start_strategy") {
            std::string strategy_id = data.value("strategy_id", "");
            
            std::lock_guard<std::mutex> lock(g_state.mutex);
            auto it = g_state.strategies.find(strategy_id);
            if (it != g_state.strategies.end()) {
                it->second->start(g_state.event_engine.get());
                
                g_state.frontend_server->send_response(client_id, true, "策略启动成功");
                g_state.frontend_server->send_event("strategy_started", {
                    {"strategy_id", strategy_id},
                    {"name", it->second->name()}
                });
                
                std::cout << "[策略] 启动: " << strategy_id << std::endl;
            } else {
                g_state.frontend_server->send_response(client_id, false, "策略不存在");
            }
        }
        // 停止策略
        else if (action == "stop_strategy") {
            std::string strategy_id = data.value("strategy_id", "");
            
            std::lock_guard<std::mutex> lock(g_state.mutex);
            auto it = g_state.strategies.find(strategy_id);
            if (it != g_state.strategies.end()) {
                it->second->stop();
                
                g_state.frontend_server->send_response(client_id, true, "策略停止成功");
                g_state.frontend_server->send_event("strategy_stopped", {
                    {"strategy_id", strategy_id},
                    {"name", it->second->name()}
                });
                
                std::cout << "[策略] 停止: " << strategy_id << std::endl;
            } else {
                g_state.frontend_server->send_response(client_id, false, "策略不存在");
            }
        }
        // 查询账户
        else if (action == "query_account") {
            auto response = g_state.okx_rest->get_account_balance();
            
            if (response["code"] == "0" && !response["data"].empty()) {
                g_state.account_info = response["data"][0];
                g_state.frontend_server->send_response(client_id, true, "查询成功");
            } else {
                g_state.frontend_server->send_response(client_id, false, "查询失败");
            }
        }
        // 查询持仓
        else if (action == "query_positions") {
            auto response = g_state.okx_rest->get_positions();
            
            if (response["code"] == "0") {
                // 更新持仓缓存
                std::lock_guard<std::mutex> lock(g_state.mutex);
                g_state.positions.clear();
                
                for (const auto& pos : response["data"]) {
                    std::string symbol = pos.value("instId", "");
                    g_state.positions[symbol] = pos;
                }
                
                g_state.frontend_server->send_response(client_id, true, "查询成功");
            } else {
                g_state.frontend_server->send_response(client_id, false, "查询失败");
            }
        }
        // 未知命令
        else {
            g_state.frontend_server->send_response(client_id, false, "未知命令: " + action);
            std::cout << "[警告] 未知命令: " << action << std::endl;
        }
        
    } catch (const std::exception& e) {
        g_state.frontend_server->send_response(client_id, false, 
            std::string("处理失败: ") + e.what());
        std::cerr << "[错误] 处理命令异常: " << e.what() << std::endl;
    }
}

// ============================================================
// 主函数
// ============================================================

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  实盘交易服务器（带前端界面）" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // ========================================
    // 读取API配置
    // ========================================
    std::string api_key = std::getenv("OKX_API_KEY") 
        ? std::getenv("OKX_API_KEY") 
        : "YOUR_API_KEY";
    
    std::string secret_key = std::getenv("OKX_SECRET_KEY") 
        ? std::getenv("OKX_SECRET_KEY") 
        : "YOUR_SECRET_KEY";
    
    std::string passphrase = std::getenv("OKX_PASSPHRASE") 
        ? std::getenv("OKX_PASSPHRASE") 
        : "YOUR_PASSPHRASE";
    
    bool is_testnet = true;  // 模拟盘
    
    std::cout << "[配置] 交易模式: " << (is_testnet ? "模拟盘" : "实盘") << std::endl;
    
    // ========================================
    // 初始化核心组件
    // ========================================
    g_state.event_engine = std::make_unique<EventEngine>();
    g_state.account_manager = std::make_unique<AccountManager>();
    g_state.account_manager->start(g_state.event_engine.get());
    
    std::cout << "[初始化] 事件引擎已创建" << std::endl;
    
    // ========================================
    // 初始化OKX连接
    // ========================================
    g_state.okx_rest = std::make_unique<OKXRestAPI>(
        api_key, secret_key, passphrase, is_testnet
    );
    
    std::cout << "[初始化] OKX REST API 已创建" << std::endl;
    
    // 创建WebSocket连接（公共频道 - 行情）
    g_state.okx_ws_public = std::make_unique<OKXWebSocket>(
        "", "", "", is_testnet, WsEndpointType::PUBLIC
    );
    
    // 设置行情回调
    g_state.okx_ws_public->set_ticker_callback([](const TickerData::Ptr& ticker) {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        
        // 更新行情缓存
        g_state.tickers[ticker->symbol()] = {
            {"symbol", ticker->symbol()},
            {"last_price", ticker->last_price()},
            {"bid_price", ticker->bid_price().value_or(0.0)},
            {"ask_price", ticker->ask_price().value_or(0.0)},
            {"volume_24h", ticker->volume_24h().value_or(0.0)},
            {"timestamp", ticker->timestamp()}
        };
        
        // 推送给事件引擎
        g_state.event_engine->put(ticker);
    });
    
    // 连接并订阅行情
    if (g_state.okx_ws_public->connect()) {
        g_state.okx_ws_public->subscribe_ticker("BTC-USDT");
        g_state.okx_ws_public->subscribe_ticker("ETH-USDT");
        std::cout << "[初始化] OKX WebSocket（公共）已连接" << std::endl;
    }
    
    // 创建WebSocket连接（私有频道 - 订单/持仓）
    g_state.okx_ws_private = std::make_unique<OKXWebSocket>(
        api_key, secret_key, passphrase, is_testnet, WsEndpointType::PRIVATE
    );
    
    // 设置订单回调
    g_state.okx_ws_private->set_order_callback([](const Order::Ptr& order) {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        
        // 更新订单列表
        // TODO: 实现订单缓存逻辑
        
        // 推送给事件引擎
        g_state.event_engine->put(order);
        
        // 推送给前端
        if (g_state.frontend_server) {
            g_state.frontend_server->send_event("order_update", {
                {"order_id", order->order_id()},
                {"symbol", order->symbol()},
                {"status", static_cast<int>(order->state())},
                {"filled_quantity", order->filled_quantity()}
            });
        }
    });
    
    // 连接并登录
    if (g_state.okx_ws_private->connect()) {
        g_state.okx_ws_private->login();
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        if (g_state.okx_ws_private->is_logged_in()) {
            g_state.okx_ws_private->subscribe_orders("SPOT");
            g_state.okx_ws_private->subscribe_positions();
            std::cout << "[初始化] OKX WebSocket（私有）已连接并登录" << std::endl;
        }
    }
    
    // ========================================
    // 初始化前端WebSocket服务器
    // ========================================
    g_state.frontend_server = std::make_unique<WebSocketServer>();
    
    // 设置消息回调
    g_state.frontend_server->set_message_callback(
        [](int client_id, const json& message) {
            handle_frontend_command(client_id, message);
        }
    );
    
    // 设置快照生成器
    g_state.frontend_server->set_snapshot_generator(generate_snapshot);
    
    // 设置快照推送频率（100ms）
    g_state.frontend_server->set_snapshot_interval(100);
    
    // 启动前端服务器
    if (!g_state.frontend_server->start("0.0.0.0", 8001)) {
        std::cerr << "❌ 前端服务器启动失败" << std::endl;
        return 1;
    }
    
    std::cout << "[初始化] 前端WebSocket服务器已启动（端口8001）" << std::endl;
    
    // ========================================
    // 启动完成
    // ========================================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  服务器启动完成！" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "  前端连接: ws://localhost:8001" << std::endl;
    std::cout << "  按 Ctrl+C 停止服务器" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // 发送启动日志
    g_state.frontend_server->send_log("info", "交易服务器启动");
    
    // ========================================
    // 主循环
    // ========================================
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(10));
        
        if (g_running.load()) {
            // 打印状态
            std::cout << "[状态] 订单: " << g_state.total_orders
                      << " | 成交: " << g_state.filled_orders
                      << " | 策略: " << g_state.strategies.size()
                      << " | 前端客户端: " << g_state.frontend_server->get_client_count()
                      << std::endl;
        }
    }
    
    // ========================================
    // 停止服务
    // ========================================
    std::cout << "\n正在停止服务..." << std::endl;
    
    // 停止策略
    for (auto& [id, strategy] : g_state.strategies) {
        strategy->stop();
    }
    
    // 断开OKX连接
    if (g_state.okx_ws_public) {
        g_state.okx_ws_public->disconnect();
    }
    if (g_state.okx_ws_private) {
        g_state.okx_ws_private->disconnect();
    }
    
    // 停止前端服务器
    if (g_state.frontend_server) {
        g_state.frontend_server->stop();
    }
    
    // 停止账户管理器
    g_state.account_manager->stop();
    
    std::cout << "✅ 服务器已停止" << std::endl;
    
    return 0;
}

