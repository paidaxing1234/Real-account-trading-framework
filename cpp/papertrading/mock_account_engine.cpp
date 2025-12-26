/**
 * @file mock_account_engine.cpp
 * @brief 模拟账户引擎实现
 */

#include "mock_account_engine.h"
#include <algorithm>
#include <iostream>
#include <set>
#include <chrono>

namespace trading {
namespace papertrading {

MockAccountEngine::MockAccountEngine(double initial_usdt_balance)
    : usdt_balance_(initial_usdt_balance)
    , frozen_usdt_(0.0)
{
}

// ==================== 账户查询 ====================

double MockAccountEngine::get_available_usdt() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return usdt_balance_;
}

double MockAccountEngine::get_frozen_usdt() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return frozen_usdt_;
}

double MockAccountEngine::get_total_usdt() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return usdt_balance_ + frozen_usdt_;
}

double MockAccountEngine::get_total_equity() const {
    std::lock_guard<std::mutex> lock(mutex_);
    double equity = usdt_balance_ + frozen_usdt_;
    
    // 累加持仓未实现盈亏
    for (const auto& pair : positions_) {
        equity += pair.second.unrealized_pnl;
    }
    
    return equity;
}

std::vector<BalanceInfo> MockAccountEngine::get_all_balances() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<BalanceInfo> result;
    
    BalanceInfo usdt_balance;
    usdt_balance.currency = "USDT";
    usdt_balance.available = usdt_balance_;
    usdt_balance.frozen = frozen_usdt_;
    usdt_balance.total = usdt_balance_ + frozen_usdt_;
    usdt_balance.usd_value = usdt_balance.total;
    usdt_balance.update_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    
    result.push_back(usdt_balance);
    return result;
}

// ==================== 持仓管理 ====================

std::vector<PositionInfo> MockAccountEngine::get_all_positions() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<PositionInfo> result;
    for (const auto& pair : positions_) {
        result.push_back(pair.second);
    }
    return result;
}

std::vector<PositionInfo> MockAccountEngine::get_active_positions() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<PositionInfo> result;
    for (const auto& pair : positions_) {
        if (pair.second.quantity != 0) {
            result.push_back(pair.second);
        }
    }
    return result;
}

PositionInfo MockAccountEngine::get_position_safe(const std::string& symbol, const std::string& pos_side) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string key = symbol + "_" + pos_side;
    auto it = positions_.find(key);
    if (it != positions_.end()) {
        return it->second;
    }
    PositionInfo pos;
    pos.symbol = symbol;
    pos.pos_side = pos_side;
    return pos;
}

PositionInfo* MockAccountEngine::get_position(const std::string& symbol, const std::string& pos_side) {
    // 注意：此方法假设调用者已经持有mutex锁
    std::string key = make_position_key(symbol, pos_side);
    auto it = positions_.find(key);
    if (it == positions_.end()) {
        // 创建新的持仓
        PositionInfo pos;
        pos.symbol = symbol;
        pos.pos_side = pos_side;
        positions_[key] = pos;
        it = positions_.find(key);
    }
    return &(it->second);
}

// ==================== 订单簿管理 ====================

void MockAccountEngine::add_limit_order(const OrderInfo& order) {
    std::lock_guard<std::mutex> lock(mutex_);
    open_orders_[order.client_order_id] = order;
    if (!order.exchange_order_id.empty()) {
        open_orders_[order.exchange_order_id] = order;
    }
}

bool MockAccountEngine::cancel_order(const std::string& order_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    // 查找订单
    auto it = open_orders_.find(order_id);
    if (it == open_orders_.end()) {
        // 可能是通过另一个ID存储的，尝试查找
        for (auto it2 = open_orders_.begin(); it2 != open_orders_.end(); ++it2) {
            if (it2->second.client_order_id == order_id || 
                it2->second.exchange_order_id == order_id) {
                it = it2;
                break;
            }
        }
        if (it == open_orders_.end()) {
            return false;
        }
    }
    
    // 解冻资金（在锁内直接操作，避免死锁）
    double frozen_amount = it->second.quantity * it->second.price;
    frozen_usdt_ = std::max(0.0, frozen_usdt_ - frozen_amount);
    usdt_balance_ += frozen_amount;
    
    // 移除订单
    OrderInfo order = it->second;
    open_orders_.erase(it);
    
    // 如果通过exchange_order_id也存储了，也要删除
    if (!order.exchange_order_id.empty() && order.exchange_order_id != order.client_order_id) {
        auto it3 = open_orders_.find(order.exchange_order_id);
        if (it3 != open_orders_.end()) {
            open_orders_.erase(it3);
        }
    }
    
    return true;
}

std::vector<OrderInfo> MockAccountEngine::get_open_orders() const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<OrderInfo> result;
    
    // 去重（可能通过client_order_id和exchange_order_id都存储了）
    std::set<std::string> seen_ids;
    for (const auto& pair : open_orders_) {
        if (seen_ids.find(pair.second.client_order_id) == seen_ids.end()) {
            result.push_back(pair.second);
            seen_ids.insert(pair.second.client_order_id);
        }
    }
    
    return result;
}

std::vector<OrderInfo> MockAccountEngine::get_open_orders(const std::string& symbol) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<OrderInfo> result;
    
    std::set<std::string> seen_ids;
    for (const auto& pair : open_orders_) {
        if (pair.second.symbol == symbol && 
            seen_ids.find(pair.second.client_order_id) == seen_ids.end()) {
            result.push_back(pair.second);
            seen_ids.insert(pair.second.client_order_id);
        }
    }
    
    return result;
}

OrderInfo* MockAccountEngine::get_order(const std::string& order_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = open_orders_.find(order_id);
    if (it != open_orders_.end()) {
        return &(it->second);
    }
    
    // 尝试通过client_order_id或exchange_order_id查找
    for (auto& pair : open_orders_) {
        if (pair.second.client_order_id == order_id || 
            pair.second.exchange_order_id == order_id) {
            return &(pair.second);
        }
    }
    
    return nullptr;
}

// ==================== 资金操作 ====================

bool MockAccountEngine::freeze_usdt(double amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (usdt_balance_ < amount) {
        return false;
    }
    usdt_balance_ -= amount;
    frozen_usdt_ += amount;
    return true;
}

void MockAccountEngine::unfreeze_usdt(double amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    frozen_usdt_ = std::max(0.0, frozen_usdt_ - amount);
    usdt_balance_ += amount;
}

void MockAccountEngine::add_usdt(double amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    usdt_balance_ += amount;
}

bool MockAccountEngine::subtract_usdt(double amount) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (usdt_balance_ < amount) {
        return false;
    }
    usdt_balance_ -= amount;
    return true;
}

// ==================== 持仓更新 ====================

void MockAccountEngine::update_position(const std::string& symbol,
                                       const std::string& side,
                                       double quantity,
                                       double price,
                                       double fee,
                                       double contract_value) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    // 默认使用net持仓
    std::string pos_side = "net";
    PositionInfo* pos = get_position(symbol, pos_side);
    
    if (!pos) return;
    
    double cost = quantity * price * contract_value;
    double signed_qty = (side == "buy") ? quantity : -quantity;
    
    // 更新持仓数量
    double old_qty = pos->quantity;
    pos->quantity += signed_qty;
    
    // 更新持仓均价（加权平均）
    if (old_qty == 0) {
        // 开新仓
        pos->avg_price = price;
    } else if (pos->quantity == 0) {
        // 平仓
        pos->avg_price = 0;
    } else {
        // 加仓或减仓，计算新的均价
        if ((old_qty > 0 && signed_qty > 0) || (old_qty < 0 && signed_qty < 0)) {
            // 加仓：加权平均
            pos->avg_price = (old_qty * pos->avg_price + signed_qty * price) / pos->quantity;
        }
        // 减仓：均价不变
    }
    
    // 更新已实现盈亏（如果是平仓）
    if ((old_qty > 0 && signed_qty < 0) || (old_qty < 0 && signed_qty > 0)) {
        double closed_qty = std::min(std::abs(old_qty), std::abs(signed_qty));
        double pnl = closed_qty * (price - pos->avg_price) * contract_value;
        if (old_qty < 0) {  // 空仓
            pnl = -pnl;
        }
        pos->realized_pnl += pnl;
        
        // 已实现盈亏需要加到USDT余额中
        usdt_balance_ += pnl;
    }
    
    // 扣除手续费
    usdt_balance_ -= fee;
    
    // 如果是买单，扣除资金；如果是卖单，增加资金
    if (side == "buy") {
        usdt_balance_ -= cost;
    } else {
        usdt_balance_ += cost;
    }
    
    // 更新时间
    pos->update_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    
    // 更新未实现盈亏（需要标记价格，这里暂时设为0，由外部调用update_unrealized_pnl更新）
    // pos->unrealized_pnl = ...;  // 需要标记价格
}

void MockAccountEngine::mark_order_filled(const std::string& order_id, double filled_qty, double filled_price) {
    std::lock_guard<std::mutex> lock(mutex_);
    OrderInfo* order = get_order(order_id);
    if (order) {
        order->filled_quantity = static_cast<int>(filled_qty);
        order->filled_price = filled_price;
        order->update_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }
}

void MockAccountEngine::remove_order(const std::string& order_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = open_orders_.find(order_id);
    if (it != open_orders_.end()) {
        OrderInfo order = it->second;
        open_orders_.erase(it);
        
        // 如果通过exchange_order_id也存储了，也要删除
        if (!order.exchange_order_id.empty() && order.exchange_order_id != order.client_order_id) {
            auto it2 = open_orders_.find(order.exchange_order_id);
            if (it2 != open_orders_.end()) {
                open_orders_.erase(it2);
            }
        }
    }
}

// ==================== 辅助方法 ====================

std::string MockAccountEngine::make_position_key(const std::string& symbol, const std::string& pos_side) const {
    return symbol + "_" + pos_side;
}

void MockAccountEngine::update_unrealized_pnl(const std::string& symbol, const std::string& pos_side, double mark_price) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::string key = make_position_key(symbol, pos_side);
    auto it = positions_.find(key);
    if (it != positions_.end() && it->second.quantity != 0) {
        double contract_value = 1.0;  // 默认合约面值
        double pnl = it->second.quantity * (mark_price - it->second.avg_price) * contract_value;
        it->second.unrealized_pnl = pnl;
        it->second.mark_price = mark_price;
    }
}

} // namespace papertrading
} // namespace trading

