#pragma once

#include "../core/event_engine.h"
#include "../trading/order.h"
#include "../core/data.h"
#include <string>
#include <memory>
#include <cstdio>

namespace trading {

/**
 * @brief 策略基类
 * 
 * 所有策略都应继承此类，实现：
 * - on_init(): 策略初始化
 * - on_ticker(): 行情回调
 * - on_trade(): 逐笔成交回调
 * - on_orderbook(): 订单簿回调
 * - on_kline(): K线回调
 * - on_order(): 订单更新回调
 * 
 * 提供便捷方法：
 * - send_order(): 发送订单
 * - cancel_order(): 撤销订单
 * - get_position(): 查询持仓
 * - get_balance(): 查询余额
 */
class StrategyBase : public Component {
public:
    StrategyBase(const std::string& name)
        : name_(name)
        , running_(false) {
    }
    
    virtual ~StrategyBase() = default;
    
    // Component接口实现
    virtual void start(EventEngine* engine) override {
        engine_ = engine;
        
        // 注册监听器
        engine->register_listener(
            typeid(TickerData),
            [this](const Event::Ptr& e) {
                on_ticker(std::dynamic_pointer_cast<TickerData>(e));
            }
        );
        
        engine->register_listener(
            typeid(TradeData),
            [this](const Event::Ptr& e) {
                on_trade(std::dynamic_pointer_cast<TradeData>(e));
            }
        );
        
        engine->register_listener(
            typeid(OrderBookData),
            [this](const Event::Ptr& e) {
                on_orderbook(std::dynamic_pointer_cast<OrderBookData>(e));
            }
        );
        
        engine->register_listener(
            typeid(KlineData),
            [this](const Event::Ptr& e) {
                on_kline(std::dynamic_pointer_cast<KlineData>(e));
            }
        );
        
        engine->register_listener(
            typeid(Order),
            [this](const Event::Ptr& e) {
                on_order(std::dynamic_pointer_cast<Order>(e));
            }
        );
        
        // 调用策略初始化
        on_init();
        running_ = true;
    }
    
    virtual void stop() override {
        running_ = false;
        on_stop();
    }
    
    // 策略生命周期
    virtual void on_init() {}
    virtual void on_stop() {}
    
    // 行情回调
    virtual void on_ticker(const TickerData::Ptr& ticker) { (void)ticker; }
    virtual void on_trade(const TradeData::Ptr& trade) { (void)trade; }
    virtual void on_orderbook(const OrderBookData::Ptr& orderbook) { (void)orderbook; }
    virtual void on_kline(const KlineData::Ptr& kline) { (void)kline; }
    
    // 订单回调
    virtual void on_order(const Order::Ptr& order) { (void)order; }
    
    // 便捷方法
    const std::string& name() const { return name_; }
    bool is_running() const { return running_; }

protected:
    /**
     * @brief 发送订单
     */
    void send_order(const Order::Ptr& order) {
        if (engine_) {
            engine_->put(order);
        }
    }
    
    /**
     * @brief 买入（限价）
     */
    Order::Ptr buy(const std::string& symbol, double quantity, double price) {
        auto order = Order::buy_limit(symbol, quantity, price);
        send_order(order);
        return order;
    }
    
    /**
     * @brief 卖出（限价）
     */
    Order::Ptr sell(const std::string& symbol, double quantity, double price) {
        auto order = Order::sell_limit(symbol, quantity, price);
        send_order(order);
        return order;
    }
    
    /**
     * @brief 买入（市价）
     */
    Order::Ptr buy_market(const std::string& symbol, double quantity) {
        auto order = Order::buy_market(symbol, quantity);
        send_order(order);
        return order;
    }
    
    /**
     * @brief 卖出（市价）
     */
    Order::Ptr sell_market(const std::string& symbol, double quantity) {
        auto order = Order::sell_market(symbol, quantity);
        send_order(order);
        return order;
    }
    
    /**
     * @brief 撤销订单
     */
    void cancel_order(const Order::Ptr& order) {
        // 创建一个取消订单的事件
        auto cancel_order = std::make_shared<Order>(*order);
        cancel_order->set_state(OrderState::CANCELLED);
        send_order(cancel_order);
    }
    
    /**
     * @brief 记录日志
     */
    void log_info(const std::string& message) {
        printf("[%s] INFO: %s\n", name_.c_str(), message.c_str());
    }
    
    void log_error(const std::string& message) {
        fprintf(stderr, "[%s] ERROR: %s\n", name_.c_str(), message.c_str());
    }

private:
    std::string name_;
    bool running_;
};

} // namespace trading

