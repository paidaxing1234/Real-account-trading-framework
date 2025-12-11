#pragma once

/**
 * @file ring_buffer.h
 * @brief Disruptor风格的无锁环形缓冲区
 * 
 * 核心设计：
 * 1. 预分配内存，避免运行时分配
 * 2. 缓存行对齐，避免伪共享
 * 3. 原子操作，无锁设计
 * 4. 支持SPMC（单生产者多消费者）模式
 */

#include <atomic>
#include <cstdint>
#include <cstddef>
#include <new>
#include <stdexcept>

namespace trading {
namespace disruptor {

// ============================================================
// 缓存行大小（防止伪共享）
// ============================================================
constexpr size_t CACHE_LINE_SIZE = 64;

/**
 * @brief 缓存行填充，防止伪共享
 */
template<typename T>
struct alignas(CACHE_LINE_SIZE) CacheLinePadded {
    T value;
    char padding[CACHE_LINE_SIZE - sizeof(T) % CACHE_LINE_SIZE];
};

/**
 * @brief 无锁环形缓冲区
 * 
 * @tparam T 事件类型（必须是POD或trivially copyable）
 * @tparam CAPACITY 容量（必须是2的幂）
 * 
 * 内存布局：
 * +-----------------+
 * | cursor (atomic) | <- 写入位置（生产者专用）
 * +-----------------+
 * | padding...      | <- 防止伪共享
 * +-----------------+
 * | cached_cursor   | <- 消费者缓存的cursor（减少原子读取）
 * +-----------------+
 * | padding...      |
 * +-----------------+
 * | events[0]       | <- 预分配的事件数组
 * | events[1]       |
 * | ...             |
 * | events[N-1]     |
 * +-----------------+
 */
template<typename T, size_t CAPACITY = 65536>
class RingBuffer {
    static_assert((CAPACITY & (CAPACITY - 1)) == 0, "CAPACITY must be power of 2");
    static_assert(CAPACITY >= 2, "CAPACITY must be at least 2");
    
public:
    static constexpr size_t MASK = CAPACITY - 1;
    
    RingBuffer() : cursor_{-1}, cached_cursor_{-1} {
        // 预分配所有事件槽位
        for (size_t i = 0; i < CAPACITY; ++i) {
            new (&events_[i]) T();
        }
    }
    
    ~RingBuffer() {
        // 析构所有事件
        for (size_t i = 0; i < CAPACITY; ++i) {
            events_[i].~T();
        }
    }
    
    // 禁止拷贝和移动
    RingBuffer(const RingBuffer&) = delete;
    RingBuffer& operator=(const RingBuffer&) = delete;
    RingBuffer(RingBuffer&&) = delete;
    RingBuffer& operator=(RingBuffer&&) = delete;
    
    // ============================================================
    // 生产者接口（单生产者专用）
    // ============================================================
    
    /**
     * @brief 获取下一个可写入的序号
     * @return 序号（-1表示满）
     * 
     * 注意：单生产者模式下，不需要CAS
     */
    int64_t next() {
        return cursor_.load(std::memory_order_relaxed) + 1;
    }
    
    /**
     * @brief 获取事件槽位（用于填充数据）
     * @param sequence 序号
     * @return 事件引用
     */
    T& get(int64_t sequence) {
        return events_[sequence & MASK];
    }
    
    /**
     * @brief 发布事件（使其对消费者可见）
     * @param sequence 序号
     * 
     * 使用 release 语义确保数据写入先于cursor更新
     */
    void publish(int64_t sequence) {
        cursor_.store(sequence, std::memory_order_release);
    }
    
    /**
     * @brief 一次性发布多个事件
     */
    void publish_batch(int64_t hi_sequence) {
        cursor_.store(hi_sequence, std::memory_order_release);
    }
    
    // ============================================================
    // 消费者接口
    // ============================================================
    
    /**
     * @brief 获取当前cursor（消费者可读的最大序号）
     */
    int64_t cursor() const {
        return cursor_.load(std::memory_order_acquire);
    }
    
    /**
     * @brief 获取事件（只读）
     */
    const T& get(int64_t sequence) const {
        return events_[sequence & MASK];
    }
    
    // ============================================================
    // 容量信息
    // ============================================================
    
    static constexpr size_t capacity() { return CAPACITY; }
    static constexpr size_t mask() { return MASK; }
    
    /**
     * @brief 获取可用空间
     */
    size_t available_capacity(int64_t consumer_sequence) const {
        int64_t producer_sequence = cursor_.load(std::memory_order_acquire);
        return CAPACITY - (producer_sequence - consumer_sequence);
    }

private:
    // 写入cursor（生产者专用）
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> cursor_;
    
    // 缓存行填充
    char padding1_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
    
    // 消费者缓存的cursor（减少原子读取频率）
    alignas(CACHE_LINE_SIZE) int64_t cached_cursor_;
    
    // 缓存行填充
    char padding2_[CACHE_LINE_SIZE - sizeof(int64_t)];
    
    // 预分配的事件数组
    alignas(CACHE_LINE_SIZE) T events_[CAPACITY];
};

/**
 * @brief 序列屏障 - 消费者等待策略
 * 
 * 用于消费者等待生产者发布新数据
 */
template<typename T, size_t CAPACITY>
class SequenceBarrier {
public:
    explicit SequenceBarrier(RingBuffer<T, CAPACITY>& ring_buffer)
        : ring_buffer_(ring_buffer)
        , alert_(false) {}
    
    /**
     * @brief 等待序号可用（Busy Spin策略）
     * @param sequence 期望的序号
     * @return 实际可用的最大序号
     * 
     * 这是最低延迟的等待策略，但会占用CPU
     */
    int64_t wait_for(int64_t sequence) {
        int64_t available;
        int spin_count = 0;
        
        while ((available = ring_buffer_.cursor()) < sequence) {
            if (alert_.load(std::memory_order_acquire)) {
                return -1;  // 被中断
            }
            
            // Busy spin with progressive backoff
            if (spin_count < 100) {
                // 纯busy spin
                spin_count++;
            } else if (spin_count < 1000) {
                // 暂停指令（省电）
                #if defined(__x86_64__) || defined(__i386__)
                __builtin_ia32_pause();
                #elif defined(__aarch64__)
                asm volatile("yield" ::: "memory");
                #endif
                spin_count++;
            } else {
                // 极短睡眠（fallback）
                // 注意：在生产环境中通常不会走到这里
                spin_count = 0;
            }
        }
        
        return available;
    }
    
    /**
     * @brief 尝试获取序号（非阻塞）
     * @param sequence 期望的序号
     * @return 实际可用的最大序号，-1表示不可用
     */
    int64_t try_wait_for(int64_t sequence) {
        int64_t available = ring_buffer_.cursor();
        return available >= sequence ? available : -1;
    }
    
    /**
     * @brief 发出警报（中断等待）
     */
    void alert() {
        alert_.store(true, std::memory_order_release);
    }
    
    /**
     * @brief 清除警报
     */
    void clear_alert() {
        alert_.store(false, std::memory_order_release);
    }
    
    /**
     * @brief 检查是否有警报
     */
    bool is_alerted() const {
        return alert_.load(std::memory_order_acquire);
    }

private:
    RingBuffer<T, CAPACITY>& ring_buffer_;
    std::atomic<bool> alert_;
};

/**
 * @brief 消费者序列 - 跟踪消费进度
 */
class Sequence {
public:
    explicit Sequence(int64_t initial = -1) : value_(initial) {}
    
    int64_t get() const {
        return value_.load(std::memory_order_acquire);
    }
    
    void set(int64_t value) {
        value_.store(value, std::memory_order_release);
    }
    
    bool compare_and_set(int64_t expected, int64_t new_value) {
        return value_.compare_exchange_strong(
            expected, new_value,
            std::memory_order_release,
            std::memory_order_acquire
        );
    }

private:
    alignas(CACHE_LINE_SIZE) std::atomic<int64_t> value_;
    char padding_[CACHE_LINE_SIZE - sizeof(std::atomic<int64_t>)];
};

} // namespace disruptor
} // namespace trading

