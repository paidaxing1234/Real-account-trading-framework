/**
 * @file trading_module.h
 * @brief 交易模块 - 下单、撤单等交易操作
 * 
 * 功能:
 * 1. 合约市价下单
 * 2. 合约限价下单
 * 3. 撤单
 * 4. 订单回报处理
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <map>
#include <set>
#include <memory>
#include <mutex>
#include <functional>
#include <atomic>
#include <chrono>
#include <iostream>

#include <zmq.hpp>
#include <nlohmann/json.hpp>

namespace trading {

// ============================================================
// 订单数据结构
// ============================================================

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
 * @brief 订单类型
 */
enum class OrderType {
    MARKET,    // 市价单
    LIMIT,     // 限价单
    STOP,      // 止损单
    TAKE_PROFIT // 止盈单
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


// ============================================================
// 交易模块
// ============================================================

/**
 * @brief 交易模块
 * 
 * 负责：
 * - 发送订单（市价、限价）
 * - 撤销订单
 * - 处理订单回报
 * - 管理活跃订单
 */
class TradingModule {
public:
    // 订单回报回调类型
    using OrderReportCallback = std::function<void(const nlohmann::json&)>;
    // 日志回调类型
    using LogCallback = std::function<void(const std::string&, bool)>;  // msg, is_error
    
    explicit TradingModule()
        : order_count_(0)
        , report_count_(0) {}
    
    // ==================== 初始化 ====================
    
    /**
     * @brief 设置策略ID
     */
    void set_strategy_id(const std::string& strategy_id) {
        strategy_id_ = strategy_id;
    }
    
    /**
     * @brief 设置 ZMQ socket
     */
    void set_sockets(zmq::socket_t* order_push, zmq::socket_t* report_sub) {
        order_push_ = order_push;
        report_sub_ = report_sub;
    }
    
    /**
     * @brief 设置日志回调
     */
    void set_log_callback(LogCallback callback) {
        log_callback_ = std::move(callback);
    }
    
    // ==================== 下单接口 ====================
    
    /**
     * @brief 发送合约市价订单
     * @param symbol 交易对（如 BTC-USDT-SWAP）
     * @param side "buy" 或 "sell"
     * @param quantity 张数
     * @param pos_side 持仓方向: "net"(单向持仓/默认), "long", "short"(双向持仓)
     * @return 客户端订单ID
     */
    std::string send_swap_market_order(const std::string& symbol,
                                       const std::string& side,
                                       int quantity,
                                       const std::string& pos_side = "net") {
        if (!order_push_) {
            log_error("订单通道未连接");
            return "";
        }
        
        std::string client_order_id = generate_client_order_id();
        std::string actual_pos_side = pos_side.empty() ? "net" : pos_side;
        
        nlohmann::json order = {
            {"type", "order_request"},
            {"strategy_id", strategy_id_},
            {"client_order_id", client_order_id},
            {"symbol", symbol},
            {"side", side},
            {"order_type", "market"},
            {"quantity", quantity},
            {"price", 0},
            {"td_mode", "cross"},
            {"pos_side", actual_pos_side},
            {"tgt_ccy", ""},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            int64_t send_ts = current_timestamp_ns();
            std::string msg = order.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            order_count_++;
            
            // 记录活跃订单
            {
                std::lock_guard<std::mutex> lock(orders_mutex_);
                OrderInfo info;
                info.client_order_id = client_order_id;
                info.symbol = symbol;
                info.side = side;
                info.order_type = "market";
                info.pos_side = actual_pos_side;
                info.quantity = quantity;
                info.create_time = current_timestamp_ms();
                info.status = OrderStatus::SUBMITTED;
                active_orders_[client_order_id] = info;
            }
            
            log_info("[下单] " + side + " " + std::to_string(quantity) + "张 " + symbol + 
                    " | 订单ID: " + client_order_id + " | 发送时间: " + std::to_string(send_ts) + "ns");
            
            return client_order_id;
        } catch (const std::exception& e) {
            log_error("发送订单失败: " + std::string(e.what()));
            return "";
        }
    }
    
    /**
     * @brief 发送合约限价订单
     */
    std::string send_swap_limit_order(const std::string& symbol,
                                      const std::string& side,
                                      int quantity,
                                      double price,
                                      const std::string& pos_side = "net") {
        if (!order_push_) {
            log_error("订单通道未连接");
            return "";
        }
        
        std::string client_order_id = generate_client_order_id();
        std::string actual_pos_side = pos_side.empty() ? "net" : pos_side;
        
        nlohmann::json order = {
            {"type", "order_request"},
            {"strategy_id", strategy_id_},
            {"client_order_id", client_order_id},
            {"symbol", symbol},
            {"side", side},
            {"order_type", "limit"},
            {"quantity", quantity},
            {"price", price},
            {"td_mode", "cross"},
            {"pos_side", actual_pos_side},
            {"tgt_ccy", ""},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = order.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            order_count_++;
            
            // 记录活跃订单
            {
                std::lock_guard<std::mutex> lock(orders_mutex_);
                OrderInfo info;
                info.client_order_id = client_order_id;
                info.symbol = symbol;
                info.side = side;
                info.order_type = "limit";
                info.pos_side = actual_pos_side;
                info.price = price;
                info.quantity = quantity;
                info.create_time = current_timestamp_ms();
                info.status = OrderStatus::SUBMITTED;
                active_orders_[client_order_id] = info;
            }
            
            log_info("[下单] " + side + " " + std::to_string(quantity) + "张 @ " + 
                    std::to_string(price) + " " + symbol);
            
            return client_order_id;
        } catch (const std::exception& e) {
            log_error("发送订单失败: " + std::string(e.what()));
            return "";
        }
    }
    
    /**
     * @brief 撤销订单
     */
    bool cancel_order(const std::string& symbol, const std::string& client_order_id) {
        if (!order_push_) {
            log_error("订单通道未连接");
            return false;
        }
        
        nlohmann::json cancel_req = {
            {"type", "cancel_request"},
            {"strategy_id", strategy_id_},
            {"symbol", symbol},
            {"client_order_id", client_order_id},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = cancel_req.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            log_info("[撤单] " + symbol + " 订单ID: " + client_order_id);
            return true;
        } catch (const std::exception& e) {
            log_error("撤单失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 撤销所有订单
     */
    bool cancel_all_orders(const std::string& symbol = "") {
        if (!order_push_) {
            log_error("订单通道未连接");
            return false;
        }
        
        nlohmann::json cancel_req = {
            {"type", "cancel_all_request"},
            {"strategy_id", strategy_id_},
            {"symbol", symbol},  // 空则撤销所有
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = cancel_req.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            log_info("[撤销全部] " + (symbol.empty() ? "所有订单" : symbol));
            return true;
        } catch (const std::exception& e) {
            log_error("撤销全部失败: " + std::string(e.what()));
            return false;
        }
    }
    
    // ==================== 订单回报处理 ====================
    
    /**
     * @brief 处理订单回报（主循环调用）
     * @return 是否有处理订单相关的回报
     */
    bool process_order_reports() {
        if (!report_sub_) return false;
        
        bool has_order_report = false;
        zmq::message_t message;
        
        while (report_sub_->recv(message, zmq::recv_flags::dontwait)) {
            try {
                std::string msg_str(static_cast<char*>(message.data()), message.size());
                auto report = nlohmann::json::parse(msg_str);
                
                std::string report_type = report.value("type", "");
                
                // 只处理订单相关回报
                if (report_type == "order_update" || 
                    report_type == "order_report" ||
                    report_type == "order_response") {
                    
                    report_count_++;
                    has_order_report = true;
                    
                    // 更新活跃订单
                    update_order_from_report(report);
                    
                    // 打印回报
                    print_order_report(report);
                    
                    // 用户回调
                    if (order_report_callback_) {
                        order_report_callback_(report);
                    }
                }
                
            } catch (const std::exception& e) {
                log_error("[回报解析] 错误: " + std::string(e.what()));
            }
        }
        
        return has_order_report;
    }
    
    /**
     * @brief 设置订单回报回调
     */
    void set_order_report_callback(OrderReportCallback callback) {
        order_report_callback_ = std::move(callback);
    }
    
    // ==================== 订单查询 ====================
    
    /**
     * @brief 获取订单信息
     */
    bool get_order(const std::string& client_order_id, OrderInfo& order) const {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        auto it = active_orders_.find(client_order_id);
        if (it == active_orders_.end()) return false;
        order = it->second;
        return true;
    }
    
    /**
     * @brief 获取所有活跃订单
     */
    std::vector<OrderInfo> get_active_orders() const {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        std::vector<OrderInfo> result;
        for (const auto& pair : active_orders_) {
            if (pair.second.status == OrderStatus::SUBMITTED ||
                pair.second.status == OrderStatus::ACCEPTED ||
                pair.second.status == OrderStatus::PARTIALLY_FILLED) {
                result.push_back(pair.second);
            }
        }
        return result;
    }
    
    /**
     * @brief 获取未完成订单数量
     */
    size_t pending_order_count() const {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        size_t count = 0;
        for (const auto& pair : active_orders_) {
            if (pair.second.status == OrderStatus::SUBMITTED ||
                pair.second.status == OrderStatus::ACCEPTED ||
                pair.second.status == OrderStatus::PARTIALLY_FILLED) {
                count++;
            }
        }
        return count;
    }
    
    // ==================== 统计 ====================
    
    int64_t total_order_count() const { return order_count_.load(); }
    int64_t total_report_count() const { return report_count_.load(); }

private:
    void update_order_from_report(const nlohmann::json& report) {
        std::string client_order_id = report.value("client_order_id", "");
        if (client_order_id.empty()) return;
        
        std::lock_guard<std::mutex> lock(orders_mutex_);
        auto it = active_orders_.find(client_order_id);
        if (it == active_orders_.end()) return;
        
        std::string status = report.value("status", "");
        it->second.exchange_order_id = report.value("exchange_order_id", "");
        it->second.filled_quantity = report.value("filled_quantity", 0);
        it->second.filled_price = report.value("filled_price", 0.0);
        it->second.update_time = current_timestamp_ms();
        it->second.error_msg = report.value("error_msg", "");
        
        if (status == "accepted") {
            it->second.status = OrderStatus::ACCEPTED;
        } else if (status == "filled") {
            it->second.status = OrderStatus::FILLED;
        } else if (status == "partially_filled" || status == "partial_filled") {
            it->second.status = OrderStatus::PARTIALLY_FILLED;
        } else if (status == "cancelled" || status == "canceled") {
            it->second.status = OrderStatus::CANCELLED;
        } else if (status == "rejected") {
            it->second.status = OrderStatus::REJECTED;
        } else if (status == "failed" || status == "error") {
            it->second.status = OrderStatus::FAILED;
        }
    }
    
    void print_order_report(const nlohmann::json& report) {
        std::string status = report.value("status", "unknown");
        std::string symbol = report.value("symbol", "");
        std::string side = report.value("side", "");
        std::string client_order_id = report.value("client_order_id", "");
        std::string exchange_order_id = report.value("exchange_order_id", "");
        std::string error_msg = report.value("error_msg", "");
        std::string error_code = report.value("error_code", "");
        double filled_qty = report.value("filled_quantity", 0.0);
        double filled_price = report.value("filled_price", 0.0);
        double quantity = report.value("quantity", 0.0);
        double price = report.value("price", 0.0);
        
        if (status == "accepted") {
            log_info("[下单成功] ✓ " + symbol + " " + side + 
                    " | 交易所订单: " + exchange_order_id +
                    " | 客户端订单: " + client_order_id);
        }
        else if (status == "rejected") {
            std::string err_info = error_msg.empty() ? "未知错误" : error_msg;
            log_error("[下单失败] ✗ " + symbol + " " + side + 
                     " | 原因: " + err_info +
                     " | 订单ID: " + client_order_id);
        }
        else if (status == "filled") {
            log_info("[订单成交] ✓ " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(filled_qty)) + "张 @ " + 
                    std::to_string(filled_price) + 
                    " | 订单ID: " + client_order_id);
        } 
        else if (status == "partially_filled" || status == "partial_filled") {
            log_info("[部分成交] " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(filled_qty)) + "/" + 
                    std::to_string(static_cast<int>(quantity)) + "张" +
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "cancelled" || status == "canceled") {
            log_info("[订单撤销] " + symbol + " " + side + 
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "live" || status == "pending" || status == "submitted") {
            std::string order_type = report.value("order_type", "");
            log_info("[订单挂单] " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(quantity)) + "张" +
                    (order_type == "limit" ? " @ " + std::to_string(price) : " 市价") +
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "failed" || status == "error") {
            std::string err_info = error_msg.empty() ? error_code : error_msg;
            log_error("[订单失败] ✗ " + symbol + " " + side + 
                     " | 原因: " + err_info + 
                     " | 订单ID: " + client_order_id);
        }
        else {
            log_info("[订单回报] " + symbol + " " + side + 
                    " | 状态: " + status + 
                    " | 订单ID: " + client_order_id);
        }
    }
    
    std::string generate_client_order_id() {
        static std::atomic<int> counter{0};
        return "py" + std::to_string(current_timestamp_ms() % 1000000000) + 
               std::to_string(counter.fetch_add(1));
    }
    
    static int64_t current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }
    
    static int64_t current_timestamp_ns() {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()
        ).count();
    }
    
    void log_info(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, false);
        } else {
            std::cout << "[Trading] " << msg << std::endl;
        }
    }
    
    void log_error(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, true);
        } else {
            std::cerr << "[Trading] ERROR: " << msg << std::endl;
        }
    }

private:
    std::string strategy_id_;
    
    // ZMQ sockets
    zmq::socket_t* order_push_ = nullptr;
    zmq::socket_t* report_sub_ = nullptr;
    
    // 订单管理
    std::map<std::string, OrderInfo> active_orders_;
    mutable std::mutex orders_mutex_;
    
    // 回调
    OrderReportCallback order_report_callback_;
    LogCallback log_callback_;
    
    // 统计
    std::atomic<int64_t> order_count_;
    std::atomic<int64_t> report_count_;
};

} // namespace trading

