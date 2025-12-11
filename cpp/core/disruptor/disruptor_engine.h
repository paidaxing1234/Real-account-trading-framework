#pragma once

/**
 * @file disruptor_engine.h
 * @brief 环形总线引擎 - 整合所有组件
 * 
 * 物理拓扑规划：
 * 
 * ┌─────────────────────────────────────────────────────────────┐
 * │                    Ring Bus Architecture                     │
 * ├─────────────────────────────────────────────────────────────┤
 * │                                                               │
 * │   Core 0: OS/SSH (垃圾回收站)                                 │
 * │                                                               │
 * │   Core 1: MD Thread (水源)                                    │
 * │      └── 收行情 → 归一化 → 写总线                              │
 * │                        ↓                                      │
 * │   ┌────────────────────────────────────────┐                 │
 * │   │      Market Data Bus (RingBuffer)      │                 │
 * │   │           SPMC 行情总线                  │                 │
 * │   └────────────────────────────────────────┘                 │
 * │          ↓               ↓              ↓                    │
 * │   Core 2: Strat A    Core 3: Strat B   Core 5: Logger        │
 * │      └── 策略1~10       └── 策略11~20     └── 写磁盘          │
 * │          ↓                   ↓                               │
 * │   ┌────────────────────────────────────────┐                 │
 * │   │        Order Bus (MPSC Queue)          │                 │
 * │   │           指令总线                       │                 │
 * │   └────────────────────────────────────────┘                 │
 * │                        ↓                                      │
 * │   Core 4: OEMS Thread (手脚)                                  │
 * │      └── 收指令 → 风控 → 路由 → TCP发单                        │
 * │                                                               │
 * └─────────────────────────────────────────────────────────────┘
 */

#include "ring_buffer.h"
#include "mpsc_queue.h"
#include "events.h"
#include "market_data_bus.h"
#include "workers.h"
#include <memory>
#include <vector>
#include <thread>

namespace trading {
namespace disruptor {

// ============================================================
// 线程配置
// ============================================================
struct ThreadConfig {
    int md_thread_cpu = 1;         // 行情线程CPU
    int strategy_group_a_cpu = 2;  // 策略组A CPU
    int strategy_group_b_cpu = 3;  // 策略组B CPU
    int oems_thread_cpu = 4;       // OEMS线程CPU
    int logger_thread_cpu = 5;     // 日志线程CPU
    
    bool enable_cpu_pinning = true;  // 是否启用绑核
    bool enable_realtime = false;    // 是否启用实时优先级
};

// ============================================================
// 引擎统计
// ============================================================
struct EngineStats {
    uint64_t market_events = 0;    // 行情事件数
    uint64_t order_requests = 0;   // 订单请求数
    uint64_t order_fills = 0;      // 订单成交数
    uint64_t order_rejects = 0;    // 订单拒绝数
    int64_t min_latency_ns = 0;    // 最小延迟
    int64_t max_latency_ns = 0;    // 最大延迟
    int64_t avg_latency_ns = 0;    // 平均延迟
};

// ============================================================
// 环形总线引擎
// ============================================================
template<
    size_t MD_CAPACITY = 65536,      // 行情总线容量（64K事件）
    size_t ORDER_CAPACITY = 4096     // 指令队列容量（4K请求）
>
class DisruptorEngine {
public:
    using MarketBus = MarketDataBus<MD_CAPACITY>;
    using OrderQueue = MPSCQueue<OrderRequest, ORDER_CAPACITY>;
    using StratWorker = StrategyWorker<MD_CAPACITY, ORDER_CAPACITY>;
    using OemsWorker = OEMSWorker<ORDER_CAPACITY>;
    using LogWorker = LoggerWorker<MD_CAPACITY>;
    
    explicit DisruptorEngine(const ThreadConfig& config = ThreadConfig())
        : config_(config)
        , running_(false) {
        
        // 创建工作线程
        int cpu_a = config.enable_cpu_pinning ? config.strategy_group_a_cpu : -1;
        int cpu_b = config.enable_cpu_pinning ? config.strategy_group_b_cpu : -1;
        int cpu_oems = config.enable_cpu_pinning ? config.oems_thread_cpu : -1;
        int cpu_logger = config.enable_cpu_pinning ? config.logger_thread_cpu : -1;
        
        strategy_worker_a_ = std::make_unique<StratWorker>(market_bus_, order_queue_, cpu_a);
        strategy_worker_b_ = std::make_unique<StratWorker>(market_bus_, order_queue_, cpu_b);
        oems_worker_ = std::make_unique<OemsWorker>(order_queue_, cpu_oems);
        logger_worker_ = std::make_unique<LogWorker>(market_bus_, cpu_logger);
    }
    
    ~DisruptorEngine() {
        stop();
    }
    
    // ============================================================
    // 策略管理
    // ============================================================
    
    /**
     * @brief 添加策略到组A
     */
    void add_strategy_group_a(std::unique_ptr<IStrategy> strategy) {
        strategy_worker_a_->add_strategy(std::move(strategy));
    }
    
    /**
     * @brief 添加策略到组B
     */
    void add_strategy_group_b(std::unique_ptr<IStrategy> strategy) {
        strategy_worker_b_->add_strategy(std::move(strategy));
    }
    
    // ============================================================
    // 交易连接管理
    // ============================================================
    
    /**
     * @brief 注册交易所连接
     */
    void register_exchange_connection(uint8_t exchange_id, std::shared_ptr<ITradeConnection> conn) {
        oems_worker_->register_connection(exchange_id, conn);
    }
    
    /**
     * @brief 设置风控检查器
     */
    void set_risk_checker(std::function<bool(const OrderRequest&)> checker) {
        oems_worker_->set_risk_checker(checker);
    }
    
    // ============================================================
    // 日志配置
    // ============================================================
    
    /**
     * @brief 设置日志文件
     */
    bool set_log_file(const char* path) {
        return logger_worker_->set_log_file(path);
    }
    
    // ============================================================
    // 行情输入（MD Thread调用）
    // ============================================================
    
    /**
     * @brief 发布行情（零拷贝）
     */
    MarketEvent& next_market_event() {
        return market_bus_.next();
    }
    
    void publish_market_event() {
        market_bus_.publish();
    }
    
    /**
     * @brief 发布行情（便捷方法）
     */
    void publish_ticker(
        uint16_t symbol_id,
        double last_price,
        double bid_price,
        double ask_price,
        double volume,
        double bid_size = 0.0,
        uint8_t exchange_id = ExchangeId::OKX
    ) {
        market_bus_.publish_ticker(
            symbol_id, last_price, bid_price, ask_price, 
            volume, bid_size, exchange_id
        );
    }
    
    // ============================================================
    // 生命周期管理
    // ============================================================
    
    /**
     * @brief 启动引擎
     */
    void start() {
        if (running_.exchange(true)) {
            return;
        }
        
        printf("========================================\n");
        printf("  Disruptor Engine Starting...\n");
        printf("========================================\n");
        printf("  MD Bus Capacity:    %zu\n", MD_CAPACITY);
        printf("  Order Queue:        %zu\n", ORDER_CAPACITY);
        printf("  CPU Pinning:        %s\n", config_.enable_cpu_pinning ? "ON" : "OFF");
        printf("========================================\n");
        
        // 启动工作线程（按依赖顺序）
        logger_worker_->start();      // 先启动日志
        oems_worker_->start();        // 再启动OEMS
        strategy_worker_a_->start();  // 再启动策略A
        strategy_worker_b_->start();  // 再启动策略B
        
        printf("[DisruptorEngine] All workers started\n");
    }
    
    /**
     * @brief 停止引擎
     */
    void stop() {
        if (!running_.exchange(false)) {
            return;
        }
        
        printf("[DisruptorEngine] Stopping...\n");
        
        // 停止工作线程（逆序）
        strategy_worker_a_->stop();
        strategy_worker_b_->stop();
        oems_worker_->stop();
        logger_worker_->stop();
        
        printf("[DisruptorEngine] Stopped\n");
    }
    
    /**
     * @brief 检查是否运行中
     */
    bool is_running() const {
        return running_.load(std::memory_order_acquire);
    }
    
    // ============================================================
    // 统计信息
    // ============================================================
    
    /**
     * @brief 获取行情总线游标
     */
    int64_t market_bus_cursor() const {
        return market_bus_.cursor();
    }
    
    /**
     * @brief 获取引擎统计
     */
    EngineStats get_stats() const {
        EngineStats stats;
        stats.market_events = market_bus_.cursor() + 1;
        stats.order_requests = strategy_worker_a_->order_count() + 
                               strategy_worker_b_->order_count();
        return stats;
    }
    
    // ============================================================
    // 直接访问（用于测试和高级用法）
    // ============================================================
    
    MarketBus& market_bus() { return market_bus_; }
    OrderQueue& order_queue() { return order_queue_; }

private:
    ThreadConfig config_;
    std::atomic<bool> running_;
    
    // 总线
    MarketBus market_bus_;
    OrderQueue order_queue_;
    
    // 工作线程
    std::unique_ptr<StratWorker> strategy_worker_a_;
    std::unique_ptr<StratWorker> strategy_worker_b_;
    std::unique_ptr<OemsWorker> oems_worker_;
    std::unique_ptr<LogWorker> logger_worker_;
};

// 默认引擎类型
using DefaultEngine = DisruptorEngine<65536, 4096>;

} // namespace disruptor
} // namespace trading

