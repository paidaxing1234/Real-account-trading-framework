#pragma once

/**
 * @file risk_manager.h
 * @brief 风险管理器 - 保护账户安全的核心组件
 *
 * 功能：
 * - 订单前置风险检查
 * - 持仓限制监控
 * - 最大回撤保护
 * - 紧急止损（Kill Switch）
 */

#include <string>
#include <map>
#include <mutex>
#include <atomic>
#include "data.h"

namespace trading {

/**
 * @brief 风险限制配置
 */
struct RiskLimits {
    // 单笔订单限制
    double max_order_value = 10000.0;        // 单笔最大金额 (USDT)
    double max_order_quantity = 100.0;       // 单笔最大数量

    // 持仓限制
    double max_position_value = 50000.0;     // 单品种最大持仓 (USDT)
    double max_total_exposure = 100000.0;    // 总敞口限制 (USDT)
    int max_open_orders = 50;                // 最大挂单数

    // 风险控制
    double max_drawdown_pct = 0.10;          // 最大回撤 10%
    double daily_loss_limit = 5000.0;        // 单日最大亏损 (USDT)

    // 频率限制
    int max_orders_per_second = 10;
    int max_orders_per_minute = 100;
};

/**
 * @brief 风险检查结果
 */
struct RiskCheckResult {
    bool passed = true;
    std::string reason;

    static RiskCheckResult ok() {
        return {true, ""};
    }

    static RiskCheckResult reject(const std::string& msg) {
        return {false, msg};
    }
};

/**
 * @brief 风险管理器
 */
class RiskManager {
public:
    RiskManager(const RiskLimits& limits = RiskLimits())
        : limits_(limits), kill_switch_(false) {}

    /**
     * @brief 订单前置风险检查
     */
    RiskCheckResult check_order(const std::string& symbol,
                                 OrderSide side,
                                 double price,
                                 double quantity) {
        std::lock_guard<std::mutex> lock(mutex_);

        // Kill Switch 检查
        if (kill_switch_) {
            return RiskCheckResult::reject("Kill switch activated");
        }

        // 订单金额检查
        double order_value = price * quantity;
        if (order_value > limits_.max_order_value) {
            return RiskCheckResult::reject(
                "Order value " + std::to_string(order_value) +
                " exceeds limit " + std::to_string(limits_.max_order_value)
            );
        }

        // 订单数量检查
        if (quantity > limits_.max_order_quantity) {
            return RiskCheckResult::reject(
                "Order quantity " + std::to_string(quantity) +
                " exceeds limit " + std::to_string(limits_.max_order_quantity)
            );
        }

        // 挂单数量检查
        if (open_order_count_ >= limits_.max_open_orders) {
            return RiskCheckResult::reject(
                "Open orders " + std::to_string(open_order_count_) +
                " exceeds limit " + std::to_string(limits_.max_open_orders)
            );
        }

        // 持仓限制检查
        double current_position = get_position_value(symbol);
        double new_position = current_position + (side == OrderSide::BUY ? order_value : -order_value);

        if (std::abs(new_position) > limits_.max_position_value) {
            return RiskCheckResult::reject(
                "Position value would exceed limit for " + symbol
            );
        }

        // 总敞口检查
        double total_exposure = calculate_total_exposure();
        if (total_exposure + order_value > limits_.max_total_exposure) {
            return RiskCheckResult::reject(
                "Total exposure would exceed limit"
            );
        }

        // 单日亏损检查
        if (daily_pnl_ < -limits_.daily_loss_limit) {
            return RiskCheckResult::reject(
                "Daily loss limit reached: " + std::to_string(daily_pnl_)
            );
        }

        // 频率限制检查
        if (!check_rate_limit()) {
            return RiskCheckResult::reject("Order rate limit exceeded");
        }

        return RiskCheckResult::ok();
    }

    /**
     * @brief 更新持仓
     */
    void update_position(const std::string& symbol, double value) {
        std::lock_guard<std::mutex> lock(mutex_);
        position_values_[symbol] = value;
    }

    /**
     * @brief 更新挂单数量
     */
    void set_open_order_count(int count) {
        std::lock_guard<std::mutex> lock(mutex_);
        open_order_count_ = count;
    }

    /**
     * @brief 更新每日盈亏
     */
    void update_daily_pnl(double pnl) {
        std::lock_guard<std::mutex> lock(mutex_);
        daily_pnl_ = pnl;

        // 检查最大回撤
        if (pnl < peak_pnl_ * (1.0 - limits_.max_drawdown_pct)) {
            activate_kill_switch("Max drawdown exceeded");
        }

        if (pnl > peak_pnl_) {
            peak_pnl_ = pnl;
        }
    }

    /**
     * @brief 激活紧急止损
     */
    void activate_kill_switch(const std::string& reason) {
        kill_switch_ = true;
        std::cout << "[风控] ⚠️ KILL SWITCH ACTIVATED: " << reason << "\n";
    }

    /**
     * @brief 解除紧急止损
     */
    void deactivate_kill_switch() {
        kill_switch_ = false;
        std::cout << "[风控] ✓ Kill switch deactivated\n";
    }

    /**
     * @brief 检查是否被止损
     */
    bool is_kill_switch_active() const {
        return kill_switch_;
    }

    /**
     * @brief 获取风险统计
     */
    nlohmann::json get_risk_stats() const {
        std::lock_guard<std::mutex> lock(mutex_);

        return {
            {"kill_switch", kill_switch_.load()},
            {"open_orders", open_order_count_},
            {"daily_pnl", daily_pnl_},
            {"peak_pnl", peak_pnl_},
            {"total_exposure", calculate_total_exposure()},
            {"position_count", position_values_.size()}
        };
    }

private:
    double get_position_value(const std::string& symbol) const {
        auto it = position_values_.find(symbol);
        return it != position_values_.end() ? it->second : 0.0;
    }

    double calculate_total_exposure() const {
        double total = 0.0;
        for (const auto& [symbol, value] : position_values_) {
            total += std::abs(value);
        }
        return total;
    }

    bool check_rate_limit() {
        auto now = std::chrono::steady_clock::now();

        // 清理过期记录
        while (!order_timestamps_.empty() &&
               std::chrono::duration_cast<std::chrono::seconds>(
                   now - order_timestamps_.front()).count() > 60) {
            order_timestamps_.pop_front();
        }

        // 检查限制
        int count_last_second = 0;
        for (auto it = order_timestamps_.rbegin(); it != order_timestamps_.rend(); ++it) {
            if (std::chrono::duration_cast<std::chrono::seconds>(now - *it).count() < 1) {
                count_last_second++;
            }
        }

        if (count_last_second >= limits_.max_orders_per_second) {
            return false;
        }

        if (order_timestamps_.size() >= limits_.max_orders_per_minute) {
            return false;
        }

        order_timestamps_.push_back(now);
        return true;
    }

    RiskLimits limits_;
    mutable std::mutex mutex_;

    std::atomic<bool> kill_switch_;
    std::map<std::string, double> position_values_;
    int open_order_count_ = 0;
    double daily_pnl_ = 0.0;
    double peak_pnl_ = 0.0;

    std::deque<std::chrono::steady_clock::time_point> order_timestamps_;
};

} // namespace trading
