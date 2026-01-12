/**
 * @file redis_recorder.cpp
 * @brief Redis 数据录制模块实现
 *
 * @author Sequence Team
 * @date 2026-01
 */

#include "redis_recorder.h"
#include <iostream>
#include <cstdarg>
#include <chrono>

namespace trading {
namespace server {

// 全局 Redis 录制器实例
std::unique_ptr<RedisRecorder> g_redis_recorder;

RedisRecorder::RedisRecorder() = default;

RedisRecorder::~RedisRecorder() {
    stop();
}

void RedisRecorder::set_config(const RedisConfig& config) {
    config_ = config;
}

bool RedisRecorder::start() {
    if (running_.load()) {
        return true;
    }

    if (!config_.enabled) {
        log_info("[RedisRecorder] 录制功能已禁用");
        return true;
    }

    if (!connect()) {
        log_error("[RedisRecorder] Redis 连接失败");
        return false;
    }

    running_.store(true);
    log_info("[RedisRecorder] 启动成功，开始录制行情数据");
    return true;
}

void RedisRecorder::stop() {
    if (!running_.load()) {
        return;
    }

    running_.store(false);
    disconnect();

    log_info("[RedisRecorder] 已停止");
    log_info("[RedisRecorder] 统计: Trades=" + std::to_string(trade_count_.load()) +
             " K线=" + std::to_string(kline_count_.load()) +
             " 深度=" + std::to_string(orderbook_count_.load()) +
             " 资金费率=" + std::to_string(funding_rate_count_.load()) +
             " 错误=" + std::to_string(error_count_.load()));
}

bool RedisRecorder::is_connected() const {
    return context_ != nullptr && context_->err == 0;
}

bool RedisRecorder::connect() {
    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (context_) {
        redisFree(context_);
        context_ = nullptr;
    }

    context_ = redisConnect(config_.host.c_str(), config_.port);

    if (context_ == nullptr || context_->err) {
        if (context_) {
            log_error("[RedisRecorder] 连接失败: " + std::string(context_->errstr));
            redisFree(context_);
            context_ = nullptr;
        } else {
            log_error("[RedisRecorder] 无法分配 Redis context");
        }
        return false;
    }

    // 认证
    if (!config_.password.empty()) {
        redisReply* reply = (redisReply*)redisCommand(context_, "AUTH %s", config_.password.c_str());
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            log_error("[RedisRecorder] 认证失败");
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
    }

    // 选择数据库
    if (config_.db != 0) {
        redisReply* reply = (redisReply*)redisCommand(context_, "SELECT %d", config_.db);
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            log_error("[RedisRecorder] 选择数据库失败");
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
    }

    // 测试连接
    redisReply* reply = (redisReply*)redisCommand(context_, "PING");
    if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
        log_error("[RedisRecorder] PING 失败");
        if (reply) freeReplyObject(reply);
        return false;
    }
    freeReplyObject(reply);

    log_info("[RedisRecorder] Redis 连接成功: " + config_.host + ":" + std::to_string(config_.port));
    return true;
}

void RedisRecorder::disconnect() {
    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (context_) {
        redisFree(context_);
        context_ = nullptr;
    }
}

bool RedisRecorder::reconnect() {
    disconnect();
    return connect();
}

void RedisRecorder::record_trade(const std::string& symbol, const std::string& exchange,
                                  const nlohmann::json& data) {
    if (!running_.load() || !config_.enabled) return;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return;
        }
    }

    // 构建完整数据
    nlohmann::json trade_data = data;
    trade_data["exchange"] = exchange;
    trade_data["symbol"] = symbol;

    std::string key = "trades:" + symbol;
    std::string value = trade_data.dump();

    // LPUSH 添加到列表头部
    redisReply* reply = (redisReply*)redisCommand(
        context_, "LPUSH %s %s", key.c_str(), value.c_str()
    );

    if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
        error_count_++;
        if (reply) freeReplyObject(reply);
        return;
    }
    freeReplyObject(reply);

    // LTRIM 保持列表长度
    reply = (redisReply*)redisCommand(
        context_, "LTRIM %s 0 %d", key.c_str(), config_.max_trades_per_symbol - 1
    );
    if (reply) freeReplyObject(reply);

    // 设置过期时间
    reply = (redisReply*)redisCommand(
        context_, "EXPIRE %s %d", key.c_str(), config_.expire_seconds
    );
    if (reply) freeReplyObject(reply);

    trade_count_++;
}

void RedisRecorder::record_kline(const std::string& symbol, const std::string& interval,
                                  const std::string& exchange, const nlohmann::json& data) {
    if (!running_.load() || !config_.enabled) return;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return;
        }
    }

    // 获取时间戳
    int64_t timestamp = data.value("timestamp", 0);
    if (timestamp == 0) {
        // 尝试其他字段
        timestamp = data.value("ts", 0);
        if (timestamp == 0) {
            timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
        }
    }

    // 构建完整数据
    nlohmann::json kline_data = data;
    kline_data["exchange"] = exchange;
    kline_data["symbol"] = symbol;
    kline_data["interval"] = interval;
    if (!kline_data.contains("timestamp")) {
        kline_data["timestamp"] = timestamp;
    }

    std::string key = "kline:" + symbol + ":" + interval;
    std::string value = kline_data.dump();

    // ZADD 添加到有序集合（score=timestamp, member=json）
    redisReply* reply = (redisReply*)redisCommand(
        context_, "ZADD %s %lld %s",
        key.c_str(), (long long)timestamp, value.c_str()
    );

    if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
        error_count_++;
        if (reply) freeReplyObject(reply);
        return;
    }
    freeReplyObject(reply);

    // ZREMRANGEBYRANK 保持有序集合大小
    reply = (redisReply*)redisCommand(
        context_, "ZREMRANGEBYRANK %s 0 -%d",
        key.c_str(), config_.max_klines_per_symbol + 1
    );
    if (reply) freeReplyObject(reply);

    // 设置过期时间
    reply = (redisReply*)redisCommand(
        context_, "EXPIRE %s %d", key.c_str(), config_.expire_seconds
    );
    if (reply) freeReplyObject(reply);

    kline_count_++;
}

void RedisRecorder::record_orderbook(const std::string& symbol, const std::string& exchange,
                                      const nlohmann::json& data) {
    if (!running_.load() || !config_.enabled) return;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return;
        }
    }

    // 构建完整数据
    nlohmann::json orderbook_data = data;
    orderbook_data["exchange"] = exchange;
    orderbook_data["symbol"] = symbol;

    std::string key = "orderbook:" + symbol;
    std::string value = orderbook_data.dump();

    // SET 只保留最新快照
    redisReply* reply = (redisReply*)redisCommand(
        context_, "SET %s %s EX %d",
        key.c_str(), value.c_str(), config_.expire_seconds
    );

    if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
        error_count_++;
        if (reply) freeReplyObject(reply);
        return;
    }
    freeReplyObject(reply);

    orderbook_count_++;
}

void RedisRecorder::record_funding_rate(const std::string& symbol, const std::string& exchange,
                                         const nlohmann::json& data) {
    if (!running_.load() || !config_.enabled) return;

    std::lock_guard<std::mutex> lock(redis_mutex_);

    if (!is_connected()) {
        if (!reconnect()) {
            error_count_++;
            return;
        }
    }

    // 获取时间戳
    int64_t timestamp = data.value("timestamp", 0);
    if (timestamp == 0) {
        timestamp = data.value("ts", 0);
        if (timestamp == 0) {
            timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();
        }
    }

    // 构建完整数据
    nlohmann::json fr_data = data;
    fr_data["exchange"] = exchange;
    fr_data["symbol"] = symbol;
    if (!fr_data.contains("timestamp")) {
        fr_data["timestamp"] = timestamp;
    }

    std::string key = "funding_rate:" + symbol;
    std::string value = fr_data.dump();

    // ZADD 添加到有序集合
    redisReply* reply = (redisReply*)redisCommand(
        context_, "ZADD %s %lld %s",
        key.c_str(), (long long)timestamp, value.c_str()
    );

    if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
        error_count_++;
        if (reply) freeReplyObject(reply);
        return;
    }
    freeReplyObject(reply);

    // 保持最近 100 条
    reply = (redisReply*)redisCommand(
        context_, "ZREMRANGEBYRANK %s 0 -101", key.c_str()
    );
    if (reply) freeReplyObject(reply);

    // 设置过期时间
    reply = (redisReply*)redisCommand(
        context_, "EXPIRE %s %d", key.c_str(), config_.expire_seconds
    );
    if (reply) freeReplyObject(reply);

    funding_rate_count_++;
}

void RedisRecorder::log_info(const std::string& msg) {
    std::cout << msg << std::endl;
}

void RedisRecorder::log_error(const std::string& msg) {
    std::cerr << msg << std::endl;
}

} // namespace server
} // namespace trading
