#pragma once

/**
 * @file frontend_ws_server.h
 * @brief 前端 WebSocket 服务器（独立线程，非阻塞）
 *
 * 功能：
 * - 接收前端账户注册/注销请求
 * - 推送账户状态更新
 * - 独立线程运行，不阻塞主程序
 */

#include <string>
#include <thread>
#include <atomic>
#include <functional>
#include <nlohmann/json.hpp>

namespace trading {
namespace server {

/**
 * @brief 前端 WebSocket 服务器
 */
class FrontendWSServer {
public:
    using MessageCallback = std::function<void(const nlohmann::json&)>;

    FrontendWSServer(int port = 8765) : port_(port), running_(false) {}
    ~FrontendWSServer() { stop(); }

    /**
     * @brief 启动服务器（独立线程）
     */
    bool start(MessageCallback callback) {
        if (running_) return false;

        callback_ = callback;
        running_ = true;

        thread_ = std::thread([this]() {
            run_server();
        });

        return true;
    }

    /**
     * @brief 停止服务器
     */
    void stop() {
        if (!running_) return;
        running_ = false;
        if (thread_.joinable()) {
            thread_.join();
        }
    }

    /**
     * @brief 广播消息给所有前端客户端
     */
    void broadcast(const nlohmann::json& msg) {
        // TODO: 实现广播逻辑
        // 这里需要使用 WebSocket 库（如 websocketpp 或 uWebSockets）
    }

private:
    void run_server() {
        // TODO: 实现 WebSocket 服务器循环
        // 使用 websocketpp 或 uWebSockets
        while (running_) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    int port_;
    std::atomic<bool> running_;
    std::thread thread_;
    MessageCallback callback_;
};

} // namespace server
} // namespace trading
