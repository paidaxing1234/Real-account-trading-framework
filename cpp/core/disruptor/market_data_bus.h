#pragma once

/**
 * @file market_data_bus.h
 * @brief 行情数据总线（SPMC模式）
 * 
 * 核心架构：
 * 
 *     MD Thread (Producer)
 *           ↓ write
 *     ┌─────────────────┐
 *     │   RingBuffer    │ ← 行情事件
 *     └─────────────────┘
 *       ↓read  ↓read  ↓read
 *    Strat1  Strat2  Logger
 *    (消费者们并发读取)
 */

#include "ring_buffer.h"
#include "events.h"
#include <vector>
#include <functional>
#include <thread>
#include <atomic>

namespace trading {
namespace disruptor {

/**
 * @brief 行情数据总线
 * 
 * 单生产者多消费者的行情分发系统
 * 
 * @tparam CAPACITY RingBuffer容量（默认64K，约4MB内存）
 */
template<size_t CAPACITY = 65536>
class MarketDataBus {
public:
    using EventHandler = std::function<void(const MarketEvent&, int64_t)>;
    
    MarketDataBus() 
        : running_(false)
        , producer_sequence_(-1) {}
    
    ~MarketDataBus() {
        stop();
    }
    
    // ============================================================
    // 生产者接口（MD Thread调用）
    // ============================================================
    
    /**
     * @brief 获取下一个可写入的事件槽位
     * @return 事件引用（直接填充，零拷贝）
     */
    MarketEvent& next() {
        int64_t seq = producer_sequence_ + 1;
        return ring_buffer_.get(seq);
    }
    
    /**
     * @brief 发布事件（使消费者可见）
     */
    void publish() {
        producer_sequence_++;
        ring_buffer_.publish(producer_sequence_);
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
        auto& event = next();
        event.clear();
        event.type = EventType::TICKER;
        event.set_timestamp();
        event.symbol_id = symbol_id;
        event.exchange_id = exchange_id;
        event.last_price = last_price;
        event.bid_price = bid_price;
        event.ask_price = ask_price;
        event.volume = volume;
        event.bid_size = bid_size;
        event.sequence = static_cast<uint32_t>(producer_sequence_ + 1);
        publish();
    }
    
    // ============================================================
    // 消费者注册
    // ============================================================
    
    /**
     * @brief 注册消费者
     * @param handler 事件处理函数
     * @return 消费者ID
     */
    size_t register_consumer(EventHandler handler) {
        size_t id = consumers_.size();
        consumers_.push_back({
            handler,
            Sequence(-1),
            nullptr,
            true
        });
        return id;
    }
    
    /**
     * @brief 获取当前生产者序号
     */
    int64_t cursor() const {
        return ring_buffer_.cursor();
    }
    
    // ============================================================
    // 消费者运行（每个消费者在独立线程中运行）
    // ============================================================
    
    /**
     * @brief 启动消费者线程
     */
    void start() {
        if (running_.exchange(true)) {
            return;  // 已经在运行
        }
        
        for (auto& consumer : consumers_) {
            consumer.running = true;
            consumer.thread = std::make_unique<std::thread>(
                &MarketDataBus::consumer_loop, this, &consumer
            );
        }
    }
    
    /**
     * @brief 停止所有消费者
     */
    void stop() {
        running_.store(false, std::memory_order_release);
        
        // 发布一个空事件唤醒消费者
        publish_ticker(0, 0, 0, 0, 0);
        
        for (auto& consumer : consumers_) {
            consumer.running = false;
            if (consumer.thread && consumer.thread->joinable()) {
                consumer.thread->join();
            }
        }
    }
    
    /**
     * @brief 检查是否运行中
     */
    bool is_running() const {
        return running_.load(std::memory_order_acquire);
    }
    
    // ============================================================
    // 消费者手动轮询（用于策略线程自己控制循环）
    // ============================================================
    
    /**
     * @brief 轮询新事件（非阻塞）
     * @param consumer_id 消费者ID
     * @param handler 处理函数
     * @return 处理的事件数量
     */
    size_t poll(size_t consumer_id, EventHandler handler) {
        if (consumer_id >= consumers_.size()) {
            return 0;
        }
        
        auto& consumer = consumers_[consumer_id];
        int64_t local_seq = consumer.sequence.get();
        int64_t available = ring_buffer_.cursor();
        
        size_t count = 0;
        while (local_seq < available) {
            local_seq++;
            const auto& event = ring_buffer_.get(local_seq);
            handler(event, local_seq);
            consumer.sequence.set(local_seq);
            count++;
        }
        
        return count;
    }
    
    /**
     * @brief 等待新事件（阻塞，Busy Spin）
     */
    int64_t wait_for(size_t consumer_id, int64_t sequence) {
        SequenceBarrier<MarketEvent, CAPACITY> barrier(ring_buffer_);
        return barrier.wait_for(sequence);
    }

private:
    struct ConsumerInfo {
        EventHandler handler;
        Sequence sequence;
        std::unique_ptr<std::thread> thread;
        bool running;
    };
    
    void consumer_loop(ConsumerInfo* consumer) {
        int64_t local_seq = consumer->sequence.get();
        SequenceBarrier<MarketEvent, CAPACITY> barrier(ring_buffer_);
        
        while (consumer->running && running_.load(std::memory_order_acquire)) {
            // 等待新数据
            int64_t available = barrier.wait_for(local_seq + 1);
            
            if (available < 0) {
                break;  // 被中断
            }
            
            // 批量处理所有可用事件
            while (local_seq < available) {
                local_seq++;
                const auto& event = ring_buffer_.get(local_seq);
                
                // 跳过空事件（心跳/停止信号）
                if (event.type != EventType::NONE) {
                    consumer->handler(event, local_seq);
                }
                
                consumer->sequence.set(local_seq);
            }
        }
    }
    
    RingBuffer<MarketEvent, CAPACITY> ring_buffer_;
    std::vector<ConsumerInfo> consumers_;
    std::atomic<bool> running_;
    int64_t producer_sequence_;
};

// 默认实例类型
using DefaultMarketDataBus = MarketDataBus<65536>;

} // namespace disruptor
} // namespace trading

