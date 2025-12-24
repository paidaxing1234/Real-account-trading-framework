/**
 * @file binance_adapter.cpp
 * @brief Binance交易所适配器实现
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "binance_adapter.h"
#include <iostream>
#include <chrono>
#include <thread>

namespace trading {
namespace binance {

BinanceAdapter::BinanceAdapter(
    const std::string& api_key,
    const std::string& secret_key,
    MarketType market_type,
    bool is_testnet
)
    : api_key_(api_key)
    , secret_key_(secret_key)
    , market_type_(market_type)
    , is_testnet_(is_testnet)
{
    // 创建REST API客户端
    rest_api_ = std::make_unique<BinanceRestAPI>(
        api_key_, secret_key_, market_type_, is_testnet_
    );
    
    // 创建行情WebSocket
    websocket_market_ = std::make_unique<BinanceWebSocket>(
        "", "", WsConnectionType::MARKET, market_type_, is_testnet_
    );
    
    // 如果有API密钥，创建用户数据WebSocket
    if (!api_key_.empty()) {
        websocket_userdata_ = std::make_unique<BinanceWebSocket>(
            api_key_, "", WsConnectionType::USER_DATA, market_type_, is_testnet_
        );
    }
    
    std::cout << "[BinanceAdapter] 初始化完成 "
              << "(market_type=" << (int)market_type_ 
              << ", testnet=" << is_testnet_ << ")" << std::endl;
}

void BinanceAdapter::start(EventEngine* engine) {
    engine_ = engine;
    
    std::cout << "[BinanceAdapter] 启动适配器..." << std::endl;
    
    // 设置行情WebSocket回调
    websocket_market_->set_ticker_callback([this](const TickerData::Ptr& ticker) {
        on_ticker_update(ticker);
    });
    
    websocket_market_->set_trade_callback([this](const TradeData::Ptr& trade) {
        on_trade_update(trade);
    });
    
    websocket_market_->set_orderbook_callback([this](const OrderBookData::Ptr& orderbook) {
        on_orderbook_update(orderbook);
    });
    
    websocket_market_->set_kline_callback([this](const KlineData::Ptr& kline) {
        on_kline_update(kline);
    });
    
    // 连接行情WebSocket
    if (!websocket_market_->connect()) {
        std::cerr << "[BinanceAdapter] 行情WebSocket连接失败" << std::endl;
    }
    
    // 如果有用户数据WebSocket，启动它
    if (websocket_userdata_) {
        // 设置用户数据WebSocket回调
        websocket_userdata_->set_order_update_callback([this](const Order::Ptr& order) {
            on_order_update(order);
        });
        
        websocket_userdata_->set_account_update_callback([this](const nlohmann::json& account) {
            on_account_update(account);
        });
        
        // 创建listenKey
        listen_key_ = create_listen_key();
        
        if (!listen_key_.empty()) {
            // 连接用户数据WebSocket
            if (websocket_userdata_->connect()) {
                // 订阅用户数据流
                websocket_userdata_->subscribe_user_data(listen_key_);
                
                // 启动keep-alive线程
                keep_alive_running_ = true;
                keep_alive_thread_ = std::make_unique<std::thread>([this]() {
                    keep_alive_listen_key();
                });
                
                std::cout << "[BinanceAdapter] 用户数据流已启动" << std::endl;
            }
        }
    }
    
    // 注册订单事件监听
    engine_->subscribe(EventType::ORDER, 
        std::bind(&BinanceAdapter::on_order_event, this, std::placeholders::_1)
    );
    
    std::cout << "[BinanceAdapter] 适配器启动完成" << std::endl;
}

void BinanceAdapter::stop() {
    std::cout << "[BinanceAdapter] 停止适配器..." << std::endl;
    
    // 停止keep-alive线程
    keep_alive_running_ = false;
    if (keep_alive_thread_ && keep_alive_thread_->joinable()) {
        keep_alive_thread_->join();
    }
    
    // 断开WebSocket连接
    if (websocket_market_) {
        websocket_market_->disconnect();
    }
    
    if (websocket_userdata_) {
        websocket_userdata_->disconnect();
    }
    
    if (websocket_trading_) {
        websocket_trading_->disconnect();
    }
    
    std::cout << "[BinanceAdapter] 适配器已停止" << std::endl;
}

// ==================== 行情订阅 ====================

void BinanceAdapter::subscribe_ticker(const std::string& symbol) {
    if (!websocket_market_) return;
    
    // Binance要求小写symbol
    std::string lower_symbol = symbol;
    std::transform(lower_symbol.begin(), lower_symbol.end(), 
                   lower_symbol.begin(), ::tolower);
    
    websocket_market_->subscribe_ticker(lower_symbol);
    std::cout << "[BinanceAdapter] 订阅Ticker: " << symbol << std::endl;
}

void BinanceAdapter::subscribe_trades(const std::string& symbol) {
    if (!websocket_market_) return;
    
    std::string lower_symbol = symbol;
    std::transform(lower_symbol.begin(), lower_symbol.end(), 
                   lower_symbol.begin(), ::tolower);
    
    websocket_market_->subscribe_trade(lower_symbol);
    std::cout << "[BinanceAdapter] 订阅逐笔成交: " << symbol << std::endl;
}

void BinanceAdapter::subscribe_orderbook(const std::string& symbol, int levels) {
    if (!websocket_market_) return;
    
    std::string lower_symbol = symbol;
    std::transform(lower_symbol.begin(), lower_symbol.end(), 
                   lower_symbol.begin(), ::tolower);
    
    websocket_market_->subscribe_depth(lower_symbol, levels);
    std::cout << "[BinanceAdapter] 订阅深度: " << symbol 
              << " (档位: " << levels << ")" << std::endl;
}

void BinanceAdapter::subscribe_kline(const std::string& symbol, const std::string& interval) {
    if (!websocket_market_) return;
    
    std::string lower_symbol = symbol;
    std::transform(lower_symbol.begin(), lower_symbol.end(), 
                   lower_symbol.begin(), ::tolower);
    
    websocket_market_->subscribe_kline(lower_symbol, interval);
    std::cout << "[BinanceAdapter] 订阅K线: " << symbol 
              << " (" << interval << ")" << std::endl;
}

// ==================== 私有频道订阅 ====================

void BinanceAdapter::subscribe_orders() {
    // 用户数据流会自动推送订单更新，无需额外订阅
    std::cout << "[BinanceAdapter] 订单更新已通过用户数据流自动订阅" << std::endl;
}

void BinanceAdapter::subscribe_positions() {
    if (market_type_ == MarketType::SPOT) {
        std::cout << "[BinanceAdapter] 现货市场不支持持仓订阅" << std::endl;
        return;
    }
    
    // 合约市场的用户数据流会自动推送持仓更新
    std::cout << "[BinanceAdapter] 持仓更新已通过用户数据流自动订阅" << std::endl;
}

void BinanceAdapter::subscribe_account() {
    // 用户数据流会自动推送账户更新
    std::cout << "[BinanceAdapter] 账户更新已通过用户数据流自动订阅" << std::endl;
}

// ==================== WebSocket回调 ====================

void BinanceAdapter::on_ticker_update(const TickerData::Ptr& ticker) {
    if (!engine_) return;
    
    // 发布Ticker事件
    auto event = std::make_shared<Event>(EventType::MARKET_DATA);
    event->set_data("ticker", ticker);
    engine_->publish(event);
}

void BinanceAdapter::on_trade_update(const TradeData::Ptr& trade) {
    if (!engine_) return;
    
    // 发布成交事件
    auto event = std::make_shared<Event>(EventType::MARKET_DATA);
    event->set_data("trade", trade);
    engine_->publish(event);
}

void BinanceAdapter::on_orderbook_update(const OrderBookData::Ptr& orderbook) {
    if (!engine_) return;
    
    // 发布订单簿事件
    auto event = std::make_shared<Event>(EventType::MARKET_DATA);
    event->set_data("orderbook", orderbook);
    engine_->publish(event);
}

void BinanceAdapter::on_kline_update(const KlineData::Ptr& kline) {
    if (!engine_) return;
    
    // 发布K线事件
    auto event = std::make_shared<Event>(EventType::MARKET_DATA);
    event->set_data("kline", kline);
    engine_->publish(event);
}

void BinanceAdapter::on_order_update(const Order::Ptr& order) {
    if (!engine_) return;
    
    std::cout << "[BinanceAdapter] 订单更新: " << order->client_order_id() 
              << " 状态: " << (int)order->status() << std::endl;
    
    // 更新订单映射
    {
        std::lock_guard<std::mutex> lock(order_map_mutex_);
        order_map_[order->client_order_id()] = order;
    }
    
    // 发布订单事件
    auto event = std::make_shared<Event>(EventType::ORDER);
    event->set_data("order", order);
    engine_->publish(event);
}

void BinanceAdapter::on_account_update(const nlohmann::json& account) {
    if (!engine_) return;
    
    std::cout << "[BinanceAdapter] 账户更新" << std::endl;
    
    // 发布账户事件
    auto event = std::make_shared<Event>(EventType::ACCOUNT);
    event->set_data("account", account);
    engine_->publish(event);
}

// ==================== 事件监听 ====================

void BinanceAdapter::on_order_event(const Event::Ptr& event) {
    auto order = event->get_data<Order::Ptr>("order");
    if (!order) return;
    
    // 根据订单操作类型处理
    std::string action = event->get_data<std::string>("action");
    
    if (action == "submit") {
        submit_order(order);
    } else if (action == "cancel") {
        cancel_order(order);
    } else if (action == "amend") {
        amend_order(order);
    }
}

// ==================== 订单操作 ====================

void BinanceAdapter::submit_order(const Order::Ptr& order) {
    try {
        std::cout << "[BinanceAdapter] 提交订单: " << order->symbol() 
                  << " " << (order->side() == OrderSide::BUY ? "买入" : "卖出")
                  << " " << order->quantity() << std::endl;
        
        // 转换订单类型和方向
        auto side = convert_order_side(order);
        auto type = convert_order_type(order);
        
        // 调用REST API下单
        auto response = rest_api_->place_order(
            order->symbol(),
            side,
            type,
            std::to_string(order->quantity()),
            std::to_string(order->price())
        );
        
        // 更新订单ID
        order->set_order_id(std::to_string(response.order_id));
        order->set_status(OrderStatus::SUBMITTED);
        
        // 保存订单映射
        {
            std::lock_guard<std::mutex> lock(order_map_mutex_);
            order_map_[order->client_order_id()] = order;
        }
        
        {
            std::lock_guard<std::mutex> lock(exchange_order_map_mutex_);
            exchange_order_map_[response.order_id] = order->client_order_id();
        }
        
        std::cout << "[BinanceAdapter] 订单已提交: " << response.order_id << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceAdapter] 下单失败: " << e.what() << std::endl;
        order->set_status(OrderStatus::REJECTED);
    }
}

void BinanceAdapter::cancel_order(const Order::Ptr& order) {
    try {
        std::cout << "[BinanceAdapter] 撤销订单: " << order->client_order_id() << std::endl;
        
        // 从订单号获取交易所订单ID
        int64_t exchange_order_id = std::stoll(order->order_id());
        
        // 调用REST API撤单
        rest_api_->cancel_order(order->symbol(), exchange_order_id);
        
        std::cout << "[BinanceAdapter] 订单已撤销: " << exchange_order_id << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceAdapter] 撤单失败: " << e.what() << std::endl;
    }
}

void BinanceAdapter::amend_order(const Order::Ptr& order) {
    std::cout << "[BinanceAdapter] Binance不支持直接修改订单，需要先撤单再下单" << std::endl;
    
    // Binance不支持修改订单，需要先撤单再下单
    cancel_order(order);
    submit_order(order);
}

// ==================== 辅助方法 ====================

std::string BinanceAdapter::create_listen_key() {
    try {
        // 通过REST API创建listenKey
        // TODO: 这里需要添加具体的REST API调用
        std::cout << "[BinanceAdapter] 创建listenKey..." << std::endl;
        
        // 临时返回空字符串，实际需要调用API
        return "";
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceAdapter] 创建listenKey失败: " << e.what() << std::endl;
        return "";
    }
}

void BinanceAdapter::keep_alive_listen_key() {
    while (keep_alive_running_) {
        // 每30分钟延长一次listenKey
        std::this_thread::sleep_for(std::chrono::minutes(30));
        
        if (!keep_alive_running_) break;
        
        try {
            // TODO: 调用REST API延长listenKey
            std::cout << "[BinanceAdapter] 延长listenKey..." << std::endl;
            
        } catch (const std::exception& e) {
            std::cerr << "[BinanceAdapter] 延长listenKey失败: " << e.what() << std::endl;
        }
    }
}

OrderType BinanceAdapter::convert_order_type(const Order::Ptr& order) {
    // 根据内部订单类型转换为Binance订单类型
    // 这里需要根据实际的Order类定义来实现
    return OrderType::LIMIT;  // 默认返回限价单
}

OrderSide BinanceAdapter::convert_order_side(const Order::Ptr& order) {
    // 根据内部订单方向转换为Binance订单方向
    return order->side() == ::trading::OrderSide::BUY ? 
           OrderSide::BUY : OrderSide::SELL;
}

} // namespace binance
} // namespace trading

