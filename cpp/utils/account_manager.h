#pragma once

#include "../core/event_engine.h"
#include "../core/order.h"
#include "../core/data.h"
#include <string>
#include <unordered_map>
#include <memory>
#include <mutex>
#include <algorithm>
#include <cmath>

namespace trading {

/**
 * @brief 持仓信息
 */
struct Position {
    std::string symbol;      // 交易对
    double quantity;         // 持仓数量（正数=多头，负数=空头）
    double avg_price;        // 平均成本价
    double unrealized_pnl;   // 未实现盈亏
    double realized_pnl;     // 已实现盈亏
    
    Position()
        : quantity(0.0)
        , avg_price(0.0)
        , unrealized_pnl(0.0)
        , realized_pnl(0.0) {
    }
};

/**
 * @brief 账户管理器
 * 
 * 职责：
 * 1. 维护订单字典（活跃订单）
 * 2. 维护持仓字典（各币种持仓）
 * 3. 维护余额信息（可用/冻结）
 * 4. 向引擎注入查询接口
 * 
 * 监听事件：
 * - Order事件：更新订单状态、持仓
 * - TickerData事件：更新未实现盈亏
 */
class AccountManager : public Component {
public:
    AccountManager() = default;
    virtual ~AccountManager() = default;
    
    // Component接口实现
    virtual void start(EventEngine* engine) override {
        engine_ = engine;
        
        // 注册监听器
        engine->register_listener(
            typeid(Order),
            [this](const Event::Ptr& e) {
                on_order(std::dynamic_pointer_cast<Order>(e));
            }
        );
        
        engine->register_listener(
            typeid(TickerData),
            [this](const Event::Ptr& e) {
                on_ticker(std::dynamic_pointer_cast<TickerData>(e));
            }
        );
        
        // 注入查询接口
        engine->inject("get_active_orders",
            [this]() { return get_active_orders(); });
        
        engine->inject("get_position",
            [this](const std::string& symbol) { return get_position(symbol); });
        
        engine->inject("get_balance",
            [this]() { return get_balance(); });
    }
    
    virtual void stop() override {
        std::lock_guard<std::mutex> lock(mutex_);
        active_orders_.clear();
        positions_.clear();
    }
    
    // 查询接口
    std::unordered_map<int64_t, Order::Ptr> get_active_orders() {
        std::lock_guard<std::mutex> lock(mutex_);
        return active_orders_;
    }
    
    Position get_position(const std::string& symbol) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = positions_.find(symbol);
        if (it != positions_.end()) {
            return it->second;
        }
        return Position{};
    }
    
    double get_balance() {
        std::lock_guard<std::mutex> lock(mutex_);
        return balance_;
    }
    
    void set_balance(double balance) {
        std::lock_guard<std::mutex> lock(mutex_);
        balance_ = balance;
    }

private:
    void on_order(const Order::Ptr& order) {
        std::lock_guard<std::mutex> lock(mutex_);
        
        // 更新活跃订单
        if (order->is_active()) {
            active_orders_[order->order_id()] = order;
        } else if (order->is_final()) {
            active_orders_.erase(order->order_id());
        }
        
        // 如果订单成交，更新持仓
        if (order->is_filled()) {
            update_position(order);
        }
    }
    
    void on_ticker(const TickerData::Ptr& ticker) {
        std::lock_guard<std::mutex> lock(mutex_);
        
        // 更新未实现盈亏
        auto it = positions_.find(ticker->symbol());
        if (it != positions_.end()) {
            Position& pos = it->second;
            if (pos.quantity != 0.0) {
                double current_price = ticker->last_price();
                pos.unrealized_pnl = (current_price - pos.avg_price) * pos.quantity;
            }
        }
    }
    
    void update_position(const Order::Ptr& order) {
        const std::string& symbol = order->symbol();
        Position& pos = positions_[symbol];
        pos.symbol = symbol;
        
        double filled_qty = order->filled_quantity();
        if (order->is_sell()) {
            filled_qty = -filled_qty;  // 卖出为负
        }
        
        double filled_price = order->filled_price();
        
        // 更新持仓
        if ((pos.quantity >= 0 && filled_qty >= 0) || (pos.quantity < 0 && filled_qty < 0)) {
            // 同向：累加持仓，更新平均价
            double total_cost = pos.avg_price * pos.quantity + filled_price * filled_qty;
            pos.quantity += filled_qty;
            if (pos.quantity != 0.0) {
                pos.avg_price = total_cost / pos.quantity;
            }
        } else {
            // 反向：减少持仓，计算已实现盈亏
            double close_qty = std::min(std::abs(filled_qty), std::abs(pos.quantity));
            double pnl = (filled_price - pos.avg_price) * close_qty;
            if (pos.quantity < 0) {
                pnl = -pnl;
            }
            pos.realized_pnl += pnl;
            pos.quantity += filled_qty;
            
            // 如果持仓反向，更新平均价
            if ((pos.quantity > 0 && filled_qty > 0) || (pos.quantity < 0 && filled_qty < 0)) {
                pos.avg_price = filled_price;
            }
        }
    }
    
    std::mutex mutex_;
    std::unordered_map<int64_t, Order::Ptr> active_orders_;  // 活跃订单
    std::unordered_map<std::string, Position> positions_;    // 持仓
    double balance_ = 0.0;                                   // 余额
};

} // namespace trading

