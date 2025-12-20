/**
 * @file market_data_module.h
 * @brief 行情数据模块 - K线、Trades等行情数据的接收和存储
 * 
 * 功能:
 * 1. K线数据订阅/取消订阅
 * 2. K线数据存储（环形缓冲区，支持2小时数据）
 * 3. Trades数据订阅
 * 4. Ticker数据订阅（预留）
 * 5. OrderBook数据订阅（预留）
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <vector>
#include <map>
#include <set>
#include <memory>
#include <mutex>
#include <functional>
#include <chrono>

#include <zmq.hpp>
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
 * @brief 逐笔成交数据
 */
struct TradeData {
    int64_t timestamp;     // 毫秒时间戳
    std::string trade_id;
    double price;
    double quantity;
    std::string side;      // "buy" or "sell"
    
    TradeData() : timestamp(0), price(0), quantity(0) {}
};


// ============================================================
// K线缓冲区（环形缓冲区）
// ============================================================

/**
 * @brief 单个币种的 K 线缓冲区
 */
class KlineBuffer {
public:
    explicit KlineBuffer(size_t max_bars = 7200)
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
            data_[0] = KlineBar(timestamp, open, high, low, close, volume);
            size_ = 1;
            return true;
        }
        
        size_t last_idx = (head_ + size_ - 1) % max_bars_;
        
        if (data_[last_idx].timestamp == timestamp) {
            data_[last_idx] = KlineBar(timestamp, open, high, low, close, volume);
            return false;
        } else {
            if (size_ < max_bars_) {
                size_t new_idx = (head_ + size_) % max_bars_;
                data_[new_idx] = KlineBar(timestamp, open, high, low, close, volume);
                size_++;
            } else {
                data_[head_] = KlineBar(timestamp, open, high, low, close, volume);
                head_ = (head_ + 1) % max_bars_;
            }
            return true;
        }
    }
    
    std::vector<KlineBar> get_all() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<KlineBar> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_]);
        }
        return result;
    }
    
    std::vector<double> get_closes() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].close);
        }
        return result;
    }
    
    std::vector<double> get_opens() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].open);
        }
        return result;
    }
    
    std::vector<double> get_highs() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].high);
        }
        return result;
    }
    
    std::vector<double> get_lows() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].low);
        }
        return result;
    }
    
    std::vector<double> get_volumes() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<double> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].volume);
        }
        return result;
    }
    
    std::vector<int64_t> get_timestamps() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<int64_t> result;
        result.reserve(size_);
        for (size_t i = 0; i < size_; ++i) {
            result.push_back(data_[(head_ + i) % max_bars_].timestamp);
        }
        return result;
    }
    
    bool get_last(KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (size_ == 0) return false;
        bar = data_[(head_ + size_ - 1) % max_bars_];
        return true;
    }
    
    bool get_at(size_t index, KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        if (index >= size_) return false;
        bar = data_[(head_ + index) % max_bars_];
        return true;
    }
    
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
    
    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        head_ = 0;
        size_ = 0;
    }

private:
    size_t max_bars_;
    std::vector<KlineBar> data_;
    size_t head_;
    size_t size_;
    mutable std::mutex mutex_;
};


// ============================================================
// K线管理器（多币种）
// ============================================================

class KlineManager {
public:
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
        else interval_ms_ = 60000;
    }
    
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
    
    std::vector<KlineBar> get_all(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_all();
    }
    
    std::vector<double> get_closes(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_closes();
    }
    
    std::vector<double> get_opens(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_opens();
    }
    
    std::vector<double> get_highs(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_highs();
    }
    
    std::vector<double> get_lows(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_lows();
    }
    
    std::vector<double> get_volumes(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_volumes();
    }
    
    std::vector<int64_t> get_timestamps(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_timestamps();
    }
    
    bool get_last(const std::string& symbol, KlineBar& bar) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return false;
        return it->second->get_last(bar);
    }
    
    std::vector<KlineBar> get_recent(const std::string& symbol, size_t n) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return {};
        return it->second->get_recent(n);
    }
    
    size_t get_bar_count(const std::string& symbol) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = buffers_.find(symbol);
        if (it == buffers_.end()) return 0;
        return it->second->size();
    }
    
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
// 行情数据模块
// ============================================================

/**
 * @brief 行情数据模块
 * 
 * 负责：
 * - 订阅/取消订阅K线、trades等行情数据
 * - 接收和存储行情数据
 * - 提供行情数据查询接口
 */
class MarketDataModule {
public:
    // K线回调类型
    using KlineCallback = std::function<void(const std::string&, const std::string&, const KlineBar&)>;
    // Trades回调类型
    using TradesCallback = std::function<void(const std::string&, const TradeData&)>;
    
    /**
     * @brief 构造函数
     * @param max_kline_bars K线最大存储数量
     */
    explicit MarketDataModule(size_t max_kline_bars = 7200)
        : max_kline_bars_(max_kline_bars)
        , kline_count_(0) {}
    
    // ==================== 初始化 ====================
    
    /**
     * @brief 设置 ZMQ socket（由策略基类调用）
     */
    void set_sockets(zmq::socket_t* market_sub, zmq::socket_t* subscribe_push) {
        market_sub_ = market_sub;
        subscribe_push_ = subscribe_push;
    }
    
    // ==================== 订阅管理 ====================
    
    /**
     * @brief 订阅 K 线数据
     */
    bool subscribe_kline(const std::string& symbol, const std::string& interval,
                        const std::string& strategy_id) {
        if (!subscribe_push_) {
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
            {"strategy_id", strategy_id},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    
    /**
     * @brief 取消订阅 K 线数据
     */
    bool unsubscribe_kline(const std::string& symbol, const std::string& interval,
                          const std::string& strategy_id) {
        if (!subscribe_push_) return false;
        
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
            {"strategy_id", strategy_id},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    
    /**
     * @brief 订阅 Trades 数据
     */
    bool subscribe_trades(const std::string& symbol, const std::string& strategy_id) {
        if (!subscribe_push_) return false;
        
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            subscribed_trades_.insert(symbol);
        }
        
        nlohmann::json request = {
            {"action", "subscribe"},
            {"channel", "trades"},
            {"symbol", symbol},
            {"strategy_id", strategy_id},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    
    /**
     * @brief 取消订阅 Trades 数据
     */
    bool unsubscribe_trades(const std::string& symbol, const std::string& strategy_id) {
        if (!subscribe_push_) return false;
        
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            subscribed_trades_.erase(symbol);
        }
        
        nlohmann::json request = {
            {"action", "unsubscribe"},
            {"channel", "trades"},
            {"symbol", symbol},
            {"strategy_id", strategy_id},
            {"timestamp", current_timestamp_ms()}
        };
        
        try {
            std::string msg = request.dump();
            subscribe_push_->send(zmq::buffer(msg), zmq::send_flags::none);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    
    // ==================== 数据处理 ====================
    
    /**
     * @brief 处理行情数据（主循环调用）
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
                } else if (msg_type == "trades" || msg_type == "trade") {
                    handle_trades(data);
                }
                
            } catch (const std::exception&) {
                // 忽略解析错误
            }
        }
    }
    
    // ==================== K线数据查询 ====================
    
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
     * @brief 获取开盘价数组
     */
    std::vector<double> get_opens(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_opens(symbol);
    }
    
    /**
     * @brief 获取最高价数组
     */
    std::vector<double> get_highs(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_highs(symbol);
    }
    
    /**
     * @brief 获取最低价数组
     */
    std::vector<double> get_lows(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_lows(symbol);
    }
    
    /**
     * @brief 获取成交量数组
     */
    std::vector<double> get_volumes(const std::string& symbol, const std::string& interval) const {
        std::lock_guard<std::mutex> lock(kline_managers_mutex_);
        auto it = kline_managers_.find(interval);
        if (it == kline_managers_.end()) return {};
        return it->second->get_volumes(symbol);
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
    
    /**
     * @brief 获取已订阅的币种列表
     */
    std::vector<std::string> get_subscribed_symbols() const {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::vector<std::string> result;
        for (const auto& pair : subscribed_klines_) {
            result.push_back(pair.first);
        }
        return result;
    }
    
    // ==================== 回调设置 ====================
    
    void set_kline_callback(KlineCallback callback) {
        kline_callback_ = std::move(callback);
    }
    
    void set_trades_callback(TradesCallback callback) {
        trades_callback_ = std::move(callback);
    }
    
    // ==================== 统计 ====================
    
    int64_t total_kline_count() const { return kline_count_.load(); }

private:
    void handle_kline(const nlohmann::json& data) {
        std::string symbol = data.value("symbol", "");
        std::string interval = data.value("interval", "");
        
        if (symbol.empty() || interval.empty()) return;
        
        // 检查是否订阅
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            auto it = subscribed_klines_.find(symbol);
            if (it == subscribed_klines_.end() || it->second.find(interval) == it->second.end()) {
                return;
            }
        }
        
        KlineBar bar;
        bar.timestamp = data.value("timestamp", 0LL);
        bar.open = data.value("open", 0.0);
        bar.high = data.value("high", 0.0);
        bar.low = data.value("low", 0.0);
        bar.close = data.value("close", 0.0);
        bar.volume = data.value("volume", 0.0);
        
        // 存储
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
        
        // 回调
        if (kline_callback_) {
            kline_callback_(symbol, interval, bar);
        }
    }
    
    void handle_trades(const nlohmann::json& data) {
        std::string symbol = data.value("symbol", "");
        
        // 检查是否订阅
        {
            std::lock_guard<std::mutex> lock(subscriptions_mutex_);
            if (subscribed_trades_.find(symbol) == subscribed_trades_.end()) {
                return;
            }
        }
        
        TradeData trade;
        trade.timestamp = data.value("timestamp", 0LL);
        trade.trade_id = data.value("trade_id", "");
        trade.price = data.value("price", 0.0);
        trade.quantity = data.value("quantity", 0.0);
        trade.side = data.value("side", "");
        
        // 回调
        if (trades_callback_) {
            trades_callback_(symbol, trade);
        }
    }
    
    static int64_t current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }

private:
    size_t max_kline_bars_;
    
    // ZMQ sockets（由策略基类设置）
    zmq::socket_t* market_sub_ = nullptr;
    zmq::socket_t* subscribe_push_ = nullptr;
    
    // K线管理器
    std::map<std::string, std::unique_ptr<KlineManager>> kline_managers_;
    mutable std::mutex kline_managers_mutex_;
    
    // 订阅记录
    std::map<std::string, std::set<std::string>> subscribed_klines_;  // symbol -> intervals
    std::set<std::string> subscribed_trades_;
    mutable std::mutex subscriptions_mutex_;
    
    // 回调
    KlineCallback kline_callback_;
    TradesCallback trades_callback_;
    
    // 统计
    std::atomic<int64_t> kline_count_;
};

} // namespace trading

