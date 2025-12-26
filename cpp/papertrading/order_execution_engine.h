/**
 * @file order_execution_engine.h
 * @brief 订单执行引擎 - 模拟订单成交逻辑
 * 
 * 功能：
 * 1. 市价单执行（立即按最新价成交，含滑点）
 * 2. 限价单挂单/成交（等待价格触发）
 * 3. 手续费计算
 * 4. 滑点模拟
 * 5. 成交回报生成
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include "mock_account_engine.h"
#include "papertrading_config.h"
#include "../strategies/trading_module.h"
#include "../strategies/market_data_module.h"
#include <string>
#include <atomic>
#include <vector>
#include <nlohmann/json.hpp>

namespace trading {
namespace papertrading {

/**
 * @brief 订单回报结构
 */
struct OrderReport {
    std::string client_order_id;
    std::string exchange_order_id;
    std::string symbol;
    std::string side;
    std::string order_type;
    std::string status;           // "accepted", "filled", "partially_filled", "rejected", "cancelled"
    double filled_quantity;
    double filled_price;
    double quantity;
    double price;
    double fee;
    std::string error_msg;
    int64_t timestamp;
    
    // 转换为JSON（用于ZMQ发布）
    nlohmann::json to_json() const;
};

/**
 * @brief 订单执行引擎
 * 
 * 负责模拟订单的执行逻辑：
 * - 市价单：立即按最新成交价成交（含滑点）
 * - 限价单：挂单，等待价格触发
 * - 计算手续费和滑点
 */
class OrderExecutionEngine {
public:
    /**
     * @brief 构造函数
     * @param account 模拟账户引擎
     * @param config 配置对象（可选，如果为nullptr则使用默认值）
     */
    explicit OrderExecutionEngine(MockAccountEngine* account, const PaperTradingConfig* config = nullptr);
    
    ~OrderExecutionEngine() = default;
    
    // ==================== 订单执行 ====================
    
    /**
     * @brief 执行市价单
     * @param order 订单信息
     * @param last_trade_price 最新成交价
     * @return 订单回报
     */
    OrderReport execute_market_order(const OrderInfo& order, double last_trade_price);
    
    /**
     * @brief 执行限价单（挂单）
     * @param order 订单信息
     * @return 订单回报（状态为accepted）
     */
    OrderReport execute_limit_order(const OrderInfo& order);
    
    /**
     * @brief 检查限价单是否可以成交（由行情更新时调用）
     * @param symbol 交易对
     * @param price 当前价格
     * @param timestamp 时间戳
     * @return 成交的订单回报列表
     */
    std::vector<OrderReport> check_limit_orders(const std::string& symbol, double price, int64_t timestamp);
    
    /**
     * @brief 生成订单回报
     * @param order 订单信息
     * @param status 状态
     * @param filled_price 成交价
     * @param filled_qty 成交数量
     * @param fee 手续费
     * @return 订单回报
     */
    OrderReport generate_report(const OrderInfo& order,
                               const std::string& status,
                               double filled_price,
                               double filled_qty,
                               double fee);

private:
    // 计算手续费
    double calculate_fee(double quantity, double price, bool is_maker);
    
    // 应用滑点
    double apply_slippage(double price, const std::string& side);
    
    // 生成交易所订单ID
    std::string generate_exchange_order_id();
    
    MockAccountEngine* account_;
    const PaperTradingConfig* config_;  // 配置对象（可能为nullptr，使用默认值）
    
    // 订单ID计数器
    std::atomic<uint64_t> order_id_counter_{1};
};

} // namespace papertrading
} // namespace trading

