#pragma once

/**
 * @file ws_reconnect.h
 * @brief WebSocket 自动重连模块
 *
 * 提供通用的 WebSocket 重连机制，支持：
 * - 指数退避重连策略
 * - 重连后自动重新订阅
 * - 线程安全操作
 *
 * @author Sequence Team
 * @date 2024-12
 */

#include <atomic>
#include <chrono>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>
#include <string>
#include <iostream>

namespace trading {
namespace core {

/**
 * @brief WebSocket 重连配置
 */
struct ReconnectConfig {
    int max_retries = 10;                    // 最大重试次数，-1 表示无限重试
    int initial_delay_ms = 1000;             // 初始重连延迟（毫秒）
    int max_delay_ms = 30000;                // 最大重连延迟（毫秒）
    double backoff_multiplier = 2.0;         // 退避倍数
    bool auto_resubscribe = true;            // 重连后自动重新订阅
};

/**
 * @brief WebSocket 重连管理器
 *
 * 使用方法：
 * 1. 创建 ReconnectManager 实例
 * 2. 设置连接函数、订阅函数
 * 3. 在 WebSocket 断开时调用 on_disconnected()
 * 4. 在 WebSocket 连接成功时调用 on_connected()
 */
class ReconnectManager {
public:
    using ConnectFunc = std::function<bool()>;
    using ResubscribeFunc = std::function<void()>;
    using OnReconnectedFunc = std::function<void()>;

    explicit ReconnectManager(const std::string& name = "WebSocket")
        : name_(name)
        , is_reconnecting_(false)
        , should_reconnect_(true)
        , retry_count_(0)
    {}

    ~ReconnectManager() {
        stop();
    }

    /**
     * @brief 设置重连配置
     */
    void set_config(const ReconnectConfig& config) {
        config_ = config;
    }

    /**
     * @brief 设置连接函数
     */
    void set_connect_func(ConnectFunc func) {
        connect_func_ = std::move(func);
    }

    /**
     * @brief 设置重新订阅函数
     */
    void set_resubscribe_func(ResubscribeFunc func) {
        resubscribe_func_ = std::move(func);
    }

    /**
     * @brief 设置重连成功回调
     */
    void set_on_reconnected(OnReconnectedFunc func) {
        on_reconnected_ = std::move(func);
    }

    /**
     * @brief 启用/禁用自动重连
     */
    void set_enabled(bool enabled) {
        should_reconnect_.store(enabled);
    }

    /**
     * @brief 检查是否正在重连
     */
    bool is_reconnecting() const {
        return is_reconnecting_.load();
    }

    /**
     * @brief 当 WebSocket 断开连接时调用
     *
     * 启动异步重连流程
     */
    void on_disconnected() {
        if (!should_reconnect_.load()) {
            std::cout << "[" << name_ << "] 自动重连已禁用" << std::endl;
            return;
        }

        // 使用 compare_exchange 确保只有一个线程能启动重连
        bool expected = false;
        if (!is_reconnecting_.compare_exchange_strong(expected, true)) {
            return;  // 已经在重连中
        }

        retry_count_ = 0;

        // 在新线程中启动重连，避免阻塞当前线程（可能是 io_thread）
        std::thread([this]() {
            // 等待旧的重连线程结束
            if (reconnect_thread_ && reconnect_thread_->joinable()) {
                reconnect_thread_->join();
            }

            // 启动新的重连线程
            reconnect_thread_ = std::make_unique<std::thread>([this]() {
                reconnect_loop();
            });
        }).detach();
    }

    /**
     * @brief 当 WebSocket 连接成功时调用
     *
     * 重置重连状态，执行重新订阅
     */
    void on_connected() {
        bool was_reconnecting = is_reconnecting_.exchange(false);
        retry_count_ = 0;

        if (was_reconnecting) {
            std::cout << "[" << name_ << "] 重连成功" << std::endl;

            // 重新订阅
            if (config_.auto_resubscribe && resubscribe_func_) {
                std::cout << "[" << name_ << "] 开始重新订阅..." << std::endl;
                try {
                    resubscribe_func_();
                    std::cout << "[" << name_ << "] 重新订阅完成" << std::endl;
                } catch (const std::exception& e) {
                    std::cerr << "[" << name_ << "] 重新订阅失败: " << e.what() << std::endl;
                }
            }

            // 调用重连成功回调
            if (on_reconnected_) {
                on_reconnected_();
            }
        }
    }

    /**
     * @brief 停止重连
     */
    void stop() {
        should_reconnect_.store(false);
        is_reconnecting_.store(false);

        if (reconnect_thread_ && reconnect_thread_->joinable()) {
            reconnect_thread_->join();
            reconnect_thread_.reset();
        }
    }

    /**
     * @brief 重置重连状态（用于手动重连）
     */
    void reset() {
        is_reconnecting_.store(false);
        retry_count_ = 0;
    }

private:
    void reconnect_loop() {
        int delay_ms = config_.initial_delay_ms;

        while (should_reconnect_.load() && is_reconnecting_.load()) {
            // 检查重试次数
            if (config_.max_retries >= 0 && retry_count_ >= config_.max_retries) {
                std::cerr << "[" << name_ << "] 达到最大重试次数 ("
                          << config_.max_retries << ")，停止重连" << std::endl;
                is_reconnecting_.store(false);
                break;
            }

            retry_count_++;
            std::cout << "[" << name_ << "] 第 " << retry_count_ << " 次重连尝试，"
                      << "等待 " << delay_ms << "ms..." << std::endl;

            // 等待（分段等待以便快速响应停止信号）
            int waited = 0;
            while (waited < delay_ms && should_reconnect_.load() && is_reconnecting_.load()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                waited += 100;
            }

            if (!should_reconnect_.load() || !is_reconnecting_.load()) {
                break;
            }

            // 尝试连接
            if (connect_func_) {
                try {
                    bool success = connect_func_();
                    if (success) {
                        // 连接成功，on_connected() 会被调用
                        return;
                    }
                } catch (const std::exception& e) {
                    std::cerr << "[" << name_ << "] 重连异常: " << e.what() << std::endl;
                }
            }

            // 计算下次延迟（指数退避）
            delay_ms = std::min(
                static_cast<int>(delay_ms * config_.backoff_multiplier),
                config_.max_delay_ms
            );
        }
    }

    std::string name_;
    ReconnectConfig config_;

    std::atomic<bool> is_reconnecting_;
    std::atomic<bool> should_reconnect_;
    int retry_count_;

    ConnectFunc connect_func_;
    ResubscribeFunc resubscribe_func_;
    OnReconnectedFunc on_reconnected_;

    std::unique_ptr<std::thread> reconnect_thread_;
};

} // namespace core
} // namespace trading
