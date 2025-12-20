/**
 * @file py_strategy_base.h
 * @brief Python 策略基类 - 通过 pybind11 暴露给 Python
 * 
 * 功能:
 * 1. ZMQ 通信封装（连接实盘服务器）
 * 2. 账户注册/注销
 * 3. K线数据存储（2小时内，内存存储）
 * 4. 下单接口（合约）
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <vector>
#include <map>
#include <deque>
#include <memory>
#include <functional>
#include <atomic>
#include <mutex>
#include <thread>
#include <chrono>
#include <iostream>

// ZMQ 头文件
#include <zmq.hpp>

// JSON
#include <nlohmann/json.hpp>

namespace trading {

// ============================================================
// K线数据结构
// ============================================================

/**
 * @brief 单根 K 线数据
 */
struct KlineBar {
    int64_t timestamp;     // 毫秒时间戳
    double open;
    double high;
    double low;
    double close;
    double volume;
    
    KlineBar() : timestamp(0), open(0), high(0), low(0), close(0), volume(0) {}
    KlineBar(int64_t ts, double o, double h, double l, double c, double v)
        : timestamp(ts), open(o), high(h), low(l), close(c), volume(v) {}
};

/**
 * @brief 单个币种的 K 线缓冲区（环形缓冲区）
 */
class KlineBuffer {
public:
    explicit KlineBuffer(size_t max_bars = 7200)  // 默认存储 2 小时 1s K线
        : max_bars_(max_bars)
        , data_(max_bars)
        , head_(0)
        , size_(0) {}
    
    /**
     * @brief 更新 K 线数据
     * @return true 如果追加了新 K 线, false 如果更新了现有 K 线
     */
    bool update(int64_t timestamp, double open, double high, 
                double low, double close, double volume) {
        std::lock_guard<std::mutex> lock(mutex_);
        
        if (size_ == 0) {
            // 第一根 K 线
            data_[0] = KlineBar(timestamp, open, high, low, close, volume);
            size_ = 1;
            return true;
        }
        
        // 获取最后一根 K 线索引
        size_t last_idx = (head_ + size_ - 1) % max_bars_;
        
        if (data_[last_idx].timestamp == timestamp) {
            // 更新当前 K 线
            data_[last_idx] = KlineBar(timestamp, open, high, low, close, volume);
            return false;
        } else {
            // 追加新 K 线
            if (size_ < max_bars_) {
                size_t new_idx = (head_ + size_) % max_bars_;
                data_[new_idx] = KlineBar(timestamp, open, high, low, close, volume);
                size_++;
            } else {
                // 缓冲区已满，覆盖最旧的
                data_[head_] = KlineBar(timestamp, open, high, low, close, volume);
                head_ = (head_ + 1) % max_bars_;
            }
            return true;
        }
    }
    
    /**
     * @brief 获取所有 K 线（按时间顺序）
     */
    std::vector<KlineBar> get_all() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<KlineBar> result;
        result.reserve(size_);
        
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_]);
        }
        return result;
    }
    
    /**
     * @brief 获取收盘价数组
     */
    std::vector<double> get_closes() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].close);
        }
        return result;
    }
    
    /**
     * @brief 获取时间戳数组
     */
    std::vector<int64_t> get_timestamps() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<int64_t> result;
        result.reserve(size_);
        
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].timestamp);
        }
        return result;
    }
    
    /**
     * @brief 获取最后一根 K 线
     */
    bool get_last(KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (size_ == 0) return false;
        bar = data_[(head_ + size_ - 1) % max_bars_];
        return true;
    }
    
    /**
     * @brief 获取指定索引的 K 线（0 = 最旧, size-1 = 最新）
     */
    bool get_at(size_t index, KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (index >= size_) return false;
        bar = data_[(head_ + index) % max_bars_];
        return true;
    }
    
    /**
     * @brief 获取最近 n 根 K 线
     */
    std::vector<KlineBar> get_recent(size_t n) const {
        std::lock_guard<std::mutex> lock(mutex_);
        n = std::min(n, size_);
        std::vector<KlineBar> result;
        result.reserve(n);
        
        for (size_t i = size_ - n; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_]);
        }
        return result;
    }
    
    size_t size() const { 
        std::lock_guard<std::mutex> lock(mutex_);
        return size_; 
    }
    
    size_t max_size() const { return max_bars_; }

private:
    size_t max_bars_;
    std::vector<KlineBar> data_;
    size_t head_;
    size_t size_;
    mutable std::mutex mutex_;
};


// ============================================================
// K线管理器
// ============================================================

/**
 * @brief 多币种 K 线管理器
 */
class KlineManager {
public:
    /**
     * @param max_bars 每个币种保留的最大 K 线数量
     * @param interval K 线周期 ("1s", "1m", etc.)
     */
    explicit KlineManager(size_t max_bars = 7200, const std::string& interval = "1s")
        : max_bars_(max_bars)
        , interval_(interval) {
        // 计算间隔毫秒数
        if (interval == "1s") interval_ms_ = 1000;
        else if (interval == "1m") interval_ms_ = 60000;
        else if (interval == "3m") interval_ms_ = 180000;
        else if (interval == "5m") interval_ms_ = 300000;
        else if (interval == "15m") interval_ms_ = 900000;
        else if (interval == "30m") interval_ms_ = 1800000;
        else if (interval == "1H") interval_ms_ = 3600000;
        else if (interval == "4H") interval_ms_ = 14400000;
        else if (interval == "1D") interval_ms_ = 86400000;
        else interval_ms_ = 60000;  // 默认 1 分钟
    }
    
    /**
     * @brief 更新 K 线数据
     */
    bool update(const std::string& symbol, int64_t timestamp,
                double open, double high, double low, double close, double volume) {
        std::lock_guard<std::mutex> lock(mutex_);
        
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) {
            buffers_[symbol] = std::make_unique<KlineBuffer>(max_bars_);
            it = buffers_.find(symbol);
        }
        return it->second->update(timestamp, open, high, low, close, volume);
    }
    
    /**
     * @brief 获取所有 K 线
     */
    std::vector<KlineBar> get_all(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_all();
    }
    
    /**
     * @brief 获取收盘价数组
     */
    std::vector<double> get_closes(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_closes();
    }
    
    /**
     * @brief 获取时间戳数组
     */
    std::vector<int64_t> get_timestamps(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_timestamps();
    }
    
    /**
     * @brief 获取最后一根 K 线
     */
    bool get_last(const std::string& symbol, KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return false;
        return it->second->get_last(bar);
    }
    
    /**
     * @brief 获取最近 n 根 K 线
     */
    std::vector<KlineBar> get_recent(const std::string& symbol, size_t n) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_recent(n);
    }
    
    /**
     * @brief 获取某币种当前存储的 K 线数量
     */
    size_t get_bar_count(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return 0;
        return it->second->size();
    }
    
    /**
     * @brief 获取所有已存储的币种列表
     */
    std::vector<std::string> get_symbols() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<std::string> result;
        result.reserve(buffers_.size());
        for (const auto& pair : buffers_) {
            result.push_back(pair.first);
        }
        return result;
    }
    
    const std::string& interval() const { return interval_; }
    int64_t interval_ms() const { return interval_ms_; }
    size_t max_bars() const { return max_bars_; }

private:
    size_t max_bars_;
    std::string interval_;
    int64_t interval_ms_;
    std::map<std::string, std::unique_ptr<KlineBuffer>> buffers_;
    mutable std::mutex mutex_;
};


// ============================================================
// Python 策略基类
// ============================================================

/**
 * @brief Python 策略基类
 * 
 * 通过 pybind11 暴露给 Python，策略开发者可以继承此类实现策略
 */
class PyStrategyBase {
public:
    /**
     * @brief 构造函数
     * @param strategy_id 策略ID
     * @param max_kline_bars K线最大存储数量（默认 7200，即 2 小时 1s K线）
     */
    explicit PyStrategyBase(const std::string& strategy_id, size_t max_kline_bars = 7200)
        : strategy_id_(strategy_id)
        , max_kline_bars_(max_kline_bars)
        , running_(false)
        , account_registered_(false)
        , kline_count_(0)
        , order_count_(0)
        , report_count_(0) {}
    
    virtual ~PyStrategyBase() {
        stop();
    }
    
    // ==================== 连接管理 ====================
    
    /**
     * @brief 连接到实盘服务器
     * @return true 连接成功
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
            
            running_ = true;
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
        
        if (account_registered_) {
            unregister_account();
        }
        
        if (market_sub_) market_sub_->close();
        if (order_push_) order_push_->close();
        if (report_sub_) report_sub_->close();
        if (subscribe_push_) subscribe_push_->close();
    }
    
    // ==================== 账户管理 ====================
    
    /**
     * @brief 注册账户
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
        
        nlohmann::json request = {
            {"type", "register_account"},
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
            log_info("已发送账户注册请求");
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
    
    // ==================== 订阅管理 ====================
    
    /**
     * @brief 订阅 K 线数据
     */
    bool subscribe_kline(const std::string& symbol, const std::string& interval) {
        if (!subscribe_push_) {
            log_error("订阅通道未连接");
            return false;
        }
        
        // 创建或更新 K 线管理器
        {
            std::lock_guard<std::mutex> lock(kline_managers_mutex_);
            if (kline_managers_.find(interval) == kline_managers_.end()) {
                kline_managers_[interval] = std::make_unique<KlineManager>(max_kline_bars_, interval);
            }
        }
        
        // 记录订阅
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            subscribed_klines_[symbol].insert(interval);
        }
        
        nlohmann::json request = {
            {"action", "subscribe"},
            {"channel", "kline"},
            {"symbol", symbol},
            {"interval", interval},
            {"strategy_id", strategy_id_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception& e) {
            log_error("订阅 K 线失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 取消订阅 K 线数据
     */
    bool unsubscribe_kline(const std::string& symbol, const std::string& interval) {
        if (!subscribe_push_) return false;
        
        // 移除订阅记录
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            auto it = subscribed_klines_.find(symbol);
            if (it != subscribed_klines_.end()) {
                it->second.erase(interval);
            }
        }
        
        nlohmann::json request = {
            {"action", "unsubscribe"},
            {"channel", "kline"},
            {"symbol", symbol},
            {"interval", interval},
            {"strategy_id", strategy_id_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception& e) {
            return false;
        }
    }
    
    /**
     * @brief 订阅交易数据（Trades）
     */
    bool subscribe_trades(const std::string& symbol) {
        if (!subscribe_push_) {
            log_error("订阅通道未连接");
            return false;
        }
        
        nlohmann::json request = {
            {"action", "subscribe"},
            {"channel", "trades"},
            {"symbol", symbol},
            {"strategy_id", strategy_id_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception& e) {
            log_error("订阅 Trades 失败: " + std::string(e.what()));
            return false;
        }
    }
    
    /**
     * @brief 取消订阅交易数据
     */
    bool unsubscribe_trades(const std::string& symbol) {
        if (!subscribe_push_) return false;
        
        nlohmann::json request = {
            {"action", "unsubscribe"},
            {"channel", "trades"},
            {"symbol", symbol},
            {"strategy_id", strategy_id_},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception& e) {
            return false;
        }
    }
    
    // ==================== 下单接口 ====================
    
    /**
     * @brief 发送合约订单（市价）
     * @param symbol 交易对（如 BTC-USDT-SWAP）
     * @param side "buy" 或 "sell"
     * @param quantity 张数
     * @param pos_side 持仓方向 "long" 或 "short"（双向持仓模式）
     * @return 客户端订单ID
     */
    std::string send_swap_market_order(const std::string& symbol,
                                       const std::string& side,
                                       int quantity,
                                       const std::string& pos_side = "") {
        if (!order_push_) {
            log_error("订单通道未连接");
            return "";
        }
        
        std::string client_order_id = generate_client_order_id();
        
        // 自动推断 pos_side（如果未指定）
        std::string actual_pos_side = pos_side;
        if (actual_pos_side.empty()) {
            actual_pos_side = (side == "buy") ? "long" : "short";
        }
        
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
            
            log_info("[下单] " + side + " " + std::to_string(quantity) + "张 " + symbol + 
                    " | 订单ID: " + client_order_id + " | 发送时间: " + std::to_string(send_ts) + "ns");
            
            return client_order_id;
        } catch (const std::exception& e) {
            log_error("发送订单失败: " + std::string(e.what()));
            return "";
        }
    }
    
    /**
     * @brief 发送合约订单（限价）
     */
    std::string send_swap_limit_order(const std::string& symbol,
                                      const std::string& side,
                                      int quantity,
                                      double price,
                                      const std::string& pos_side = "") {
        if (!order_push_) {
            log_error("订单通道未连接");
            return "";
        }
        
        std::string client_order_id = generate_client_order_id();
        
        std::string actual_pos_side = pos_side;
        if (actual_pos_side.empty()) {
            actual_pos_side = (side == "buy") ? "long" : "short";
        }
        
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
            
            log_info("[下单] " + side + " " + std::to_string(quantity) + "张 @ " + 
                    std::to_string(price) + " " + symbol);
            
            return client_order_id;
        } catch (const std::exception& e) {
            log_error("发送订单失败: " + std::string(e.what()));
            return "";
        }
    }
    
    // ==================== K线数据读取 ====================
    
    /**
     * @brief 获取所有 K 线数据
     */
    std::vector<KlineBar> get_klines(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_all(symbol);
    }
    
    /**
     * @brief 获取收盘价数组
     */
    std::vector<double> get_closes(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_closes(symbol);
    }
    
    /**
     * @brief 获取最近 n 根 K 线
     */
    std::vector<KlineBar> get_recent_klines(const std::string& symbol, 
                                            const std::string& interval, 
                                            size_t n) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_recent(symbol, n);
    }
    
    /**
     * @brief 获取最后一根 K 线
     */
    bool get_last_kline(const std::string& symbol, const std::string& interval, KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return false;
        return it->second->get_last(symbol, bar);
    }
    
    /**
     * @brief 获取 K 线数量
     */
    size_t get_kline_count(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return 0;
        return it->second->get_bar_count(symbol);
    }
    
    // ==================== 主循环 ====================
    
    /**
     * @brief 运行策略（主循环）
     */
    void run() {
        if (!connect()) {
            log_error("连接失败，无法启动策略");
            return;
        }
        
        // 调用策略初始化
        on_init();
        
        log_info("策略运行中...");
        start_time_ = std::chrono::steady_clock::now();
        
        try {
            while (running_) {
                // 处理行情
                process_market_data();
                
                // 处理回报
                process_reports();
                
                // 调用策略 tick
                on_tick();
                
                // 短暂休眠（避免 CPU 空转）
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
    
    // ==================== 虚函数（供 Python 重写）====================
    
    /**
     * @brief 策略初始化（在主循环开始前调用）
     */
    virtual void on_init() {}
    
    /**
     * @brief 策略停止（在主循环结束后调用）
     */
    virtual void on_stop() {}
    
    /**
     * @brief 每次循环调用（可用于定时逻辑）
     */
    virtual void on_tick() {}
    
    /**
     * @brief K线回调
     */
    virtual void on_kline(const std::string& symbol, const std::string& interval,
                         const KlineBar& bar) {
        (void)symbol; (void)interval; (void)bar;
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
    
    // ==================== 工具方法 ====================
    
    void log_info(const std::string& msg) const {
        std::cout << "[" << strategy_id_ << "] " << msg << std::endl;
    }
    
    void log_error(const std::string& msg) const {
        std::cerr << "[" << strategy_id_ << "] ERROR: " << msg << std::endl;
    }
    
    const std::string& strategy_id() const { return strategy_id_; }
    bool is_running() const { return running_; }
    bool is_account_registered() const { return account_registered_; }
    int64_t kline_count() const { return kline_count_; }
    int64_t order_count() const { return order_count_; }
    int64_t report_count() const { return report_count_; }

protected:
    // IPC 地址
    static constexpr const char* MARKET_DATA_IPC = "ipc:///tmp/trading_md.ipc";
    static constexpr const char* ORDER_IPC = "ipc:///tmp/trading_order.ipc";
    static constexpr const char* REPORT_IPC = "ipc:///tmp/trading_report.ipc";
    static constexpr const char* SUBSCRIBE_IPC = "ipc:///tmp/trading_sub.ipc";
    
    /**
     * @brief 处理行情数据
     */
    void process_market_data() {
        if (!market_sub_) return;
        
        zmq::message_t message;
        while (market_sub_->recv(message, zmq::recv_flags::dontwait)) {
            try {
                std::string msg_str(static_cast<char*>(message.data()), message.size());
                auto data = nlohmann::json::parse(msg_str);
                
                std::string msg_type = data.value("type", "");
                
                if (msg_type == "kline") {
                    handle_kline(data);
                }
                // 可以扩展处理其他类型
                
            } catch (const std::exception& e) {
                // 忽略解析错误
            }
        }
    }
    
    /**
     * @brief 处理 K 线数据
     */
    void handle_kline(const nlohmann::json& data) {
        std::string symbol = data.value("symbol", "");
        std::string interval = data.value("interval", "");
        
        if (symbol.empty() || interval.empty()) return;
        
        // 检查是否订阅了此 K 线
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            auto it = subscribed_klines_.find(symbol);
            if (it == subscribed_klines_.end() || it->second.find(interval) == it->second.end()) {
                return;  // 未订阅，忽略
            }
        }
        
        KlineBar bar;
        bar.timestamp = data.value("timestamp", 0LL);
        bar.open = data.value("open", 0.0);
        bar.high = data.value("high", 0.0);
        bar.low = data.value("low", 0.0);
        bar.close = data.value("close", 0.0);
        bar.volume = data.value("volume", 0.0);
        
        // 存储到 K 线管理器
        {
            std::lock_guard<std::mutex> lock(kline_managers_mutex_);
            auto it = kline_managers_.find(interval);
            if (it != kline_managers_.end()) {
                bool is_new = it->second->update(symbol, bar.timestamp, bar.open, bar.high, 
                                                  bar.low, bar.close, bar.volume);
                if (is_new) {
                    kline_count_++;
                }
            }
        }
        
        // 调用回调
        on_kline(symbol, interval, bar);
    }
    
    /**
     * @brief 处理回报
     */
    void process_reports() {
        if (!report_sub_) return;
        
        zmq::message_t message;
        while (report_sub_->recv(message, zmq::recv_flags::dontwait)) {
            try {
                std::string msg_str(static_cast<char*>(message.data()), message.size());
                auto report = nlohmann::json::parse(msg_str);
                
                report_count_++;
                
                std::string report_type = report.value("type", "");
                std::string status = report.value("status", "");
                
                // 处理账户注册回报
                if (report_type == "register_report") {
                    if (status == "registered") {
                        account_registered_ = true;
                        log_info("[账户注册] ✓ 注册成功");
                        on_register_report(true, "");
                    } else {
                        std::string error_msg = report.value("error_msg", "未知错误");
                        log_error("[账户注册] ✗ 失败: " + error_msg);
                        on_register_report(false, error_msg);
                    }
                    continue;
                }
                
                // 处理账户注销回报
                if (report_type == "unregister_report") {
                    if (status == "unregistered") {
                        account_registered_ = false;
                        log_info("[账户注销] ✓ 已注销");
                    }
                    continue;
                }
                
                // 忽略非订单类型的回报（账户更新、持仓更新等）
                if (report_type == "account_update" || 
                    report_type == "position_update" ||
                    report_type == "balance_update") {
                    continue;  // 静默忽略
                }
                
                // 只处理订单相关回报
                if (report_type == "order_update" || report_type == "order_report" ||
                    report_type == "order_response") {
                    // 打印订单回报详情
                    print_order_report(report);
                    
                    // 调用用户回调
                    on_order_report(report);
                }
                
            } catch (const std::exception& e) {
                log_error("[回报解析] 错误: " + std::string(e.what()));
            }
        }
    }
    
    /**
     * @brief 打印订单回报详情
     */
    void print_order_report(const nlohmann::json& report) {
        std::string report_type = report.value("type", "unknown");
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
        
        // 根据状态选择不同的输出格式
        if (status == "accepted") {
            // 下单成功（已提交到交易所）
            log_info("[下单成功] ✓ " + symbol + " " + side + 
                    " | 交易所订单: " + exchange_order_id +
                    " | 客户端订单: " + client_order_id);
        }
        else if (status == "rejected") {
            // 下单被拒绝
            std::string err_info = error_msg.empty() ? "未知错误" : error_msg;
            log_error("[下单失败] ✗ " + symbol + " " + side + 
                     " | 原因: " + err_info +
                     " | 订单ID: " + client_order_id);
        }
        else if (status == "filled") {
            // 完全成交
            log_info("[订单成交] ✓ " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(filled_qty)) + "张 @ " + 
                    std::to_string(filled_price) + 
                    " | 订单ID: " + client_order_id);
        } 
        else if (status == "partially_filled" || status == "partial_filled") {
            // 部分成交
            log_info("[部分成交] " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(filled_qty)) + "/" + 
                    std::to_string(static_cast<int>(quantity)) + "张" +
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "cancelled" || status == "canceled") {
            // 撤销
            log_info("[订单撤销] " + symbol + " " + side + 
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "live" || status == "pending" || status == "submitted") {
            // 挂单中
            std::string order_type = report.value("order_type", "");
            log_info("[订单挂单] " + symbol + " " + side + " " + 
                    std::to_string(static_cast<int>(quantity)) + "张" +
                    (order_type == "limit" ? " @ " + std::to_string(price) : " 市价") +
                    " | 订单ID: " + client_order_id);
        }
        else if (status == "failed" || status == "error") {
            // 失败
            std::string err_info = error_msg.empty() ? error_code : error_msg;
            log_error("[订单失败] ✗ " + symbol + " " + side + 
                     " | 原因: " + err_info + 
                     " | 订单ID: " + client_order_id);
        }
        else {
            // 其他状态 - 打印关键信息
            log_info("[订单回报] " + symbol + " " + side + 
                    " | 状态: " + status + 
                    " | 订单ID: " + client_order_id);
        }
    }
    
    /**
     * @brief 生成客户端订单ID
     */
    std::string generate_client_order_id() {
        static std::atomic<int> counter{0};
        return "py" + std::to_string(current_timestamp_ms() % 1000000000) + 
               std::to_string(counter.fetch_add(1));
    }
    
    /**
     * @brief 获取当前时间戳（毫秒）
     */
    static int64_t current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }
    
    /**
     * @brief 获取当前时间戳（纳秒）
     */
    static int64_t current_timestamp_ns() {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()
        ).count();
    }
    
    /**
     * @brief 打印运行总结
     */
    void print_summary() {
        auto end_time = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(end_time - start_time_).count();
        
        std::cout << "\n";
        std::cout << "================================================\n";
        std::cout << "              策略运行总结\n";
        std::cout << "================================================\n";
        std::cout << "  策略ID:       " << strategy_id_ << "\n";
        std::cout << "  运行时间:     " << elapsed << " 秒\n";
        std::cout << "  接收K线:      " << kline_count_ << " 根\n";
        std::cout << "  发送订单:     " << order_count_ << " 个\n";
        std::cout << "  收到回报:     " << report_count_ << " 个\n";
        std::cout << "================================================\n";
    }

protected:
    // 策略配置
    std::string strategy_id_;
    size_t max_kline_bars_;
    
    // 账户信息
    std::string api_key_;
    std::string secret_key_;
    std::string passphrase_;
    bool is_testnet_ = true;
    
    // 状态
    std::atomic<bool> running_;
    std::atomic<bool> account_registered_;
    
    // ZMQ
    std::unique_ptr<zmq::context_t> context_;
    std::unique_ptr<zmq::socket_t> market_sub_;
    std::unique_ptr<zmq::socket_t> order_push_;
    std::unique_ptr<zmq::socket_t> report_sub_;
    std::unique_ptr<zmq::socket_t> subscribe_push_;
    
    // K线管理器（按 interval 分组）
    std::map<std::string, std::unique_ptr<KlineManager>> kline_managers_;
    mutable std::mutex kline_managers_mutex_;
    
    // 订阅记录
    std::map<std::string, std::set<std::string>> subscribed_klines_;  // symbol -> intervals
    std::mutex subscriptions_mutex_;
    
    // 统计
    std::atomic<int64_t> kline_count_;
    std::atomic<int64_t> order_count_;
    std::atomic<int64_t> report_count_;
    std::chrono::steady_clock::time_point start_time_;
};

} // namespace trading

