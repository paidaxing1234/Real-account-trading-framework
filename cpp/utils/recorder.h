#pragma once

#include "../core/event_engine.h"
#include "../core/order.h"
#include "../core/data.h"
#include <fstream>
#include <memory>
#include <mutex>
#include <string>

namespace trading {

/**
 * @brief 数据记录器
 * 
 * 职责：
 * 1. 记录所有订单成交
 * 2. 记录关键事件
 * 3. 定期快照（PnL、持仓）
 * 4. CSV/日志文件存储
 */
class Recorder : public Component {
public:
    Recorder(const std::string& log_file = "trading.log")
        : log_file_(log_file) {
    }
    
    virtual ~Recorder() {
        close_log();
    }
    
    // Component接口实现
    virtual void start(EventEngine* engine) override {
        engine_ = engine;
        
        // 打开日志文件
        open_log();
        
        // 注册全局监听器（记录所有事件）
        engine->register_global_listener(
            [this](const Event::Ptr& e) {
                on_event(e);
            },
            false,  // 不忽略自己产生的事件
            false   // 不是高优先级
        );
    }
    
    virtual void stop() override {
        close_log();
    }
    
    // 记录消息
    void log(const std::string& message) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (log_stream_.is_open()) {
            auto ts = Event::current_timestamp();
            log_stream_ << ts << " | " << message << std::endl;
        }
    }

private:
    void open_log() {
        std::lock_guard<std::mutex> lock(mutex_);
        log_stream_.open(log_file_, std::ios::app);
        if (log_stream_.is_open()) {
            log_stream_ << "\n=== Trading Session Started ===" << std::endl;
        }
    }
    
    void close_log() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (log_stream_.is_open()) {
            log_stream_ << "=== Trading Session Ended ===" << std::endl;
            log_stream_.close();
        }
    }
    
    void on_event(const Event::Ptr& event) {
        std::string event_type = event->type_name();
        
        // 记录订单事件
        if (event_type == "Order") {
            auto order = std::dynamic_pointer_cast<Order>(event);
            if (order && order->is_filled()) {
                log("ORDER_FILLED: " + order->to_string());
            }
        }
        // 可以根据需要记录其他事件
    }
    
    std::string log_file_;
    std::ofstream log_stream_;
    std::mutex mutex_;
};

} // namespace trading

