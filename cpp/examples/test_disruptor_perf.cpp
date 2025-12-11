/**
 * @file test_disruptor_perf.cpp
 * @brief 环形总线性能测试（防止编译器优化）
 */

#include "../core/disruptor/ring_buffer.h"
#include "../core/disruptor/mpsc_queue.h"
#include "../core/disruptor/events.h"
#include <chrono>
#include <thread>
#include <atomic>
#include <vector>
#include <algorithm>
#include <numeric>
#include <cstdio>

using namespace trading::disruptor;
using namespace std::chrono;

// 防止优化的变量
volatile double g_sink = 0.0;
volatile int64_t g_count = 0;

// ============================================================
// 测试1：单线程写入性能
// ============================================================
void test_write_performance() {
    printf("\n========================================\n");
    printf("  Test 1: Write Performance\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    
    const int NUM_EVENTS = 1000000;
    
    // 预热
    for (int i = 0; i < 1000; ++i) {
        auto& event = buffer.get(i);
        event.type = EventType::TICKER;
        event.last_price = 50000.0;
        buffer.publish(i);
    }
    
    // 开始计时
    auto start = steady_clock::now();
    
    int64_t seq = 1000;
    for (int i = 0; i < NUM_EVENTS; ++i) {
        auto& event = buffer.get(seq & 65535);
        event.type = EventType::TICKER;
        event.timestamp_ns = MarketEvent::now_ns();  // 获取时间戳
        event.last_price = 50000.0 + (i % 100);
        event.bid_price = event.last_price - 5.0;
        event.ask_price = event.last_price + 5.0;
        event.volume = 1000.0;
        buffer.publish(seq);
        seq++;
    }
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    // 读取最后一个值（防止优化）
    g_sink = buffer.get(seq - 1 & 65535).last_price;
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    double latency = static_cast<double>(elapsed_ns) / NUM_EVENTS;
    
    printf("  Events:      %d\n", NUM_EVENTS);
    printf("  Time:        %.3f ms\n", elapsed_ns / 1e6);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    printf("  Latency:     %.1f ns/event\n", latency);
    printf("  (checksum:   %.0f)\n", g_sink);
}

// ============================================================
// 测试2：端到端延迟测量
// ============================================================
void test_e2e_latency() {
    printf("\n========================================\n");
    printf("  Test 2: End-to-End Latency\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    std::vector<int64_t> latencies;
    latencies.reserve(100000);
    
    const int NUM_EVENTS = 100000;
    
    // 写入并立即读取（单线程模拟）
    for (int i = 0; i < NUM_EVENTS; ++i) {
        // 写入
        int64_t seq = i;
        auto& event = buffer.get(seq & 65535);
        event.type = EventType::TICKER;
        event.timestamp_ns = MarketEvent::now_ns();
        event.last_price = 50000.0 + i;
        buffer.publish(seq);
        
        // 立即读取
        const auto& read_event = buffer.get(seq & 65535);
        int64_t now = MarketEvent::now_ns();
        int64_t latency = now - read_event.timestamp_ns;
        
        if (latency > 0 && latency < 1000000) {  // 过滤异常值
            latencies.push_back(latency);
        }
    }
    
    // 统计
    if (!latencies.empty()) {
        std::sort(latencies.begin(), latencies.end());
        
        size_t count = latencies.size();
        int64_t min_lat = latencies.front();
        int64_t max_lat = latencies.back();
        int64_t avg_lat = std::accumulate(latencies.begin(), latencies.end(), 0LL) / count;
        int64_t p50 = latencies[count * 50 / 100];
        int64_t p95 = latencies[count * 95 / 100];
        int64_t p99 = latencies[count * 99 / 100];
        
        printf("  Samples:     %zu\n", count);
        printf("  Min:         %lld ns\n", (long long)min_lat);
        printf("  Avg:         %lld ns\n", (long long)avg_lat);
        printf("  P50:         %lld ns\n", (long long)p50);
        printf("  P95:         %lld ns\n", (long long)p95);
        printf("  P99:         %lld ns\n", (long long)p99);
        printf("  Max:         %lld ns\n", (long long)max_lat);
    }
}

// ============================================================
// 测试3：MPSC队列性能
// ============================================================
void test_mpsc_performance() {
    printf("\n========================================\n");
    printf("  Test 3: MPSC Queue Performance\n");
    printf("========================================\n");
    
    SPSCQueue<OrderRequest, 4096> queue;
    
    const int NUM_ORDERS = 100000;
    
    // 写入测试
    auto start_write = steady_clock::now();
    
    for (int i = 0; i < NUM_ORDERS; ++i) {
        OrderRequest req;
        req.clear();
        req.order_id = i;
        req.set_timestamp();
        req.price = 50000.0 + (i % 100);
        queue.try_push(req);
    }
    
    auto end_write = steady_clock::now();
    auto write_ns = duration_cast<nanoseconds>(end_write - start_write).count();
    
    // 读取测试
    auto start_read = steady_clock::now();
    
    OrderRequest req;
    int count = 0;
    double sum = 0.0;
    
    while (queue.try_pop(req)) {
        sum += req.price;
        count++;
    }
    
    auto end_read = steady_clock::now();
    auto read_ns = duration_cast<nanoseconds>(end_read - start_read).count();
    
    g_sink = sum;
    g_count = count;
    
    printf("  Orders:      %d\n", NUM_ORDERS);
    printf("  Read:        %d\n", count);
    printf("  Write Time:  %.3f ms (%.1f ns/op)\n", 
           write_ns / 1e6, static_cast<double>(write_ns) / NUM_ORDERS);
    printf("  Read Time:   %.3f ms (%.1f ns/op)\n", 
           read_ns / 1e6, static_cast<double>(read_ns) / count);
    printf("  (checksum:   %.0f)\n", g_sink);
}

// ============================================================
// 测试4：多线程SPSC性能
// ============================================================
void test_spsc_concurrent() {
    printf("\n========================================\n");
    printf("  Test 4: SPSC Concurrent (2 threads)\n");
    printf("========================================\n");
    
    RingBuffer<MarketEvent, 65536> buffer;
    std::atomic<bool> producer_done{false};
    std::atomic<int64_t> consumed{0};
    std::vector<int64_t> latencies;
    
    const int64_t NUM_EVENTS = 1000000;
    
    // 消费者线程
    std::thread consumer([&]() {
        int64_t local_seq = -1;
        std::vector<int64_t> local_latencies;
        local_latencies.reserve(NUM_EVENTS);
        
        // 等待生产者开始
        while (buffer.cursor() < 0 && !producer_done.load(std::memory_order_acquire)) {
            #if defined(__x86_64__)
            __builtin_ia32_pause();
            #endif
        }
        
        // 持续消费直到生产者完成且所有数据消费完
        while (true) {
            int64_t available = buffer.cursor();
            
            // 处理所有可用事件
            while (local_seq < available) {
                local_seq++;
                const auto& event = buffer.get(local_seq & 65535);
                
                // 计算延迟
                int64_t now = MarketEvent::now_ns();
                int64_t lat = now - event.timestamp_ns;
                if (lat > 0 && lat < 1000000) {
                    local_latencies.push_back(lat);
                }
            }
            
            // 检查是否完成
            if (producer_done.load(std::memory_order_acquire) && 
                local_seq >= NUM_EVENTS - 1) {
                break;
            }
            
            // 短暂等待
            #if defined(__x86_64__)
            __builtin_ia32_pause();
            #endif
        }
        
        consumed.store(local_seq + 1, std::memory_order_release);
        latencies = std::move(local_latencies);
    });
    
    // 生产者（主线程）
    auto start = steady_clock::now();
    
    for (int64_t i = 0; i < NUM_EVENTS; ++i) {
        auto& event = buffer.get(i & 65535);
        event.type = EventType::TICKER;
        event.timestamp_ns = MarketEvent::now_ns();
        event.last_price = static_cast<double>(i);
        buffer.publish(i);
    }
    
    // 标记生产完成
    producer_done.store(true, std::memory_order_release);
    
    // 等待消费者完成
    consumer.join();
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    
    printf("  Events:      %lld\n", (long long)NUM_EVENTS);
    printf("  Consumed:    %lld\n", (long long)consumed.load());
    printf("  Time:        %.3f s\n", elapsed_ns / 1e9);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    
    // 延迟统计
    if (!latencies.empty()) {
        std::sort(latencies.begin(), latencies.end());
        size_t count = latencies.size();
        
        printf("\n  Latency Statistics:\n");
        printf("  Samples:     %zu\n", count);
        printf("  Min:         %lld ns\n", (long long)latencies.front());
        printf("  P50:         %lld ns (%.2f μs)\n", 
               (long long)latencies[count * 50 / 100],
               latencies[count * 50 / 100] / 1000.0);
        printf("  P95:         %lld ns (%.2f μs)\n", 
               (long long)latencies[count * 95 / 100],
               latencies[count * 95 / 100] / 1000.0);
        printf("  P99:         %lld ns (%.2f μs)\n", 
               (long long)latencies[count * 99 / 100],
               latencies[count * 99 / 100] / 1000.0);
        printf("  Max:         %lld ns (%.2f μs)\n", 
               (long long)latencies.back(),
               latencies.back() / 1000.0);
    }
}

// ============================================================
// 主函数
// ============================================================
int main() {
    printf("========================================\n");
    printf("  Disruptor Ring Buffer Performance\n");
    printf("========================================\n");
    printf("  Architecture: LMAX Disruptor Style\n");
    printf("  MarketEvent:  %zu bytes\n", sizeof(MarketEvent));
    printf("  OrderRequest: %zu bytes\n", sizeof(OrderRequest));
    printf("========================================\n");
    
    test_write_performance();
    test_e2e_latency();
    test_mpsc_performance();
    test_spsc_concurrent();
    
    printf("\n========================================\n");
    printf("  All Tests Complete!\n");
    printf("========================================\n");
    
    return 0;
}

