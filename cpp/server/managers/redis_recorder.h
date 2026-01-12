/**
 * @file redis_recorder.h
 * @brief Redis 数据录制模块 - 将行情数据实时存入 Redis
 *
 * 功能：
 * 1. 订阅 ZMQ 行情数据（trades, K线, 深度, 资金费率）
 * 2. 将数据存入 Redis（除订单数据外）
 * 3. 集成到主服务器，随服务器启动
 *
 * Redis 数据结构：
 * - trades:{symbol} -> List (最近的 trades)
 * - kline:{symbol}:{interval} -> Sorted Set (score=timestamp)
 * - orderbook:{symbol} -> Hash (最新深度快照)
 * - funding_rate:{symbol} -> Sorted Set (score=timestamp)
 *
 * @author Sequence Team
 * @date 2026-01
 */

#pragma once

#include <string>
#include <atomic>
#include <thread>
#include <mutex>
#include <memory>
#include <functional>

#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>

namespace trading {
namespace server {

/**
 * @brief Redis 配置
 */
struct RedisConfig {
    std::string host = "127.0.0.1";
    int port = 6379;
    std::string password;
    int db = 0;
    int expire_seconds = 2 * 60 * 60;      // 数据过期时间（默认2小时）
    int max_trades_per_symbol = 10000;      // 每个币种最大 trades 数量
    int max_klines_per_symbol = 7200;       // 每个币种最大 K 线数量
    bool enabled = true;                    // 是否启用录制
};

/**
 * @brief Redis 数据录制器
 *
 * 接收行情数据并存入 Redis，用于策略获取历史数据
 */
class RedisRecorder {
public:
    RedisRecorder();
    ~RedisRecorder();

    /**
     * @brief 设置配置
     */
    void set_config(const RedisConfig& config);

    /**
     * @brief 获取配置
     */
    const RedisConfig& get_config() const { return config_; }

    /**
     * @brief 启动录制器
     * @return 是否成功
     */
    bool start();

    /**
     * @brief 停止录制器
     */
    void stop();

    /**
     * @brief 是否正在运行
     */
    bool is_running() const { return running_.load(); }

    /**
     * @brief 是否已连接 Redis
     */
    bool is_connected() const;

    // ==================== 数据录制接口 ====================

    /**
     * @brief 录制 trade 数据
     * @param symbol 交易对
     * @param exchange 交易所 (okx/binance)
     * @param data 原始数据 JSON
     */
    void record_trade(const std::string& symbol, const std::string& exchange,
                      const nlohmann::json& data);

    /**
     * @brief 录制 K 线数据
     * @param symbol 交易对
     * @param interval K 线周期
     * @param exchange 交易所
     * @param data 原始数据 JSON
     */
    void record_kline(const std::string& symbol, const std::string& interval,
                      const std::string& exchange, const nlohmann::json& data);

    /**
     * @brief 录制深度数据（只保留最新快照）
     * @param symbol 交易对
     * @param exchange 交易所
     * @param data 原始数据 JSON
     */
    void record_orderbook(const std::string& symbol, const std::string& exchange,
                          const nlohmann::json& data);

    /**
     * @brief 录制资金费率
     * @param symbol 交易对
     * @param exchange 交易所
     * @param data 原始数据 JSON
     */
    void record_funding_rate(const std::string& symbol, const std::string& exchange,
                             const nlohmann::json& data);

    // ==================== 统计 ====================

    uint64_t get_trade_count() const { return trade_count_.load(); }
    uint64_t get_kline_count() const { return kline_count_.load(); }
    uint64_t get_orderbook_count() const { return orderbook_count_.load(); }
    uint64_t get_funding_rate_count() const { return funding_rate_count_.load(); }
    uint64_t get_error_count() const { return error_count_.load(); }

private:
    /**
     * @brief 连接到 Redis
     */
    bool connect();

    /**
     * @brief 断开 Redis 连接
     */
    void disconnect();

    /**
     * @brief 重连逻辑
     */
    bool reconnect();

    /**
     * @brief 执行 Redis 命令（带重试）
     */
    bool execute_command(const char* format, ...);

    /**
     * @brief 日志输出
     */
    void log_info(const std::string& msg);
    void log_error(const std::string& msg);

private:
    RedisConfig config_;
    redisContext* context_ = nullptr;
    std::mutex redis_mutex_;
    std::atomic<bool> running_{false};

    // 统计
    std::atomic<uint64_t> trade_count_{0};
    std::atomic<uint64_t> kline_count_{0};
    std::atomic<uint64_t> orderbook_count_{0};
    std::atomic<uint64_t> funding_rate_count_{0};
    std::atomic<uint64_t> error_count_{0};
};

// 全局 Redis 录制器实例
extern std::unique_ptr<RedisRecorder> g_redis_recorder;

} // namespace server
} // namespace trading
