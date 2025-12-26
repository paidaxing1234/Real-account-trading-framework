/**
 * @file order_execution_engine.cpp
 * @brief 订单执行引擎实现
 */

#include "order_execution_engine.h"
#include <cmath>
#include <chrono>
#include <algorithm>

namespace trading {
namespace papertrading {

OrderExecutionEngine::OrderExecutionEngine(MockAccountEngine* account, const PaperTradingConfig* config)
    : account_(account)
    , config_(config)
{
    if (!account_) {
        throw std::invalid_argument("MockAccountEngine cannot be null");
    }
}

// ==================== 订单执行 ====================

OrderReport OrderExecutionEngine::execute_market_order(const OrderInfo& order, double last_trade_price) {
    OrderReport report;
    report.client_order_id = order.client_order_id;
    report.symbol = order.symbol;
    report.side = order.side;
    report.order_type = order.order_type;
    report.quantity = order.quantity;
    report.price = 0;  // 市价单无价格
    report.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    
    // 检查余额（买单需要资金）
    if (order.side == "buy") {
        // 估算需要的资金（使用当前价格 + 滑点 + 手续费）
        double estimated_price = apply_slippage(last_trade_price, "buy");
        double estimated_cost = order.quantity * estimated_price;
        double estimated_fee = calculate_fee(order.quantity, estimated_price, false);  // 市价单是taker
        double total_needed = estimated_cost + estimated_fee;
        
        if (account_->get_available_usdt() < total_needed) {
            report.status = "rejected";
            report.error_msg = "Insufficient balance";
            report.exchange_order_id = "";
            return report;
        }
    }
    
    // 计算执行价格（含滑点）
    double execution_price = apply_slippage(last_trade_price, order.side);
    
    // 计算手续费（市价单是taker）
    double fee = calculate_fee(order.quantity, execution_price, false);
    
    // 生成交易所订单ID
    std::string exchange_order_id = generate_exchange_order_id();
    report.exchange_order_id = exchange_order_id;
    
    // 更新账户（使用配置的合约面值）
    double contract_value = config_ ? config_->get_contract_value(order.symbol) : 1.0;
    double cost = order.quantity * execution_price * contract_value;
    
    if (order.side == "buy") {
        // 买单：扣除资金
        if (!account_->subtract_usdt(cost + fee)) {
            report.status = "rejected";
            report.error_msg = "Insufficient balance";
            return report;
        }
    } else {
        // 卖单：增加资金
        account_->add_usdt(cost - fee);
    }
    
    // 更新持仓
    account_->update_position(order.symbol, order.side, order.quantity, 
                            execution_price, fee, contract_value);
    
    // 生成回报
    report.status = "filled";
    report.filled_quantity = order.quantity;
    report.filled_price = execution_price;
    report.fee = fee;
    
    return report;
}

OrderReport OrderExecutionEngine::execute_limit_order(const OrderInfo& order) {
    OrderReport report;
    report.client_order_id = order.client_order_id;
    report.symbol = order.symbol;
    report.side = order.side;
    report.order_type = order.order_type;
    report.quantity = order.quantity;
    report.price = order.price;
    report.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    
    // 检查余额（买单需要冻结资金）
    if (order.side == "buy") {
        double cost = order.quantity * order.price;
        double estimated_fee = calculate_fee(order.quantity, order.price, true);  // 限价单是maker（如果成交）
        double total_needed = cost + estimated_fee;
        
        if (account_->get_available_usdt() < total_needed) {
            report.status = "rejected";
            report.error_msg = "Insufficient balance";
            report.exchange_order_id = "";
            return report;
        }
        
        // 冻结资金
        account_->freeze_usdt(cost + estimated_fee);
    }
    
    // 生成交易所订单ID
    std::string exchange_order_id = generate_exchange_order_id();
    report.exchange_order_id = exchange_order_id;
    
    // 添加到订单簿
    OrderInfo order_copy = order;
    order_copy.exchange_order_id = exchange_order_id;
    order_copy.status = OrderStatus::ACCEPTED;
    order_copy.create_time = report.timestamp;
    account_->add_limit_order(order_copy);
    
    // 生成回报（状态为accepted，还未成交）
    report.status = "accepted";
    report.filled_quantity = 0;
    report.filled_price = 0;
    report.fee = 0;
    
    return report;
}

std::vector<OrderReport> OrderExecutionEngine::check_limit_orders(
    const std::string& symbol, 
    double price, 
    int64_t timestamp) {
    
    std::vector<OrderReport> filled_reports;
    
    // 获取该交易对的所有挂单
    auto open_orders = account_->get_open_orders(symbol);
    
    for (const auto& order : open_orders) {
        // 检查是否可以成交
        bool can_fill = false;
        if (order.side == "buy" && price <= order.price) {
            // 买单：当前价格 <= 限价，可以成交
            can_fill = true;
        } else if (order.side == "sell" && price >= order.price) {
            // 卖单：当前价格 >= 限价，可以成交
            can_fill = true;
        }
        
        if (!can_fill) {
            continue;
        }
        
        // 计算剩余未成交数量
        double remaining_qty = order.quantity - order.filled_quantity;
        if (remaining_qty <= 0) {
            continue;
        }
        
        // 成交价格使用限价（因为是限价单，按照限价成交）
        double execution_price = order.price;
        
        // 计算手续费（限价单是maker）
        double fee = calculate_fee(remaining_qty, execution_price, true);
        
        // 生成回报
        OrderReport report;
        report.client_order_id = order.client_order_id;
        report.exchange_order_id = order.exchange_order_id;
        report.symbol = order.symbol;
        report.side = order.side;
        report.order_type = order.order_type;
        report.quantity = order.quantity;
        report.price = order.price;
        report.timestamp = timestamp;
        
        // 更新账户（使用配置的合约面值）
        double contract_value = config_ ? config_->get_contract_value(order.symbol) : 1.0;
        
        if (order.side == "buy") {
            // 买单：解冻资金，扣除资金
            double cost = remaining_qty * execution_price * contract_value;
            account_->unfreeze_usdt(cost + fee);
            account_->subtract_usdt(cost + fee);
        } else {
            // 卖单：增加资金
            double cost = remaining_qty * execution_price * contract_value;
            account_->add_usdt(cost - fee);
        }
        
        // 更新持仓
        account_->update_position(order.symbol, order.side, remaining_qty,
                                execution_price, fee, contract_value);
        
        // 标记订单已成交
        account_->mark_order_filled(order.client_order_id, remaining_qty, execution_price);
        
        // 移除订单（完全成交）
        account_->remove_order(order.client_order_id);
        
        // 生成回报
        report.status = "filled";
        report.filled_quantity = remaining_qty;
        report.filled_price = execution_price;
        report.fee = fee;
        
        filled_reports.push_back(report);
    }
    
    return filled_reports;
}

OrderReport OrderExecutionEngine::generate_report(const OrderInfo& order,
                                                  const std::string& status,
                                                  double filled_price,
                                                  double filled_qty,
                                                  double fee) {
    OrderReport report;
    report.client_order_id = order.client_order_id;
    report.exchange_order_id = order.exchange_order_id;
    report.symbol = order.symbol;
    report.side = order.side;
    report.order_type = order.order_type;
    report.status = status;
    report.filled_quantity = filled_qty;
    report.filled_price = filled_price;
    report.fee = fee;
    report.quantity = order.quantity;
    report.price = order.price;
    report.timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
    return report;
}

// ==================== 辅助方法 ====================

double OrderExecutionEngine::calculate_fee(double quantity, double price, bool is_maker) {
    double fee_rate;
    if (config_) {
        fee_rate = is_maker ? config_->maker_fee_rate() : config_->taker_fee_rate();
    } else {
        // 默认值
        fee_rate = is_maker ? 0.0002 : 0.0005;
    }
    return quantity * price * fee_rate;
}

double OrderExecutionEngine::apply_slippage(double price, const std::string& side) {
    double slippage = config_ ? config_->market_order_slippage() : 0.0001;
    if (side == "buy") {
        // 买单：价格向上滑点
        return price * (1.0 + slippage);
    } else {
        // 卖单：价格向下滑点
        return price * (1.0 - slippage);
    }
}

std::string OrderExecutionEngine::generate_exchange_order_id() {
    uint64_t id = order_id_counter_.fetch_add(1);
    return "mock_" + std::to_string(id);
}

// ==================== OrderReport to_json ====================

nlohmann::json OrderReport::to_json() const {
    nlohmann::json j;
    j["type"] = "order_report";
    j["client_order_id"] = client_order_id;
    j["exchange_order_id"] = exchange_order_id;
    j["symbol"] = symbol;
    j["side"] = side;
    j["order_type"] = order_type;
    j["status"] = status;
    j["filled_quantity"] = filled_quantity;
    j["filled_price"] = filled_price;
    j["quantity"] = quantity;
    j["price"] = price;
    j["fee"] = fee;
    j["error_msg"] = error_msg;
    j["timestamp"] = timestamp;
    return j;
}

// 在头文件中声明，这里实现
// OrderReport::to_json() 的实现

} // namespace papertrading
} // namespace trading

