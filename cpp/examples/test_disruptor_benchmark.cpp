/**
 * @file test_disruptor_benchmark.cpp
 * @brief 环形总线性能基准测试
 * 
 * 测试纯写入和纯读取的极限性能
 */

#include "../core/disruptor/ring_buffer.h"
#include "../core/disruptor/mpsc_queue.h"
#include "../core/disruptor/events.h"
#include <chrono>
#include <thread>
#include <vector>
#include <atomic>
#include <cstdio>

using namespace trading::disruptor;
using namespace std::chrono;

// ============================================================
// 基准测试1：单生产者写入速度
// ============================================================
void benchmark_single_producer() {
    printf("\n========================================\n");
    printf("  Benchmark: Single Producer Write\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    
    // 预热
    for (int i = 0; i < 10000; ++i) {
        int64_t seq = buffer.next();
        auto& event = buffer.get(seq);
        event.clear();
        buffer.publish(seq);
    }
    
    // 测试
    const int64_t NUM_EVENTS = 10000000;  // 1000万
    
    auto start = steady_clock::now();
    
    for (int64_t i = 0; i < NUM_EVENTS; ++i) {
        int64_t seq = buffer.next();
        auto& event = buffer.get(seq);
        event.type = EventType::TICKER;
        event.timestamp_ns = i;
        event.last_price = 50000.0;
        buffer.publish(seq);
    }
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    double latency = static_cast<double>(elapsed_ns) / NUM_EVENTS;
    
    printf("  Events:      %lld\n", (long long)NUM_EVENTS);
    printf("  Time:        %.3f s\n", elapsed_ns / 1e9);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    printf("  Latency:     %.1f ns/event\n", latency);
}

// ============================================================
// 基准测试2：单消费者读取速度
// ============================================================
void benchmark_single_consumer() {
    printf("\n========================================\n");
    printf("  Benchmark: Single Consumer Read\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    
    // 先写入数据
    const int64_t NUM_EVENTS = 60000;  // 略小于容量
    
    for (int64_t i = 0; i < NUM_EVENTS; ++i) {
        int64_t seq = buffer.next();
        auto& event = buffer.get(seq);
        event.type = EventType::TICKER;
        event.timestamp_ns = i;
        event.last_price = 50000.0 + i;
        buffer.publish(seq);
    }
    
    // 测试读取
    auto start = steady_clock::now();
    
    double sum = 0.0;
    for (int64_t i = 0; i < NUM_EVENTS; ++i) {
        const auto& event = buffer.get(i);
        sum += event.last_price;  // 防止被优化掉
    }
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    double latency = static_cast<double>(elapsed_ns) / NUM_EVENTS;
    
    printf("  Events:      %lld\n", (long long)NUM_EVENTS);
    printf("  Time:        %.3f ms\n", elapsed_ns / 1e6);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    printf("  Latency:     %.1f ns/event\n", latency);
    printf("  (checksum:   %.0f)\n", sum);  // 防止优化
}

// ============================================================
// 基准测试3：生产者-消费者并发（SPSC）
// ============================================================
void benchmark_spsc_concurrent() {
    printf("\n========================================\n");
    printf("  Benchmark: SPSC Concurrent\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    std::atomic<bool> running{true};
    std::atomic<int64_t> consumed{0};
    
    const int64_t NUM_EVENTS = 10000000;
    
    // 消费者线程
    std::thread consumer([&]() {
        int64_t local_seq = -1;
        int64_t count = 0;
        
        while (running.load(std::memory_order_acquire) || local_seq < buffer.cursor()) {
            int64_t available = buffer.cursor();
            
            while (local_seq < available) {
                local_seq++;
                const auto& event = buffer.get(local_seq);
                (void)event.last_price;  // 模拟处理
                count++;
            }
            
            if (local_seq >= available) {
                // Busy spin
                #if defined(__x86_64__)
                __builtin_ia32_pause();
                #endif
            }
        }
        
        consumed.store(count, std::memory_order_release);
    });
    
    // 生产者（主线程）
    auto start = steady_clock::now();
    
    for (int64_t i = 0; i < NUM_EVENTS; ++i) {
        int64_t seq = buffer.next();
        auto& event = buffer.get(seq);
        event.type = EventType::TICKER;
        event.last_price = static_cast<double>(i);
        buffer.publish(seq);
    }
    
    running.store(false, std::memory_order_release);
    consumer.join();
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    
    printf("  Events:      %lld\n", (long long)NUM_EVENTS);
    printf("  Consumed:    %lld\n", (long long)consumed.load());
    printf("  Time:        %.3f s\n", elapsed_ns / 1e9);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
}

// ============================================================
// 基准测试4：MPSC队列（多生产者）
// ============================================================
void benchmark_mpsc() {
    printf("\n========================================\n");
    printf("  Benchmark: MPSC Queue (4 Producers)\n");
    printf("========================================\n");
    
    MPSCQueue<OrderRequest, 65536> queue;
    std::atomic<bool> running{true};
    std::atomic<int64_t> produced{0};
    std::atomic<int64_t> consumed{0};
    
    const int NUM_PRODUCERS = 4;
    const int64_t EVENTS_PER_PRODUCER = 250000;
    
    std::vector<std::thread> producers;
    
    // 消费者线程
    std::thread consumer([&]() {
        int64_t count = 0;
        OrderRequest req;
        
        while (running.load(std::memory_order_acquire) || !queue.empty()) {
            while (queue.try_pop(req)) {
                count++;
            }
            #if defined(__x86_64__)
            __builtin_ia32_pause();
            #endif
        }
        
        consumed.store(count, std::memory_order_release);
    });
    
    auto start = steady_clock::now();
    
    // 生产者线程
    for (int p = 0; p < NUM_PRODUCERS; ++p) {
        producers.emplace_back([&, p]() {
            for (int64_t i = 0; i < EVENTS_PER_PRODUCER; ++i) {
                OrderRequest req;
                req.order_id = p * EVENTS_PER_PRODUCER + i;
                queue.push(req);
            }
            produced.fetch_add(EVENTS_PER_PRODUCER, std::memory_order_relaxed);
        });
    }
    
    // 等待生产者完成
    for (auto& t : producers) {
        t.join();
    }
    
    running.store(false, std::memory_order_release);
    consumer.join();
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    int64_t total = NUM_PRODUCERS * EVENTS_PER_PRODUCER;
    double throughput = total / (elapsed_ns / 1e9);
    
    printf("  Producers:   %d\n", NUM_PRODUCERS);
    printf("  Total:       %lld\n", (long long)total);
    printf("  Consumed:    %lld\n", (long long)consumed.load());
    printf("  Time:        %.3f s\n", elapsed_ns / 1e9);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
}

// ============================================================
// 基准测试5：事件大小对比
// ============================================================
void benchmark_event_sizes() {
    printf("\n========================================\n");
    printf("  Benchmark: Event Size Comparison\n");
    printf("========================================\n");
    
    printf("  MarketEvent:    %zu bytes\n", sizeof(MarketEvent));
    printf("  DepthEvent:     %zu bytes\n", sizeof(DepthEvent));
    printf("  OrderRequest:   %zu bytes\n", sizeof(OrderRequest));
    printf("  OrderResponse:  %zu bytes\n", sizeof(OrderResponse));
    printf("  Cache Line:     %zu bytes\n", CACHE_LINE_SIZE);
    
    printf("\n  Memory per 64K slots:\n");
    printf("  MarketEvent:    %.2f MB\n", 65536 * sizeof(MarketEvent) / 1e6);
    printf("  OrderRequest:   %.2f MB\n", 65536 * sizeof(OrderRequest) / 1e6);
}

// ============================================================
// 主函数
// ============================================================
int main() {
    printf("========================================\n");
    printf("  Disruptor Engine Benchmark\n");
    printf("========================================\n");
    printf("  Testing low-latency components\n");
    printf("========================================\n");
    
    benchmark_event_sizes();
    benchmark_single_producer();
    benchmark_single_consumer();
    benchmark_spsc_concurrent();
    benchmark_mpsc();
    
    printf("\n========================================\n");
    printf("  Benchmark Complete!\n");
    printf("========================================\n");
    
    return 0;
}

