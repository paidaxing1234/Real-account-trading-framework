/**
 * @file mock_account_engine.h
 * @brief 模拟账户引擎 - 管理模拟交易的账户余额、持仓、订单簿
 * 
 * 功能：
 * 1. 余额管理（USDT等）
 * 2. 持仓管理（多空持仓）
 * 3. 订单簿管理（限价单挂单）
 * 4. 资金冻结/解冻
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include "../strategies/account_module.h"
#include <string>
#include <map>
#include <vector>
#include <mutex>
#include <memory>
#include <cstdint>

namespace trading {
// 为了避免 OrderType 冲突，在这里直接定义 OrderInfo 和 OrderStatus
// 这些定义与 trading_module.h 中的定义保持一致，但不包含 OrderType

/**
 * @brief 订单状态
 */
enum class OrderStatus {
    PENDING,           // 待提交
    SUBMITTED,         // 已提交
    ACCEPTED,          // 已接受（交易所确认）
    PARTIALLY_FILLED,  // 部分成交
    FILLED,            // 完全成交
    CANCELLED,         // 已撤销
    REJECTED,          // 被拒绝
    FAILED             // 失败
};

/**
 * @brief 订单信息
 */
struct OrderInfo {
    std::string client_order_id;    // 客户端订单ID
    std::string exchange_order_id;  // 交易所订单ID
    std::string symbol;             // 交易对
    std::string side;               // "buy" or "sell"
    std::string order_type;         // "market" or "limit"
    std::string pos_side;           // "net", "long", "short"
    double price;                   // 价格
    int quantity;                   // 数量（张）
    int filled_quantity;            // 已成交数量
    double filled_price;            // 成交均价
    OrderStatus status;             // 状态
    int64_t create_time;            // 创建时间
    int64_t update_time;            // 更新时间
    std::string error_msg;          // 错误信息
    
    OrderInfo() : price(0), quantity(0), filled_quantity(0), 
                  filled_price(0), status(OrderStatus::PENDING),
                  create_time(0), update_time(0) {}
};

namespace papertrading {

/**
 * @brief 模拟账户引擎
 * 
 * 管理模拟交易的账户状态：
 * - USDT余额（可用、冻结）
 * - 持仓（多空持仓）
 * - 挂单（限价单订单簿）
 */
class MockAccountEngine {
public:
    /**
     * @brief 构造函数
     * @param initial_usdt_balance 初始USDT余额
     */
    explicit MockAccountEngine(double initial_usdt_balance = 10000.0);
    
    ~MockAccountEngine() = default;
    
    // ==================== 账户查询 ====================
    
    /**
     * @brief 获取可用USDT余额
     */
    double get_available_usdt() const;
    
    /**
     * @brief 获取冻结USDT余额
     */
    double get_frozen_usdt() const;
    
    /**
     * @brief 获取总USDT余额（可用+冻结）
     */
    double get_total_usdt() const;
    
    /**
     * @brief 获取总权益（USD）
     * 
     * 计算：USDT余额 + 持仓未实现盈亏
     */
    double get_total_equity() const;
    
    /**
     * @brief 获取所有余额
     */
    std::vector<BalanceInfo> get_all_balances() const;
    
    // ==================== 持仓管理 ====================
    
    /**
     * @brief 获取所有持仓
     */
    std::vector<PositionInfo> get_all_positions() const;
    
    /**
     * @brief 获取有效持仓（数量不为0）
     */
    std::vector<PositionInfo> get_active_positions() const;
    
    /**
     * @brief 获取指定交易对的持仓
     * @param symbol 交易对
     * @param pos_side 持仓方向 "net"/"long"/"short"
     * @return 持仓信息指针，如果不存在则创建新的持仓
     * 
     * 注意：此方法内部已加锁，但返回的指针在锁外使用，调用者需要小心使用
     */
    PositionInfo get_position_safe(const std::string& symbol, const std::string& pos_side = "net") const;
    
    // ==================== 订单簿管理（限价单） ====================
    
    /**
     * @brief 添加限价单到订单簿
     */
    void add_limit_order(const OrderInfo& order);
    
    /**
     * @brief 撤销订单
     * @param order_id 订单ID（client_order_id或exchange_order_id）
     */
    bool cancel_order(const std::string& order_id);
    
    /**
     * @brief 获取所有挂单
     */
    std::vector<OrderInfo> get_open_orders() const;
    
    /**
     * @brief 获取指定交易对的所有挂单
     */
    std::vector<OrderInfo> get_open_orders(const std::string& symbol) const;
    
    // ==================== 资金操作（由执行引擎调用） ====================
    
    /**
     * @brief 冻结资金（下单时）
     * @param amount 冻结金额
     * @return true 成功，false 余额不足
     */
    bool freeze_usdt(double amount);
    
    /**
     * @brief 解冻资金（撤单时）
     * @param amount 解冻金额
     */
    void unfreeze_usdt(double amount);
    
    /**
     * @brief 增加USDT（卖单成交时）
     * @param amount 增加金额
     */
    void add_usdt(double amount);
    
    /**
     * @brief 减少USDT（买单成交时）
     * @param amount 减少金额
     * @return true 成功，false 余额不足
     */
    bool subtract_usdt(double amount);
    
    // ==================== 持仓更新（由执行引擎调用） ====================
    
    /**
     * @brief 更新持仓（成交时调用）
     * @param symbol 交易对
     * @param side 买卖方向 "buy"/"sell"
     * @param quantity 成交数量（张）
     * @param price 成交价格
     * @param fee 手续费
     * @param contract_value 合约面值（默认1，表示1张=1个币）
     */
    void update_position(const std::string& symbol,
                        const std::string& side,
                        double quantity,
                        double price,
                        double fee,
                        double contract_value = 1.0);
    
    // ==================== 订单更新 ====================
    
    /**
     * @brief 标记订单为已成交（部分或全部）
     * @param order_id 订单ID
     * @param filled_qty 已成交数量
     * @param filled_price 成交均价
     */
    void mark_order_filled(const std::string& order_id, double filled_qty, double filled_price);
    
    /**
     * @brief 移除已完成的订单（成交或撤销）
     */
    void remove_order(const std::string& order_id);

    // ==================== 账户重置 ====================

    /**
     * @brief 重置账户到初始状态
     * @param initial_balance 初始余额
     */
    void reset(double initial_balance);

private:
    /**
     * @brief 内部方法：获取持仓指针（假设已持有锁）
     */
    PositionInfo* get_position(const std::string& symbol, const std::string& pos_side = "net");
    
    /**
     * @brief 根据订单ID获取订单信息
     */
    OrderInfo* get_order(const std::string& order_id);

private:
    // 生成持仓key
    std::string make_position_key(const std::string& symbol, const std::string& pos_side) const;
    
    // 更新持仓未实现盈亏（使用标记价格）
    void update_unrealized_pnl(const std::string& symbol, const std::string& pos_side, double mark_price);
    
    // 成员变量
    double usdt_balance_;                           // USDT余额
    double frozen_usdt_;                            // 冻结USDT
    std::map<std::string, PositionInfo> positions_; // 持仓: symbol_posside -> PositionInfo
    std::map<std::string, OrderInfo> open_orders_;  // 挂单: order_id -> OrderInfo
    mutable std::mutex mutex_;
};

} // namespace papertrading
} // namespace trading

