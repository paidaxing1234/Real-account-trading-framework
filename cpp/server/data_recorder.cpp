/**
 * @file data_recorder.cpp
 * @brief 数据记录器 - 将实盘行情数据存入 Redis
 *
 * 功能：
 * 1. 被动监听 trade-server-main 发布的行情数据（ZMQ SUB）
 * 2. 记录所有通过 ZMQ 通道接收到的 1min K线数据
 * 3. 将 1min K线数据存入 Redis，过期时间 2 个月
 * 4. 聚合 1min K线为 5min, 15min, 30min, 1h
 * 5. 不同周期使用不同的过期时间（1min/5min/15min/30min: 2个月，1h: 6个月）
 *
 * 架构说明：
 * - trade-server-main 通过 WebSocket 订阅交易所的全市场合约
 * - data_recorder 只负责被动接收和记录数据，不发送订阅请求
 *
 * Redis 数据结构：
 * - kline:{exchange}:{symbol}:{interval} -> Sorted Set (K线数据，score=timestamp)
 *
 * 使用方法：
 *   ./data_recorder --redis-host 127.0.0.1 --redis-port 6379
 *
 * 依赖：
 *   - ZeroMQ (libzmq + cppzmq)
 *   - hiredis (Redis C 客户端)
 *   - nlohmann/json
 *
 * @author Sequence Team
 * @date 2025-12
 */

#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <atomic>
#include <thread>
#include <chrono>
#include <csignal>
#include <cstring>
#include <iomanip>
#include <mutex>

#include <zmq.hpp>
#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>

using namespace std::chrono;
using json = nlohmann::json;

// ============================================================
// 配置
// ============================================================

namespace Config {
    // ZMQ IPC 地址（与实盘服务器一致）
    const std::string MARKET_DATA_IPC = "ipc:///tmp/seq_md.ipc";

    // Redis 配置
    std::string redis_host = "127.0.0.1";
    int redis_port = 6379;
    std::string redis_password = "";

    // 数据过期时间（秒）
    const int EXPIRE_2_MONTHS = 60 * 24 * 60 * 60;  // 2个月
    const int EXPIRE_6_MONTHS = 180 * 24 * 60 * 60; // 6个月

    // 每个币种/周期保留的最大 K 线数量
    int max_klines_1m = 60 * 24 * 60;      // 2个月的1分钟K线
    int max_klines_5m = 12 * 24 * 60;      // 2个月的5分钟K线
    int max_klines_15m = 4 * 24 * 60;      // 2个月的15分钟K线
    int max_klines_30m = 2 * 24 * 60;      // 2个月的30分钟K线
    int max_klines_1h = 24 * 180;          // 6个月的1小时K线
    int max_klines_4h = 6 * 60;            // 2个月的4小时K线
    int max_klines_8h = 3 * 60;            // 2个月的8小时K线
}

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};

// 统计
std::atomic<uint64_t> g_kline_1m_count{0};
std::atomic<uint64_t> g_kline_5m_count{0};
std::atomic<uint64_t> g_kline_15m_count{0};
std::atomic<uint64_t> g_kline_30m_count{0};
std::atomic<uint64_t> g_kline_1h_count{0};
std::atomic<uint64_t> g_kline_4h_count{0};
std::atomic<uint64_t> g_kline_8h_count{0};
std::atomic<uint64_t> g_redis_write_count{0};
std::atomic<uint64_t> g_redis_error_count{0};

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[DataRecorder] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
}

// ============================================================
// K线数据结构
// ============================================================

struct KlineData {
    int64_t timestamp;
    double open;
    double high;
    double low;
    double close;
    double volume;

    KlineData() : timestamp(0), open(0), high(0), low(0), close(0), volume(0) {}

    KlineData(const json& j) {
        timestamp = j.value("timestamp", 0LL);
        open = j.value("open", 0.0);
        high = j.value("high", 0.0);
        low = j.value("low", 0.0);
        close = j.value("close", 0.0);
        volume = j.value("volume", 0.0);
    }

    json to_json(const std::string& exchange, const std::string& symbol, const std::string& interval) const {
        return {
            {"type", "kline"},
            {"exchange", exchange},
            {"symbol", symbol},
            {"interval", interval},
            {"timestamp", timestamp},
            {"open", open},
            {"high", high},
            {"low", low},
            {"close", close},
            {"volume", volume}
        };
    }
};

// ============================================================
// K线聚合器
// ============================================================

class KlineAggregator {
public:
    /**
     * @brief 聚合 1min K线到更大周期
     * @param interval_minutes 目标周期（分钟）
     * @param kline_1m 1分钟K线数据
     * @return 是否生成了新的聚合K线
     *
     * 修改逻辑：只有当收集到完整数量的1分钟K线后，才输出聚合K线
     * 例如：5分钟K线需要等5根1分钟K线都完成后才聚合
     */
    bool aggregate(int interval_minutes, const KlineData& kline_1m, KlineData& output) {
        // 计算当前K线所属的聚合周期起始时间
        int64_t period_start = (kline_1m.timestamp / (interval_minutes * 60 * 1000)) * (interval_minutes * 60 * 1000);

        auto& state = aggregation_state_[interval_minutes];

        // 如果是新周期
        if (state.timestamp != 0 && period_start != state.timestamp) {
            // 检查上一个周期是否完整（收集到足够数量的1分钟K线）
            if (state.count == interval_minutes) {
                // 上一个周期完整，输出聚合K线
                output = state.kline;

                // 重置并开始新周期
                state.timestamp = period_start;
                state.kline.timestamp = period_start;
                state.kline.open = kline_1m.open;
                state.kline.high = kline_1m.high;
                state.kline.low = kline_1m.low;
                state.kline.close = kline_1m.close;
                state.kline.volume = kline_1m.volume;
                state.count = 1;

                return true;
            } else {
                // 上一个周期不完整，丢弃并开始新周期
                state.timestamp = period_start;
                state.kline.timestamp = period_start;
                state.kline.open = kline_1m.open;
                state.kline.high = kline_1m.high;
                state.kline.low = kline_1m.low;
                state.kline.close = kline_1m.close;
                state.kline.volume = kline_1m.volume;
                state.count = 1;

                return false;
            }
        }

        // 初始化或更新当前周期
        if (state.timestamp == 0) {
            // 第一次初始化
            state.timestamp = period_start;
            state.kline.timestamp = period_start;
            state.kline.open = kline_1m.open;
            state.kline.high = kline_1m.high;
            state.kline.low = kline_1m.low;
            state.kline.close = kline_1m.close;
            state.kline.volume = kline_1m.volume;
            state.count = 1;
        } else {
            // 更新当前周期
            state.kline.high = std::max(state.kline.high, kline_1m.high);
            state.kline.low = std::min(state.kline.low, kline_1m.low);
            state.kline.close = kline_1m.close;
            state.kline.volume += kline_1m.volume;
            state.count++;
        }

        return false;
    }

private:
    struct AggregationState {
        int64_t timestamp = 0;  // 当前聚合周期的起始时间
        KlineData kline;        // 当前聚合的K线数据
        int count = 0;          // 已收集的1分钟K线数量
    };

    std::map<int, AggregationState> aggregation_state_;  // interval_minutes -> AggregationState
};

// ============================================================
// Redis 客户端封装
// ============================================================

class RedisClient {
public:
    RedisClient() : context_(nullptr) {}

    ~RedisClient() {
        disconnect();
    }

    bool connect(const std::string& host, int port, const std::string& password = "") {
        context_ = redisConnect(host.c_str(), port);

        if (context_ == nullptr || context_->err) {
            if (context_) {
                std::cerr << "[Redis] 连接失败: " << context_->errstr << "\n";
                redisFree(context_);
                context_ = nullptr;
            } else {
                std::cerr << "[Redis] 无法分配 context\n";
            }
            return false;
        }

        // 如果有密码，进行认证
        if (!password.empty()) {
            redisReply* reply = (redisReply*)redisCommand(context_, "AUTH %s", password.c_str());
            if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
                std::cerr << "[Redis] 认证失败\n";
                if (reply) freeReplyObject(reply);
                return false;
            }
            freeReplyObject(reply);
        }

        // 测试连接
        redisReply* reply = (redisReply*)redisCommand(context_, "PING");
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            std::cerr << "[Redis] PING 失败\n";
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);

        std::cout << "[Redis] 连接成功: " << host << ":" << port << "\n";
        return true;
    }

    void disconnect() {
        if (context_) {
            redisFree(context_);
            context_ = nullptr;
        }
    }

    bool is_connected() const {
        return context_ != nullptr && context_->err == 0;
    }

    /**
     * @brief 存储 K 线数据到 Redis
     *
     * Key: kline:{exchange}:{symbol}:{interval} -> Sorted Set (score=timestamp, member=json)
     */
    bool store_kline(const std::string& exchange, const std::string& symbol,
                     const std::string& interval, const json& kline_data) {
        if (!is_connected()) return false;

        int64_t timestamp = kline_data.value("timestamp", 0LL);
        if (timestamp == 0) return false;

        // Key: Sorted Set 存储所有 K 线时间戳
        std::string zset_key = "kline:" + exchange + ":" + symbol + ":" + interval;
        std::string value = kline_data.dump();

        // ZADD 添加到有序集合（score=timestamp, member=json）
        redisReply* reply = (redisReply*)redisCommand(
            context_, "ZADD %s %lld %s",
            zset_key.c_str(), (long long)timestamp, value.c_str()
        );

        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            g_redis_error_count++;
            if (reply) {
                std::cerr << "[Redis] ZADD 错误: " << reply->str << "\n";
                freeReplyObject(reply);
            }
            return false;
        }
        freeReplyObject(reply);

        // 根据周期设置不同的过期时间和最大数量
        int expire_seconds;
        int max_count;

        if (interval == "1m") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_1m;
        } else if (interval == "5m") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_5m;
        } else if (interval == "15m") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_15m;
        } else if (interval == "30m") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_30m;
        } else if (interval == "1h") {
            expire_seconds = Config::EXPIRE_6_MONTHS;
            max_count = Config::max_klines_1h;
        } else if (interval == "4h") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_4h;
        } else if (interval == "8h") {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = Config::max_klines_8h;
        } else {
            expire_seconds = Config::EXPIRE_2_MONTHS;
            max_count = 10000;
        }

        // ZREMRANGEBYRANK 保持有序集合大小
        reply = (redisReply*)redisCommand(
            context_, "ZREMRANGEBYRANK %s 0 -%d",
            zset_key.c_str(), max_count + 1
        );
        if (reply) freeReplyObject(reply);

        // 设置过期时间
        reply = (redisReply*)redisCommand(
            context_, "EXPIRE %s %d", zset_key.c_str(), expire_seconds
        );
        if (reply) freeReplyObject(reply);

        g_redis_write_count++;
        return true;
    }

    /**
     * @brief 检查 Redis 连接状态
     */
    bool ping() {
        if (!is_connected()) return false;

        redisReply* reply = (redisReply*)redisCommand(context_, "PING");
        bool ok = (reply != nullptr && reply->type == REDIS_REPLY_STATUS);
        if (reply) freeReplyObject(reply);
        return ok;
    }

private:
    redisContext* context_;
};

// ============================================================
// 数据记录器
// ============================================================

class DataRecorder {
public:
    DataRecorder() : zmq_context_(1) {}

    ~DataRecorder() {
        stop();
    }

    bool start() {
        // 连接 Redis
        if (!redis_.connect(Config::redis_host, Config::redis_port, Config::redis_password)) {
            std::cerr << "[DataRecorder] Redis 连接失败\n";
            return false;
        }

        // 创建 ZMQ socket - 只需要 SUB socket 被动接收行情数据
        try {
            // 行情订阅 (SUB) - 被动接收 trade-server-main 发布的所有行情数据
            market_sub_ = std::make_unique<zmq::socket_t>(zmq_context_, zmq::socket_type::sub);
            market_sub_->connect(Config::MARKET_DATA_IPC);
            market_sub_->set(zmq::sockopt::subscribe, "");  // 订阅所有消息
            market_sub_->set(zmq::sockopt::rcvtimeo, 100);  // 100ms 超时
            std::cout << "[ZMQ] 行情通道: " << Config::MARKET_DATA_IPC << "\n";
            std::cout << "[ZMQ] 被动监听模式 - 记录所有接收到的K线数据\n";

        } catch (const zmq::error_t& e) {
            std::cerr << "[ZMQ] 连接失败: " << e.what() << "\n";
            return false;
        }

        std::cout << "[DataRecorder] 初始化完成\n";
        return true;
    }

    void stop() {
        // 关闭 ZMQ socket
        if (market_sub_) market_sub_->close();

        // 断开 Redis
        redis_.disconnect();
    }

    /**
     * @brief 主循环：接收数据并存入 Redis
     */
    void run() {
        std::cout << "[DataRecorder] 开始运行...\n";
        std::cout << "  - 被动监听 trade-server-main 发布的所有K线数据\n";
        std::cout << "  - 1min/5min/15min/30min/4h/8h 过期时间: 2 个月\n";
        std::cout << "  - 1h 过期时间: 6 个月\n";
        std::cout << "  - 按 Ctrl+C 停止\n\n";

        auto last_status_time = steady_clock::now();

        while (g_running.load()) {
            // 接收行情数据
            zmq::message_t msg;
            zmq::recv_result_t result;

            try {
                result = market_sub_->recv(msg, zmq::recv_flags::dontwait);
            } catch (const zmq::error_t& e) {
                if (e.num() != EAGAIN) {
                    std::cerr << "[ZMQ] 接收错误: " << e.what() << "\n";
                }
                std::this_thread::sleep_for(microseconds(100));
                continue;
            }

            if (result.has_value()) {
                std::string data_str(static_cast<char*>(msg.data()), msg.size());

                // 检查消息格式：topic|json_data
                // 如果包含 '|'，则分割并只解析后半部分
                size_t separator_pos = data_str.find('|');
                if (separator_pos != std::string::npos) {
                    // 跳过 topic 部分，只保留 JSON 数据
                    data_str = data_str.substr(separator_pos + 1);
                }

                try {
                    json data = json::parse(data_str);
                    process_market_data(data);
                } catch (const json::parse_error& e) {
                    std::cerr << "[JSON] 解析错误: " << e.what() << "\n";
                    std::cerr << "[JSON] 原始数据: " << data_str.substr(0, 100) << "...\n";
                }
            }

            // 每 10 秒打印状态
            auto now = steady_clock::now();
            if (duration_cast<seconds>(now - last_status_time).count() >= 10) {
                last_status_time = now;
                print_status();
            }

            // 短暂休眠
            std::this_thread::sleep_for(microseconds(100));
        }
    }

private:
    void process_market_data(const json& data) {
        std::string type = data.value("type", "");

        if (type == "kline") {
            std::string exchange = data.value("exchange", "okx");
            std::string symbol = data.value("symbol", "");
            std::string interval = data.value("interval", "");

            if (symbol.empty() || interval != "1m") {
                return;  // 只处理 1min K线
            }

            // 解析 1min K线数据
            KlineData kline_1m(data);

            // 存储 1min K线
            redis_.store_kline(exchange, symbol, "1m", data);
            g_kline_1m_count++;

            // 获取该币种的聚合器
            std::string key = exchange + ":" + symbol;
            std::lock_guard<std::mutex> lock(aggregator_mutex_);
            auto& aggregator = aggregators_[key];

            // 聚合到 5min
            KlineData kline_5m;
            if (aggregator.aggregate(5, kline_1m, kline_5m)) {
                json j = kline_5m.to_json(exchange, symbol, "5m");
                redis_.store_kline(exchange, symbol, "5m", j);
                g_kline_5m_count++;
            }

            // 聚合到 15min
            KlineData kline_15m;
            if (aggregator.aggregate(15, kline_1m, kline_15m)) {
                json j = kline_15m.to_json(exchange, symbol, "15m");
                redis_.store_kline(exchange, symbol, "15m", j);
                g_kline_15m_count++;
            }

            // 聚合到 30min
            KlineData kline_30m;
            if (aggregator.aggregate(30, kline_1m, kline_30m)) {
                json j = kline_30m.to_json(exchange, symbol, "30m");
                redis_.store_kline(exchange, symbol, "30m", j);
                g_kline_30m_count++;
            }

            // 聚合到 1h
            KlineData kline_1h;
            if (aggregator.aggregate(60, kline_1m, kline_1h)) {
                json j = kline_1h.to_json(exchange, symbol, "1h");
                redis_.store_kline(exchange, symbol, "1h", j);
                g_kline_1h_count++;
            }

            // 聚合到 4h
            KlineData kline_4h;
            if (aggregator.aggregate(240, kline_1m, kline_4h)) {
                json j = kline_4h.to_json(exchange, symbol, "4h");
                redis_.store_kline(exchange, symbol, "4h", j);
                g_kline_4h_count++;
            }

            // 聚合到 8h
            KlineData kline_8h;
            if (aggregator.aggregate(480, kline_1m, kline_8h)) {
                json j = kline_8h.to_json(exchange, symbol, "8h");
                redis_.store_kline(exchange, symbol, "8h", j);
                g_kline_8h_count++;
            }
        }
    }

    void print_status() {
        auto now = system_clock::now();
        auto time_t = system_clock::to_time_t(now);
        std::tm* tm = std::localtime(&time_t);

        std::cout << "[" << std::put_time(tm, "%H:%M:%S") << "] "
                  << "1m: " << g_kline_1m_count.load()
                  << " | 5m: " << g_kline_5m_count.load()
                  << " | 15m: " << g_kline_15m_count.load()
                  << " | 30m: " << g_kline_30m_count.load()
                  << " | 1h: " << g_kline_1h_count.load()
                  << " | 4h: " << g_kline_4h_count.load()
                  << " | 8h: " << g_kline_8h_count.load()
                  << " | Redis写入: " << g_redis_write_count.load()
                  << " | 错误: " << g_redis_error_count.load()
                  << "\n";
    }

private:
    zmq::context_t zmq_context_;
    std::unique_ptr<zmq::socket_t> market_sub_;
    RedisClient redis_;

    // K线聚合器（每个 exchange:symbol 一个）
    std::map<std::string, KlineAggregator> aggregators_;
    std::mutex aggregator_mutex_;
};

// ============================================================
// 命令行参数解析
// ============================================================

void print_usage(const char* prog) {
    std::cout << "用法: " << prog << " [选项]\n"
              << "\n"
              << "选项:\n"
              << "  --redis-host HOST    Redis 主机 (默认: 127.0.0.1)\n"
              << "  --redis-port PORT    Redis 端口 (默认: 6379)\n"
              << "  --redis-pass PASS    Redis 密码 (默认: 无)\n"
              << "  -h, --help           显示帮助\n"
              << "\n"
              << "示例:\n"
              << "  " << prog << " --redis-host 192.168.1.100 --redis-port 6379\n";
}

void parse_args(int argc, char* argv[]) {
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];

        if (arg == "-h" || arg == "--help") {
            print_usage(argv[0]);
            exit(0);
        }
        else if (arg == "--redis-host" && i + 1 < argc) {
            Config::redis_host = argv[++i];
        }
        else if (arg == "--redis-port" && i + 1 < argc) {
            Config::redis_port = std::stoi(argv[++i]);
        }
        else if (arg == "--redis-pass" && i + 1 < argc) {
            Config::redis_password = argv[++i];
        }
    }
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "    Sequence 数据记录器 (DataRecorder)\n";
    std::cout << "    实盘 1min K线 -> Redis (聚合多周期)\n";
    std::cout << "========================================\n\n";

    // 解析命令行参数
    parse_args(argc, argv);

    // 打印配置
    std::cout << "[配置]\n";
    std::cout << "  Redis: " << Config::redis_host << ":" << Config::redis_port << "\n";
    std::cout << "  模式: 被动监听 trade-server-main 发布的所有K线数据\n";
    std::cout << "  聚合周期: 1min -> 5min, 15min, 30min, 1h, 4h, 8h\n";
    std::cout << "  过期时间: 1m/5m/15m/30m/4h/8h = 2个月, 1h = 6个月\n\n";

    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    // 创建并启动数据记录器
    DataRecorder recorder;

    if (!recorder.start()) {
        std::cerr << "[错误] 启动失败\n";
        return 1;
    }

    // 主循环 - 被动接收并记录所有K线数据
    recorder.run();

    // 停止
    recorder.stop();

    // 打印统计
    std::cout << "\n========================================\n";
    std::cout << "  数据记录器已停止\n";
    std::cout << "  1min K线: " << g_kline_1m_count.load() << " 条\n";
    std::cout << "  5min K线: " << g_kline_5m_count.load() << " 条\n";
    std::cout << "  15min K线: " << g_kline_15m_count.load() << " 条\n";
    std::cout << "  30min K线: " << g_kline_30m_count.load() << " 条\n";
    std::cout << "  1h K线: " << g_kline_1h_count.load() << " 条\n";
    std::cout << "  4h K线: " << g_kline_4h_count.load() << " 条\n";
    std::cout << "  8h K线: " << g_kline_8h_count.load() << " 条\n";
    std::cout << "  Redis 写入: " << g_redis_write_count.load() << " 次\n";
    std::cout << "  Redis 错误: " << g_redis_error_count.load() << " 次\n";
    std::cout << "========================================\n";

    return 0;
}
