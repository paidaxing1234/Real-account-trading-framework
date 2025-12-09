#pragma once

#include "strategy_base.h"
#include <unordered_map>

namespace trading {

/**
 * @brief 示例策略 - 简单网格策略
 * 
 * 策略逻辑：
 * 1. 在当前价格上下设置买卖网格
 * 2. 价格下跌时买入，价格上涨时卖出
 * 3. 每次成交后在相反方向挂单
 * 
 * 这只是一个演示策略，展示如何使用框架
 */
class DemoStrategy : public StrategyBase {
public:
    DemoStrategy(
        const std::string& symbol,
        double grid_size = 100.0,      // 网格间距
        double quantity = 0.01,        // 每次交易数量
        int grid_levels = 5            // 网格层数
    ) 
        : StrategyBase("DemoStrategy")
        , symbol_(symbol)
        , grid_size_(grid_size)
        , quantity_(quantity)
        , grid_levels_(grid_levels)
        , mid_price_(0.0) {
    }
    
    virtual void on_init() override {
        log_info("策略初始化 - Symbol: " + symbol_);
        log_info("网格间距: " + std::to_string(grid_size_));
        log_info("交易数量: " + std::to_string(quantity_));
        log_info("网格层数: " + std::to_string(grid_levels_));
    }
    
    virtual void on_ticker(const TickerData::Ptr& ticker) override {
        if (ticker->symbol() != symbol_) {
            return;
        }
        
        // 更新中间价
        auto mid = ticker->mid_price();
        if (mid) {
            mid_price_ = *mid;
        } else {
            mid_price_ = ticker->last_price();
        }
        
        // 如果还没有挂单，则初始化网格
        if (active_orders_.empty() && mid_price_ > 0) {
            initialize_grid();
        }
    }
    
    virtual void on_order(const Order::Ptr& order) override {
        if (order->symbol() != symbol_) {
            return;
        }
        
        // 订单完全成交
        if (order->is_filled()) {
            log_info("订单成交: " + order->to_string());
            
            // 从活跃订单中移除
            active_orders_.erase(order->order_id());
            
            // 在相反方向挂单
            place_opposite_order(order);
        }
        // 订单取消
        else if (order->state() == OrderState::CANCELLED) {
            log_info("订单取消: " + order->to_string());
            active_orders_.erase(order->order_id());
        }
        // 订单被拒绝
        else if (order->state() == OrderState::REJECTED) {
            log_error("订单被拒绝: " + order->to_string());
            active_orders_.erase(order->order_id());
        }
    }
    
    virtual void on_stop() override {
        log_info("策略停止 - 撤销所有订单");
        
        // 撤销所有活跃订单
        for (auto& [id, order] : active_orders_) {
            cancel_order(order);
        }
        
        active_orders_.clear();
    }

private:
    /**
     * @brief 初始化网格
     */
    void initialize_grid() {
        log_info("初始化网格 - 中间价: " + std::to_string(mid_price_));
        
        // 在中间价上下各挂 grid_levels 层网格
        for (int i = 1; i <= grid_levels_; i++) {
            // 下方买单
            double buy_price = mid_price_ - i * grid_size_;
            auto buy_order = buy(symbol_, quantity_, buy_price);
            active_orders_[buy_order->order_id()] = buy_order;
            
            // 上方卖单
            double sell_price = mid_price_ + i * grid_size_;
            auto sell_order = sell(symbol_, quantity_, sell_price);
            active_orders_[sell_order->order_id()] = sell_order;
        }
    }
    
    /**
     * @brief 在相反方向挂单
     */
    void place_opposite_order(const Order::Ptr& filled_order) {
        if (filled_order->is_buy()) {
            // 买单成交，在上方挂卖单
            double sell_price = filled_order->filled_price() + grid_size_;
            auto sell_order = sell(symbol_, quantity_, sell_price);
            active_orders_[sell_order->order_id()] = sell_order;
            
            log_info("买单成交后挂卖单 @ " + std::to_string(sell_price));
        } else {
            // 卖单成交，在下方挂买单
            double buy_price = filled_order->filled_price() - grid_size_;
            auto buy_order = buy(symbol_, quantity_, buy_price);
            active_orders_[buy_order->order_id()] = buy_order;
            
            log_info("卖单成交后挂买单 @ " + std::to_string(buy_price));
        }
    }
    
    std::string symbol_;
    double grid_size_;
    double quantity_;
    int grid_levels_;
    double mid_price_;
    
    // 活跃订单映射：order_id → Order
    std::unordered_map<int64_t, Order::Ptr> active_orders_;
};

} // namespace trading

