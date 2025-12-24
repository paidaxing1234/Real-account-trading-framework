#pragma once

/**
 * @file binance_adapter.h
 * @brief Binance交易所适配器
 * 
 * 职责：
 * 1. 接收内部Order事件 → 调用REST API下单
 * 2. 接收WebSocket推送 → 转换为内部Event
 * 3. 错误处理和重试逻辑
 * 4. 维护订单映射（本地ID ↔ 交易所ID）
 * 
 * 与OKX适配器保持一致的接口设计
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "../../core/event_engine.h"
#include "../../core/order.h"
#include "../../core/data.h"
#include "binance_rest_api.h"
#include "binance_websocket.h"
#include <memory>
#include <string>
#include <unordered_map>

namespace trading {
namespace binance {

/**
 * @brief Binance交易所适配器
 * 
 * 完全对标OKXAdapter的设计，提供统一的交易所接口
 * 
 * 使用示例：
 * @code
 * auto adapter = std::make_shared<BinanceAdapter>(api_key, secret_key, market_type);
 * adapter->start(engine);
 * 
 * // 订阅行情
 * adapter->subscribe_ticker("BTCUSDT");
 * adapter->subscribe_kline("BTCUSDT", "1m");
 * 
 * // 订阅私有频道
 * adapter->subscribe_orders();
 * adapter->subscribe_positions();  // 仅合约
 * @endcode
 */
class BinanceAdapter : public Component {
public:
    /**
     * @brief 构造函数
     * 
     * @param api_key API密钥
     * @param secret_key Secret密钥
     * @param market_type 市场类型（现货/U本位合约/币本位合约）
     * @param is_testnet 是否使用测试网
     */
    BinanceAdapter(
        const std::string& api_key,
        const std::string& secret_key,
        MarketType market_type = MarketType::SPOT,
        bool is_testnet = false
    );
    
    virtual ~BinanceAdapter() = default;
    
    // ==================== Component接口实现 ====================
    
    /**
     * @brief 启动适配器
     * 
     * 连接WebSocket，订阅必要的数据流
     */
    virtual void start(EventEngine* engine) override;
    
    /**
     * @brief 停止适配器
     * 
     * 断开WebSocket连接，清理资源
     */
    virtual void stop() override;
    
    // ==================== 行情订阅（对标OKX） ====================
    
    /**
     * @brief 订阅Ticker行情
     * 
     * @param symbol 交易对，如 "BTCUSDT"
     */
    void subscribe_ticker(const std::string& symbol);
    
    /**
     * @brief 订阅逐笔成交
     * 
     * @param symbol 交易对
     */
    void subscribe_trades(const std::string& symbol);
    
    /**
     * @brief 订阅订单簿（深度）
     * 
     * @param symbol 交易对
     * @param levels 档位数量，默认20
     */
    void subscribe_orderbook(const std::string& symbol, int levels = 20);
    
    /**
     * @brief 订阅K线数据
     * 
     * @param symbol 交易对
     * @param interval K线间隔（1m, 5m, 15m, 1h, 1d等）
     */
    void subscribe_kline(const std::string& symbol, const std::string& interval);
    
    // ==================== 私有频道订阅（对标OKX） ====================
    
    /**
     * @brief 订阅订单更新
     * 
     * 实时接收订单状态变化
     */
    void subscribe_orders();
    
    /**
     * @brief 订阅持仓更新
     * 
     * 仅合约市场可用
     */
    void subscribe_positions();
    
    /**
     * @brief 订阅账户余额更新
     */
    void subscribe_account();
    
    // ==================== 交易接口 ====================
    
    /**
     * @brief 获取REST API客户端
     * 
     * 用于主动查询和低频操作
     */
    BinanceRestAPI* get_rest_api() { return rest_api_.get(); }
    
    /**
     * @brief 获取WebSocket客户端
     * 
     * 用于高频交易和实时数据
     */
    BinanceWebSocket* get_websocket() { return websocket_.get(); }
    
    /**
     * @brief 获取市场类型
     */
    MarketType get_market_type() const { return market_type_; }

private:
    // ==================== 事件监听器 ====================
    
    /**
     * @brief 处理订单事件
     * 
     * 当策略发出下单/撤单指令时调用
     */
    void on_order_event(const Event::Ptr& event);
    
    // ==================== WebSocket回调 ====================
    
    /**
     * @brief Ticker数据更新回调
     * 
     * 将WebSocket数据转换为内部Event并发布
     */
    void on_ticker_update(const TickerData::Ptr& ticker);
    
    /**
     * @brief 成交数据更新回调
     */
    void on_trade_update(const TradeData::Ptr& trade);
    
    /**
     * @brief 订单簿更新回调
     */
    void on_orderbook_update(const OrderBookData::Ptr& orderbook);
    
    /**
     * @brief K线数据更新回调
     */
    void on_kline_update(const KlineData::Ptr& kline);
    
    /**
     * @brief 订单更新回调
     */
    void on_order_update(const Order::Ptr& order);
    
    /**
     * @brief 账户更新回调
     */
    void on_account_update(const nlohmann::json& account);
    
    // ==================== 订单操作 ====================
    
    /**
     * @brief 提交订单
     * 
     * @param order 订单对象
     */
    void submit_order(const Order::Ptr& order);
    
    /**
     * @brief 撤销订单
     * 
     * @param order 订单对象
     */
    void cancel_order(const Order::Ptr& order);
    
    /**
     * @brief 修改订单
     * 
     * @param order 订单对象
     */
    void amend_order(const Order::Ptr& order);
    
    // ==================== 辅助方法 ====================
    
    /**
     * @brief 创建listenKey（用户数据流）
     * 
     * 私有频道需要先通过REST API获取listenKey
     */
    std::string create_listen_key();
    
    /**
     * @brief 保持listenKey活跃
     * 
     * 每30分钟需要延长一次listenKey
     */
    void keep_alive_listen_key();
    
    /**
     * @brief 转换内部订单类型到Binance订单类型
     */
    OrderType convert_order_type(const Order::Ptr& order);
    
    /**
     * @brief 转换内部订单方向到Binance订单方向
     */
    OrderSide convert_order_side(const Order::Ptr& order);
    
    // ==================== 成员变量 ====================
    
    // API客户端
    std::unique_ptr<BinanceRestAPI> rest_api_;
    std::unique_ptr<BinanceWebSocket> websocket_market_;    // 行情WebSocket
    std::unique_ptr<BinanceWebSocket> websocket_trading_;   // 交易WebSocket（可选）
    std::unique_ptr<BinanceWebSocket> websocket_userdata_;  // 用户数据WebSocket
    
    // 配置参数
    std::string api_key_;
    std::string secret_key_;
    MarketType market_type_;
    bool is_testnet_;
    
    // 用户数据流
    std::string listen_key_;
    std::unique_ptr<std::thread> keep_alive_thread_;
    std::atomic<bool> keep_alive_running_{false};
    
    // 订单映射：client_order_id → Order
    std::unordered_map<std::string, Order::Ptr> order_map_;
    std::mutex order_map_mutex_;
    
    // 交易所订单ID映射：exchange_order_id → client_order_id
    std::unordered_map<int64_t, std::string> exchange_order_map_;
    std::mutex exchange_order_map_mutex_;
};

} // namespace binance
} // namespace trading

