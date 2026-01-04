/**
 * @file logger.h
 * @brief 轻量级日志系统
 *
 * 功能：
 * 1. 多级别日志（DEBUG/INFO/WARN/ERROR）
 * 2. 文件日志持久化
 * 3. 日志轮转（按大小）
 * 4. 线程安全
 * 5. 高性能（异步写入）
 *
 * @author Sequence Team
 * @date 2025-01
 */

#pragma once

#include <string>
#include <fstream>
#include <mutex>
#include <memory>
#include <chrono>
#include <sstream>
#include <iomanip>
#include <queue>
#include <thread>
#include <atomic>
#include <condition_variable>

namespace trading {
namespace core {

enum class LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
};

class Logger {
public:
    static Logger& instance() {
        static Logger logger;
        return logger;
    }

    void init(const std::string& log_dir = "logs",
              const std::string& log_prefix = "trading",
              LogLevel level = LogLevel::INFO,
              size_t max_file_size = 100 * 1024 * 1024);  // 100MB

    void set_level(LogLevel level) { min_level_ = level; }
    void set_console_output(bool enable) { console_output_ = enable; }

    void debug(const std::string& msg);
    void info(const std::string& msg);
    void warn(const std::string& msg);
    void error(const std::string& msg);

    // 审计日志
    void audit(const std::string& action, const std::string& details);
    // 订单生命周期日志
    void order_lifecycle(const std::string& order_id, const std::string& action, const std::string& details);

    void shutdown();

    ~Logger();

private:
    Logger() = default;
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;

    void log(LogLevel level, const std::string& msg);
    void write_thread_func();
    void rotate_if_needed();
    std::string get_timestamp();
    std::string level_to_string(LogLevel level);
    std::string get_log_filename();

    std::string log_dir_;
    std::string log_prefix_;
    LogLevel min_level_{LogLevel::INFO};
    size_t max_file_size_{100 * 1024 * 1024};
    bool console_output_{true};

    std::ofstream log_file_;
    std::mutex file_mutex_;
    size_t current_file_size_{0};

    std::queue<std::string> log_queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::atomic<bool> running_{false};
    std::thread write_thread_;
};

// 便捷宏
#define LOG_DEBUG(msg) trading::core::Logger::instance().debug(msg)
#define LOG_INFO(msg) trading::core::Logger::instance().info(msg)
#define LOG_WARN(msg) trading::core::Logger::instance().warn(msg)
#define LOG_ERROR(msg) trading::core::Logger::instance().error(msg)

// 审计日志宏
#define LOG_AUDIT(action, details) trading::core::Logger::instance().audit(action, details)
#define LOG_ORDER(order_id, action, details) trading::core::Logger::instance().order_lifecycle(order_id, action, details)

} // namespace core
} // namespace trading
