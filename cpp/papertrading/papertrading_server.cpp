/**
 * @file papertrading_server.cpp
 * @brief 模拟交易服务器实现
 *
 * 功能：
 * 1. 通过ZMQ订阅主服务器的实盘行情
 * 2. 接收策略订单请求（ZMQ PULL）
 * 3. 模拟执行订单（本地引擎）
 * 4. 发布订单回报（ZMQ PUB）
 * 5. 发布行情数据（ZMQ PUB）
 *
 * @author Sequence Team
 * @date 2025-12
 */

// 先包含定义新类型的头文件（通过 papertrading_server.h）
#include "papertrading_server.h"

// 然后包含其他必要的头文件
// 注意：OrderInfo 和 OrderStatus 已在 mock_account_engine.h 中定义，避免包含 trading_module.h
#include "mock_account_engine.h"
#include "order_execution_engine.h"
#include "../server/zmq_server.h"
#include "../core/logger.h"
#include <iostream>
#include <chrono>
#include <csignal>

using namespace trading;
using namespace trading::server;
using namespace trading::core;
using namespace std::chrono;

namespace trading {
namespace papertrading {

// ============================================================
// 辅助函数
// ============================================================

static std::string order_status_to_string(OrderStatus status) {
    switch (status) {
        case OrderStatus::PENDING: return "pending";
        case OrderStatus::SUBMITTED: return "submitted";
        case OrderStatus::ACCEPTED: return "accepted";
        case OrderStatus::PARTIALLY_FILLED: return "partially_filled";
        case OrderStatus::FILLED: return "filled";
        case OrderStatus::CANCELLED: return "cancelled";
        case OrderStatus::REJECTED: return "rejected";
        case OrderStatus::FAILED: return "failed";
        default: return "unknown";
    }
}

// ============================================================
// 构造函数和析构函数
// ============================================================

PaperTradingServer::PaperTradingServer(const PaperTradingConfig& config)
    : config_(config) {
}

PaperTradingServer::PaperTradingServer(double initial_balance, bool is_testnet) {
    config_.use_defaults();
    config_.set_initial_balance(initial_balance);
    config_.set_testnet(is_testnet);
}

PaperTradingServer::~PaperTradingServer() {
    stop();
}

// ============================================================
// 生命周期管理
// ============================================================

bool PaperTradingServer::start() {
    if (running_.load()) {
        LOG_ERROR("服务器已经在运行中");
        return false;
    }

    // 初始化日志系统
    Logger::instance().init("logs", "papertrading", LogLevel::INFO);
    LOG_INFO("正在启动模拟交易服务器...");

    // 初始化模拟账户引擎
    mock_account_engine_ = std::make_shared<MockAccountEngine>(config_.initial_balance());
    LOG_INFO("模拟账户引擎已初始化，初始余额: " + std::to_string(config_.initial_balance()) + " USDT");

    // 注意：MarketDataModule主要用于策略端，服务器端不需要
    // 如果需要存储行情数据供订单执行引擎使用，可以单独实现

    // 初始化订单执行引擎
    order_execution_engine_ = std::make_unique<OrderExecutionEngine>(mock_account_engine_.get(), &config_);
    LOG_INFO("订单执行引擎已初始化");
    
    // 初始化ZMQ服务器
    init_zmq_server();
    
    // 初始化前端WebSocket服务器
    init_frontend_server();

    // 初始化ZMQ行情客户端
    init_zmq_market_data_client();

    // 启动工作线程
    zmq_server_->set_order_callback([this](const nlohmann::json& order_json) {
        std::string type = order_json.value("type", "order_request");
        if (type == "order_request") {
            handle_order_request(order_json);
        } else if (type == "cancel_request") {
            handle_cancel_request(order_json);
        } else if (type == "cancel_all_request") {
            handle_cancel_all_request(order_json);
        }
    });
    
    zmq_server_->set_query_callback([this](const nlohmann::json& query_json) -> nlohmann::json {
        return handle_query_request(query_json);
    });
    
    zmq_server_->set_subscribe_callback([this](const nlohmann::json& sub_json) {
        handle_subscribe_request(sub_json);
    });
    
    // 启动工作线程
    order_thread_ = std::thread([this]() {
        while (running_.load()) {
            zmq_server_->poll_orders();
            std::this_thread::sleep_for(microseconds(100));
        }
    });
    
    query_thread_ = std::thread([this]() {
        while (running_.load()) {
            zmq_server_->poll_queries();
            std::this_thread::sleep_for(milliseconds(1));
        }
    });
    
    subscribe_thread_ = std::thread([this]() {
        while (running_.load()) {
            zmq_server_->poll_subscriptions();
            std::this_thread::sleep_for(milliseconds(10));
        }
    });

    market_data_thread_ = std::thread([this]() {
        while (running_.load()) {
            if (market_data_sub_) {
                zmq::message_t message;
                auto result = market_data_sub_->recv(message, zmq::recv_flags::dontwait);
                if (result) {
                    try {
                        std::string msg_str(static_cast<char*>(message.data()), message.size());
                        nlohmann::json data = nlohmann::json::parse(msg_str);
                        on_market_data_update(data);
                    } catch (const std::exception& e) {
                        LOG_ERROR("解析行情数据失败: " + std::string(e.what()));
                    }
                }
            }
            std::this_thread::sleep_for(microseconds(100));
        }
    });

    running_.store(true);
    LOG_INFO("模拟交易服务器启动完成（所有工作线程已启动，主线程不阻塞）");
    
    // 注意：start()方法快速返回，所有工作都在独立线程中运行
    // - order_thread_: 处理订单请求
    // - query_thread_: 处理查询请求
    // - subscribe_thread_: 处理订阅请求
    // - frontend_server_: WebSocket服务器（独立线程）
    // - snapshot_thread: 快照推送（独立线程）
    
    return true;
}

void PaperTradingServer::stop() {
    if (!running_.load()) {
        return;
    }
    
    LOG_INFO("正在停止模拟交易服务器...");
    running_.store(false);

    // 等待工作线程退出
    if (order_thread_.joinable()) {
        order_thread_.join();
    }
    if (query_thread_.joinable()) {
        query_thread_.join();
    }
    if (subscribe_thread_.joinable()) {
        subscribe_thread_.join();
    }
    if (market_data_thread_.joinable()) {
        market_data_thread_.join();
    }

    // 停止前端WebSocket服务器
    if (frontend_server_) {
        frontend_server_->stop();
    }
    
    // 停止ZMQ服务器
    if (zmq_server_) {
        zmq_server_->stop();
    }
    
    LOG_INFO("模拟交易服务器已停止");
}

// ============================================================
// 初始化方法
// ============================================================

void PaperTradingServer::init_zmq_server() {
    zmq_server_ = std::make_unique<server::ZmqServer>(true);  // true = 使用模拟盘地址
    if (!zmq_server_->start()) {
        throw std::runtime_error("ZMQ服务器启动失败");
    }
    LOG_INFO("ZMQ服务器已启动");
}

void PaperTradingServer::init_zmq_market_data_client() {
    zmq_context_ = std::make_unique<zmq::context_t>(1);
    market_data_sub_ = std::make_unique<zmq::socket_t>(*zmq_context_, zmq::socket_type::sub);

    // 连接到主服务器的行情发布端口
    market_data_sub_->connect(IpcAddresses::MARKET_DATA);

    // 订阅所有行情消息（空字符串表示订阅所有）
    market_data_sub_->set(zmq::sockopt::subscribe, "");

    // 设置非阻塞模式
    market_data_sub_->set(zmq::sockopt::rcvtimeo, 0);

    LOG_INFO("ZMQ行情订阅已连接到主服务器");
}

// ============================================================
// ZMQ行情回调
// ============================================================

void PaperTradingServer::on_market_data_update(const nlohmann::json& data) {
    try {
        std::string type = data.value("type", "");

        if (type == "trade") {
            // 更新最新成交价
            std::string symbol = data.value("symbol", "");
            double price = data.value("price", 0.0);
            if (!symbol.empty() && price > 0) {
                std::lock_guard<std::mutex> lock(prices_mutex_);
                last_trade_prices_[symbol] = price;
            }

            // 转发给订阅者
            zmq_server_->publish_ticker(data);

            // 发送给前端
            if (frontend_server_) {
                frontend_server_->send_event("trade", data);
            }
        } else if (type == "kline") {
            zmq_server_->publish_kline(data);
            if (frontend_server_) {
                frontend_server_->send_event("kline", data);
            }
        } else if (type == "orderbook") {
            zmq_server_->publish_depth(data);
            if (frontend_server_) {
                frontend_server_->send_event("orderbook", data);
            }
        }
    } catch (const std::exception& e) {
        LOG_ERROR("处理行情数据失败: " + std::string(e.what()));
    }
}

// ============================================================
// 订单处理
// ============================================================

void PaperTradingServer::handle_order_request(const nlohmann::json& order_json) {
    // 解析订单请求
    OrderInfo order;
    order.client_order_id = order_json.value("client_order_id", "");
    order.symbol = order_json.value("symbol", "");
    order.side = order_json.value("side", "");
    order.order_type = order_json.value("order_type", "");
    order.quantity = order_json.value("quantity", 0);
    order.price = order_json.value("price", 0.0);
    order.pos_side = order_json.value("pos_side", "net");
    order.create_time = current_timestamp_ms();
    order.update_time = order.create_time;
    order.status = OrderStatus::SUBMITTED;
    
    if (order.client_order_id.empty() || order.symbol.empty() || order.side.empty() || order.quantity <= 0) {
        nlohmann::json report = {
            {"type", "order_response"},
            {"strategy_id", order_json.value("strategy_id", "unknown")},
            {"client_order_id", order.client_order_id},
            {"status", "rejected"},
            {"error_msg", "Invalid order request: missing required fields"},
            {"timestamp", current_timestamp_ms()}
        };
        zmq_server_->publish_report(report);
        return;
    }
    
    // 获取最新成交价（用于市价单）
    double last_price = 0.0;
    {
        std::lock_guard<std::mutex> lock(prices_mutex_);
        auto it = last_trade_prices_.find(order.symbol);
        if (it != last_trade_prices_.end()) {
            last_price = it->second;
        }
    }
    
    OrderReport report;
    if (order.order_type == "market") {
        // 市价单：立即执行
        if (last_price == 0.0) {
            report.status = "rejected";
            report.error_msg = "No market data available";
        } else {
            report = order_execution_engine_->execute_market_order(order, last_price);
        }
    } else if (order.order_type == "limit") {
        // 限价单：挂单
        report = order_execution_engine_->execute_limit_order(order);
        // 挂单后，需要添加到MockAccountEngine的订单簿中
        if (report.status == "accepted") {
            mock_account_engine_->add_limit_order(order);
        }
    } else {
        report.status = "rejected";
        report.error_msg = "Unsupported order type: " + order.order_type;
    }
    
    // 发布订单回报
    nlohmann::json report_json = report.to_json();
    report_json["strategy_id"] = order_json.value("strategy_id", "unknown");
    zmq_server_->publish_report(report_json);
}

void PaperTradingServer::handle_cancel_request(const nlohmann::json& cancel_json) {
    std::string client_order_id = cancel_json.value("client_order_id", "");
    std::string symbol = cancel_json.value("symbol", "");
    
    if (client_order_id.empty() || symbol.empty()) {
        return;
    }
    
    // 从MockAccountEngine中撤销订单
    bool success = mock_account_engine_->cancel_order(client_order_id);
    
    // 生成回报
    nlohmann::json report = {
        {"type", "order_response"},
        {"strategy_id", cancel_json.value("strategy_id", "unknown")},
        {"client_order_id", client_order_id},
        {"symbol", symbol},
        {"status", success ? "cancelled" : "rejected"},
        {"error_msg", success ? "" : "Order not found"},
        {"timestamp", current_timestamp_ms()}
    };
    
    zmq_server_->publish_report(report);
}

void PaperTradingServer::handle_cancel_all_request(const nlohmann::json& cancel_all_json) {
    std::string symbol = cancel_all_json.value("symbol", "");
    
    // 获取所有挂单
    auto open_orders = mock_account_engine_->get_open_orders();
    
    int cancelled_count = 0;
    for (const auto& order : open_orders) {
        if (symbol.empty() || order.symbol == symbol) {
            if (mock_account_engine_->cancel_order(order.client_order_id)) {
                cancelled_count++;
            }
        }
    }
    
    LOG_INFO("批量撤单: " + std::to_string(cancelled_count) + " 个订单");
}

nlohmann::json PaperTradingServer::handle_query_request(const nlohmann::json& query_json) {
    std::string query_type = query_json.value("query_type", "");
    
    if (query_type == "account" || query_type == "balance") {
        // 账户余额查询
        double available = mock_account_engine_->get_available_usdt();
        double frozen = mock_account_engine_->get_frozen_usdt();
        double total = mock_account_engine_->get_total_usdt();
        
        return {
            {"code", 0},
            {"query_type", query_type},
            {"data", {
                {"available", available},
                {"frozen", frozen},
                {"total", total},
                {"currency", "USDT"}
            }}
        };
    } else if (query_type == "positions") {
        // 持仓查询
        auto positions = mock_account_engine_->get_active_positions();
        nlohmann::json positions_json = nlohmann::json::array();
        
        for (const auto& pos : positions) {
            positions_json.push_back({
                {"symbol", pos.symbol},
                {"pos_side", pos.pos_side},
                {"quantity", pos.quantity},
                {"avg_price", pos.avg_price},
                {"mark_price", pos.mark_price},
                {"unrealized_pnl", pos.unrealized_pnl},
                {"realized_pnl", pos.realized_pnl},
                {"margin", pos.margin},
                {"leverage", pos.leverage}
            });
        }
        
        return {
            {"code", 0},
            {"query_type", query_type},
            {"data", positions_json}
        };
    } else if (query_type == "pending_orders" || query_type == "orders") {
        // 未成交订单查询
        auto orders = mock_account_engine_->get_open_orders();
        nlohmann::json orders_json = nlohmann::json::array();
        
        for (const auto& order : orders) {
            orders_json.push_back({
                {"client_order_id", order.client_order_id},
                {"exchange_order_id", order.exchange_order_id},
                {"symbol", order.symbol},
                {"side", order.side},
                {"order_type", order.order_type},
                {"price", order.price},
                {"quantity", order.quantity},
                {"filled_quantity", order.filled_quantity},
                {"status", order_status_to_string(order.status)}
            });
        }
        
        return {
            {"code", 0},
            {"query_type", query_type},
            {"data", orders_json}
        };
    } else {
        return {
            {"code", -1},
            {"error", "Unknown query type: " + query_type}
        };
    }
}

void PaperTradingServer::handle_subscribe_request(const nlohmann::json& sub_json) {
    std::string action = sub_json.value("action", "subscribe");
    std::string channel = sub_json.value("channel", "");
    std::string symbol = sub_json.value("symbol", "");
    std::string interval = sub_json.value("interval", "1m");

    std::lock_guard<std::mutex> lock(subscribed_symbols_mutex_);

    // PaperTrading服务器从主服务器订阅行情，不直接连接交易所
    // 这里只记录订阅状态，实际行情由主服务器通过ZMQ推送
    if (channel == "trades") {
        if (action == "subscribe") {
            subscribed_trades_.insert(symbol);
            LOG_INFO("订阅 trades: " + symbol + " (通过主服务器)");
        } else if (action == "unsubscribe") {
            subscribed_trades_.erase(symbol);
            LOG_INFO("取消订阅 trades: " + symbol);
        }
    } else if (channel == "kline" || channel == "candle") {
        if (action == "subscribe") {
            subscribed_klines_[symbol].insert(interval);
            LOG_INFO("订阅 K线: " + symbol + " " + interval + " (通过主服务器)");
        } else if (action == "unsubscribe") {
            subscribed_klines_[symbol].erase(interval);
            LOG_INFO("取消订阅 K线: " + symbol + " " + interval);
        }
    } else if (channel == "orderbook" || channel == "books" || channel == "books5") {
        std::string depth_channel = (channel == "orderbook") ? "books5" : channel;
        if (action == "subscribe") {
            subscribed_orderbooks_[symbol].insert(depth_channel);
            LOG_INFO("订阅 深度: " + symbol + " " + depth_channel + " (通过主服务器)");
        } else if (action == "unsubscribe") {
            subscribed_orderbooks_[symbol].erase(depth_channel);
            LOG_INFO("取消订阅 深度: " + symbol + " " + depth_channel);
        }
    } else if (channel == "funding_rate" || channel == "funding-rate") {
        if (action == "subscribe") {
            subscribed_funding_rates_.insert(symbol);
            LOG_INFO("订阅 资金费率: " + symbol + " (通过主服务器)");
        } else if (action == "unsubscribe") {
            subscribed_funding_rates_.erase(symbol);
            LOG_INFO("取消订阅 资金费率: " + symbol);
        }
    }
}


// ============================================================
// WebSocket前端服务器
// ============================================================

void PaperTradingServer::init_frontend_server() {
    frontend_server_ = std::make_unique<core::WebSocketServer>();
    
    // 设置消息回调（线程安全）
    frontend_server_->set_message_callback(
        [this](int client_id, const nlohmann::json& message) {
            // 注意：这个回调在WebSocket服务器的独立线程中执行
            // 不会阻塞主线程或PaperTrading服务器线程
            handle_frontend_command(client_id, message);
        }
    );
    
    // 设置快照生成器（线程安全）
    frontend_server_->set_snapshot_generator([this]() {
        // 注意：这个函数在快照推送线程中执行
        // 不会阻塞主线程
        return generate_snapshot();
    });
    
    // 设置快照推送频率（100ms）
    frontend_server_->set_snapshot_interval(100);
    
    // 启动前端服务器（在独立线程中运行，不阻塞）
    if (!frontend_server_->start("0.0.0.0", 8001)) {
        LOG_ERROR("前端WebSocket服务器启动失败");
        throw std::runtime_error("前端WebSocket服务器启动失败");
    }
    
    LOG_INFO("前端WebSocket服务器已启动（端口8001，独立线程运行）");
}

void PaperTradingServer::handle_frontend_command(int client_id, const nlohmann::json& message) {
    try {
        std::string action = message.value("action", "");
        nlohmann::json data = message.value("data", nlohmann::json::object());
        std::string request_id = data.value("requestId", "");
        
        LOG_INFO("收到前端命令: " + action + " (客户端: " + std::to_string(client_id) + ")");
        
        // 重置账户
        if (action == "reset_account") {
            if (mock_account_engine_) {
                double initial_balance = config_.initial_balance();
                mock_account_engine_->reset(initial_balance);

                frontend_server_->send_response(client_id, true, "账户重置成功", {
                    {"requestId", request_id},
                    {"initial_balance", initial_balance}
                });
                LOG_INFO("账户已重置到初始余额: " + std::to_string(initial_balance));
            } else {
                frontend_server_->send_response(client_id, false, "账户引擎未初始化", {
                    {"requestId", request_id}
                });
            }
        }
        // 更新配置
        else if (action == "update_config") {
            if (data.contains("initialBalance")) {
                double new_balance = data["initialBalance"];
                config_.set_initial_balance(new_balance);
                
                // 如果账户已初始化，更新余额
                if (mock_account_engine_) {
                    // 注意：MockAccountEngine可能需要添加set_balance方法
                    // 这里先记录，需要时再实现
                }
            }
            
            if (data.contains("makerFeeRate")) {
                config_.set_maker_fee_rate(data["makerFeeRate"]);
            }
            
            if (data.contains("takerFeeRate")) {
                config_.set_taker_fee_rate(data["takerFeeRate"]);
            }
            
            if (data.contains("slippage")) {
                config_.set_market_order_slippage(data["slippage"]);
            }

            // 保存配置到文件
            if (config_.save_to_file("papertrading_config.json")) {
                LOG_INFO("配置已保存到文件");
            } else {
                LOG_ERROR("配置保存失败");
            }

            frontend_server_->send_response(client_id, true, "配置更新成功", {
                {"requestId", request_id}
            });
            LOG_INFO("配置已更新");
        }
        // 查询账户
        else if (action == "query_account") {
            if (mock_account_engine_) {
                double balance = mock_account_engine_->get_total_usdt();
                double equity = mock_account_engine_->get_total_equity();
                double total_pnl = equity - config_.initial_balance();
                double return_rate = config_.initial_balance() > 0 
                    ? (total_pnl / config_.initial_balance()) * 100.0 
                    : 0.0;
                
                frontend_server_->send_response(client_id, true, "查询成功", {
                    {"requestId", request_id},
                    {"balance", balance},
                    {"equity", equity},
                    {"totalPnl", total_pnl},
                    {"returnRate", return_rate}
                });
            } else {
                frontend_server_->send_response(client_id, false, "账户引擎未初始化", {
                    {"requestId", request_id}
                });
            }
        }
        // 平仓
        else if (action == "close_position") {
            std::string symbol = data.value("symbol", "");
            std::string pos_side = data.value("posSide", "net");

            if (!mock_account_engine_) {
                frontend_server_->send_response(client_id, false, "账户引擎未初始化", {
                    {"requestId", request_id}
                });
                return;
            }

            // 获取持仓信息
            PositionInfo pos = mock_account_engine_->get_position_safe(symbol, pos_side);

            if (pos.quantity == 0) {
                frontend_server_->send_response(client_id, false, "无持仓", {
                    {"requestId", request_id}
                });
                return;
            }

            // 构造平仓订单（反向市价单）
            std::string close_side = (pos.quantity > 0) ? "sell" : "buy";
            int close_qty = std::abs(pos.quantity);

            nlohmann::json order_req = {
                {"symbol", symbol},
                {"side", close_side},
                {"order_type", "market"},
                {"pos_side", pos_side},
                {"quantity", close_qty}
            };

            // 提交平仓订单
            handle_order_request(order_req);

            frontend_server_->send_response(client_id, true, "平仓订单已提交", {
                {"requestId", request_id},
                {"symbol", symbol},
                {"side", close_side},
                {"quantity", close_qty}
            });
            LOG_INFO("平仓: " + symbol + " " + pos_side + " 数量: " + std::to_string(close_qty));
        }
        // 撤单
        else if (action == "cancel_order") {
            std::string order_id = data.value("orderId", "");
            
            if (mock_account_engine_ && mock_account_engine_->cancel_order(order_id)) {
                frontend_server_->send_response(client_id, true, "撤单成功", {
                    {"requestId", request_id}
                });
                LOG_INFO("撤单成功: " + order_id);
            } else {
                frontend_server_->send_response(client_id, false, "撤单失败", {
                    {"requestId", request_id}
                });
            }
        }
        // 获取配置
        else if (action == "get_config") {
            frontend_server_->send_response(client_id, true, "查询成功", {
                {"requestId", request_id},
                {"initialBalance", config_.initial_balance()},
                {"makerFeeRate", config_.maker_fee_rate()},
                {"takerFeeRate", config_.taker_fee_rate()},
                {"slippage", config_.market_order_slippage()}
            });
        }
        // 未知命令
        else {
            frontend_server_->send_response(client_id, false, "未知命令: " + action, {
                {"requestId", request_id}
            });
            LOG_ERROR("未知命令: " + action);
        }
        
    } catch (const std::exception& e) {
        std::string request_id = message.value("data", nlohmann::json::object()).value("requestId", "");
        frontend_server_->send_response(client_id, false, 
            std::string("处理失败: ") + e.what(), {
                {"requestId", request_id}
            });
        LOG_ERROR("处理前端命令异常: " + std::string(e.what()));
    }
}

nlohmann::json PaperTradingServer::generate_snapshot() {
    nlohmann::json snapshot;
    
    try {
        // 账户信息
        if (mock_account_engine_) {
            double balance = mock_account_engine_->get_total_usdt();
            double equity = mock_account_engine_->get_total_equity();
            double total_pnl = equity - config_.initial_balance();
            double return_rate = config_.initial_balance() > 0 
                ? (total_pnl / config_.initial_balance()) * 100.0 
                : 0.0;
            
            snapshot["account"] = {
                {"balance", balance},
                {"equity", equity},
                {"totalPnl", total_pnl},
                {"returnRate", return_rate}
            };
        }
        
        // 持仓列表
        if (mock_account_engine_) {
            auto positions = mock_account_engine_->get_active_positions();
            snapshot["positions"] = nlohmann::json::array();
            
            for (const auto& pos : positions) {
                snapshot["positions"].push_back({
                    {"symbol", pos.symbol},
                    {"side", pos.pos_side == "long" ? "long" : "short"},
                    {"size", pos.quantity},
                    {"entryPrice", pos.avg_price},
                    {"markPrice", pos.mark_price},
                    {"unrealizedPnl", pos.unrealized_pnl},
                    {"returnRate", pos.avg_price > 0 
                        ? ((pos.mark_price - pos.avg_price) / pos.avg_price) * 100.0 
                        : 0.0}
                });
            }
        }
        
        // 订单列表
        if (mock_account_engine_) {
            auto orders = mock_account_engine_->get_open_orders();
            snapshot["orders"] = nlohmann::json::array();
            
            for (const auto& order : orders) {
                snapshot["orders"].push_back({
                    {"orderId", order.client_order_id},
                    {"symbol", order.symbol},
                    {"side", order.side == "buy" ? "buy" : "sell"},
                    {"type", order.order_type == "market" ? "market" : "limit"},
                    {"price", order.price},
                    {"quantity", order.quantity},
                    {"filled", order.filled_quantity},
                    {"status", order.status},
                    {"createTime", order.create_time}
                });
            }
        }
        
        // 订单统计
        if (mock_account_engine_) {
            auto orders = mock_account_engine_->get_open_orders();
            int total_orders = orders.size();
            int filled_orders = 0;
            for (const auto& order : orders) {
                if (order.status == OrderStatus::FILLED) {
                    filled_orders++;
                }
            }
            
            snapshot["orderStats"] = {
                {"total", total_orders},
                {"filled", filled_orders},
                {"trades", filled_orders}  // 简化：成交笔数等于已成交订单数
            };
        }
        
        // 持仓统计
        if (mock_account_engine_) {
            auto positions = mock_account_engine_->get_active_positions();
            snapshot["positionStats"] = {
                {"total", static_cast<int>(positions.size())}
            };
        }
        
    } catch (const std::exception& e) {
        LOG_ERROR("生成快照失败: " + std::string(e.what()));
    }
    
    return snapshot;
}

} // namespace papertrading
} // namespace trading

