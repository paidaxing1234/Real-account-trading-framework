/**
 * @file redis_data_provider.cpp
 * @brief Redis 数据查询模块实现（只读）
 *
 * @author Sequence Team
 * @date 2026-01
 */

#include "redis_data_provider.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <set>

namespace trading {
namespace server {

// 全局 Redis 数据提供者实例
std::unique_ptr<RedisDataProvider> g_redis_data_provider;

RedisDataProvider::RedisDataProvider() = default;

RedisDataProvider::~RedisDataProvider() {
    disconnect();
}

void RedisDataProvider::set_config(const RedisProviderConfig& config) {
    config_ = config;
}

bool RedisDataProvider::connect() {
    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (context_) {
        redisFree(context_);
        context_ = nullptr;
    }

    // 设置连接超时
    struct timeval timeout = {
        config_.connection_timeout_ms / 1000,
        (config_.connection_timeout_ms % 1000) * 1000
    };

    context_ = redisConnectWithTimeout(config_.host.c_str(), config_.port, timeout);

    if (context_ == nullptr || context_->err) {
        if (context_) {
            log_error("[RedisDataProvider] 连接失败: " + std::string(context_->errstr));
            redisFree(context_);
            context_ = nullptr;
        } else {
            log_error("[RedisDataProvider] 无法分配 Redis context");
        }
        return false;
    }

    // 认证
    if (!config_.password.empty()) {
        redisReply* reply = (redisReply*)redisCommand(context_, "AUTH %s", config_.password.c_str());
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            log_error("[RedisDataProvider] 认证失败");
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
    }

    // 选择数据库
    if (config_.db != 0) {
        redisReply* reply = (redisReply*)redisCommand(context_, "SELECT %d", config_.db);
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            log_error("[RedisDataProvider] 选择数据库失败");
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
    }

    log_info("[RedisDataProvider] Redis 连接成功: " + config_.host + ":" + std::to_string(config_.port));
    return true;
}

void RedisDataProvider::disconnect() {
    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (context_) {
        redisFree(context_);
        context_ = nullptr;
    }
}

bool RedisDataProvider::is_connected() const {
    return context_ != nullptr && context_->err == 0;
}

bool RedisDataProvider::reconnect() {
    disconnect();
    return connect();
}

int64_t RedisDataProvider::interval_to_ms(const std::string& interval) const {
    // 解析时间周期字符串
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

    // 默认返回 1 分钟
    return 60 * 1000;
}

int64_t RedisDataProvider::align_timestamp(int64_t timestamp, const std::string& interval) const {
    int64_t interval_ms = interval_to_ms(interval);
    return (timestamp / interval_ms) * interval_ms;
}

std::vector<KlineBar> RedisDataProvider::query_raw_klines(
    const std::string& key,
    int64_t start_time,
    int64_t end_time
) {
    std::vector<KlineBar> result;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return result;
        }
    }

    // 使用 ZRANGEBYSCORE 查询时间范围内的数据
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
                result.push_back(KlineBar::from_json(j));
            } catch (const std::exception& e) {
                // 解析失败，跳过
                log_error("[RedisDataProvider] JSON 解析失败: " + std::string(e.what()));
            }
        }
    }

    freeReplyObject(reply);
    return result;
}

std::vector<KlineBar> RedisDataProvider::get_klines(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& interval,
    int64_t start_time,
    int64_t end_time
) {
    // 构建 Redis key
    // 格式: kline:{exchange}:{symbol}:{interval}
    std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

    // 先尝试直接查询该周期的数据
    auto result = query_raw_klines(key, start_time, end_time);

    // 如果没有数据且请求的不是 1m，尝试从 1m 聚合
    if (result.empty() && interval != "1m") {
        result = aggregate_klines(symbol, exchange, interval, start_time, end_time);
    }

    return result;
}

std::vector<KlineBar> RedisDataProvider::get_klines_by_days(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& interval,
    int days
) {
    // 限制最大 60 天
    if (days > 60) days = 60;
    if (days < 1) days = 1;

    // 计算时间范围
    auto now = std::chrono::system_clock::now();
    auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();

    auto start_time = end_time - (int64_t)days * 24 * 60 * 60 * 1000;

    return get_klines(symbol, exchange, interval, start_time, end_time);
}

std::vector<KlineBar> RedisDataProvider::get_latest_klines(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& interval,
    int count
) {
    std::vector<KlineBar> result;

    if (count <= 0) return result;

    std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return result;
        }
    }

    // 使用 ZREVRANGE 获取最新的 N 条数据（按 score 降序）
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
                result.push_back(KlineBar::from_json(j));
            } catch (const std::exception& e) {
                log_error("[RedisDataProvider] JSON 解析失败: " + std::string(e.what()));
            }
        }
    }

    freeReplyObject(reply);

    // 反转结果，使其按时间升序
    std::reverse(result.begin(), result.end());

    return result;
}

std::vector<KlineBar> RedisDataProvider::aggregate_klines(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& target_interval,
    int64_t start_time,
    int64_t end_time
) {
    // 从 1m K 线聚合（基础周期为 1m）
    std::string source_key = "kline:" + exchange + ":" + symbol + ":1m";

    // 对齐开始时间到目标周期边界
    start_time = align_timestamp(start_time, target_interval);

    auto source_bars = query_raw_klines(source_key, start_time, end_time);

    if (source_bars.empty()) {
        return {};
    }

    return do_aggregate(source_bars, target_interval, symbol, exchange);
}

std::vector<KlineBar> RedisDataProvider::do_aggregate(
    const std::vector<KlineBar>& source_bars,
    const std::string& target_interval,
    const std::string& symbol,
    const std::string& exchange
) {
    std::vector<KlineBar> result;

    if (source_bars.empty()) return result;

    int64_t interval_ms = interval_to_ms(target_interval);

    // 按目标周期分组聚合
    std::map<int64_t, std::vector<const KlineBar*>> groups;

    for (const auto& bar : source_bars) {
        int64_t group_ts = align_timestamp(bar.timestamp, target_interval);
        groups[group_ts].push_back(&bar);
    }

    result.reserve(groups.size());

    for (const auto& [group_ts, bars] : groups) {
        if (bars.empty()) continue;

        KlineBar aggregated;
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
        [](const KlineBar& a, const KlineBar& b) {
            return a.timestamp < b.timestamp;
        });

    return result;
}

std::vector<std::string> RedisDataProvider::get_available_symbols(const std::string& exchange) {
    std::vector<std::string> result;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return result;
        }
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

std::pair<int64_t, int64_t> RedisDataProvider::get_data_time_range(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& interval
) {
    std::pair<int64_t, int64_t> result = {0, 0};

    std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return result;
        }
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

int64_t RedisDataProvider::get_kline_count(
    const std::string& symbol,
    const std::string& exchange,
    const std::string& interval
) {
    std::string key = "kline:" + exchange + ":" + symbol + ":" + interval;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return 0;
        }
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

void RedisDataProvider::log_info(const std::string& msg) {
    std::cout << msg << std::endl;
}

void RedisDataProvider::log_error(const std::string& msg) {
    std::cerr << msg << std::endl;
}

} // namespace server
} // namespace trading
