#pragma once

#include "journal_protocol.h"
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <string>
#include <stdexcept>
#include <chrono>
#include <cstdio>

namespace trading {
namespace journal {

class JournalWriter {
public:
    /**
     * @brief 构造函数
     * @param file_path Journal文件路径
     * @param page_size 页面大小（默认128MB）
     */
    JournalWriter(const std::string& file_path, size_t page_size = 128 * 1024 * 1024) 
        : file_path_(file_path), page_size_(page_size), fd_(-1), buffer_(nullptr) {
        
        // 1. 创建/打开文件
        fd_ = open(file_path.c_str(), O_RDWR | O_CREAT, 0666);
        if (fd_ < 0) {
            throw std::runtime_error("Failed to open journal file: " + file_path);
        }
        
        // 2. 设置文件大小
        if (ftruncate(fd_, page_size) != 0) {
            close(fd_);
            throw std::runtime_error("Failed to set file size");
        }
        
        // 3. mmap 映射
        buffer_ = static_cast<char*>(
            mmap(nullptr, page_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0)
        );
        
        if (buffer_ == MAP_FAILED) {
            close(fd_);
            throw std::runtime_error("Failed to mmap");
        }
        
        // 4. 初始化 PageHeader
        header_ = new (buffer_) PageHeader();
        header_->capacity = page_size;
        header_->version = 1;
        
        // 5. 建议使用大页（性能优化）
        #ifdef MADV_HUGEPAGE
        madvise(buffer_, page_size, MADV_HUGEPAGE);
        #endif
        
        printf("[JournalWriter] Initialized: %s (size: %zu MB)\n", 
               file_path.c_str(), page_size / 1024 / 1024);
    }
    
    ~JournalWriter() {
        if (buffer_ != MAP_FAILED && buffer_ != nullptr) {
            msync(buffer_, page_size_, MS_SYNC);  // 同步到磁盘
            munmap(buffer_, page_size_);
        }
        if (fd_ >= 0) {
            close(fd_);
        }
        printf("[JournalWriter] Destroyed\n");
    }
    
    /**
     * @brief 写入 Ticker 事件
     * @return true=成功, false=页面满
     */
    bool write_ticker(const char* symbol, double last_price, 
                     double bid_price, double ask_price, double volume) {
        // 1. 检查空间
        uint32_t curr = header_->write_cursor.load(std::memory_order_relaxed);
        uint32_t required = sizeof(TickerFrame);
        
        if (curr + required > page_size_) {
            printf("[JournalWriter] Page full! curr=%u, required=%u, page_size=%zu\n",
                   curr, required, page_size_);
            return false;
        }
        
        // 2. 定位写入位置
        TickerFrame* frame = reinterpret_cast<TickerFrame*>(buffer_ + curr);
        
        // 3. 填充数据（零拷贝的精髓：直接写入mmap内存）
        frame->header.length = sizeof(TickerFrame) - sizeof(FrameHeader);
        frame->header.msg_type = static_cast<uint32_t>(MessageType::TICKER);
        frame->header.gen_time_ns = now_in_nano();
        frame->header.trigger_time_ns = 0;
        frame->header.source = 0;
        frame->header.dest = 0;
        
        strncpy(frame->symbol, symbol, sizeof(frame->symbol) - 1);
        frame->symbol[sizeof(frame->symbol) - 1] = '\0';
        frame->last_price = last_price;
        frame->bid_price = bid_price;
        frame->ask_price = ask_price;
        frame->volume = volume;
        
        // 4. 【关键】原子更新游标（一旦更新，Reader 立即可见）
        header_->write_cursor.store(curr + required, std::memory_order_release);
        
        return true;
    }
    
    /**
     * @brief 写入 Order 事件
     */
    bool write_order(const char* symbol, uint64_t order_id, 
                    uint32_t side, uint32_t order_type, double price, double quantity) {
        uint32_t curr = header_->write_cursor.load(std::memory_order_relaxed);
        uint32_t required = sizeof(OrderFrame);
        
        if (curr + required > page_size_) {
            return false;
        }
        
        OrderFrame* frame = reinterpret_cast<OrderFrame*>(buffer_ + curr);
        
        frame->header.length = sizeof(OrderFrame) - sizeof(FrameHeader);
        frame->header.msg_type = static_cast<uint32_t>(MessageType::ORDER);
        frame->header.gen_time_ns = now_in_nano();
        frame->header.trigger_time_ns = 0;
        
        strncpy(frame->symbol, symbol, sizeof(frame->symbol) - 1);
        frame->symbol[sizeof(frame->symbol) - 1] = '\0';
        frame->order_id = order_id;
        frame->side = side;
        frame->order_type = order_type;
        frame->price = price;
        frame->quantity = quantity;
        
        header_->write_cursor.store(curr + required, std::memory_order_release);
        
        return true;
    }
    
    /**
     * @brief 获取当前写入位置
     */
    uint32_t get_write_cursor() const {
        return header_->write_cursor.load(std::memory_order_acquire);
    }
    
    /**
     * @brief 获取已写入的事件数量（估算）
     */
    uint32_t get_event_count() const {
        uint32_t cursor = header_->write_cursor.load(std::memory_order_acquire);
        // 假设平均每个事件64字节
        return (cursor - sizeof(PageHeader)) / 64;
    }
    
    /**
     * @brief 重置Journal（清空数据）
     */
    void reset() {
        header_->write_cursor.store(sizeof(PageHeader), std::memory_order_release);
        header_->read_cursor.store(sizeof(PageHeader), std::memory_order_release);
        printf("[JournalWriter] Reset\n");
    }

private:
    /**
     * @brief 获取纳秒级时间戳
     */
    static int64_t now_in_nano() {
        using namespace std::chrono;
        return duration_cast<nanoseconds>(
            steady_clock::now().time_since_epoch()
        ).count();
    }
    
    std::string file_path_;
    size_t page_size_;
    int fd_;
    char* buffer_;
    PageHeader* header_;
};

} // namespace journal
} // namespace trading

