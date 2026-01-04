#include "logger.h"
#include <iostream>
#include <sys/stat.h>
#include <sys/types.h>

namespace trading {
namespace core {

void Logger::init(const std::string& log_dir,
                  const std::string& log_prefix,
                  LogLevel level,
                  size_t max_file_size) {
    log_dir_ = log_dir;
    log_prefix_ = log_prefix;
    min_level_ = level;
    max_file_size_ = max_file_size;

    // 创建日志目录
    mkdir(log_dir_.c_str(), 0755);

    // 打开日志文件
    std::string filename = get_log_filename();
    log_file_.open(filename, std::ios::app);
    if (!log_file_.is_open()) {
        std::cerr << "[Logger] 无法打开日志文件: " << filename << std::endl;
        return;
    }

    // 获取当前文件大小
    log_file_.seekp(0, std::ios::end);
    current_file_size_ = log_file_.tellp();

    // 启动写入线程
    running_.store(true);
    write_thread_ = std::thread(&Logger::write_thread_func, this);

    info("日志系统已初始化: " + filename);
}

void Logger::debug(const std::string& msg) {
    log(LogLevel::DEBUG, msg);
}

void Logger::info(const std::string& msg) {
    log(LogLevel::INFO, msg);
}

void Logger::warn(const std::string& msg) {
    log(LogLevel::WARN, msg);
}

void Logger::error(const std::string& msg) {
    log(LogLevel::ERROR, msg);
}

void Logger::audit(const std::string& action, const std::string& details) {
    std::string audit_msg = "[AUDIT] " + action + " | " + details;
    log(LogLevel::INFO, audit_msg);
}

void Logger::order_lifecycle(const std::string& order_id, const std::string& action, const std::string& details) {
    std::string order_msg = "[ORDER:" + order_id + "] " + action + " | " + details;
    log(LogLevel::INFO, order_msg);
}

void Logger::log(LogLevel level, const std::string& msg) {
    if (level < min_level_) {
        return;
    }

    std::string log_line = "[" + get_timestamp() + "] "
                         + "[" + level_to_string(level) + "] "
                         + msg;

    // 控制台输出
    if (console_output_) {
        if (level >= LogLevel::ERROR) {
            std::cerr << log_line << std::endl;
        } else {
            std::cout << log_line << std::endl;
        }
    }

    // 加入队列
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        log_queue_.push(log_line);
    }
    queue_cv_.notify_one();
}

void Logger::write_thread_func() {
    while (running_.load()) {
        std::unique_lock<std::mutex> lock(queue_mutex_);
        queue_cv_.wait_for(lock, std::chrono::milliseconds(100), [this]() {
            return !log_queue_.empty() || !running_.load();
        });

        while (!log_queue_.empty()) {
            std::string log_line = log_queue_.front();
            log_queue_.pop();
            lock.unlock();

            // 写入文件
            {
                std::lock_guard<std::mutex> file_lock(file_mutex_);
                if (log_file_.is_open()) {
                    log_file_ << log_line << std::endl;
                    current_file_size_ += log_line.size() + 1;

                    // 检查是否需要轮转
                    if (current_file_size_ >= max_file_size_) {
                        rotate_if_needed();
                    }
                }
            }

            lock.lock();
        }
    }
}

void Logger::rotate_if_needed() {
    log_file_.close();

    // 重命名旧文件
    std::string old_filename = get_log_filename();
    std::string new_filename = old_filename + "." + get_timestamp();
    rename(old_filename.c_str(), new_filename.c_str());

    // 打开新文件
    log_file_.open(old_filename, std::ios::app);
    current_file_size_ = 0;
}

std::string Logger::get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;

    std::stringstream ss;
    ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S");
    ss << '.' << std::setfill('0') << std::setw(3) << ms.count();
    return ss.str();
}

std::string Logger::level_to_string(LogLevel level) {
    switch (level) {
        case LogLevel::DEBUG: return "DEBUG";
        case LogLevel::INFO:  return "INFO ";
        case LogLevel::WARN:  return "WARN ";
        case LogLevel::ERROR: return "ERROR";
        default: return "UNKNOWN";
    }
}

std::string Logger::get_log_filename() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::stringstream ss;
    ss << log_dir_ << "/" << log_prefix_ << "_"
       << std::put_time(std::localtime(&time_t), "%Y%m%d") << ".log";
    return ss.str();
}

void Logger::shutdown() {
    if (running_.load()) {
        running_.store(false);
        queue_cv_.notify_all();
        if (write_thread_.joinable()) {
            write_thread_.join();
        }
        if (log_file_.is_open()) {
            log_file_.close();
        }
    }
}

Logger::~Logger() {
    shutdown();
}

} // namespace core
} // namespace trading
