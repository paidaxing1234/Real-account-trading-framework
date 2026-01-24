/**
 * @file historical_data_module.h
 * @brief 历史数据模块 - 为策略端提供 Redis 历史 K 线数据查询接口
 *
 * 功能：
 * 1. 查询指定时间范围的历史 K 线数据
 * 2. 查询最近 N 天的历史 K 线数据
 * 3. 支持不同时间周期的 K 线聚合（1s -> 1m/5m/15m/1h/4h/1d）
 * 4. 支持 OKX 和 Binance 两个交易所
 *
 * @author Sequence Team
 * @date 2026-01
 */

#pragma once

#include <string>
#include <vector>
#include <memory>
#include <mutex>
#include <chrono>
#include <functional>
#include <iostream>
#include <thread>
#include <future>
#include <algorithm>

#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>

namespace trading {

/**
 * @brief 历史 K 线数据结构
 */
struct HistoricalKline {
    std::string symbol;         // 交易对
    std::string exchange;       // 交易所
    std::string interval;       // 时间周期
    int64_t timestamp;          // 开盘时间戳（毫秒）
    double open;                // 开盘价
    double high;                // 最高价
    double low;                 // 最低价
    double close;               // 收盘价
    double volume;              // 成交量
    double turnover;            // 成交额（可选）
    bool is_closed;             // 是否已完结

    HistoricalKline()
        : timestamp(0), open(0), high(0), low(0), close(0)
        , volume(0), turnover(0), is_closed(true) {}

    nlohmann::json to_json() const {
        return {
            {"symbol", symbol},
            {"exchange", exchange},
            {"interval", interval},
            {"timestamp", timestamp},
            {"open", open},
            {"high", high},
            {"low", low},
            {"close", close},
            {"volume", volume},
            {"turnover", turnover},
            {"is_closed", is_closed}
        };
    }

    static HistoricalKline from_json(const nlohmann::json& j) {
        HistoricalKline bar;
        bar.symbol = j.value("symbol", "");
        bar.exchange = j.value("exchange", "");
        bar.interval = j.value("interval", "1s");
        bar.timestamp = j.value("timestamp", (int64_t)0);
        bar.open = j.value("open", 0.0);
        bar.high = j.value("high", 0.0);
        bar.low = j.value("low", 0.0);
        bar.close = j.value("close", 0.0);
        bar.volume = j.value("volume", 0.0);
        bar.turnover = j.value("turnover", 0.0);
        bar.is_closed = j.value("is_closed", true);
        return bar;
    }
};

/**
 * @brief 历史数据模块配置
 */
struct HistoricalDataConfig {
    std::string redis_host = "127.0.0.1";
    int redis_port = 6379;
    std::string redis_password;
    int redis_db = 0;
    int connection_timeout_ms = 5000;
    int query_timeout_ms = 10000;
};

/**
 * @brief 历史数据模块
 *
 * 为策略端提供 Redis 历史 K 线数据查询功能
 */
class HistoricalDataModule {
public:
    using LogCallback = std::function<void(const std::string&, bool)>;

    HistoricalDataModule() = default;
    ~HistoricalDataModule() { disconnect(); }

    /**
     * @brief 设置日志回调
     */
    void set_log_callback(LogCallback callback) {
        log_callback_ = std::move(callback);
    }

    /**
     * @brief 设置配置
     */
    void set_config(const HistoricalDataConfig& config) {
        config_ = config;
    }

    /**
     * @brief 从环境变量加载配置
     */
    void load_config_from_env() {
        if (const char* v = std::getenv("REDIS_HOST")) config_.redis_host = v;
        if (const char* v = std::getenv("REDIS_PORT")) config_.redis_port = std::stoi(v);
        if (const char* v = std::getenv("REDIS_PASSWORD")) config_.redis_password = v;
        if (const char* v = std::getenv("REDIS_DB")) config_.redis_db = std::stoi(v);
    }

    /**
     * @brief 连接到 Redis
     * @return 是否成功
     */
    bool connect() {
        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (context_) {
            redisFree(context_);
            context_ = nullptr;
        }

        struct timeval timeout = {
            config_.connection_timeout_ms / 1000,
            (config_.connection_timeout_ms % 1000) * 1000
        };

        context_ = redisConnectWithTimeout(config_.redis_host.c_str(), config_.redis_port, timeout);

        if (context_ == nullptr || context_->err) {
            if (context_) {
                log_error("Redis 连接失败: " + std::string(context_->errstr));
                redisFree(context_);
                context_ = nullptr;
            } else {
                log_error("无法分配 Redis context");
            }
            return false;
        }

        // 认证
        if (!config_.redis_password.empty()) {
            redisReply* reply = (redisReply*)redisCommand(context_, "AUTH %s", config_.redis_password.c_str());
            if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                log_error("Redis 认证失败");
                if (reply) freeReplyObject(reply);
                return false;
            }
            freeReplyObject(reply);
        }

        // 选择数据库
        if (config_.redis_db != 0) {
            redisReply* reply = (redisReply*)redisCommand(context_, "SELECT %d", config_.redis_db);
            if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                log_error("Redis 选择数据库失败");
                if (reply) freeReplyObject(reply);
                return false;
            }
            freeReplyObject(reply);
        }

        connected_ = true;
        log_info("Redis 连接成功: " + config_.redis_host + ":" + std::to_string(config_.redis_port));
        return true;
    }

    /**
     * @brief 断开连接
     */
    void disconnect() {
        std::lock_guard<std::mutex> lock(redis_mutex_);
        if (context_) {
            redisFree(context_);
            context_ = nullptr;
        }
        connected_ = false;
    }

    /**
     * @brief 是否已连接
     */
    bool is_connected() const {
        return connected_ && context_ != nullptr && context_->err == 0;
    }

    // ==================== K 线查询接口 ====================

    /**
     * @brief 查询指定时间范围的历史 K 线数据
     * @param symbol 交易对（如 BTC-USDT-SWAP 或 BTCUSDT）
     * @param exchange 交易所（okx/binance）
     * @param interval 时间周期（1s/1m/5m/15m/1h/4h/1d）
     * @param start_time 开始时间戳（毫秒）
     * @param end_time 结束时间戳（毫秒）
     * @return K 线数据列表（按时间升序）
     */
    std::vector<HistoricalKline> get_historical_klines(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval,
        int64_t start_time,
        int64_t end_time
    ) {
        // 先尝试直接查询该周期的数据
        std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;
        auto result = query_raw_klines(key, start_time, end_time);

        // 如果没有数据且请求的不是 1m，尝试从 1m 聚合
        if (result.empty() && interval != "1m") {
            return aggregate_klines(symbol, exchange, interval, start_time, end_time);
        }

        return result;
    }

    /**
     * @brief 查询最近 N 天的历史 K 线数据
     * @param symbol 交易对
     * @param exchange 交易所
     * @param interval 时间周期
     * @param days 天数（最大 60 天）
     * @return K 线数据列表（按时间升序）
     */
    std::vector<HistoricalKline> get_historical_klines_by_days(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval,
        int days
    ) {
        // 限制最大 60 天
        if (days > 60) days = 60;
        if (days < 1) days = 1;

        auto now = std::chrono::system_clock::now();
        auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();

        auto start_time = end_time - (int64_t)days * 24 * 60 * 60 * 1000;

        return get_historical_klines(symbol, exchange, interval, start_time, end_time);
    }

    /**
     * @brief 查询最近 N 根历史 K 线
     * @param symbol 交易对
     * @param exchange 交易所
     * @param interval 时间周期
     * @param count 数量
     * @return K 线数据列表（按时间升序）
     */
    std::vector<HistoricalKline> get_latest_historical_klines(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval,
        int count
    ) {
        std::vector<HistoricalKline> result;
        if (count <= 0) return result;

        std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (!ensure_connected()) {
            return result;
        }

        // 使用 ZREVRANGE 获取最新的 N 条数据
        redisReply* reply = (redisReply*)redisCommand(
            context_,
            "ZREVRANGE %s 0 %d",
            key.c_str(),
            count - 1
        );

        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            error_count_++;
            if (reply) freeReplyObject(reply);
            return result;
        }

        query_count_++;

        if (reply->type == REDIS_REPLY_ARRAY) {
            result.reserve(reply->elements);
            for (size_t i = 0; i < reply->elements; i++) {
                try {
                    std::string json_str(reply->element[i]->str, reply->element[i]->len);
                    nlohmann::json j = nlohmann::json::parse(json_str);
                    result.push_back(HistoricalKline::from_json(j));
                } catch (const std::exception& e) {
                    log_error("JSON 解析失败: " + std::string(e.what()));
                }
            }
        }

        freeReplyObject(reply);

        // 反转结果，使其按时间升序
        std::reverse(result.begin(), result.end());

        return result;
    }

    /**
     * @brief 从 1 秒 K 线聚合成更大周期
     * @param symbol 交易对
     * @param exchange 交易所
     * @param target_interval 目标周期（1m/5m/15m/1h/4h/1d）
     * @param start_time 开始时间戳（毫秒）
     * @param end_time 结束时间戳（毫秒）
     * @return 聚合后的 K 线数据列表
     */
    std::vector<HistoricalKline> aggregate_klines(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& target_interval,
        int64_t start_time,
        int64_t end_time
    ) {
        // 对齐开始时间到目标周期边界
        start_time = align_timestamp(start_time, target_interval);

        // 从 1m K 线聚合（基础周期为 1m）
        std::string source_key = "kline:" + exchange + ":" + symbol + ":1m";
        auto source_bars = query_raw_klines(source_key, start_time, end_time);

        if (source_bars.empty()) {
            return {};
        }

        return do_aggregate(source_bars, target_interval, symbol, exchange);
    }

    /**
     * @brief 获取可用的交易对列表
     * @param exchange 交易所（可选，空则返回所有）
     * @return 交易对列表
     */
    std::vector<std::string> get_available_symbols(const std::string& exchange = "") {
        std::vector<std::string> result;

        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (!ensure_connected()) {
            return result;
        }

        // 使用 KEYS 命令查找所有 K 线 key（基于 1m 周期）
        std::string pattern = exchange.empty()
            ? "kline:*:*:1m"
            : "kline:" + exchange + ":*:1m";

        redisReply* reply = (redisReply*)redisCommand(
            context_,
            "KEYS %s",
            pattern.c_str()
        );

        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            error_count_++;
            if (reply) freeReplyObject(reply);
            return result;
        }

        query_count_++;

        if (reply->type == REDIS_REPLY_ARRAY) {
            for (size_t i = 0; i < reply->elements; i++) {
                std::string key(reply->element[i]->str, reply->element[i]->len);
                // 解析 key: kline:{exchange}:{symbol}:{interval}
                size_t pos1 = key.find(':');
                if (pos1 == std::string::npos) continue;
                size_t pos2 = key.find(':', pos1 + 1);
                if (pos2 == std::string::npos) continue;
                size_t pos3 = key.find(':', pos2 + 1);
                if (pos3 == std::string::npos) continue;

                std::string symbol = key.substr(pos2 + 1, pos3 - pos2 - 1);
                result.push_back(symbol);
            }
        }

        freeReplyObject(reply);

        // 去重
        std::sort(result.begin(), result.end());
        result.erase(std::unique(result.begin(), result.end()), result.end());

        return result;
    }

    /**
     * @brief 获取指定交易对的数据时间范围
     * @param symbol 交易对
     * @param exchange 交易所
     * @param interval 时间周期
     * @return {earliest_timestamp, latest_timestamp}
     */
    std::pair<int64_t, int64_t> get_data_time_range(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval
    ) {
        std::pair<int64_t, int64_t> result = {0, 0};

        std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (!ensure_connected()) {
            return result;
        }

        // 获取最早的时间戳
        redisReply* reply = (redisReply*)redisCommand(
            context_,
            "ZRANGE %s 0 0 WITHSCORES",
            key.c_str()
        );

        if (reply && reply->type == REDIS_REPLY_ARRAY && reply->elements >= 2) {
            result.first = std::stoll(reply->element[1]->str);
        }
        if (reply) freeReplyObject(reply);

        // 获取最新的时间戳
        reply = (redisReply*)redisCommand(
            context_,
            "ZREVRANGE %s 0 0 WITHSCORES",
            key.c_str()
        );

        if (reply && reply->type == REDIS_REPLY_ARRAY && reply->elements >= 2) {
            result.second = std::stoll(reply->element[1]->str);
        }
        if (reply) freeReplyObject(reply);

        query_count_ += 2;

        return result;
    }

    /**
     * @brief 获取指定交易对的 K 线数量
     * @param symbol 交易对
     * @param exchange 交易所
     * @param interval 时间周期
     * @return K 线数量
     */
    int64_t get_historical_kline_count(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval
    ) {
        std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (!ensure_connected()) {
            return 0;
        }

        redisReply* reply = (redisReply*)redisCommand(
            context_,
            "ZCARD %s",
            key.c_str()
        );

        int64_t count = 0;
        if (reply && reply->type == REDIS_REPLY_INTEGER) {
            count = reply->integer;
        }
        if (reply) freeReplyObject(reply);

        query_count_++;

        return count;
    }

    // ==================== 便捷方法 ====================

    /**
     * @brief 获取 OKX 历史 K 线
     */
    std::vector<HistoricalKline> get_okx_klines(
        const std::string& symbol,
        const std::string& interval,
        int days
    ) {
        return get_historical_klines_by_days(symbol, "okx", interval, days);
    }

    /**
     * @brief 获取 Binance 历史 K 线
     */
    std::vector<HistoricalKline> get_binance_klines(
        const std::string& symbol,
        const std::string& interval,
        int days
    ) {
        return get_historical_klines_by_days(symbol, "binance", interval, days);
    }

    /**
     * @brief 获取收盘价数组
     */
    std::vector<double> get_historical_closes(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval,
        int days
    ) {
        auto klines = get_historical_klines_by_days(symbol, exchange, interval, days);
        std::vector<double> closes;
        closes.reserve(klines.size());
        for (const auto& k : klines) {
            closes.push_back(k.close);
        }
        return closes;
    }

    /**
     * @brief 获取 OHLCV 数据（返回 JSON 数组）
     */
    nlohmann::json get_historical_ohlcv(
        const std::string& symbol,
        const std::string& exchange,
        const std::string& interval,
        int days
    ) {
        auto klines = get_historical_klines_by_days(symbol, exchange, interval, days);
        nlohmann::json result = nlohmann::json::array();
        for (const auto& k : klines) {
            result.push_back({
                {"timestamp", k.timestamp},
                {"open", k.open},
                {"high", k.high},
                {"low", k.low},
                {"close", k.close},
                {"volume", k.volume}
            });
        }
        return result;
    }

    // ==================== 统计 ====================

    uint64_t get_query_count() const { return query_count_; }
    uint64_t get_error_count() const { return error_count_; }

    // ==================== 批量并行查询 ====================

    /**
     * @brief 批量并行查询多个币种的历史 K 线
     * @param symbols 交易对列表
     * @param exchange 交易所
     * @param interval 时间周期
     * @param days 天数
     * @param max_threads 最大线程数（默认16）
     * @return map<symbol, klines>
     *
     * 使用多线程并行查询，500个币种约 2-5 秒完成
     */
    std::map<std::string, std::vector<HistoricalKline>> get_batch_historical_klines(
        const std::vector<std::string>& symbols,
        const std::string& exchange,
        const std::string& interval,
        int days,
        int max_threads = 16
    ) {
        std::map<std::string, std::vector<HistoricalKline>> results;

        if (symbols.empty()) return results;

        // 计算时间范围
        auto now = std::chrono::system_clock::now();
        auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();
        auto start_time = end_time - (int64_t)days * 24 * 60 * 60 * 1000;

        // 限制线程数
        int num_threads = std::min(max_threads, (int)symbols.size());
        num_threads = std::max(1, num_threads);

        // 分配任务
        std::vector<std::future<std::pair<std::string, std::vector<HistoricalKline>>>> futures;
        futures.reserve(symbols.size());

        // 使用线程池模式：每个线程创建独立的 Redis 连接
        std::atomic<size_t> task_index{0};
        std::vector<std::thread> workers;
        std::mutex results_mutex;

        auto worker_func = [&]() {
            // 每个线程创建独立的 Redis 连接
            redisContext* local_ctx = nullptr;
            struct timeval timeout = {
                config_.connection_timeout_ms / 1000,
                (config_.connection_timeout_ms % 1000) * 1000
            };

            local_ctx = redisConnectWithTimeout(config_.redis_host.c_str(), config_.redis_port, timeout);
            if (local_ctx == nullptr || local_ctx->err) {
                if (local_ctx) redisFree(local_ctx);
                return;
            }

            // 认证
            if (!config_.redis_password.empty()) {
                redisReply* reply = (redisReply*)redisCommand(local_ctx, "AUTH %s", config_.redis_password.c_str());
                if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                    if (reply) freeReplyObject(reply);
                    redisFree(local_ctx);
                    return;
                }
                freeReplyObject(reply);
            }

            // 选择数据库
            if (config_.redis_db != 0) {
                redisReply* reply = (redisReply*)redisCommand(local_ctx, "SELECT %d", config_.redis_db);
                if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                    if (reply) freeReplyObject(reply);
                    redisFree(local_ctx);
                    return;
                }
                freeReplyObject(reply);
            }

            // 处理任务
            while (true) {
                size_t idx = task_index.fetch_add(1);
                if (idx >= symbols.size()) break;

                const std::string& symbol = symbols[idx];
                std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

                // 查询数据
                std::vector<HistoricalKline> klines;
                redisReply* reply = (redisReply*)redisCommand(
                    local_ctx,
                    "ZRANGEBYSCORE %s %lld %lld",
                    key.c_str(),
                    (long long)start_time,
                    (long long)end_time
                );

                if (reply && reply->type == REDIS_REPLY_ARRAY) {
                    klines.reserve(reply->elements);
                    for (size_t i = 0; i < reply->elements; i++) {
                        try {
                            std::string json_str(reply->element[i]->str, reply->element[i]->len);
                            nlohmann::json j = nlohmann::json::parse(json_str);
                            klines.push_back(HistoricalKline::from_json(j));
                        } catch (...) {
                            // 解析失败，跳过
                        }
                    }
                }
                if (reply) freeReplyObject(reply);

                // 如果需要聚合
                if (klines.empty() && interval != "1m") {
                    // 从 1m K 线聚合（基础周期为 1m）
                    std::string source_key = "kline:" + exchange + ":" + symbol + ":1m";
                    reply = (redisReply*)redisCommand(
                        local_ctx,
                        "ZRANGEBYSCORE %s %lld %lld",
                        source_key.c_str(),
                        (long long)start_time,
                        (long long)end_time
                    );

                    if (reply && reply->type == REDIS_REPLY_ARRAY && reply->elements > 0) {
                        std::vector<HistoricalKline> source_bars;
                        source_bars.reserve(reply->elements);
                        for (size_t i = 0; i < reply->elements; i++) {
                            try {
                                std::string json_str(reply->element[i]->str, reply->element[i]->len);
                                nlohmann::json j = nlohmann::json::parse(json_str);
                                source_bars.push_back(HistoricalKline::from_json(j));
                            } catch (...) {}
                        }

                        // 聚合
                        klines = do_aggregate_static(source_bars, interval, symbol, exchange);
                    }
                    if (reply) freeReplyObject(reply);
                }

                // 保存结果
                {
                    std::lock_guard<std::mutex> lock(results_mutex);
                    results[symbol] = std::move(klines);
                }
            }

            // 关闭连接
            redisFree(local_ctx);
        };

        // 启动工作线程
        for (int i = 0; i < num_threads; i++) {
            workers.emplace_back(worker_func);
        }

        // 等待所有线程完成
        for (auto& w : workers) {
            w.join();
        }

        return results;
    }

    /**
     * @brief 批量获取多个币种的收盘价数组
     * @param symbols 交易对列表
     * @param exchange 交易所
     * @param interval 时间周期
     * @param days 天数
     * @param max_threads 最大线程数
     * @return map<symbol, closes>
     */
    std::map<std::string, std::vector<double>> get_batch_historical_closes(
        const std::vector<std::string>& symbols,
        const std::string& exchange,
        const std::string& interval,
        int days,
        int max_threads = 16
    ) {
        auto klines_map = get_batch_historical_klines(symbols, exchange, interval, days, max_threads);

        std::map<std::string, std::vector<double>> results;
        for (const auto& [symbol, klines] : klines_map) {
            std::vector<double> closes;
            closes.reserve(klines.size());
            for (const auto& k : klines) {
                closes.push_back(k.close);
            }
            results[symbol] = std::move(closes);
        }
        return results;
    }

private:
    // 静态聚合方法（供多线程使用）
    static std::vector<HistoricalKline> do_aggregate_static(
        const std::vector<HistoricalKline>& source_bars,
        const std::string& target_interval,
        const std::string& symbol,
        const std::string& exchange
    ) {
        std::vector<HistoricalKline> result;
        if (source_bars.empty()) return result;

        int64_t interval_ms = interval_to_ms_static(target_interval);

        // 按目标周期分组聚合
        std::map<int64_t, std::vector<const HistoricalKline*>> groups;

        for (const auto& bar : source_bars) {
            int64_t group_ts = (bar.timestamp / interval_ms) * interval_ms;
            groups[group_ts].push_back(&bar);
        }

        result.reserve(groups.size());

        for (const auto& [group_ts, bars] : groups) {
            if (bars.empty()) continue;

            HistoricalKline aggregated;
            aggregated.symbol = symbol;
            aggregated.exchange = exchange;
            aggregated.interval = target_interval;
            aggregated.timestamp = group_ts;
            aggregated.open = bars.front()->open;
            aggregated.high = bars.front()->high;
            aggregated.low = bars.front()->low;
            aggregated.close = bars.back()->close;
            aggregated.volume = 0;
            aggregated.turnover = 0;
            aggregated.is_closed = true;

            for (const auto* bar : bars) {
                if (bar->high > aggregated.high) aggregated.high = bar->high;
                if (bar->low < aggregated.low) aggregated.low = bar->low;
                aggregated.volume += bar->volume;
                aggregated.turnover += bar->turnover;
            }

            result.push_back(aggregated);
        }

        // 按时间排序
        std::sort(result.begin(), result.end(),
            [](const HistoricalKline& a, const HistoricalKline& b) {
                return a.timestamp < b.timestamp;
            });

        return result;
    }

    static int64_t interval_to_ms_static(const std::string& interval) {
        if (interval == "1s") return 1000;
        if (interval == "5s") return 5000;
        if (interval == "15s") return 15000;
        if (interval == "30s") return 30000;
        if (interval == "1m") return 60 * 1000;
        if (interval == "3m") return 3 * 60 * 1000;
        if (interval == "5m") return 5 * 60 * 1000;
        if (interval == "15m") return 15 * 60 * 1000;
        if (interval == "30m") return 30 * 60 * 1000;
        if (interval == "1h" || interval == "1H") return 60 * 60 * 1000;
        if (interval == "2h" || interval == "2H") return 2 * 60 * 60 * 1000;
        if (interval == "4h" || interval == "4H") return 4 * 60 * 60 * 1000;
        if (interval == "6h" || interval == "6H") return 6 * 60 * 60 * 1000;
        if (interval == "12h" || interval == "12H") return 12 * 60 * 60 * 1000;
        if (interval == "1d" || interval == "1D") return 24 * 60 * 60 * 1000;
        if (interval == "1w" || interval == "1W") return 7 * 24 * 60 * 60 * 1000;
        return 60 * 1000;
    }

    bool ensure_connected() {
        if (is_connected()) return true;
        return reconnect();
    }

    bool reconnect() {
        if (context_) {
            redisFree(context_);
            context_ = nullptr;
        }
        connected_ = false;

        struct timeval timeout = {
            config_.connection_timeout_ms / 1000,
            (config_.connection_timeout_ms % 1000) * 1000
        };

        context_ = redisConnectWithTimeout(config_.redis_host.c_str(), config_.redis_port, timeout);

        if (context_ == nullptr || context_->err) {
            if (context_) {
                redisFree(context_);
                context_ = nullptr;
            }
            return false;
        }

        if (!config_.redis_password.empty()) {
            redisReply* reply = (redisReply*)redisCommand(context_, "AUTH %s", config_.redis_password.c_str());
            if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                if (reply) freeReplyObject(reply);
                return false;
            }
            freeReplyObject(reply);
        }

        if (config_.redis_db != 0) {
            redisReply* reply = (redisReply*)redisCommand(context_, "SELECT %d", config_.redis_db);
            if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                if (reply) freeReplyObject(reply);
                return false;
            }
            freeReplyObject(reply);
        }

        connected_ = true;
        return true;
    }

    int64_t interval_to_ms(const std::string& interval) const {
        if (interval == "1s") return 1000;
        if (interval == "5s") return 5000;
        if (interval == "15s") return 15000;
        if (interval == "30s") return 30000;
        if (interval == "1m") return 60 * 1000;
        if (interval == "3m") return 3 * 60 * 1000;
        if (interval == "5m") return 5 * 60 * 1000;
        if (interval == "15m") return 15 * 60 * 1000;
        if (interval == "30m") return 30 * 60 * 1000;
        if (interval == "1h" || interval == "1H") return 60 * 60 * 1000;
        if (interval == "2h" || interval == "2H") return 2 * 60 * 60 * 1000;
        if (interval == "4h" || interval == "4H") return 4 * 60 * 60 * 1000;
        if (interval == "6h" || interval == "6H") return 6 * 60 * 60 * 1000;
        if (interval == "12h" || interval == "12H") return 12 * 60 * 60 * 1000;
        if (interval == "1d" || interval == "1D") return 24 * 60 * 60 * 1000;
        if (interval == "1w" || interval == "1W") return 7 * 24 * 60 * 60 * 1000;
        return 60 * 1000;
    }

    int64_t align_timestamp(int64_t timestamp, const std::string& interval) const {
        int64_t interval_ms = interval_to_ms(interval);
        return (timestamp / interval_ms) * interval_ms;
    }

    std::vector<HistoricalKline> query_raw_klines(
        const std::string& key,
        int64_t start_time,
        int64_t end_time
    ) {
        std::vector<HistoricalKline> result;

        std::lock_guard<std::mutex> lock(redis_mutex_);

        if (!ensure_connected()) {
            error_count_++;
            return result;
        }

        redisReply* reply = (redisReply*)redisCommand(
            context_,
            "ZRANGEBYSCORE %s %lld %lld",
            key.c_str(),
            (long long)start_time,
            (long long)end_time
        );

        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            error_count_++;
            if (reply) freeReplyObject(reply);
            return result;
        }

        query_count_++;

        if (reply->type == REDIS_REPLY_ARRAY) {
            result.reserve(reply->elements);
            for (size_t i = 0; i < reply->elements; i++) {
                try {
                    std::string json_str(reply->element[i]->str, reply->element[i]->len);
                    nlohmann::json j = nlohmann::json::parse(json_str);
                    result.push_back(HistoricalKline::from_json(j));
                } catch (const std::exception&) {
                    // 解析失败，跳过
                }
            }
        }

        freeReplyObject(reply);
        return result;
    }

    std::vector<HistoricalKline> do_aggregate(
        const std::vector<HistoricalKline>& source_bars,
        const std::string& target_interval,
        const std::string& symbol,
        const std::string& exchange
    ) {
        std::vector<HistoricalKline> result;

        if (source_bars.empty()) return result;

        int64_t interval_ms = interval_to_ms(target_interval);

        // 按目标周期分组聚合
        std::map<int64_t, std::vector<const HistoricalKline*>> groups;

        for (const auto& bar : source_bars) {
            int64_t group_ts = align_timestamp(bar.timestamp, target_interval);
            groups[group_ts].push_back(&bar);
        }

        result.reserve(groups.size());

        for (const auto& [group_ts, bars] : groups) {
            if (bars.empty()) continue;

            HistoricalKline aggregated;
            aggregated.symbol = symbol;
            aggregated.exchange = exchange;
            aggregated.interval = target_interval;
            aggregated.timestamp = group_ts;
            aggregated.open = bars.front()->open;
            aggregated.high = bars.front()->high;
            aggregated.low = bars.front()->low;
            aggregated.close = bars.back()->close;
            aggregated.volume = 0;
            aggregated.turnover = 0;
            aggregated.is_closed = true;

            for (const auto* bar : bars) {
                if (bar->high > aggregated.high) aggregated.high = bar->high;
                if (bar->low < aggregated.low) aggregated.low = bar->low;
                aggregated.volume += bar->volume;
                aggregated.turnover += bar->turnover;
            }

            result.push_back(aggregated);
        }

        // 按时间排序
        std::sort(result.begin(), result.end(),
            [](const HistoricalKline& a, const HistoricalKline& b) {
                return a.timestamp < b.timestamp;
            });

        return result;
    }

    void log_info(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, false);
        } else {
            std::cout << "[HistoricalData] " << msg << std::endl;
        }
    }

    void log_error(const std::string& msg) {
        if (log_callback_) {
            log_callback_(msg, true);
        } else {
            std::cerr << "[HistoricalData] ERROR: " << msg << std::endl;
        }
    }

private:
    HistoricalDataConfig config_;
    redisContext* context_ = nullptr;
    mutable std::mutex redis_mutex_;
    bool connected_ = false;

    LogCallback log_callback_;

    mutable uint64_t query_count_ = 0;
    mutable uint64_t error_count_ = 0;
};

} // namespace trading
