/**
 * @file test_disruptor_latency.cpp
 * @brief 环形总线延迟测试程序
 * 
 * 测试内容：
 * 1. 行情总线延迟（MD Thread → Strategy Thread）
 * 2. 指令总线延迟（Strategy Thread → OEMS Thread）
 * 3. 端到端延迟（行情 → 策略 → 订单）
 */

#include "../core/disruptor/disruptor_engine.h"
#include <chrono>
#include <vector>
#include <algorithm>
#include <numeric>
#include <cstdio>
#include <cmath>

using namespace trading::disruptor;
using namespace std::chrono;

// ============================================================
// 延迟测试策略
// ============================================================
class LatencyTestStrategy : public IStrategy {
public:
    explicit LatencyTestStrategy(uint32_t id) : id_(id) {}
    
    uint32_t strategy_id() const override { return id_; }
    
    bool on_market_event(const MarketEvent& event) override {
        // 计算延迟
        int64_t now = MarketEvent::now_ns();
        int64_t latency = now - event.timestamp_ns;
        
        if (latency > 0 && latency < 1000000000) {  // < 1秒
            latencies_.push_back(latency);
        }
        
        event_count_++;
        
        // 每1000个事件发一个订单（测试指令总线）
        if (event_count_ % 1000 == 0) {
            pending_order_ = true;
            pending_request_.clear();
            pending_request_.set_timestamp();
            pending_request_.order_id = event_count_;
            pending_request_.symbol_id = event.symbol_id;
            pending_request_.side = Side::BUY;
            pending_request_.ord_type = OrdType::LIMIT;
            pending_request_.price = event.last_price;
            pending_request_.quantity = 0.001;
            return true;
        }
        
        return false;
    }
    
    void on_order_response(const OrderResponse& response) override {
        (void)response;
    }
    
    bool get_pending_order(OrderRequest& request) override {
        if (pending_order_) {
            request = pending_request_;
            pending_order_ = false;
            return true;
        }
        return false;
    }
    
    // 统计
    const std::vector<int64_t>& latencies() const { return latencies_; }
    uint64_t event_count() const { return event_count_; }

private:
    uint32_t id_;
    std::vector<int64_t> latencies_;
    uint64_t event_count_ = 0;
    bool pending_order_ = false;
    OrderRequest pending_request_;
};

// ============================================================
// 统计计算
// ============================================================
struct LatencyStats {
    int64_t min_ns = 0;
    int64_t max_ns = 0;
    int64_t avg_ns = 0;
    int64_t p50_ns = 0;
    int64_t p95_ns = 0;
    int64_t p99_ns = 0;
    size_t count = 0;
};

LatencyStats calculate_stats(std::vector<int64_t>& latencies) {
    LatencyStats stats;
    
    if (latencies.empty()) {
        return stats;
    }
    
    std::sort(latencies.begin(), latencies.end());
    
    stats.count = latencies.size();
    stats.min_ns = latencies.front();
    stats.max_ns = latencies.back();
    stats.avg_ns = std::accumulate(latencies.begin(), latencies.end(), 0LL) / stats.count;
    stats.p50_ns = latencies[stats.count * 50 / 100];
    stats.p95_ns = latencies[stats.count * 95 / 100];
    stats.p99_ns = latencies[stats.count * 99 / 100];
    
    return stats;
}

void print_stats(const char* name, const LatencyStats& stats) {
    printf("\n%s Latency Statistics:\n", name);
    printf("  Samples:  %zu\n", stats.count);
    printf("  Min:      %ld ns (%.2f μs)\n", stats.min_ns, stats.min_ns / 1000.0);
    printf("  Avg:      %ld ns (%.2f μs)\n", stats.avg_ns, stats.avg_ns / 1000.0);
    printf("  P50:      %ld ns (%.2f μs)\n", stats.p50_ns, stats.p50_ns / 1000.0);
    printf("  P95:      %ld ns (%.2f μs)\n", stats.p95_ns, stats.p95_ns / 1000.0);
    printf("  P99:      %ld ns (%.2f μs)\n", stats.p99_ns, stats.p99_ns / 1000.0);
    printf("  Max:      %ld ns (%.2f μs)\n", stats.max_ns, stats.max_ns / 1000.0);
}

// ============================================================
// 测试1：纯RingBuffer写入性能
// ============================================================
void test_ringbuffer_write() {
    printf("\n========================================\n");
    printf("  Test 1: RingBuffer Write Performance\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    const int NUM_EVENTS = 1000000;
    
    auto start = steady_clock::now();
    
    for (int i = 0; i < NUM_EVENTS; ++i) {
        int64_t seq = buffer.next();
        auto& event = buffer.get(seq);
        event.clear();
        event.type = EventType::TICKER;
        event.set_timestamp();
        event.last_price = 50000.0 + (i % 100);
        buffer.publish(seq);
    }
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    double avg_latency = static_cast<double>(elapsed_ns) / NUM_EVENTS;
    
    printf("  Events:      %d\n", NUM_EVENTS);
    printf("  Time:        %.3f ms\n", elapsed_ns / 1e6);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    printf("  Avg Latency: %.1f ns\n", avg_latency);
}

// ============================================================
// 测试2：MPSC队列性能
// ============================================================
void test_mpsc_queue() {
    printf("\n========================================\n");
    printf("  Test 2: MPSC Queue Performance\n");
    printf("========================================\n");
    
    MPSCQueue<OrderRequest, 4096> queue;
    const int NUM_ORDERS = 100000;
    
    // 写入
    auto start_write = steady_clock::now();
    
    for (int i = 0; i < NUM_ORDERS; ++i) {
        OrderRequest req;
        req.clear();
        req.order_id = i;
        req.set_timestamp();
        queue.push(req);
    }
    
    auto end_write = steady_clock::now();
    
    // 读取
    OrderRequest req;
    int count = 0;
    auto start_read = steady_clock::now();
    
    while (queue.try_pop(req)) {
        count++;
    }
    
    auto end_read = steady_clock::now();
    
    auto write_ns = duration_cast<nanoseconds>(end_write - start_write).count();
    auto read_ns = duration_cast<nanoseconds>(end_read - start_read).count();
    
    printf("  Orders:      %d\n", NUM_ORDERS);
    printf("  Write Time:  %.3f ms (%.1f ns/op)\n", 
           write_ns / 1e6, static_cast<double>(write_ns) / NUM_ORDERS);
    printf("  Read Time:   %.3f ms (%.1f ns/op)\n", 
           read_ns / 1e6, static_cast<double>(read_ns) / count);
    printf("  Read Count:  %d\n", count);
}

// ============================================================
// 测试3：端到端延迟测试
// ============================================================
void test_end_to_end_latency() {
    printf("\n========================================\n");
    printf("  Test 3: End-to-End Latency\n");
    printf("========================================\n");
    
    // 创建引擎（禁用CPU绑核，方便测试）
    ThreadConfig config;
    config.enable_cpu_pinning = false;
    
    DisruptorEngine<65536, 4096> engine(config);
    
    // 创建测试策略
    auto strategy1 = std::make_unique<LatencyTestStrategy>(1);
    auto strategy2 = std::make_unique<LatencyTestStrategy>(2);
    
    auto* strat1_ptr = strategy1.get();
    auto* strat2_ptr = strategy2.get();
    
    engine.add_strategy_group_a(std::move(strategy1));
    engine.add_strategy_group_b(std::move(strategy2));
    
    // 启动引擎
    engine.start();
    
    // 等待启动
    std::this_thread::sleep_for(milliseconds(100));
    
    // 发送行情
    const int NUM_EVENTS = 100000;
    printf("  Sending %d market events...\n", NUM_EVENTS);
    
    auto start = steady_clock::now();
    
    for (int i = 0; i < NUM_EVENTS; ++i) {
        engine.publish_ticker(
            SymbolMapper::BTC_USDT,
            50000.0 + (i % 100),   // last_price
            49995.0 + (i % 100),   // bid_price
            50005.0 + (i % 100),   // ask_price
            1000.0 + (i % 50),     // volume
            0.5                     // bid_size
        );
        
        // 控制发送速率（可选）
        // std::this_thread::sleep_for(microseconds(10));
    }
    
    auto end = steady_clock::now();
    
    // 等待处理完成
    std::this_thread::sleep_for(milliseconds(500));
    
    // 停止引擎
    engine.stop();
    
    // 统计
    auto elapsed_ms = duration_cast<milliseconds>(end - start).count();
    double throughput = NUM_EVENTS / (elapsed_ms / 1000.0);
    
    printf("\n  Send Statistics:\n");
    printf("  Events:      %d\n", NUM_EVENTS);
    printf("  Time:        %ld ms\n", elapsed_ms);
    printf("  Throughput:  %.2f K events/s\n", throughput / 1000.0);
    
    // 延迟统计
    auto latencies1 = strat1_ptr->latencies();
    auto latencies2 = strat2_ptr->latencies();
    
    // 合并延迟数据
    std::vector<int64_t> all_latencies;
    all_latencies.reserve(latencies1.size() + latencies2.size());
    all_latencies.insert(all_latencies.end(), latencies1.begin(), latencies1.end());
    all_latencies.insert(all_latencies.end(), latencies2.begin(), latencies2.end());
    
    if (!all_latencies.empty()) {
        auto stats = calculate_stats(all_latencies);
        print_stats("  Market Data Bus", stats);
    }
    
    printf("\n  Strategy 1 processed: %lu events\n", strat1_ptr->event_count());
    printf("  Strategy 2 processed: %lu events\n", strat2_ptr->event_count());
}

// ============================================================
// 测试4：高负载下的延迟
// ============================================================
void test_high_load_latency() {
    printf("\n========================================\n");
    printf("  Test 4: High Load Latency (Burst)\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    std::vector<int64_t> latencies;
    latencies.reserve(100000);
    
    const int BURST_SIZE = 1000;
    const int NUM_BURSTS = 100;
    
    for (int burst = 0; burst < NUM_BURSTS; ++burst) {
        // 发送一批
        for (int i = 0; i < BURST_SIZE; ++i) {
            int64_t seq = buffer.next();
            auto& event = buffer.get(seq);
            event.clear();
            event.type = EventType::TICKER;
            event.set_timestamp();
            buffer.publish(seq);
        }
        
        // 消费一批
        int64_t consumer_seq = burst * BURST_SIZE;
        int64_t available = buffer.cursor();
        
        while (consumer_seq < available) {
            consumer_seq++;
            const auto& event = buffer.get(consumer_seq);
            int64_t latency = MarketEvent::now_ns() - event.timestamp_ns;
            if (latency > 0) {
                latencies.push_back(latency);
            }
        }
    }
    
    if (!latencies.empty()) {
        auto stats = calculate_stats(latencies);
        print_stats("  Burst Mode", stats);
    }
}

// ============================================================
// 主函数
// ============================================================
int main() {
    printf("========================================\n");
    printf("  Disruptor Engine Latency Test\n");
    printf("========================================\n");
    printf("  Architecture: Ring Bus (LMAX Style)\n");
    printf("  RingBuffer:   64K slots\n");
    printf("  Order Queue:  4K slots\n");
    printf("========================================\n");
    
    // 运行测试
    test_ringbuffer_write();
    test_mpsc_queue();
    test_end_to_end_latency();
    test_high_load_latency();
    
    printf("\n========================================\n");
    printf("  All Tests Completed!\n");
    printf("========================================\n");
    
    return 0;
}

