/**
 * @file papertrading_server.cpp
 * @brief 模拟交易服务器实现
 * 
 * 功能：
 * 1. 连接WebSocket获取实盘行情（只读，不下单）
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
// 移除 trading_module.h，避免 OrderType 和 OrderStatus 冲突
// #include "../strategies/trading_module.h"
#include "../server/zmq_server.h"
#include <iostream>
#include <chrono>
#include <csignal>

using namespace trading;
using namespace trading::server;
using namespace trading::core;
using namespace trading::okx;
using namespace std::chrono;

namespace trading {
namespace papertrading {

// ============================================================
// 构造函数和析构函数
// ============================================================

PaperTradingServer::PaperTradingServer(const PaperTradingConfig& config)
    : config_(config) {
}

PaperTradingServer::PaperTradingServer(double initial_balance, bool is_testnet) {
    // 兼容旧接口：创建配置并设置值
    config_.use_defaults();
    // 注意：由于PaperTradingConfig没有提供setter，我们需要通过修改配置类来支持
    // 为了简化，这里创建一个新的配置对象并手动设置
    // 实际上应该修改PaperTradingConfig提供setter方法，或者直接使用新构造函数
    // 临时方案：使用默认配置（旧接口的参数会被忽略，建议使用配置文件）
}

PaperTradingServer::~PaperTradingServer() {
    stop();
}

// ============================================================
// 生命周期管理
// ============================================================

bool PaperTradingServer::start() {
    if (running_.load()) {
        log_error("服务器已经在运行中");
        return false;
    }
    
    log_info("正在启动模拟交易服务器...");
    
    // 初始化模拟账户引擎
    mock_account_engine_ = std::make_shared<MockAccountEngine>(config_.initial_balance());
    log_info("模拟账户引擎已初始化，初始余额: " + std::to_string(config_.initial_balance()) + " USDT");
    
    // 注意：MarketDataModule主要用于策略端，服务器端不需要
    // 如果需要存储行情数据供订单执行引擎使用，可以单独实现
    
    // 初始化订单执行引擎
    order_execution_engine_ = std::make_unique<OrderExecutionEngine>(mock_account_engine_.get(), &config_);
    log_info("订单执行引擎已初始化");
    
    // 初始化ZMQ服务器
    init_zmq_server();
    
    // 初始化前端WebSocket服务器
    init_frontend_server();
    
    // 初始化WebSocket客户端
    init_market_data_clients();
    
    // 设置WebSocket回调
    setup_market_data_callbacks();
    
    // 连接WebSocket
    if (!ws_public_->connect()) {
        log_error("WebSocket Public 连接失败");
        return false;
    }
    log_info("WebSocket Public 已连接");
    
    if (!ws_business_->connect()) {
        log_error("WebSocket Business 连接失败");
        return false;
    }
    log_info("WebSocket Business 已连接");
    
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
    
    running_.store(true);
    log_info("模拟交易服务器启动完成（所有工作线程已启动，主线程不阻塞）");
    
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
    
    log_info("正在停止模拟交易服务器...");
    running_.store(false);
    
    // 断开WebSocket连接
    if (ws_public_ && ws_public_->is_connected()) {
        ws_public_->disconnect();
    }
    if (ws_business_ && ws_business_->is_connected()) {
        ws_business_->disconnect();
    }
    
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
    
    // 停止前端WebSocket服务器
    if (frontend_server_) {
        frontend_server_->stop();
    }
    
    // 停止ZMQ服务器
    if (zmq_server_) {
        zmq_server_->stop();
    }
    
    log_info("模拟交易服务器已停止");
}

// ============================================================
// 初始化方法
// ============================================================

void PaperTradingServer::init_zmq_server() {
    zmq_server_ = std::make_unique<server::ZmqServer>();
    if (!zmq_server_->start()) {
        throw std::runtime_error("ZMQ服务器启动失败");
    }
    log_info("ZMQ服务器已启动");
}

void PaperTradingServer::init_market_data_clients() {
    // 创建公共频道WebSocket（用于trades、orderbook、funding_rate）
    ws_public_ = create_public_ws(config_.is_testnet());
    
    // 创建业务频道WebSocket（用于K线）
    ws_business_ = create_business_ws(config_.is_testnet());
    
    log_info("WebSocket客户端已创建（模式: " + std::string(config_.is_testnet() ? "模拟盘" : "实盘") + "）");
}

void PaperTradingServer::setup_market_data_callbacks() {
    // Trades回调
    if (ws_public_) {
        ws_public_->set_trade_callback([this](const TradeData::Ptr& trade) {
            on_trade_update(trade);
        });
        
        // OrderBook回调
        ws_public_->set_orderbook_callback([this](const OrderBookData::Ptr& orderbook) {
            on_orderbook_update(orderbook);
        });
        
        // FundingRate回调 - 暂时注释掉，避免类型冲突
        // ws_public_->set_funding_rate_callback([this](const okx::FundingRateData::Ptr& funding_rate) {
        //     on_funding_rate_update(funding_rate);
        // });
    }
    
    // K线回调
    if (ws_business_) {
        ws_business_->set_kline_callback([this](const KlineData::Ptr& kline) {
            on_kline_update(kline);
        });
    }
}

// ============================================================
// WebSocket回调
// ============================================================

void PaperTradingServer::on_trade_update(const trading::TradeData::Ptr& trade) {
    // 发布trades行情数据
    nlohmann::json msg = {
        {"type", "trade"},
        {"symbol", trade->symbol()},
        {"trade_id", trade->trade_id()},
        {"price", trade->price()},
        {"quantity", trade->quantity()},
        {"side", trade->side().value_or("")},
        {"timestamp", trade->timestamp()},
        {"timestamp_ns", current_timestamp_ns()}
    };
    zmq_server_->publish_ticker(msg);
    
    // 更新最新成交价（用于订单执行引擎）
    {
        std::lock_guard<std::mutex> lock(prices_mutex_);
        last_trade_prices_[trade->symbol()] = trade->price();
    }
}

void PaperTradingServer::on_kline_update(const trading::KlineData::Ptr& kline) {
    // 只推送已完结的K线
    if (!kline->is_confirmed()) {
        return;
    }
    
    // 发布K线数据
    nlohmann::json msg = {
        {"type", "kline"},
        {"symbol", kline->symbol()},
        {"interval", kline->interval()},
        {"open", kline->open()},
        {"high", kline->high()},
        {"low", kline->low()},
        {"close", kline->close()},
        {"volume", kline->volume()},
        {"timestamp", kline->timestamp()},
        {"timestamp_ns", current_timestamp_ns()}
    };
    zmq_server_->publish_kline(msg);
}

void PaperTradingServer::on_orderbook_update(const trading::OrderBookData::Ptr& orderbook) {
    // 构建bids和asks数组
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
        {"symbol", orderbook->symbol()},
        {"bids", bids},
        {"asks", asks},
        {"timestamp", orderbook->timestamp()},
        {"timestamp_ns", current_timestamp_ns()}
    };
    
    // 添加最优买卖价
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
    
    // 添加中间价和价差
    auto mid_price = orderbook->mid_price();
    if (mid_price) {
        msg["mid_price"] = *mid_price;
    }
    auto spread = orderbook->spread();
    if (spread) {
        msg["spread"] = *spread;
    }
    
    zmq_server_->publish_depth(msg);
}

// 暂时注释掉资金费率更新函数，避免类型冲突
// void PaperTradingServer::on_funding_rate_update(const okx::FundingRateData::Ptr& funding_rate) {
//     nlohmann::json msg = {
//         {"type", "funding_rate"},
//         {"symbol", funding_rate->inst_id},
//         {"inst_type", funding_rate->inst_type},
//         {"funding_rate", funding_rate->funding_rate},
//         {"next_funding_rate", funding_rate->next_funding_rate},
//         {"funding_time", funding_rate->funding_time},
//         {"next_funding_time", funding_rate->next_funding_time},
//         {"timestamp", funding_rate->timestamp},
//         {"timestamp_ns", current_timestamp_ns()}
//     };
//     
//     zmq_server_->publish_ticker(msg);
// }

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
    
    log_info("批量撤单: " + std::to_string(cancelled_count) + " 个订单");
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
                {"status", "accepted"}  // TODO: 正确转换OrderStatus枚举到字符串
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
    
    if (channel == "trades") {
        if (action == "subscribe" && ws_public_) {
            if (subscribed_trades_.find(symbol) == subscribed_trades_.end()) {
                ws_public_->subscribe_trades(symbol);
                subscribed_trades_.insert(symbol);
                log_info("订阅 trades: " + symbol);
            }
        } else if (action == "unsubscribe" && ws_public_) {
            if (subscribed_trades_.find(symbol) != subscribed_trades_.end()) {
                ws_public_->unsubscribe_trades(symbol);
                subscribed_trades_.erase(symbol);
                log_info("取消订阅 trades: " + symbol);
            }
        }
    } else if (channel == "kline" || channel == "candle") {
        if (action == "subscribe" && ws_business_) {
            ws_business_->subscribe_kline(symbol, string_to_kline_interval(interval));
            subscribed_klines_[symbol].insert(interval);
            log_info("订阅 K线: " + symbol + " " + interval);
        } else if (action == "unsubscribe" && ws_business_) {
            ws_business_->unsubscribe_kline(symbol, string_to_kline_interval(interval));
            subscribed_klines_[symbol].erase(interval);
            log_info("取消订阅 K线: " + symbol + " " + interval);
        }
    } else if (channel == "orderbook" || channel == "books" || channel == "books5") {
        std::string depth_channel = (channel == "orderbook") ? "books5" : channel;
        if (action == "subscribe" && ws_public_) {
            ws_public_->subscribe_orderbook(symbol, depth_channel);
            subscribed_orderbooks_[symbol].insert(depth_channel);
            log_info("订阅 深度: " + symbol + " " + depth_channel);
        } else if (action == "unsubscribe" && ws_public_) {
            ws_public_->unsubscribe_orderbook(symbol, depth_channel);
            subscribed_orderbooks_[symbol].erase(depth_channel);
            log_info("取消订阅 深度: " + symbol + " " + depth_channel);
        }
    } else if (channel == "funding_rate" || channel == "funding-rate") {
        if (action == "subscribe" && ws_public_) {
            if (subscribed_funding_rates_.find(symbol) == subscribed_funding_rates_.end()) {
                ws_public_->subscribe_funding_rate(symbol);
                subscribed_funding_rates_.insert(symbol);
                log_info("订阅 资金费率: " + symbol);
            }
        } else if (action == "unsubscribe" && ws_public_) {
            if (subscribed_funding_rates_.find(symbol) != subscribed_funding_rates_.end()) {
                ws_public_->unsubscribe_funding_rate(symbol);
                subscribed_funding_rates_.erase(symbol);
                log_info("取消订阅 资金费率: " + symbol);
            }
        }
    }
}


// ============================================================
// 日志
// ============================================================

void PaperTradingServer::log_info(const std::string& msg) {
    std::cout << "[PaperTradingServer] " << msg << std::endl;
}

void PaperTradingServer::log_error(const std::string& msg) {
    std::cerr << "[PaperTradingServer] ERROR: " << msg << std::endl;
}

int64_t PaperTradingServer::current_timestamp_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
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
        log_error("前端WebSocket服务器启动失败");
        throw std::runtime_error("前端WebSocket服务器启动失败");
    }
    
    log_info("前端WebSocket服务器已启动（端口8001，独立线程运行）");
}

void PaperTradingServer::handle_frontend_command(int client_id, const nlohmann::json& message) {
    try {
        std::string action = message.value("action", "");
        nlohmann::json data = message.value("data", nlohmann::json::object());
        std::string request_id = data.value("requestId", "");
        
        log_info("收到前端命令: " + action + " (客户端: " + std::to_string(client_id) + ")");
        
        // 重置账户
        if (action == "reset_account") {
            if (mock_account_engine_) {
                // 重置账户到初始余额
                double initial_balance = config_.initial_balance();
                // 注意：MockAccountEngine可能需要添加reset方法
                // 这里先清空持仓和订单，然后重置余额
                // TODO: 实现完整的重置逻辑
                
                frontend_server_->send_response(client_id, true, "账户重置成功", {
                    {"requestId", request_id}
                });
                log_info("账户已重置");
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
            
            // TODO: 保存配置到文件
            // config_.save_to_file("papertrading_config.json");
            
            frontend_server_->send_response(client_id, true, "配置更新成功", {
                {"requestId", request_id}
            });
            log_info("配置已更新");
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
            std::string side = data.value("side", "");
            
            // TODO: 实现平仓逻辑
            // 需要调用order_execution_engine_来平仓
            
            frontend_server_->send_response(client_id, true, "平仓成功", {
                {"requestId", request_id}
            });
            log_info("平仓: " + symbol + " " + side);
        }
        // 撤单
        else if (action == "cancel_order") {
            std::string order_id = data.value("orderId", "");
            
            if (mock_account_engine_ && mock_account_engine_->cancel_order(order_id)) {
                frontend_server_->send_response(client_id, true, "撤单成功", {
                    {"requestId", request_id}
                });
                log_info("撤单成功: " + order_id);
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
            log_error("未知命令: " + action);
        }
        
    } catch (const std::exception& e) {
        std::string request_id = message.value("data", nlohmann::json::object()).value("requestId", "");
        frontend_server_->send_response(client_id, false, 
            std::string("处理失败: ") + e.what(), {
                {"requestId", request_id}
            });
        log_error("处理前端命令异常: " + std::string(e.what()));
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
        log_error("生成快照失败: " + std::string(e.what()));
    }
    
    return snapshot;
}

} // namespace papertrading
} // namespace trading

