#pragma once

/**
 * @file mpsc_queue.h
 * @brief 多生产者单消费者无锁队列（用于指令总线）
 * 
 * 策略线程（多个） -> OrderBus -> OEMS线程（单个）
 */

#include <atomic>
#include <cstdint>
#include <cstddef>
#include "ring_buffer.h"

namespace trading {
namespace disruptor {

/**
 * @brief MPSC无锁队列
 * 
 * 基于环形缓冲区，支持多个生产者并发写入
 * 
 * @tparam T 元素类型
 * @tparam CAPACITY 容量（必须是2的幂）
 */
template<typename T, size_t CAPACITY = 4096>
class MPSCQueue {
    static_assert((CAPACITY & (CAPACITY - 1)) == 0, "CAPACITY must be power of 2");
    
public:
    static constexpr size_t MASK = CAPACITY - 1;
    
    MPSCQueue() : head_{0}, tail_{0} {
        for (size_t i = 0; i < CAPACITY; ++i) {
            sequence_[i].store(-1, std::memory_order_relaxed);
        }
    }
    
    /**
     * @brief 尝试入队（生产者调用）
     * @param item 要入队的元素
     * @return true=成功, false=队列满
     * 
     * 使用CAS实现多生产者并发安全
     */
    bool try_push(const T& item) {
        int64_t head;
        size_t index;
        
        do {
            head = head_.load(std::memory_order_relaxed);
            index = head & MASK;
            
            // 检查槽位是否可用
            int64_t seq = sequence_[index].load(std::memory_order_acquire);
            int64_t expected = head - CAPACITY;
            
            if (seq < expected) {
                // 队列满
                return false;
            }
            
            if (seq != expected) {
                // 其他生产者正在写入，重试
                continue;
            }
            
        } while (!head_.compare_exchange_weak(
            head, head + 1,
            std::memory_order_relaxed,
            std::memory_order_relaxed
        ));
        
        // 写入数据
        buffer_[index] = item;
        
        // 标记完成（使消费者可见）
        sequence_[index].store(head, std::memory_order_release);
        
        return true;
    }
    
    /**
     * @brief 阻塞入队（带自旋）
     */
    void push(const T& item) {
        while (!try_push(item)) {
            #if defined(__x86_64__) || defined(__i386__)
            __builtin_ia32_pause();
            #elif defined(__aarch64__)
            asm volatile("yield" ::: "memory");
            #endif
        }
    }
    
    /**
     * @brief 尝试出队（消费者调用）
     * @param item 输出参数
     * @return true=成功, false=队列空
     * 
     * 单消费者，无需CAS
     */
    bool try_pop(T& item) {
        int64_t tail = tail_.load(std::memory_order_relaxed);
        size_t index = tail & MASK;
        
        // 检查是否有数据
        int64_t seq = sequence_[index].load(std::memory_order_acquire);
        
        if (seq != tail) {
            // 队列空或数据未就绪
            return false;
        }
        
        // 读取数据
        item = buffer_[index];
        
        // 标记已消费（释放槽位）
        sequence_[index].store(tail - CAPACITY + 1, std::memory_order_release);
        
        // 推进tail
        tail_.store(tail + 1, std::memory_order_relaxed);
        
        return true;
    }
    
    /**
     * @brief 批量出队
     * @param items 输出数组
     * @param max_count 最大数量
     * @return 实际出队数量
     */
    size_t pop_batch(T* items, size_t max_count) {
        size_t count = 0;
        
        while (count < max_count && try_pop(items[count])) {
            count++;
        }
        
        return count;
    }
    
    /**
     * @brief 检查队列是否为空
     */
    bool empty() const {
        int64_t head = head_.load(std::memory_order_acquire);
        int64_t tail = tail_.load(std::memory_order_acquire);
        return head == tail;
    }
    
    /**
     * @brief 获取当前大小（近似值）
     */
    size_t size() const {
        int64_t head = head_.load(std::memory_order_acquire);
        int64_t tail = tail_.load(std::memory_order_acquire);
        return static_cast<size_t>(head - tail);
    }

private:
    // 生产者游标（多生产者共享，用CAS）
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> head_;
    char padding1_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
    
    // 消费者游标（单消费者专用）
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> tail_;
    char padding2_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
    
    // 序列号数组（用于同步）
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> sequence_[CAPACITY];
    
    // 数据缓冲区
    alignas(CACHE_LINE_SIZE) T buffer_[CAPACITY];
};

/**
 * @brief 简化版SPSC队列（单生产者单消费者）
 * 
 * 比MPSC更快，适用于1:1场景
 */
template<typename T, size_t CAPACITY = 4096>
class SPSCQueue {
    static_assert((CAPACITY & (CAPACITY - 1)) == 0, "CAPACITY must be power of 2");
    
public:
    static constexpr size_t MASK = CAPACITY - 1;
    
    SPSCQueue() : head_{0}, tail_{0} {}
    
    /**
     * @brief 入队（单生产者）
     */
    bool try_push(const T& item) {
        int64_t head = head_.load(std::memory_order_relaxed);
        int64_t tail = tail_.load(std::memory_order_acquire);
        
        if (head - tail >= static_cast<int64_t>(CAPACITY)) {
            return false;  // 满
        }
        
        buffer_[head & MASK] = item;
        head_.store(head + 1, std::memory_order_release);
        
        return true;
    }
    
    /**
     * @brief 出队（单消费者）
     */
    bool try_pop(T& item) {
        int64_t tail = tail_.load(std::memory_order_relaxed);
        int64_t head = head_.load(std::memory_order_acquire);
        
        if (tail >= head) {
            return false;  // 空
        }
        
        item = buffer_[tail & MASK];
        tail_.store(tail + 1, std::memory_order_release);
        
        return true;
    }
    
    bool empty() const {
        return head_.load(std::memory_order_acquire) == 
               tail_.load(std::memory_order_acquire);
    }
    
    size_t size() const {
        int64_t head = head_.load(std::memory_order_acquire);
        int64_t tail = tail_.load(std::memory_order_acquire);
        return static_cast<size_t>(head - tail);
    }

private:
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> head_;
    char padding1_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
    
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> tail_;
    char padding2_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
    
    alignas(CACHE_LINE_SIZE) T buffer_[CAPACITY];
};

} // namespace disruptor
} // namespace trading

