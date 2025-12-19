/**
 * @file data_recorder.cpp
 * @brief 数据记录器 - 将实盘行情数据存入 Redis
 * 
 * 功能：
 * 1. 像策略一样连接到实盘服务器（ZMQ SUB）
 * 2. 订阅所有 trades 和 K 线数据
 * 3. 将数据存入 Redis，过期时间 2 小时
 * 
 * Redis 数据结构：
 * - trades:{symbol}:list -> List (最近的 trades)
 * - kline:{symbol}:{interval}:list -> List (K线数据)
 * - kline:{symbol}:{interval}:{timestamp} -> Hash (单根K线)
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
#include <atomic>
#include <thread>
#include <chrono>
#include <csignal>
#include <cstring>
#include <iomanip>

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
    const std::string MARKET_DATA_IPC = "ipc:///tmp/trading_md.ipc";
    const std::string SUBSCRIBE_IPC = "ipc:///tmp/trading_sub.ipc";
    
    // Redis 配置
    std::string redis_host = "127.0.0.1";
    int redis_port = 6379;
    std::string redis_password = "";
    
    // 数据过期时间（秒）
    int expire_seconds = 2 * 60 * 60;  // 2小时
    
    // 每个币种保留的最大 trades 数量
    int max_trades_per_symbol = 10000;
    
    // 每个币种/周期保留的最大 K 线数量
    int max_klines_per_symbol = 7200;  // 2小时的1秒K线
    
    // 要订阅的币种列表
    std::vector<std::string> symbols = {
        // 现货
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "DOGE-USDT",
        "ADA-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT", "MATIC-USDT",
        "UNI-USDT", "ATOM-USDT", "LTC-USDT", "ETC-USDT", "FIL-USDT",
        "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT", "INJ-USDT",
        // 合约
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
        "DOGE-USDT-SWAP", "ADA-USDT-SWAP", "AVAX-USDT-SWAP", "DOT-USDT-SWAP",
        "LINK-USDT-SWAP", "MATIC-USDT-SWAP"
    };
    
    // 要订阅的 K 线周期
    std::vector<std::string> kline_intervals = {"1s", "1m", "5m", "1H"};
}

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};

// 统计
std::atomic<uint64_t> g_trade_count{0};
std::atomic<uint64_t> g_kline_count{0};
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
     * @brief 存储 trade 数据到 Redis List
     * 
     * Key: trades:{symbol}
     * 使用 LPUSH + LTRIM 保持固定长度
     */
    bool store_trade(const std::string& symbol, const json& trade_data) {
        if (!is_connected()) return false;
        
        std::string key = "trades:" + symbol;
        std::string value = trade_data.dump();
        
        // LPUSH 添加到列表头部
        redisReply* reply = (redisReply*)redisCommand(
            context_, "LPUSH %s %s", key.c_str(), value.c_str()
        );
        
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            g_redis_error_count++;
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
        
        // LTRIM 保持列表长度
        reply = (redisReply*)redisCommand(
            context_, "LTRIM %s 0 %d", key.c_str(), Config::max_trades_per_symbol - 1
        );
        if (reply) freeReplyObject(reply);
        
        // 设置过期时间
        reply = (redisReply*)redisCommand(
            context_, "EXPIRE %s %d", key.c_str(), Config::expire_seconds
        );
        if (reply) freeReplyObject(reply);
        
        g_redis_write_count++;
        return true;
    }
    
    /**
     * @brief 存储 K 线数据到 Redis
     * 
     * Key 1: kline:{symbol}:{interval} -> Sorted Set (score=timestamp)
     * Key 2: kline:{symbol}:{interval}:{timestamp} -> Hash (OHLCV)
     */
    bool store_kline(const std::string& symbol, const std::string& interval, 
                     const json& kline_data) {
        if (!is_connected()) return false;
        
        int64_t timestamp = kline_data.value("timestamp", 0);
        
        // Key 1: Sorted Set 存储所有 K 线时间戳
        std::string zset_key = "kline:" + symbol + ":" + interval;
        std::string value = kline_data.dump();
        
        // ZADD 添加到有序集合（score=timestamp, member=json）
        redisReply* reply = (redisReply*)redisCommand(
            context_, "ZADD %s %lld %s", 
            zset_key.c_str(), (long long)timestamp, value.c_str()
        );
        
        if (reply == nullptr || reply->type == REDIS_REPLY_ERROR) {
            g_redis_error_count++;
            if (reply) freeReplyObject(reply);
            return false;
        }
        freeReplyObject(reply);
        
        // ZREMRANGEBYRANK 保持有序集合大小
        reply = (redisReply*)redisCommand(
            context_, "ZREMRANGEBYRANK %s 0 -%d", 
            zset_key.c_str(), Config::max_klines_per_symbol + 1
        );
        if (reply) freeReplyObject(reply);
        
        // 设置过期时间
        reply = (redisReply*)redisCommand(
            context_, "EXPIRE %s %d", zset_key.c_str(), Config::expire_seconds
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
        
        // 创建 ZMQ sockets
        try {
            // 行情订阅 (SUB)
            market_sub_ = std::make_unique<zmq::socket_t>(zmq_context_, zmq::socket_type::sub);
            market_sub_->connect(Config::MARKET_DATA_IPC);
            market_sub_->set(zmq::sockopt::subscribe, "");
            market_sub_->set(zmq::sockopt::rcvtimeo, 100);  // 100ms 超时
            std::cout << "[ZMQ] 行情通道: " << Config::MARKET_DATA_IPC << "\n";
            
            // 订阅管理 (PUSH)
            subscribe_push_ = std::make_unique<zmq::socket_t>(zmq_context_, zmq::socket_type::push);
            subscribe_push_->connect(Config::SUBSCRIBE_IPC);
            std::cout << "[ZMQ] 订阅通道: " << Config::SUBSCRIBE_IPC << "\n";
            
        } catch (const zmq::error_t& e) {
            std::cerr << "[ZMQ] 连接失败: " << e.what() << "\n";
            return false;
        }
        
        std::cout << "[DataRecorder] 初始化完成\n";
        return true;
    }
    
    void stop() {
        // 取消订阅
        for (const auto& symbol : Config::symbols) {
            unsubscribe_trades(symbol);
            for (const auto& interval : Config::kline_intervals) {
                unsubscribe_kline(symbol, interval);
            }
        }
        
        // 关闭 ZMQ sockets
        if (market_sub_) market_sub_->close();
        if (subscribe_push_) subscribe_push_->close();
        
        // 断开 Redis
        redis_.disconnect();
    }
    
    /**
     * @brief 发送订阅请求
     */
    void subscribe_trades(const std::string& symbol) {
        send_subscription("subscribe", "trades", symbol, "");
    }
    
    void subscribe_kline(const std::string& symbol, const std::string& interval) {
        send_subscription("subscribe", "kline", symbol, interval);
    }
    
    void unsubscribe_trades(const std::string& symbol) {
        send_subscription("unsubscribe", "trades", symbol, "");
    }
    
    void unsubscribe_kline(const std::string& symbol, const std::string& interval) {
        send_subscription("unsubscribe", "kline", symbol, interval);
    }
    
    /**
     * @brief 订阅所有配置的币种和周期
     */
    void subscribe_all() {
        std::cout << "\n[订阅] 正在订阅行情数据...\n";
        
        // 订阅 trades
        for (const auto& symbol : Config::symbols) {
            subscribe_trades(symbol);
        }
        std::cout << "  ✓ trades: " << Config::symbols.size() << " 个币种\n";
        
        // 订阅 K 线
        int kline_count = 0;
        for (const auto& symbol : Config::symbols) {
            for (const auto& interval : Config::kline_intervals) {
                subscribe_kline(symbol, interval);
                kline_count++;
            }
        }
        std::cout << "  ✓ K线: " << kline_count << " 个订阅\n";
    }
    
    /**
     * @brief 主循环：接收数据并存入 Redis
     */
    void run() {
        std::cout << "\n[DataRecorder] 开始运行...\n";
        std::cout << "  - 数据过期时间: " << Config::expire_seconds / 3600 << " 小时\n";
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
                continue;
            }
            
            if (result.has_value()) {
                std::string data_str(static_cast<char*>(msg.data()), msg.size());
                
                try {
                    json data = json::parse(data_str);
                    process_market_data(data);
                } catch (const json::parse_error& e) {
                    std::cerr << "[JSON] 解析错误: " << e.what() << "\n";
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
    void send_subscription(const std::string& action, const std::string& channel,
                          const std::string& symbol, const std::string& interval) {
        if (!subscribe_push_) return;
        
        json request = {
            {"action", action},
            {"channel", channel},
            {"symbol", symbol},
            {"interval", interval},
            {"strategy_id", "data_recorder"},
            {"timestamp", duration_cast<milliseconds>(
                system_clock::now().time_since_epoch()).count()}
        };
        
        std::string msg = request.dump();
        
        try {
            zmq::message_t zmq_msg(msg.size());
            memcpy(zmq_msg.data(), msg.c_str(), msg.size());
            subscribe_push_->send(zmq_msg, zmq::send_flags::dontwait);
        } catch (const zmq::error_t& e) {
            std::cerr << "[ZMQ] 发送订阅请求失败: " << e.what() << "\n";
        }
    }
    
    void process_market_data(const json& data) {
        std::string type = data.value("type", "");
        
        if (type == "trade") {
            std::string symbol = data.value("symbol", "");
            if (!symbol.empty()) {
                redis_.store_trade(symbol, data);
                g_trade_count++;
            }
        }
        else if (type == "kline") {
            std::string symbol = data.value("symbol", "");
            std::string interval = data.value("interval", "");
            if (!symbol.empty() && !interval.empty()) {
                redis_.store_kline(symbol, interval, data);
                g_kline_count++;
            }
        }
    }
    
    void print_status() {
        auto now = system_clock::now();
        auto time_t = system_clock::to_time_t(now);
        std::tm* tm = std::localtime(&time_t);
        
        std::cout << "[" << std::put_time(tm, "%H:%M:%S") << "] "
                  << "Trades: " << g_trade_count.load()
                  << " | K线: " << g_kline_count.load()
                  << " | Redis写入: " << g_redis_write_count.load()
                  << " | 错误: " << g_redis_error_count.load()
                  << "\n";
    }
    
private:
    zmq::context_t zmq_context_;
    std::unique_ptr<zmq::socket_t> market_sub_;
    std::unique_ptr<zmq::socket_t> subscribe_push_;
    RedisClient redis_;
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
              << "  --expire SECONDS     数据过期时间 (默认: 7200 即 2 小时)\n"
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
        else if (arg == "--expire" && i + 1 < argc) {
            Config::expire_seconds = std::stoi(argv[++i]);
        }
    }
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "    Sequence 数据记录器 (DataRecorder)\n";
    std::cout << "    实盘行情 -> Redis\n";
    std::cout << "========================================\n\n";
    
    // 解析命令行参数
    parse_args(argc, argv);
    
    // 打印配置
    std::cout << "[配置]\n";
    std::cout << "  Redis: " << Config::redis_host << ":" << Config::redis_port << "\n";
    std::cout << "  过期时间: " << Config::expire_seconds / 3600.0 << " 小时\n";
    std::cout << "  订阅币种: " << Config::symbols.size() << " 个\n";
    std::cout << "  K线周期: ";
    for (const auto& interval : Config::kline_intervals) {
        std::cout << interval << " ";
    }
    std::cout << "\n\n";
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 创建并启动数据记录器
    DataRecorder recorder;
    
    if (!recorder.start()) {
        std::cerr << "[错误] 启动失败\n";
        return 1;
    }
    
    // 订阅所有行情
    recorder.subscribe_all();
    
    // 等待订阅生效
    std::this_thread::sleep_for(seconds(2));
    
    // 主循环
    recorder.run();
    
    // 停止
    recorder.stop();
    
    // 打印统计
    std::cout << "\n========================================\n";
    std::cout << "  数据记录器已停止\n";
    std::cout << "  Trades: " << g_trade_count.load() << " 条\n";
    std::cout << "  K线: " << g_kline_count.load() << " 条\n";
    std::cout << "  Redis 写入: " << g_redis_write_count.load() << " 次\n";
    std::cout << "  Redis 错误: " << g_redis_error_count.load() << " 次\n";
    std::cout << "========================================\n";
    
    return 0;
}

