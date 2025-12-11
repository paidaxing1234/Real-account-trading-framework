/**
 * @file test_ringbuffer_simple.cpp
 * @brief 简化版RingBuffer测试
 */

#include "../core/disruptor/ring_buffer.h"
#include "../core/disruptor/events.h"
#include "../core/disruptor/mpsc_queue.h"
#include <chrono>
#include <cstdio>

using namespace trading::disruptor;
using namespace std::chrono;

int main() {
    printf("========================================\n");
    printf("  Simple RingBuffer Test\n");
    printf("========================================\n");
    
    // 测试事件大小
    printf("\nEvent Sizes:\n");
    printf("  MarketEvent:    %zu bytes\n", sizeof(MarketEvent));
    printf("  OrderRequest:   %zu bytes\n", sizeof(OrderRequest));
    printf("  Cache Line:     %zu bytes\n", CACHE_LINE_SIZE);
    
    // 测试RingBuffer基本功能
    printf("\nRingBuffer Basic Test:\n");
    
    RingBuffer<MarketEvent, 1024> buffer;  // 小容量测试
    
    // 写入测试
    printf("  Writing 100 events...\n");
    for (int i = 0; i < 100; ++i) {
        int64_t seq = i;  // 使用简单递增序号
        auto& event = buffer.get(seq);
        event.clear();
        event.type = EventType::TICKER;
        event.timestamp_ns = MarketEvent::now_ns();
        event.last_price = 50000.0 + i;
        buffer.publish(seq);
    }
    
    printf("  Cursor: %lld\n", (long long)buffer.cursor());
    
    // 读取测试
    printf("  Reading events...\n");
    double sum = 0.0;
    for (int i = 0; i <= buffer.cursor(); ++i) {
        const auto& event = buffer.get(i);
        sum += event.last_price;
    }
    printf("  Sum: %.0f (expected ~5049500)\n", sum);
    
    // MPSC队列测试
    printf("\nMPSC Queue Test:\n");
    
    SPSCQueue<OrderRequest, 1024> queue;
    
    // 写入
    printf("  Writing 100 orders...\n");
    for (int i = 0; i < 100; ++i) {
        OrderRequest req;
        req.clear();
        req.order_id = i;
        req.price = 50000.0 + i;
        queue.try_push(req);
    }
    
    printf("  Queue size: %zu\n", queue.size());
    
    // 读取
    OrderRequest req;
    int count = 0;
    sum = 0.0;
    while (queue.try_pop(req)) {
        sum += req.price;
        count++;
    }
    printf("  Read %d orders, sum=%.0f\n", count, sum);
    
    // 性能测试
    printf("\nPerformance Test:\n");
    
    RingBuffer<MarketEvent, 65536> perf_buffer;
    const int NUM_EVENTS = 1000000;
    
    auto start = steady_clock::now();
    
    for (int i = 0; i < NUM_EVENTS; ++i) {
        int64_t seq = i;
        auto& event = perf_buffer.get(seq & 65535);  // 手动取模
        event.type = EventType::TICKER;
        event.timestamp_ns = i;
        event.last_price = 50000.0;
        perf_buffer.publish(seq);
    }
    
    auto end = steady_clock::now();
    auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
    
    double throughput = NUM_EVENTS / (elapsed_ns / 1e9);
    double latency = static_cast<double>(elapsed_ns) / NUM_EVENTS;
    
    printf("  Events:      %d\n", NUM_EVENTS);
    printf("  Time:        %.3f ms\n", elapsed_ns / 1e6);
    printf("  Throughput:  %.2f M events/s\n", throughput / 1e6);
    printf("  Latency:     %.1f ns/event\n", latency);
    
    printf("\n========================================\n");
    printf("  Test Complete!\n");
    printf("========================================\n");
    
    return 0;
}

