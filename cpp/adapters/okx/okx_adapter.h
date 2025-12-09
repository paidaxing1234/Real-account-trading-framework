#pragma once

#include "../../core/event_engine.h"
#include "../../core/order.h"
#include "../../core/data.h"
#include "okx_rest_api.h"
#include "okx_websocket.h"
#include <memory>
#include <string>
#include <unordered_map>

namespace trading {
namespace okx {

/**
 * @brief OKX交易所适配器
 * 
 * 职责：
 * 1. 接收内部Order事件 → 调用REST API下单
 * 2. 接收WebSocket推送 → 转换为内部Event
 * 3. 错误处理和重试逻辑
 * 4. 维护订单映射（本地ID ↔ 交易所ID）
 */
class OKXAdapter : public Component {
public:
    OKXAdapter(
        const std::string& api_key,
        const std::string& secret_key,
        const std::string& passphrase,
        bool is_testnet = false
    );
    
    virtual ~OKXAdapter() = default;
    
    // Component接口实现
    virtual void start(EventEngine* engine) override;
    virtual void stop() override;
    
    // 订阅行情
    void subscribe_ticker(const std::string& symbol);
    void subscribe_trades(const std::string& symbol);
    void subscribe_orderbook(const std::string& symbol);
    void subscribe_kline(const std::string& symbol, const std::string& interval);
    
    // 订阅私有频道
    void subscribe_orders();
    void subscribe_positions();
    void subscribe_account();

private:
    // 事件监听器
    void on_order_event(const Event::Ptr& event);
    
    // WebSocket回调
    void on_ticker_update(const TickerData::Ptr& ticker);
    void on_trade_update(const TradeData::Ptr& trade);
    void on_orderbook_update(const OrderBookData::Ptr& orderbook);
    void on_kline_update(const KlineData::Ptr& kline);
    void on_order_update(const Order::Ptr& order);
    
    // 订单提交
    void submit_order(const Order::Ptr& order);
    void cancel_order(const Order::Ptr& order);
    
    // 成员变量
    std::unique_ptr<OKXRestAPI> rest_api_;
    std::unique_ptr<OKXWebSocket> websocket_;
    
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    bool is_testnet_;
    
    // 订单映射：client_order_id → Order
    std::unordered_map<std::string, Order::Ptr> order_map_;
};

} // namespace okx
} // namespace trading

