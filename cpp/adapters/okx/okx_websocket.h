#pragma once

/**
 * @file okx_websocket.h
 * @brief OKX WebSocket 客户端
 * 
 * 功能：
 * - 连接OKX WebSocket服务器（public/business/private三种端点）
 * - 登录认证（私有频道）
 * - 订阅频道（行情、K线、订单、账户）
 * - 心跳保持
 * - 自动重连
 * - 消息解析和回调
 * 
 * URL 端点:
 * - public:   wss://ws.okx.com:8443/ws/v5/public   (行情、深度、成交)
 * - business: wss://ws.okx.com:8443/ws/v5/business (K线、trades-all)
 * - private:  wss://ws.okx.com:8443/ws/v5/private  (订单、持仓、账户)
 * 
 * 模拟盘URL:
 * - public:   wss://wspap.okx.com:8443/ws/v5/public
 * - business: wss://wspap.okx.com:8443/ws/v5/business
 * - private:  wss://wspap.okx.com:8443/ws/v5/private
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "../../core/data.h"
#include "../../core/order.h"
#include <string>
#include <functional>
#include <memory>
#include <vector>
#include <unordered_map>
#include <mutex>
#include <thread>
#include <atomic>
#include <nlohmann/json.hpp>

namespace trading {
namespace okx {

// ==================== K线间隔枚举 ====================

/**
 * @brief K线时间间隔
 * 
 * OKX支持的所有K线间隔
 */
enum class KlineInterval {
    SECOND_1,   // 1秒
    MINUTE_1,   // 1分钟
    MINUTE_3,   // 3分钟
    MINUTE_5,   // 5分钟
    MINUTE_15,  // 15分钟
    MINUTE_30,  // 30分钟
    HOUR_1,     // 1小时
    HOUR_2,     // 2小时
    HOUR_4,     // 4小时
    HOUR_6,     // 6小时
    HOUR_12,    // 12小时
    DAY_1,      // 1天
    DAY_2,      // 2天
    DAY_3,      // 3天
    DAY_5,      // 5天
    WEEK_1,     // 1周
    MONTH_1,    // 1月
    MONTH_3,    // 3月
    // UTC时区版本
    MONTH_3_UTC,
    MONTH_1_UTC,
    WEEK_1_UTC,
    DAY_1_UTC,
    DAY_2_UTC,
    DAY_3_UTC,
    DAY_5_UTC,
    HOUR_12_UTC,
    HOUR_6_UTC
};

/**
 * @brief K线间隔转频道名称
 */
inline std::string kline_interval_to_channel(KlineInterval interval) {
    switch (interval) {
        case KlineInterval::SECOND_1:   return "candle1s";
        case KlineInterval::MINUTE_1:   return "candle1m";
        case KlineInterval::MINUTE_3:   return "candle3m";
        case KlineInterval::MINUTE_5:   return "candle5m";
        case KlineInterval::MINUTE_15:  return "candle15m";
        case KlineInterval::MINUTE_30:  return "candle30m";
        case KlineInterval::HOUR_1:     return "candle1H";
        case KlineInterval::HOUR_2:     return "candle2H";
        case KlineInterval::HOUR_4:     return "candle4H";
        case KlineInterval::HOUR_6:     return "candle6H";
        case KlineInterval::HOUR_12:    return "candle12H";
        case KlineInterval::DAY_1:      return "candle1D";
        case KlineInterval::DAY_2:      return "candle2D";
        case KlineInterval::DAY_3:      return "candle3D";
        case KlineInterval::DAY_5:      return "candle5D";
        case KlineInterval::WEEK_1:     return "candle1W";
        case KlineInterval::MONTH_1:    return "candle1M";
        case KlineInterval::MONTH_3:    return "candle3M";
        case KlineInterval::MONTH_3_UTC: return "candle3Mutc";
        case KlineInterval::MONTH_1_UTC: return "candle1Mutc";
        case KlineInterval::WEEK_1_UTC:  return "candle1Wutc";
        case KlineInterval::DAY_1_UTC:   return "candle1Dutc";
        case KlineInterval::DAY_2_UTC:   return "candle2Dutc";
        case KlineInterval::DAY_3_UTC:   return "candle3Dutc";
        case KlineInterval::DAY_5_UTC:   return "candle5Dutc";
        case KlineInterval::HOUR_12_UTC: return "candle12Hutc";
        case KlineInterval::HOUR_6_UTC:  return "candle6Hutc";
        default:                        return "candle1m";
    }
}

/**
 * @brief 字符串转K线间隔
 */
inline KlineInterval string_to_kline_interval(const std::string& str) {
    static const std::unordered_map<std::string, KlineInterval> map = {
        {"1s", KlineInterval::SECOND_1},
        {"1m", KlineInterval::MINUTE_1},
        {"3m", KlineInterval::MINUTE_3},
        {"5m", KlineInterval::MINUTE_5},
        {"15m", KlineInterval::MINUTE_15},
        {"30m", KlineInterval::MINUTE_30},
        {"1H", KlineInterval::HOUR_1},
        {"2H", KlineInterval::HOUR_2},
        {"4H", KlineInterval::HOUR_4},
        {"6H", KlineInterval::HOUR_6},
        {"12H", KlineInterval::HOUR_12},
        {"1D", KlineInterval::DAY_1},
        {"2D", KlineInterval::DAY_2},
        {"3D", KlineInterval::DAY_3},
        {"5D", KlineInterval::DAY_5},
        {"1W", KlineInterval::WEEK_1},
        {"1M", KlineInterval::MONTH_1},
        {"3M", KlineInterval::MONTH_3}
    };
    
    auto it = map.find(str);
    return (it != map.end()) ? it->second : KlineInterval::MINUTE_1;
}

// ==================== WebSocket端点类型 ====================

/**
 * @brief WebSocket端点类型
 */
enum class WsEndpointType {
    PUBLIC,    // 公共频道：行情、深度、成交
    BUSINESS,  // 业务频道：K线、trades-all
    PRIVATE    // 私有频道：订单、持仓、账户
};

// ==================== 持仓总量数据结构 ====================

/**
 * @brief 持仓总量数据
 * 
 * 用于永续/交割合约的持仓总量信息
 */
struct OpenInterestData {
    using Ptr = std::shared_ptr<OpenInterestData>;
    
    std::string inst_id;      // 产品ID，如 BTC-USDT-SWAP
    std::string inst_type;    // 产品类型，如 SWAP
    double oi;                // 持仓量（按张）
    double oi_ccy;            // 持仓量（按币）
    double oi_usd;            // 持仓量（按USD）
    int64_t timestamp;        // 时间戳（毫秒）
    
    OpenInterestData(
        const std::string& inst_id_,
        const std::string& inst_type_,
        double oi_,
        double oi_ccy_,
        double oi_usd_,
        int64_t ts_
    ) : inst_id(inst_id_)
      , inst_type(inst_type_)
      , oi(oi_)
      , oi_ccy(oi_ccy_)
      , oi_usd(oi_usd_)
      , timestamp(ts_)
    {}
};

// ==================== 标记价格数据结构 ====================

/**
 * @brief 标记价格数据
 * 
 * 标记价格有变化时每200ms推送一次，没变化时每10s推送一次
 */
struct MarkPriceData {
    using Ptr = std::shared_ptr<MarkPriceData>;
    
    std::string inst_id;      // 产品ID，如 BTC-USDT
    std::string inst_type;    // 产品类型，如 MARGIN/SWAP/FUTURES
    double mark_px;           // 标记价格
    int64_t timestamp;        // 时间戳（毫秒）
    
    MarkPriceData(
        const std::string& inst_id_,
        const std::string& inst_type_,
        double mark_px_,
        int64_t ts_
    ) : inst_id(inst_id_)
      , inst_type(inst_type_)
      , mark_px(mark_px_)
      , timestamp(ts_)
    {}
};

// ==================== 回调类型定义 ====================

/**
 * @brief 各类数据的回调函数类型
 */
using TickerCallback = std::function<void(const TickerData::Ptr&)>;
using TradeCallback = std::function<void(const TradeData::Ptr&)>;
using OrderBookCallback = std::function<void(const OrderBookData::Ptr&)>;
using KlineCallback = std::function<void(const KlineData::Ptr&)>;
using OrderCallback = std::function<void(const Order::Ptr&)>;
using PositionCallback = std::function<void(const nlohmann::json&)>;  // 持仓数据（原始JSON）
using AccountCallback = std::function<void(const nlohmann::json&)>;   // 账户数据（原始JSON）
using OpenInterestCallback = std::function<void(const OpenInterestData::Ptr&)>;  // 持仓总量
using MarkPriceCallback = std::function<void(const MarkPriceData::Ptr&)>;        // 标记价格
using RawMessageCallback = std::function<void(const nlohmann::json&)>;

// ==================== OKXWebSocket类 ====================

/**
 * @brief OKX WebSocket客户端
 * 
 * 支持公共频道和私有频道的订阅
 * 
 * 使用示例：
 * @code
 * // 公共频道（行情）
 * OKXWebSocket ws_public;
 * ws_public.connect();
 * ws_public.subscribe_ticker("BTC-USDT");
 * ws_public.set_ticker_callback([](const TickerData::Ptr& ticker) {
 *     std::cout << "Price: " << ticker->last_price() << std::endl;
 * });
 * 
 * // K线频道（需要使用business端点）
 * OKXWebSocket ws_business("", "", "", false, WsEndpointType::BUSINESS);
 * ws_business.connect();
 * ws_business.subscribe_kline("BTC-USDT", KlineInterval::MINUTE_1);
 * ws_business.set_kline_callback([](const KlineData::Ptr& kline) {
 *     std::cout << "OHLC: " << kline->open() << ", " << kline->close() << std::endl;
 * });
 * 
 * // 私有频道（订单）
 * OKXWebSocket ws_private(api_key, secret_key, passphrase, true);
 * ws_private.connect();
 * ws_private.login();
 * ws_private.subscribe_orders("SWAP");
 * @endcode
 */
class OKXWebSocket {
public:
    /**
     * @brief 构造函数
     * 
     * @param api_key API密钥（私有频道需要）
     * @param secret_key Secret密钥（私有频道需要）
     * @param passphrase 密码短语（私有频道需要）
     * @param is_testnet 是否使用模拟盘
     * @param endpoint_type 端点类型（public/business/private）
     */
    OKXWebSocket(
        const std::string& api_key = "",
        const std::string& secret_key = "",
        const std::string& passphrase = "",
        bool is_testnet = false,
        WsEndpointType endpoint_type = WsEndpointType::PUBLIC
    );
    
    ~OKXWebSocket();
    
    // ==================== 连接管理 ====================
    
    /**
     * @brief 连接WebSocket服务器
     * 
     * 建立WebSocket连接并启动接收线程
     * 
     * @return true 连接成功
     */
    bool connect();
    
    /**
     * @brief 断开连接
     */
    void disconnect();
    
    /**
     * @brief 检查是否已连接
     */
    bool is_connected() const { return is_connected_.load(); }
    
    /**
     * @brief 检查是否已登录（私有频道）
     */
    bool is_logged_in() const { return is_logged_in_.load(); }
    
    /**
     * @brief 登录（用于私有频道）
     * 
     * 需要在订阅私有频道前调用
     */
    void login();
    
    // ==================== 公共频道订阅 ====================
    
    /**
     * @brief 订阅行情快照
     * 
     * 推送频率：100ms
     * 
     * @param inst_id 产品ID，如 "BTC-USDT"
     */
    void subscribe_ticker(const std::string& inst_id);
    
    /**
     * @brief 取消订阅行情快照
     */
    void unsubscribe_ticker(const std::string& inst_id);
    
    /**
     * @brief 订阅逐笔成交
     * 
     * @param inst_id 产品ID
     */
    void subscribe_trades(const std::string& inst_id);
    
    /**
     * @brief 取消订阅逐笔成交
     */
    void unsubscribe_trades(const std::string& inst_id);
    
    /**
     * @brief 订阅订单簿（深度数据）
     * 
     * @param inst_id 产品ID
     * @param channel 频道类型：
     *                - "books5"：5档，推送频率100ms
     *                - "books"：400档，推送频率100ms
     *                - "bbo-tbt"：1档，推送频率10ms
     *                - "books-l2-tbt"：400档，推送频率10ms
     *                - "books50-l2-tbt"：50档，推送频率10ms
     */
    void subscribe_orderbook(const std::string& inst_id, const std::string& channel = "books5");
    
    /**
     * @brief 取消订阅订单簿
     */
    void unsubscribe_orderbook(const std::string& inst_id, const std::string& channel = "books5");
    
    /**
     * @brief 订阅持仓总量频道
     * 
     * 用于获取永续/交割合约的持仓总量
     * 推送频率：每3秒有数据更新时推送
     * 
     * @param inst_id 产品ID，如 "BTC-USDT-SWAP", "LTC-USD-SWAP"
     */
    void subscribe_open_interest(const std::string& inst_id);
    
    /**
     * @brief 取消订阅持仓总量频道
     */
    void unsubscribe_open_interest(const std::string& inst_id);
    
    /**
     * @brief 订阅标记价格频道
     * 
     * 标记价格有变化时每200ms推送，没变化时每10s推送
     * 
     * @param inst_id 产品ID，如 "BTC-USDT", "ETH-USDT-SWAP"
     */
    void subscribe_mark_price(const std::string& inst_id);
    
    /**
     * @brief 取消订阅标记价格频道
     */
    void unsubscribe_mark_price(const std::string& inst_id);
    
    // ==================== K线频道订阅（需要使用business端点） ====================
    
    /**
     * @brief 订阅K线数据
     * 
     * ⚠️ 注意：K线订阅需要使用 WsEndpointType::BUSINESS 端点
     * 推送频率：最快1秒
     * 
     * @param inst_id 产品ID，如 "BTC-USDT"
     * @param interval K线间隔
     * 
     * 使用示例：
     * @code
     * // 创建business端点的WebSocket
     * OKXWebSocket ws("", "", "", false, WsEndpointType::BUSINESS);
     * ws.connect();
     * ws.subscribe_kline("BTC-USDT", KlineInterval::MINUTE_1);
     * @endcode
     */
    void subscribe_kline(const std::string& inst_id, KlineInterval interval);
    
    /**
     * @brief 订阅K线数据（字符串版本）
     * 
     * @param inst_id 产品ID
     * @param bar K线间隔字符串，如 "1m", "5m", "1H", "1D"
     */
    void subscribe_kline(const std::string& inst_id, const std::string& bar);
    
    /**
     * @brief 取消订阅K线数据
     */
    void unsubscribe_kline(const std::string& inst_id, KlineInterval interval);
    void unsubscribe_kline(const std::string& inst_id, const std::string& bar);
    
    /**
     * @brief 订阅全部成交数据
     * 
     * ⚠️ 注意：需要使用 WsEndpointType::BUSINESS 端点
     * 每次仅推送一条成交记录
     * 
     * @param inst_id 产品ID
     */
    void subscribe_trades_all(const std::string& inst_id);
    
    /**
     * @brief 取消订阅全部成交数据
     */
    void unsubscribe_trades_all(const std::string& inst_id);
    
    // ==================== 私有频道订阅（需要登录） ====================
    
    /**
     * @brief 订阅订单频道
     * 
     * @param inst_type 产品类型：SPOT/MARGIN/SWAP/FUTURES/OPTION/ANY
     * @param inst_id 产品ID（可选，如 "BTC-USDT"）
     * @param inst_family 交易品种（可选，适用于交割/永续/期权）
     */
    void subscribe_orders(
        const std::string& inst_type = "SPOT",
        const std::string& inst_id = "",
        const std::string& inst_family = ""
    );
    
    /**
     * @brief 取消订阅订单频道
     */
    void unsubscribe_orders(
        const std::string& inst_type = "SPOT",
        const std::string& inst_id = "",
        const std::string& inst_family = ""
    );
    
    /**
     * @brief 订阅持仓频道
     * 
     * @param inst_type 产品类型：MARGIN/SWAP/FUTURES/OPTION/ANY
     * @param inst_id 产品ID（可选）
     * @param inst_family 交易品种（可选）
     */
    void subscribe_positions(
        const std::string& inst_type = "SWAP",
        const std::string& inst_id = "",
        const std::string& inst_family = ""
    );
    
    /**
     * @brief 取消订阅持仓频道
     */
    void unsubscribe_positions(
        const std::string& inst_type = "SWAP",
        const std::string& inst_id = "",
        const std::string& inst_family = ""
    );
    
    /**
     * @brief 订阅账户频道
     * 
     * @param ccy 币种（可选，空表示所有币种）
     */
    void subscribe_account(const std::string& ccy = "");
    
    /**
     * @brief 取消订阅账户频道
     */
    void unsubscribe_account(const std::string& ccy = "");
    
    /**
     * @brief 订阅Spread订单频道（sprd-orders）
     * 
     * ⚠️ 注意：需要使用 WsEndpointType::BUSINESS 端点并登录
     * 首次订阅不推送，只有下单、撤单等事件触发时才推送
     * 
     * @param sprd_id Spread ID（可选），如 "BTC-USDT_BTC-USDT-SWAP"
     *                如果为空，则订阅所有Spread订单
     */
    void subscribe_sprd_orders(const std::string& sprd_id = "");
    
    /**
     * @brief 取消订阅Spread订单频道
     */
    void unsubscribe_sprd_orders(const std::string& sprd_id = "");
    
    // ==================== 回调设置 ====================
    
    void set_ticker_callback(TickerCallback callback) { ticker_callback_ = std::move(callback); }
    void set_trade_callback(TradeCallback callback) { trade_callback_ = std::move(callback); }
    void set_orderbook_callback(OrderBookCallback callback) { orderbook_callback_ = std::move(callback); }
    void set_kline_callback(KlineCallback callback) { kline_callback_ = std::move(callback); }
    void set_order_callback(OrderCallback callback) { order_callback_ = std::move(callback); }
    void set_position_callback(PositionCallback callback) { position_callback_ = std::move(callback); }
    void set_account_callback(AccountCallback callback) { account_callback_ = std::move(callback); }
    void set_open_interest_callback(OpenInterestCallback callback) { open_interest_callback_ = std::move(callback); }
    void set_mark_price_callback(MarkPriceCallback callback) { mark_price_callback_ = std::move(callback); }
    
    /**
     * @brief 设置原始消息回调（调试用）
     */
    void set_raw_message_callback(RawMessageCallback callback) { raw_callback_ = std::move(callback); }
    
    // ==================== 状态查询 ====================
    
    /**
     * @brief 获取已订阅的频道列表
     */
    std::vector<std::string> get_subscribed_channels() const;
    
    /**
     * @brief 获取端点类型
     */
    WsEndpointType get_endpoint_type() const { return endpoint_type_; }
    
    /**
     * @brief 获取WebSocket URL
     */
    const std::string& get_url() const { return ws_url_; }

private:
    // ==================== 内部方法 ====================
    
    /**
     * @brief 构建WebSocket URL
     */
    std::string build_ws_url() const;
    
    /**
     * @brief 运行接收线程
     */
    void run();
    
    /**
     * @brief 处理接收到的消息
     */
    void on_message(const std::string& message);
    
    /**
     * @brief 发送WebSocket消息
     */
    bool send_message(const nlohmann::json& msg);
    
    /**
     * @brief 发送订阅/取消订阅请求
     */
    void send_subscribe(const std::string& channel, const std::string& inst_id, 
                       const std::string& extra_key = "", const std::string& extra_value = "");
    void send_unsubscribe(const std::string& channel, const std::string& inst_id,
                         const std::string& extra_key = "", const std::string& extra_value = "");
    
    /**
     * @brief 发送心跳
     */
    void send_ping();
    
    /**
     * @brief 生成登录签名
     */
    std::string create_signature(const std::string& timestamp);
    std::string get_timestamp();
    
    // ==================== 消息解析 ====================
    
    void parse_ticker(const nlohmann::json& data, const std::string& inst_id);
    void parse_trade(const nlohmann::json& data, const std::string& inst_id);
    void parse_orderbook(const nlohmann::json& data, const std::string& inst_id);
    void parse_kline(const nlohmann::json& data, const std::string& inst_id, const std::string& channel);
    void parse_order(const nlohmann::json& data);
    void parse_position(const nlohmann::json& data);
    void parse_account(const nlohmann::json& data);
    void parse_open_interest(const nlohmann::json& data);
    void parse_mark_price(const nlohmann::json& data);
    void parse_sprd_order(const nlohmann::json& data);
    
    // ==================== 成员变量 ====================
    
    // API凭证
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    
    // 配置
    std::string ws_url_;
    bool is_testnet_;
    WsEndpointType endpoint_type_;
    
    // 状态
    std::atomic<bool> is_running_{false};
    std::atomic<bool> is_connected_{false};
    std::atomic<bool> is_logged_in_{false};
    
    // 线程
    std::unique_ptr<std::thread> recv_thread_;
    std::unique_ptr<std::thread> heartbeat_thread_;
    
    // 订阅列表
    std::unordered_map<std::string, std::string> subscriptions_;  // channel_key -> inst_id
    mutable std::mutex subscriptions_mutex_;
    
    // 回调函数
    TickerCallback ticker_callback_;
    TradeCallback trade_callback_;
    OrderBookCallback orderbook_callback_;
    KlineCallback kline_callback_;
    OrderCallback order_callback_;
    PositionCallback position_callback_;
    AccountCallback account_callback_;
    OpenInterestCallback open_interest_callback_;
    MarkPriceCallback mark_price_callback_;
    RawMessageCallback raw_callback_;
    
    // WebSocket实现（使用pImpl模式隐藏实现细节）
    class Impl;
    std::unique_ptr<Impl> impl_;
};

// ==================== 便捷工厂函数 ====================

/**
 * @brief 创建公共频道WebSocket（行情、深度、成交）
 */
inline std::unique_ptr<OKXWebSocket> create_public_ws(bool is_testnet = false) {
    return std::make_unique<OKXWebSocket>("", "", "", is_testnet, WsEndpointType::PUBLIC);
}

/**
 * @brief 创建业务频道WebSocket（K线、trades-all）
 */
inline std::unique_ptr<OKXWebSocket> create_business_ws(bool is_testnet = false) {
    return std::make_unique<OKXWebSocket>("", "", "", is_testnet, WsEndpointType::BUSINESS);
}

/**
 * @brief 创建私有频道WebSocket（订单、持仓、账户）
 */
inline std::unique_ptr<OKXWebSocket> create_private_ws(
    const std::string& api_key,
    const std::string& secret_key,
    const std::string& passphrase,
    bool is_testnet = false
) {
    return std::make_unique<OKXWebSocket>(api_key, secret_key, passphrase, is_testnet, WsEndpointType::PRIVATE);
}

} // namespace okx
} // namespace trading
