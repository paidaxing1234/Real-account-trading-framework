#pragma once

/**
 * @file workers.h
 * @brief 工作线程实现（策略、OEMS、日志）
 * 
 * 线程角色：
 * - MD Thread (Core 1): 收行情 -> 写总线
 * - Strategy Group A (Core 2): 订阅总线 -> 跑策略 -> 发指令
 * - Strategy Group B (Core 3): 订阅总线 -> 跑策略 -> 发指令
 * - OEMS Thread (Core 4): 收指令 -> 风控 -> 路由 -> 发单
 * - Logger Thread (Core 5): 订阅总线 -> 写磁盘
 */

#include "ring_buffer.h"
#include "mpsc_queue.h"
#include "events.h"
#include "market_data_bus.h"
#include <thread>
#include <vector>
#include <functional>
#include <atomic>
#include <cstdio>

#ifdef __linux__
#include <sched.h>
#include <pthread.h>
#endif

#ifdef __APPLE__
#include <mach/thread_policy.h>
#include <mach/thread_act.h>
#endif

namespace trading {
namespace disruptor {

// ============================================================
// CPU亲和性设置
// ============================================================

/**
 * @brief 将当前线程绑定到指定CPU核心
 * @param cpu_id CPU核心ID
 * @return true=成功
 */
inline bool set_cpu_affinity(int cpu_id) {
#ifdef __linux__
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu_id, &cpuset);
    return pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) == 0;
#elif defined(__APPLE__)
    // macOS不支持直接绑核，但可以设置线程亲和性提示
    thread_affinity_policy_data_t policy = { cpu_id };
    return thread_policy_set(
        pthread_mach_thread_np(pthread_self()),
        THREAD_AFFINITY_POLICY,
        (thread_policy_t)&policy,
        THREAD_AFFINITY_POLICY_COUNT
    ) == KERN_SUCCESS;
#else
    (void)cpu_id;
    return false;
#endif
}

/**
 * @brief 设置线程实时优先级
 */
inline bool set_realtime_priority() {
#ifdef __linux__
    struct sched_param param;
    param.sched_priority = sched_get_priority_max(SCHED_FIFO);
    return pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) == 0;
#else
    return false;
#endif
}

// ============================================================
// 策略工作线程
// ============================================================

/**
 * @brief 策略基类（用于环形总线架构）
 */
class IStrategy {
public:
    virtual ~IStrategy() = default;
    
    /**
     * @brief 策略ID
     */
    virtual uint32_t strategy_id() const = 0;
    
    /**
     * @brief 处理行情事件
     * @param event 行情事件
     * @return 是否产生了订单请求
     */
    virtual bool on_market_event(const MarketEvent& event) = 0;
    
    /**
     * @brief 处理订单回报
     */
    virtual void on_order_response(const OrderResponse& response) = 0;
    
    /**
     * @brief 获取待发送的订单请求（如果有）
     */
    virtual bool get_pending_order(OrderRequest& request) = 0;
};

/**
 * @brief 策略工作线程
 * 
 * 订阅行情总线，运行多个策略，发送订单到OEMS
 */
template<size_t MD_CAPACITY = 65536, size_t ORDER_CAPACITY = 4096>
class StrategyWorker {
public:
    using MarketBus = MarketDataBus<MD_CAPACITY>;
    using OrderQueue = MPSCQueue<OrderRequest, ORDER_CAPACITY>;
    
    StrategyWorker(
        MarketBus& market_bus,
        OrderQueue& order_queue,
        int cpu_id = -1
    ) 
        : market_bus_(market_bus)
        , order_queue_(order_queue)
        , cpu_id_(cpu_id)
        , running_(false)
        , local_sequence_(-1)
        , event_count_(0)
        , order_count_(0) {}
    
    /**
     * @brief 添加策略
     */
    void add_strategy(std::unique_ptr<IStrategy> strategy) {
        strategies_.push_back(std::move(strategy));
    }
    
    /**
     * @brief 启动工作线程
     */
    void start() {
        if (running_.exchange(true)) {
            return;
        }
        
        thread_ = std::thread(&StrategyWorker::run, this);
    }
    
    /**
     * @brief 停止工作线程
     */
    void stop() {
        running_.store(false, std::memory_order_release);
        if (thread_.joinable()) {
            thread_.join();
        }
    }
    
    /**
     * @brief 获取统计信息
     */
    uint64_t event_count() const { return event_count_; }
    uint64_t order_count() const { return order_count_; }

private:
    void run() {
        // 绑定CPU
        if (cpu_id_ >= 0) {
            if (set_cpu_affinity(cpu_id_)) {
                printf("[StrategyWorker] Pinned to CPU %d\n", cpu_id_);
            }
            set_realtime_priority();
        }
        
        printf("[StrategyWorker] Started with %zu strategies\n", strategies_.size());
        
        while (running_.load(std::memory_order_acquire)) {
            // 获取行情总线游标
            int64_t available = market_bus_.cursor();
            
            // 处理所有新事件
            while (local_sequence_ < available && running_.load(std::memory_order_relaxed)) {
                local_sequence_++;
                
                // 通过poll获取事件
                market_bus_.poll(0, [this](const MarketEvent& event, int64_t seq) {
                    (void)seq;
                    if (event.type == EventType::NONE) {
                        return;
                    }
                    
                    event_count_++;
                    
                    // 分发给所有策略
                    for (auto& strategy : strategies_) {
                        if (strategy->on_market_event(event)) {
                            // 策略产生了订单
                            OrderRequest request;
                            if (strategy->get_pending_order(request)) {
                                request.strategy_id = strategy->strategy_id();
                                order_queue_.push(request);
                                order_count_++;
                            }
                        }
                    }
                });
                break;  // poll会处理所有可用事件
            }
            
            // 短暂让出CPU（如果没有新数据）
            if (local_sequence_ >= available) {
                #if defined(__x86_64__) || defined(__i386__)
                __builtin_ia32_pause();
                #elif defined(__aarch64__)
                asm volatile("yield" ::: "memory");
                #endif
            }
        }
        
        printf("[StrategyWorker] Stopped. Events: %llu, Orders: %llu\n",
               (unsigned long long)event_count_, (unsigned long long)order_count_);
    }
    
    MarketBus& market_bus_;
    OrderQueue& order_queue_;
    std::vector<std::unique_ptr<IStrategy>> strategies_;
    
    int cpu_id_;
    std::atomic<bool> running_;
    std::thread thread_;
    
    int64_t local_sequence_;
    uint64_t event_count_;
    uint64_t order_count_;
};

// ============================================================
// OEMS工作线程（交易执行管理）
// ============================================================

/**
 * @brief 交易连接接口
 */
class ITradeConnection {
public:
    virtual ~ITradeConnection() = default;
    virtual bool send_order(const OrderRequest& request) = 0;
    virtual bool cancel_order(int64_t order_id) = 0;
    virtual void poll_responses() = 0;
};

/**
 * @brief OEMS工作线程
 * 
 * 职责：
 * 1. 从指令队列读取订单请求
 * 2. 风控检查
 * 3. 路由到正确的交易所连接
 * 4. 处理交易所回报
 */
template<size_t ORDER_CAPACITY = 4096>
class OEMSWorker {
public:
    using OrderQueue = MPSCQueue<OrderRequest, ORDER_CAPACITY>;
    using ResponseHandler = std::function<void(const OrderResponse&)>;
    
    OEMSWorker(OrderQueue& order_queue, int cpu_id = -1)
        : order_queue_(order_queue)
        , cpu_id_(cpu_id)
        , running_(false)
        , order_count_(0)
        , reject_count_(0) {}
    
    /**
     * @brief 注册交易连接
     * @param exchange_id 交易所ID
     * @param connection 连接对象
     */
    void register_connection(uint8_t exchange_id, std::shared_ptr<ITradeConnection> connection) {
        if (exchange_id < connections_.size()) {
            connections_[exchange_id] = connection;
        }
    }
    
    /**
     * @brief 设置订单回报处理器
     */
    void set_response_handler(ResponseHandler handler) {
        response_handler_ = handler;
    }
    
    /**
     * @brief 设置风控检查器
     */
    void set_risk_checker(std::function<bool(const OrderRequest&)> checker) {
        risk_checker_ = checker;
    }
    
    /**
     * @brief 启动
     */
    void start() {
        if (running_.exchange(true)) {
            return;
        }
        thread_ = std::thread(&OEMSWorker::run, this);
    }
    
    /**
     * @brief 停止
     */
    void stop() {
        running_.store(false, std::memory_order_release);
        if (thread_.joinable()) {
            thread_.join();
        }
    }
    
    /**
     * @brief 手动处理一批订单（用于测试）
     */
    size_t process_batch(size_t max_count = 100) {
        OrderRequest requests[100];
        size_t count = order_queue_.pop_batch(requests, std::min(max_count, size_t(100)));
        
        for (size_t i = 0; i < count; ++i) {
            process_order(requests[i]);
        }
        
        return count;
    }

private:
    void run() {
        if (cpu_id_ >= 0) {
            if (set_cpu_affinity(cpu_id_)) {
                printf("[OEMSWorker] Pinned to CPU %d\n", cpu_id_);
            }
        }
        
        printf("[OEMSWorker] Started\n");
        
        OrderRequest request;
        
        while (running_.load(std::memory_order_acquire)) {
            // 1. 处理订单请求
            while (order_queue_.try_pop(request)) {
                process_order(request);
            }
            
            // 2. 轮询交易所回报
            for (auto& conn : connections_) {
                if (conn) {
                    conn->poll_responses();
                }
            }
            
            // 短暂让出CPU
            #if defined(__x86_64__) || defined(__i386__)
            __builtin_ia32_pause();
            #elif defined(__aarch64__)
            asm volatile("yield" ::: "memory");
            #endif
        }
        
        printf("[OEMSWorker] Stopped. Orders: %llu, Rejects: %llu\n",
               (unsigned long long)order_count_, (unsigned long long)reject_count_);
    }
    
    void process_order(const OrderRequest& request) {
        order_count_++;
        
        // 风控检查
        if (risk_checker_ && !risk_checker_(request)) {
            reject_count_++;
            
            // 发送拒绝回报
            if (response_handler_) {
                OrderResponse resp;
                resp.clear();
                resp.type = EventType::ORDER_ACK;
                resp.order_id = request.order_id;
                resp.status = OrdStatus::REJECTED;
                resp.error_code = 1001;
                strncpy(resp.error_msg, "Risk check failed", sizeof(resp.error_msg) - 1);
                response_handler_(resp);
            }
            return;
        }
        
        // 路由到交易所
        uint8_t exchange_id = request.exchange_id;
        if (exchange_id < connections_.size() && connections_[exchange_id]) {
            connections_[exchange_id]->send_order(request);
        } else {
            reject_count_++;
            printf("[OEMSWorker] Unknown exchange: %d\n", exchange_id);
        }
    }
    
    OrderQueue& order_queue_;
    std::array<std::shared_ptr<ITradeConnection>, 8> connections_;  // 最多8个交易所
    ResponseHandler response_handler_;
    std::function<bool(const OrderRequest&)> risk_checker_;
    
    int cpu_id_;
    std::atomic<bool> running_;
    std::thread thread_;
    
    uint64_t order_count_;
    uint64_t reject_count_;
};

// ============================================================
// 日志工作线程
// ============================================================

/**
 * @brief 日志工作线程
 * 
 * 职责：
 * 1. 订阅行情总线（旁听者）
 * 2. 订阅指令队列（旁听者）
 * 3. 批量写入磁盘
 */
template<size_t MD_CAPACITY = 65536>
class LoggerWorker {
public:
    using MarketBus = MarketDataBus<MD_CAPACITY>;
    
    LoggerWorker(MarketBus& market_bus, int cpu_id = -1)
        : market_bus_(market_bus)
        , cpu_id_(cpu_id)
        , running_(false)
        , local_sequence_(-1)
        , event_count_(0)
        , log_file_(nullptr) {}
    
    ~LoggerWorker() {
        stop();
        if (log_file_) {
            fclose(log_file_);
        }
    }
    
    /**
     * @brief 设置日志文件
     */
    bool set_log_file(const char* path) {
        if (log_file_) {
            fclose(log_file_);
        }
        log_file_ = fopen(path, "wb");
        return log_file_ != nullptr;
    }
    
    /**
     * @brief 启动
     */
    void start() {
        if (running_.exchange(true)) {
            return;
        }
        thread_ = std::thread(&LoggerWorker::run, this);
    }
    
    /**
     * @brief 停止
     */
    void stop() {
        running_.store(false, std::memory_order_release);
        if (thread_.joinable()) {
            thread_.join();
        }
    }

private:
    void run() {
        if (cpu_id_ >= 0) {
            set_cpu_affinity(cpu_id_);
            printf("[LoggerWorker] Pinned to CPU %d\n", cpu_id_);
        }
        
        printf("[LoggerWorker] Started\n");
        
        // 缓冲区（攒满4KB写一次）
        constexpr size_t BUFFER_SIZE = 4096;
        char buffer[BUFFER_SIZE];
        size_t buffer_pos = 0;
        
        auto last_flush = std::chrono::steady_clock::now();
        
        while (running_.load(std::memory_order_acquire)) {
            int64_t available = market_bus_.cursor();
            
            // 处理新事件
            while (local_sequence_ < available) {
                local_sequence_++;
                
                const auto& event = reinterpret_cast<const RingBuffer<MarketEvent, MD_CAPACITY>&>(market_bus_).get(local_sequence_);
                
                if (event.type == EventType::NONE) {
                    continue;
                }
                
                event_count_++;
                
                // 写入缓冲区
                if (log_file_) {
                    size_t to_write = sizeof(MarketEvent);
                    if (buffer_pos + to_write > BUFFER_SIZE) {
                        // 刷新缓冲区
                        fwrite(buffer, 1, buffer_pos, log_file_);
                        buffer_pos = 0;
                    }
                    memcpy(buffer + buffer_pos, &event, to_write);
                    buffer_pos += to_write;
                }
            }
            
            // 定期刷新（每1ms或缓冲区满）
            auto now = std::chrono::steady_clock::now();
            if (buffer_pos > 0 && 
                (buffer_pos >= BUFFER_SIZE / 2 || 
                 now - last_flush > std::chrono::milliseconds(1))) {
                if (log_file_) {
                    fwrite(buffer, 1, buffer_pos, log_file_);
                    buffer_pos = 0;
                }
                last_flush = now;
            }
            
            // 长一点的睡眠（日志不需要那么快）
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
        
        // 最终刷新
        if (log_file_ && buffer_pos > 0) {
            fwrite(buffer, 1, buffer_pos, log_file_);
            fflush(log_file_);
        }
        
        printf("[LoggerWorker] Stopped. Events logged: %llu\n", (unsigned long long)event_count_);
    }
    
    MarketBus& market_bus_;
    int cpu_id_;
    std::atomic<bool> running_;
    std::thread thread_;
    
    int64_t local_sequence_;
    uint64_t event_count_;
    FILE* log_file_;
};

} // namespace disruptor
} // namespace trading

