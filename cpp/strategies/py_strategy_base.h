/**
 * @file py_strategy_base.h
 * @brief Python 策略基类 - 模块化设计
 * 
 * 组合三个独立模块：
 * 1. MarketDataModule - 行情数据（K线、trades等）
 * 2. TradingModule - 交易操作（下单、撤单）
 * 3. AccountModule - 账户操作（登录、余额、持仓）
 * 
 * 通过 pybind11 暴露给 Python，策略继承此类实现业务逻辑
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <memory>
#include <atomic>
#include <thread>
#include <chrono>
#include <iostream>

// ZMQ
#include <zmq.hpp>

// JSON
#include <nlohmann/json.hpp>

// 三个独立模块
#include "market_data_module.h"
#include "trading_module.h"
#include "account_module.h"

namespace trading {

/**
 * @brief Python 策略基类
 * 
 * 通过组合三个模块提供完整的策略基础设施：
 * - 行情数据：订阅、接收、存储K线/trades等
 * - 交易操作：下单、撤单、查询订单
 * - 账户管理：注册、查询余额/持仓
 */
class PyStrategyBase {
public:
    /**
     * @brief 构造函数
     * @param strategy_id 策略ID
     * @param max_kline_bars K线最大存储数量（默认 7200 = 2小时1s K线）
     */
    explicit PyStrategyBase(const std::string& strategy_id, size_t max_kline_bars = 7200)
        : strategy_id_(strategy_id)
        , running_(false)
        , market_data_(max_kline_bars)
        , start_time_(std::chrono::steady_clock::now()) {
        
        // 设置策略ID
        trading_.set_strategy_id(strategy_id);
        account_.set_strategy_id(strategy_id);
        
        // 设置日志回调
        auto log_cb = [this](const std::string& msg, bool is_error) {
            if (is_error) {
                log_error(msg);
            } else {
                log_info(msg);
            }
        };
        trading_.set_log_callback(log_cb);
        account_.set_log_callback(log_cb);
    }
    
    virtual ~PyStrategyBase() {
        stop();
    }
    
    // ============================================================
    // 连接管理
    // ============================================================
    
    /**
     * @brief 连接到实盘服务器
     */
    bool connect() {
        try {
            context_ = std::make_unique<zmq::context_t>(1);
            
            // 行情订阅 (SUB)
            market_sub_ = std::make_unique<zmq::socket_t>(*context_, zmq::socket_type::sub);
            market_sub_->connect(MARKET_DATA_IPC);
            market_sub_->set(zmq::sockopt::subscribe, "");
            market_sub_->set(zmq::sockopt::rcvtimeo, 100);
            
            // 订单发送 (PUSH)
            order_push_ = std::make_unique<zmq::socket_t>(*context_, zmq::socket_type::push);
            order_push_->connect(ORDER_IPC);
            
            // 回报订阅 (SUB)
            report_sub_ = std::make_unique<zmq::socket_t>(*context_, zmq::socket_type::sub);
            report_sub_->connect(REPORT_IPC);
            report_sub_->set(zmq::sockopt::subscribe, "");
            report_sub_->set(zmq::sockopt::rcvtimeo, 100);
            
            // 订阅管理 (PUSH)
            subscribe_push_ = std::make_unique<zmq::socket_t>(*context_, zmq::socket_type::push);
            subscribe_push_->connect(SUBSCRIBE_IPC);
            
            // 将 socket 传递给各模块
            market_data_.set_sockets(market_sub_.get(), subscribe_push_.get());
            trading_.set_sockets(order_push_.get(), report_sub_.get());
            account_.set_sockets(order_push_.get(), report_sub_.get());
            
            running_ = true;
            log_info("已连接到实盘服务器");
            return true;
            
        } catch (const std::exception& e) {
            log_error("连接失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 断开连接
     */
    void disconnect() {
        running_ = false;
        
        if (account_.is_registered()) {
            account_.unregister_account();
        }
        
        if (market_sub_) market_sub_->close();
        if (order_push_) order_push_->close();
        if (report_sub_) report_sub_->close();
        if (subscribe_push_) subscribe_push_->close();
    }
    
    // ============================================================
    // 行情数据模块 API
    // ============================================================
    
    // --- 订阅管理 ---
    
    bool subscribe_kline(const std::string& symbol, const std::string& interval) {
        bool result = market_data_.subscribe_kline(symbol, interval, strategy_id_);
        if (result) {
            log_info("已订阅 " + symbol + " " + interval + " K线");
        }
        return result;
    }
    
    bool unsubscribe_kline(const std::string& symbol, const std::string& interval) {
        return market_data_.unsubscribe_kline(symbol, interval, strategy_id_);
    }
    
    bool subscribe_trades(const std::string& symbol) {
        bool result = market_data_.subscribe_trades(symbol, strategy_id_);
        if (result) {
            log_info("已订阅 " + symbol + " trades");
        }
        return result;
    }
    
    bool unsubscribe_trades(const std::string& symbol) {
        return market_data_.unsubscribe_trades(symbol, strategy_id_);
    }
    
    // --- 数据查询 ---
    
    std::vector<KlineBar> get_klines(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_klines(symbol, interval);
    }
    
    std::vector<double> get_closes(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_closes(symbol, interval);
    }
    
    std::vector<double> get_opens(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_opens(symbol, interval);
    }
    
    std::vector<double> get_highs(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_highs(symbol, interval);
    }
    
    std::vector<double> get_lows(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_lows(symbol, interval);
    }
    
    std::vector<double> get_volumes(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_volumes(symbol, interval);
    }
    
    std::vector<KlineBar> get_recent_klines(const std::string& symbol, 
                                            const std::string& interval, 
                                            size_t n) const {
        return market_data_.get_recent_klines(symbol, interval, n);
    }
    
    bool get_last_kline(const std::string& symbol, const std::string& interval, KlineBar& bar) const {
        return market_data_.get_last_kline(symbol, interval, bar);
    }
    
    size_t get_kline_count(const std::string& symbol, const std::string& interval) const {
        return market_data_.get_kline_count(symbol, interval);
    }
    
    // ============================================================
    // 交易模块 API
    // ============================================================
    
    // --- 下单接口 ---
    
    std::string send_swap_market_order(const std::string& symbol,
                                       const std::string& side,
                                       int quantity,
                                       const std::string& pos_side = "net") {
        return trading_.send_swap_market_order(symbol, side, quantity, pos_side);
    }
    
    std::string send_swap_limit_order(const std::string& symbol,
                                      const std::string& side,
                                      int quantity,
                                      double price,
                                      const std::string& pos_side = "net") {
        return trading_.send_swap_limit_order(symbol, side, quantity, price, pos_side);
    }
    
    // --- 撤单接口 ---
    
    bool cancel_order(const std::string& symbol, const std::string& client_order_id) {
        return trading_.cancel_order(symbol, client_order_id);
    }
    
    bool cancel_all_orders(const std::string& symbol = "") {
        return trading_.cancel_all_orders(symbol);
    }
    
    // --- 订单查询 ---
    
    std::vector<OrderInfo> get_active_orders() const {
        return trading_.get_active_orders();
    }
    
    size_t pending_order_count() const {
        return trading_.pending_order_count();
    }
    
    // ============================================================
    // 账户模块 API
    // ============================================================
    
    // --- 注册/注销 ---
    
    bool register_account(const std::string& api_key, 
                         const std::string& secret_key,
                         const std::string& passphrase,
                         bool is_testnet = true) {
        return account_.register_account(api_key, secret_key, passphrase, is_testnet);
    }
    
    bool unregister_account() {
        return account_.unregister_account();
    }
    
    bool is_account_registered() const {
        return account_.is_registered();
    }
    
    // --- 余额查询 ---
    
    double get_usdt_available() const {
        return account_.get_usdt_available();
    }
    
    double get_total_equity() const {
        return account_.get_total_equity();
    }
    
    std::vector<BalanceInfo> get_all_balances() const {
        return account_.get_all_balances();
    }
    
    // --- 持仓查询 ---
    
    std::vector<PositionInfo> get_all_positions() const {
        return account_.get_all_positions();
    }
    
    std::vector<PositionInfo> get_active_positions() const {
        return account_.get_active_positions();
    }
    
    bool get_position(const std::string& symbol, PositionInfo& position,
                     const std::string& pos_side = "net") const {
        return account_.get_position(symbol, position, pos_side);
    }
    
    // --- 刷新 ---
    
    bool refresh_account() {
        return account_.refresh_account();
    }
    
    bool refresh_positions() {
        return account_.refresh_positions();
    }
    
    // ============================================================
    // 主循环
    // ============================================================
    
    /**
     * @brief 运行策略（主循环）
     */
    void run() {
        if (!connect()) {
            log_error("连接失败，无法启动策略");
            return;
        }
        
        // 设置内部回调
        setup_callbacks();
        
        // 调用策略初始化
        on_init();
        
        log_info("策略运行中...");
        
        try {
            while (running_) {
                // 处理行情数据
                market_data_.process_market_data();
                
                // 处理订单回报
                trading_.process_order_reports();
                
                // 处理账户回报
                process_account_reports();
                
                // 调用策略 tick
                on_tick();
                
                // 短暂休眠
                std::this_thread::sleep_for(std::chrono::microseconds(100));
            }
        } catch (const std::exception& e) {
            log_error("策略异常: " + std::string(e.what()));
        }
        
        // 调用策略停止
        on_stop();
        
        // 断开连接
        disconnect();
        
        // 打印总结
        print_summary();
    }
    
    /**
     * @brief 停止策略
     */
    void stop() {
        running_ = false;
    }
    
    // ============================================================
    // 虚函数（供 Python 重写）
    // ============================================================
    
    virtual void on_init() {}
    virtual void on_stop() {}
    virtual void on_tick() {}
    
    /**
     * @brief K线回调
     */
    virtual void on_kline(const std::string& symbol, const std::string& interval,
                         const KlineBar& bar) {
        (void)symbol; (void)interval; (void)bar;
    }
    
    /**
     * @brief Trades回调
     */
    virtual void on_trade(const std::string& symbol, const TradeData& trade) {
        (void)symbol; (void)trade;
    }
    
    /**
     * @brief 订单回报回调
     */
    virtual void on_order_report(const nlohmann::json& report) {
        (void)report;
    }
    
    /**
     * @brief 账户注册回报回调
     */
    virtual void on_register_report(bool success, const std::string& error_msg) {
        (void)success; (void)error_msg;
    }
    
    /**
     * @brief 持仓更新回调
     */
    virtual void on_position_update(const PositionInfo& position) {
        (void)position;
    }
    
    /**
     * @brief 余额更新回调
     */
    virtual void on_balance_update(const BalanceInfo& balance) {
        (void)balance;
    }
    
    // ============================================================
    // 日志
    // ============================================================
    
    void log_info(const std::string& msg) const {
        std::cout << "[" << strategy_id_ << "] " << msg << std::endl;
    }
    
    void log_error(const std::string& msg) const {
        std::cerr << "[" << strategy_id_ << "] ERROR: " << msg << std::endl;
    }
    
    // ============================================================
    // 属性
    // ============================================================
    
    const std::string& strategy_id() const { return strategy_id_; }
    bool is_running() const { return running_; }
    
    // 统计
    int64_t kline_count() const { return market_data_.total_kline_count(); }
    int64_t order_count() const { return trading_.total_order_count(); }
    int64_t report_count() const { return trading_.total_report_count(); }
    
    // 获取模块引用（高级用法）
    MarketDataModule& market_data() { return market_data_; }
    TradingModule& trading() { return trading_; }
    AccountModule& account() { return account_; }
    const MarketDataModule& market_data() const { return market_data_; }
    const TradingModule& trading() const { return trading_; }
    const AccountModule& account() const { return account_; }

protected:
    // IPC 地址
    static constexpr const char* MARKET_DATA_IPC = "ipc:///tmp/trading_md.ipc";
    static constexpr const char* ORDER_IPC = "ipc:///tmp/trading_order.ipc";
    static constexpr const char* REPORT_IPC = "ipc:///tmp/trading_report.ipc";
    static constexpr const char* SUBSCRIBE_IPC = "ipc:///tmp/trading_sub.ipc";

private:
    void setup_callbacks() {
        // 设置 K 线回调
        market_data_.set_kline_callback(
            [this](const std::string& symbol, const std::string& interval, const KlineBar& bar) {
                on_kline(symbol, interval, bar);
            }
        );
        
        // 设置 trades 回调
        market_data_.set_trades_callback(
            [this](const std::string& symbol, const TradeData& trade) {
                on_trade(symbol, trade);
            }
        );
        
        // 设置订单回报回调
        trading_.set_order_report_callback(
            [this](const nlohmann::json& report) {
                on_order_report(report);
            }
        );
        
        // 设置账户回调
        account_.set_register_callback(
            [this](bool success, const std::string& error_msg) {
                on_register_report(success, error_msg);
            }
        );
        
        account_.set_position_update_callback(
            [this](const PositionInfo& position) {
                on_position_update(position);
            }
        );
        
        account_.set_balance_update_callback(
            [this](const BalanceInfo& balance) {
                on_balance_update(balance);
            }
        );
    }
    
    /**
     * @brief 处理账户回报（需要单独处理，因为共享 report_sub_）
     */
    void process_account_reports() {
        if (!report_sub_) return;
        
        zmq::message_t message;
        while (report_sub_->recv(message, zmq::recv_flags::dontwait)) {
            try {
                std::string msg_str(static_cast<char*>(message.data()), message.size());
                auto report = nlohmann::json::parse(msg_str);
                
                std::string report_type = report.value("type", "");
                
                // 分发给各模块处理
                if (report_type == "order_update" || 
                    report_type == "order_report" ||
                    report_type == "order_response") {
                    // 订单回报 - 手动处理（因为 trading_ 已经处理过了）
                }
                else if (report_type == "register_report" ||
                         report_type == "unregister_report") {
                    handle_register_report(report);
                }
                else if (report_type == "account_update") {
                    handle_account_update(report);
                }
                else if (report_type == "position_update") {
                    handle_position_update(report);
                }
                else if (report_type == "balance_update") {
                    handle_balance_update(report);
                }
                
            } catch (const std::exception&) {
                // 忽略解析错误
            }
        }
    }
    
    void handle_register_report(const nlohmann::json& report) {
        std::string status = report.value("status", "");
        
        if (status == "registered") {
            log_info("[账户注册] ✓ 注册成功");
            on_register_report(true, "");
        } else if (status == "unregistered") {
            log_info("[账户注销] ✓ 已注销");
        } else {
            std::string error_msg = report.value("error_msg", "未知错误");
            log_error("[账户注册] ✗ 失败: " + error_msg);
            on_register_report(false, error_msg);
        }
    }
    
    void handle_account_update(const nlohmann::json& report) {
        // 静默处理账户更新，不打印日志
        (void)report;
    }
    
    void handle_position_update(const nlohmann::json& report) {
        if (!report.contains("data")) return;
        
        for (const auto& pos_data : report["data"]) {
            PositionInfo position;
            position.symbol = pos_data.value("instId", "");
            position.pos_side = pos_data.value("posSide", "net");
            position.quantity = std::stod(pos_data.value("pos", "0"));
            position.avg_price = std::stod(pos_data.value("avgPx", "0"));
            position.unrealized_pnl = std::stod(pos_data.value("upl", "0"));
            
            if (!position.symbol.empty()) {
                on_position_update(position);
            }
        }
    }
    
    void handle_balance_update(const nlohmann::json& report) {
        if (!report.contains("data")) return;
        
        for (const auto& bal_data : report["data"]) {
            BalanceInfo balance;
            balance.currency = bal_data.value("ccy", "");
            balance.available = std::stod(bal_data.value("availBal", "0"));
            balance.frozen = std::stod(bal_data.value("frozenBal", "0"));
            balance.total = std::stod(bal_data.value("cashBal", "0"));
            
            if (!balance.currency.empty()) {
                on_balance_update(balance);
            }
        }
    }
    
    void print_summary() {
        auto end_time = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(end_time - start_time_).count();
        
        std::cout << "\n";
        std::cout << "================================================\n";
        std::cout << "              策略运行总结\n";
        std::cout << "================================================\n";
        std::cout << "  策略ID:       " << strategy_id_ << "\n";
        std::cout << "  运行时间:     " << elapsed << " 秒\n";
        std::cout << "  接收K线:      " << kline_count() << " 根\n";
        std::cout << "  发送订单:     " << order_count() << " 个\n";
        std::cout << "  收到回报:     " << report_count() << " 个\n";
        std::cout << "================================================\n";
    }

private:
    // 策略配置
    std::string strategy_id_;
    std::atomic<bool> running_;
    
    // ZMQ
    std::unique_ptr<zmq::context_t> context_;
    std::unique_ptr<zmq::socket_t> market_sub_;
    std::unique_ptr<zmq::socket_t> order_push_;
    std::unique_ptr<zmq::socket_t> report_sub_;
    std::unique_ptr<zmq::socket_t> subscribe_push_;
    
    // 三个独立模块
    MarketDataModule market_data_;
    TradingModule trading_;
    AccountModule account_;
    
    // 时间
    std::chrono::steady_clock::time_point start_time_;
};

} // namespace trading
