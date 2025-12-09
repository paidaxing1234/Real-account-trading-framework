#pragma once

#include "../../core/data.h"
#include "../../core/order.h"
#include <string>
#include <functional>
#include <memory>
#include <vector>
#include <nlohmann/json.hpp>

namespace trading {
namespace okx {

/**
 * @brief OKX WebSocket客户端
 * 
 * 功能：
 * - 连接OKX WebSocket服务器
 * - 登录认证（私有频道）
 * - 订阅频道（行情、订单、账户）
 * - 心跳保持
 * - 自动重连
 * - 消息解析和回调
 */
class OKXWebSocket {
public:
    using TickerCallback = std::function<void(const TickerData::Ptr&)>;
    using TradeCallback = std::function<void(const TradeData::Ptr&)>;
    using OrderBookCallback = std::function<void(const OrderBookData::Ptr&)>;
    using KlineCallback = std::function<void(const KlineData::Ptr&)>;
    using OrderCallback = std::function<void(const Order::Ptr&)>;
    
    OKXWebSocket(
        const std::string& api_key = "",
        const std::string& secret_key = "",
        const std::string& passphrase = "",
        bool is_testnet = false
    );
    
    ~OKXWebSocket();
    
    // 连接和断开
    void connect();
    void disconnect();
    
    // 登录（用于私有频道）
    void login();
    
    // 订阅公共频道
    void subscribe_ticker(const std::string& inst_id);
    void subscribe_trades(const std::string& inst_id);
    void subscribe_orderbook(const std::string& inst_id);
    void subscribe_kline(const std::string& inst_id, const std::string& bar);
    
    // 订阅私有频道
    void subscribe_orders(const std::string& inst_type = "SWAP");
    void subscribe_positions(const std::string& inst_type = "SWAP");
    void subscribe_account(const std::string& ccy = "");
    
    // 设置回调
    void set_ticker_callback(TickerCallback callback) { ticker_callback_ = callback; }
    void set_trade_callback(TradeCallback callback) { trade_callback_ = callback; }
    void set_orderbook_callback(OrderBookCallback callback) { orderbook_callback_ = callback; }
    void set_kline_callback(KlineCallback callback) { kline_callback_ = callback; }
    void set_order_callback(OrderCallback callback) { order_callback_ = callback; }

private:
    void run();
    void on_message(const std::string& message);
    void parse_ticker(const nlohmann::json& data);
    void parse_trade(const nlohmann::json& data);
    void parse_orderbook(const nlohmann::json& data);
    void parse_kline(const nlohmann::json& data);
    void parse_order(const nlohmann::json& data);
    
    std::string create_signature(const std::string& timestamp);
    std::string get_iso8601_timestamp();
    
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    std::string ws_url_;
    bool is_testnet_;
    bool is_running_;
    
    // 回调函数
    TickerCallback ticker_callback_;
    TradeCallback trade_callback_;
    OrderBookCallback orderbook_callback_;
    KlineCallback kline_callback_;
    OrderCallback order_callback_;
    
    // WebSocket实现（使用pImpl模式隐藏实现细节）
    class Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace okx
} // namespace trading

