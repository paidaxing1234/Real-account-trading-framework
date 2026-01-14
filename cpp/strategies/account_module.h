/**
 * @file account_module.h
 * @brief 账户模块 - 登录、查看余额、持仓等账户操作
 * 
 * 功能:
 * 1. 账户注册/注销
 * 2. 账户余额查询
 * 3. 账户持仓查询
 * 4. 账户更新回报处理
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <map>
#include <vector>
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
// 账户数据结构
// ============================================================

/**
 * @brief 币种余额信息
 */
struct BalanceInfo {
    std::string currency;      // 币种（如 USDT, BTC）
    double available;          // 可用余额
    double frozen;             // 冻结余额
    double total;              // 总余额
    double usd_value;          // USD估值
    int64_t update_time;       // 更新时间
    
    BalanceInfo() : available(0), frozen(0), total(0), usd_value(0), update_time(0) {}
};

/**
 * @brief 持仓信息
 */
struct PositionInfo {
    std::string symbol;        // 交易对
    std::string pos_side;      // 持仓方向: "net", "long", "short"
    double quantity;           // 持仓数量（张）
    double avg_price;          // 持仓均价
    double mark_price;         // 标记价格
    double unrealized_pnl;     // 未实现盈亏
    double realized_pnl;       // 已实现盈亏
    double margin;             // 保证金
    double leverage;           // 杠杆倍数
    double liquidation_price;  // 强平价格
    int64_t update_time;       // 更新时间
    
    PositionInfo() : quantity(0), avg_price(0), mark_price(0), 
                     unrealized_pnl(0), realized_pnl(0), margin(0),
                     leverage(1), liquidation_price(0), update_time(0) {}
};

/**
 * @brief 账户概要
 */
struct AccountSummary {
    double total_equity;        // 总权益（USD）
    double available_balance;   // 可用余额（USD）
    double frozen_balance;      // 冻结余额（USD）
    double unrealized_pnl;      // 总未实现盈亏
    double margin_ratio;        // 保证金率
    int64_t update_time;        // 更新时间
    
    AccountSummary() : total_equity(0), available_balance(0), 
                       frozen_balance(0), unrealized_pnl(0), 
                       margin_ratio(0), update_time(0) {}
};


// ============================================================
// 账户模块
// ============================================================

/**
 * @brief 账户模块
 * 
 * 负责：
 * - 账户注册/注销
 * - 查询余额和持仓
 * - 处理账户更新回报
 */
class AccountModule {
public:
    // 注册结果回调
    using RegisterCallback = std::function<void(bool success, const std::string& error_msg)>;
    // 账户更新回调
    using AccountUpdateCallback = std::function<void(const AccountSummary&)>;
    // 持仓更新回调
    using PositionUpdateCallback = std::function<void(const PositionInfo&)>;
    // 余额更新回调
    using BalanceUpdateCallback = std::function<void(const BalanceInfo&)>;
    // 日志回调
    using LogCallback = std::function<void(const std::string&, bool)>;
    
    explicit AccountModule()
        : account_registered_(false) {}
    
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
    
    // ==================== 账户注册/注销 ====================

    /**
     * @brief 注册 OKX 账户
     */
    bool register_account(const std::string& api_key,
                         const std::string& secret_key,
                         const std::string& passphrase,
                         bool is_testnet = true) {
        if (!order_push_) {
            log_error("订单通道未连接");
            return false;
        }

        api_key_ = api_key;
        secret_key_ = secret_key;
        passphrase_ = passphrase;
        is_testnet_ = is_testnet;
        exchange_ = "okx";

        nlohmann::json request = {
            {"type", "register_account"},
            {"exchange", "okx"},
            {"strategy_id", strategy_id_},
            {"api_key", api_key},
            {"secret_key", secret_key},
            {"passphrase", passphrase},
            {"is_testnet", is_testnet},
            {"timestamp", current_timestamp_ms()}
        };

        try {
            std::string msg = request.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            log_info("已发送 OKX 账户注册请求");
            return true;
        } catch (const std::exception& e) {
            log_error("发送注册请求失败: " + std::string(e.what()));
            return false;
        }
    }

    /**
     * @brief 注册 Binance 账户
     * @param api_key Binance API Key
     * @param secret_key Binance Secret Key
     * @param is_testnet 是否使用测试网
     * @return 是否发送成功
     */
    bool register_binance_account(const std::string& api_key,
                                  const std::string& secret_key,
                                  bool is_testnet = true) {
        if (!order_push_) {
            log_error("订单通道未连接");
            return false;
        }

        api_key_ = api_key;
        secret_key_ = secret_key;
        passphrase_ = "";  // Binance 不需要 passphrase
        is_testnet_ = is_testnet;
        exchange_ = "binance";

        nlohmann::json request = {
            {"type", "register_account"},
            {"exchange", "binance"},
            {"strategy_id", strategy_id_},
            {"api_key", api_key},
            {"secret_key", secret_key},
            {"is_testnet", is_testnet},
            {"timestamp", current_timestamp_ms()}
        };

        try {
            std::string msg = request.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            log_info("已发送 Binance 账户注册请求");
            return true;
        } catch (const std::exception& e) {
            log_error("发送注册请求失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 注销账户
     */
    bool unregister_account() {
        if (!order_push_) return false;
        
        nlohmann::json request = {
            {"type", "unregister_account"},
            {"strategy_id", strategy_id_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            account_registered_ = false;
            log_info("已发送账户注销请求");
            return true;
        } catch (const std::exception& e) {
            log_error("发送注销请求失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 请求刷新账户信息
     */
    bool refresh_account() {
        if (!order_push_) return false;

        nlohmann::json request = {
            {"type", "query_account"},
            {"strategy_id", strategy_id_},
            {"exchange", exchange_},
            {"timestamp", current_timestamp_ms()}
        };

        try {
            std::string msg = request.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }

    /**
     * @brief 请求刷新持仓信息
     */
    bool refresh_positions() {
        if (!order_push_) return false;

        nlohmann::json request = {
            {"type", "query_positions"},
            {"strategy_id", strategy_id_},
            {"exchange", exchange_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            order_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    
    // ==================== 账户回报处理 ====================
    
    /**
     * @brief 处理账户回报（主循环调用）
     * @return 是否有账户相关回报
     */
    bool process_account_reports() {
        if (!report_sub_) return false;
        
        bool has_account_report = false;
        zmq::message_t message;
        
        while (report_sub_->recv(message, zmq::recv_flags::dontwait)) {
            try {
                std::string msg_str(static_cast<char*>(message.data()), message.size());
                auto report = nlohmann::json::parse(msg_str);
                
                std::string report_type = report.value("type", "");
                
                // 处理注册回报
                if (report_type == "register_report") {
                    handle_register_report(report);
                    has_account_report = true;
                }
                // 处理注销回报
                else if (report_type == "unregister_report") {
                    handle_unregister_report(report);
                    has_account_report = true;
                }
                // 处理账户更新
                else if (report_type == "account_update") {
                    handle_account_update(report);
                    has_account_report = true;
                }
                // 处理持仓更新
                else if (report_type == "position_update") {
                    handle_position_update(report);
                    has_account_report = true;
                }
                // 处理余额更新
                else if (report_type == "balance_update") {
                    handle_balance_update(report);
                    has_account_report = true;
                }
                
            } catch (const std::exception&) {
                // 忽略解析错误
            }
        }
        
        return has_account_report;
    }
    
    // ==================== 查询接口 ====================
    
    /**
     * @brief 获取账户概要
     */
    AccountSummary get_account_summary() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        return account_summary_;
    }
    
    /**
     * @brief 获取某币种余额
     */
    bool get_balance(const std::string& currency, BalanceInfo& balance) const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        auto it = balances_.find(currency);
        if (it == balances_.end()) return false;
        balance = it->second;
        return true;
    }
    
    /**
     * @brief 获取所有余额
     */
    std::vector<BalanceInfo> get_all_balances() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        std::vector<BalanceInfo> result;
        for (const auto& pair : balances_) {
            result.push_back(pair.second);
        }
        return result;
    }
    
    /**
     * @brief 获取某交易对持仓
     */
    bool get_position(const std::string& symbol, PositionInfo& position, 
                     const std::string& pos_side = "net") const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        std::string key = symbol + "_" + pos_side;
        auto it = positions_.find(key);
        if (it == positions_.end()) return false;
        position = it->second;
        return true;
    }
    
    /**
     * @brief 获取所有持仓
     */
    std::vector<PositionInfo> get_all_positions() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        std::vector<PositionInfo> result;
        for (const auto& pair : positions_) {
            result.push_back(pair.second);
        }
        return result;
    }
    
    /**
     * @brief 获取有效持仓（数量不为0）
     */
    std::vector<PositionInfo> get_active_positions() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        std::vector<PositionInfo> result;
        for (const auto& pair : positions_) {
            if (pair.second.quantity != 0) {
                result.push_back(pair.second);
            }
        }
        return result;
    }
    
    /**
     * @brief 获取 USDT 可用余额
     */
    double get_usdt_available() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        auto it = balances_.find("USDT");
        if (it == balances_.end()) return 0;
        return it->second.available;
    }
    
    /**
     * @brief 获取总权益（USD）
     */
    double get_total_equity() const {
        std::lock_guard<std::mutex> lock(account_mutex_);
        return account_summary_.total_equity;
    }
    
    // ==================== 状态查询 ====================
    
    bool is_registered() const { return account_registered_.load(); }
    bool is_testnet() const { return is_testnet_; }
    
    // ==================== 回调设置 ====================
    
    void set_register_callback(RegisterCallback callback) {
        register_callback_ = std::move(callback);
    }
    
    void set_account_update_callback(AccountUpdateCallback callback) {
        account_update_callback_ = std::move(callback);
    }
    
    void set_position_update_callback(PositionUpdateCallback callback) {
        position_update_callback_ = std::move(callback);
    }
    
    void set_balance_update_callback(BalanceUpdateCallback callback) {
        balance_update_callback_ = std::move(callback);
    }

private:
    void handle_register_report(const nlohmann::json& report) {
        std::string status = report.value("status", "");
        
        if (status == "registered") {
            account_registered_ = true;
            log_info("[账户注册] ✓ 注册成功");
            if (register_callback_) {
                register_callback_(true, "");
            }
        } else {
            std::string error_msg = report.value("error_msg", "未知错误");
            log_error("[账户注册] ✗ 失败: " + error_msg);
            if (register_callback_) {
                register_callback_(false, error_msg);
            }
        }
    }
    
    void handle_unregister_report(const nlohmann::json& report) {
        std::string status = report.value("status", "");
        
        if (status == "unregistered") {
            account_registered_ = false;
            log_info("[账户注销] ✓ 已注销");
        }
    }
    
    void handle_account_update(const nlohmann::json& report) {
        std::lock_guard<std::mutex> lock(account_mutex_);
        
        if (report.contains("data")) {
            auto& data = report["data"];
            account_summary_.total_equity = std::stod(data.value("totalEq", "0"));
            account_summary_.margin_ratio = std::stod(data.value("mgnRatio", "0"));
            account_summary_.update_time = current_timestamp_ms();
            
            // 解析各币种余额
            if (data.contains("details") && data["details"].is_array()) {
                for (const auto& detail : data["details"]) {
                    BalanceInfo balance;
                    balance.currency = detail.value("ccy", "");
                    balance.available = std::stod(detail.value("availBal", "0"));
                    balance.frozen = std::stod(detail.value("frozenBal", "0"));
                    balance.total = std::stod(detail.value("eq", "0"));
                    balance.usd_value = std::stod(detail.value("eqUsd", "0"));
                    balance.update_time = current_timestamp_ms();
                    
                    if (!balance.currency.empty()) {
                        balances_[balance.currency] = balance;
                        
                        if (balance_update_callback_) {
                            balance_update_callback_(balance);
                        }
                    }
                }
            }
        }
        
        if (account_update_callback_) {
            account_update_callback_(account_summary_);
        }
    }
    
    void handle_position_update(const nlohmann::json& report) {
        if (!report.contains("data")) return;
        
        std::lock_guard<std::mutex> lock(account_mutex_);
        
        for (const auto& pos_data : report["data"]) {
            PositionInfo position;
            position.symbol = pos_data.value("instId", "");
            position.pos_side = pos_data.value("posSide", "net");
            position.quantity = std::stod(pos_data.value("pos", "0"));
            position.avg_price = std::stod(pos_data.value("avgPx", "0"));
            position.mark_price = std::stod(pos_data.value("markPx", "0"));
            position.unrealized_pnl = std::stod(pos_data.value("upl", "0"));
            position.realized_pnl = std::stod(pos_data.value("realizedPnl", "0"));
            position.margin = std::stod(pos_data.value("margin", "0"));
            position.leverage = std::stod(pos_data.value("lever", "1"));
            position.liquidation_price = std::stod(pos_data.value("liqPx", "0"));
            position.update_time = current_timestamp_ms();
            
            if (!position.symbol.empty()) {
                std::string key = position.symbol + "_" + position.pos_side;
                positions_[key] = position;
                
                if (position_update_callback_) {
                    position_update_callback_(position);
                }
            }
        }
    }
    
    void handle_balance_update(const nlohmann::json& report) {
        if (!report.contains("data")) return;
        
        std::lock_guard<std::mutex> lock(account_mutex_);
        
        for (const auto& bal_data : report["data"]) {
            BalanceInfo balance;
            balance.currency = bal_data.value("ccy", "");
            balance.available = std::stod(bal_data.value("availBal", "0"));
            balance.frozen = std::stod(bal_data.value("frozenBal", "0"));
            balance.total = std::stod(bal_data.value("cashBal", "0"));
            balance.update_time = current_timestamp_ms();
            
            if (!balance.currency.empty()) {
                balances_[balance.currency] = balance;
                
                if (balance_update_callback_) {
                    balance_update_callback_(balance);
                }
            }
        }
    }
    
    static int64_t current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }
    
    void log_info(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, false);
        } else {
            std::cout << "[Account] " << msg << std::endl;
        }
    }
    
    void log_error(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, true);
        } else {
            std::cerr << "[Account] ERROR: " << msg << std::endl;
        }
    }

private:
    std::string strategy_id_;

    // 账户凭证
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    std::string exchange_ = "okx";  // "okx" or "binance"
    bool is_testnet_ = true;
    
    // 状态
    std::atomic<bool> account_registered_;
    
    // ZMQ sockets
    zmq::socket_t* order_push_ = nullptr;
    zmq::socket_t* report_sub_ = nullptr;
    
    // 账户数据
    AccountSummary account_summary_;
    std::map<std::string, BalanceInfo> balances_;      // currency -> balance
    std::map<std::string, PositionInfo> positions_;    // symbol_posside -> position
    mutable std::mutex account_mutex_;
    
    // 回调
    RegisterCallback register_callback_;
    AccountUpdateCallback account_update_callback_;
    PositionUpdateCallback position_update_callback_;
    BalanceUpdateCallback balance_update_callback_;
    LogCallback log_callback_;
};

} // namespace trading

