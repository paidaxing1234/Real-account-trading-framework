/**
 * @file websocket_server.h
 * @brief WebSocket服务器 - 用于前端连接（独立线程运行）
 * 
 * 功能：
 * - 启动WebSocket服务器（端口8001）
 * - 定时推送快照数据（100ms）
 * - 处理前端命令
 * - 推送实时事件
 * 
 * 特性：
 * - 在独立线程中运行，不阻塞主线程
 * - 线程安全的消息发送和接收
 * - 自动管理客户端连接
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <functional>
#include <string>
#include <map>
#include <mutex>
#include <thread>
#include <atomic>
#include <memory>
#include <queue>
#include <condition_variable>
#include <nlohmann/json.hpp>

namespace trading {
namespace core {

/**
 * @brief WebSocket服务器（独立线程运行）
 * 
 * 所有操作都在独立线程中执行，不会阻塞主线程
 */
class WebSocketServer {
public:
    using MessageCallback = std::function<void(int client_id, const nlohmann::json& message)>;
    using SnapshotGenerator = std::function<nlohmann::json()>;
    
    WebSocketServer();
    ~WebSocketServer();
    
    // 禁止拷贝和移动
    WebSocketServer(const WebSocketServer&) = delete;
    WebSocketServer& operator=(const WebSocketServer&) = delete;
    WebSocketServer(WebSocketServer&&) = delete;
    WebSocketServer& operator=(WebSocketServer&&) = delete;
    
    /**
     * @brief 启动服务器（在独立线程中运行）
     * @param host 监听地址
     * @param port 监听端口
     * @return true 成功，false 失败
     */
    bool start(const std::string& host, uint16_t port);
    
    /**
     * @brief 停止服务器（线程安全）
     */
    void stop();
    
    /**
     * @brief 检查是否运行中
     */
    bool is_running() const { return running_.load(); }
    
    /**
     * @brief 设置消息回调（线程安全）
     */
    void set_message_callback(MessageCallback callback);
    
    /**
     * @brief 设置快照生成器（线程安全）
     */
    void set_snapshot_generator(SnapshotGenerator generator);
    
    /**
     * @brief 设置快照推送频率（毫秒）
     */
    void set_snapshot_interval(int interval_ms);
    
    /**
     * @brief 发送响应给客户端（线程安全，异步）
     */
    void send_response(int client_id, bool success, const std::string& message, const nlohmann::json& data = {});
    
    /**
     * @brief 发送事件给所有客户端（线程安全，异步）
     */
    void send_event(const std::string& event_type, const nlohmann::json& data);
    
    /**
     * @brief 发送日志消息（线程安全，异步）
     */
    void send_log(const std::string& level, const std::string& message);

private:
    // 内部消息队列结构
    struct PendingMessage {
        int client_id;
        nlohmann::json message;
    };
    
    // 服务器主循环（在独立线程中运行）
    void server_thread_func();
    
    // 快照推送线程
    void snapshot_thread_func();
    
    // 处理客户端消息
    void handle_client_message(int client_id, const std::string& message);
    
    // 广播消息给所有客户端（内部使用）
    void broadcast_internal(const nlohmann::json& message);
    
    // 发送消息给指定客户端（内部使用）
    void send_to_client_internal(int client_id, const nlohmann::json& message);
    
    // 处理待发送消息队列
    void process_message_queue();
    
    // 运行状态
    std::atomic<bool> running_{false};
    std::atomic<bool> stopped_{true};
    
    // 线程
    std::unique_ptr<std::thread> server_thread_;
    std::unique_ptr<std::thread> snapshot_thread_;
    
    // 回调函数（线程安全访问）
    std::mutex callback_mutex_;
    MessageCallback message_callback_;
    SnapshotGenerator snapshot_generator_;
    int snapshot_interval_ms_{100};
    
    // 客户端管理（线程安全）
    std::mutex clients_mutex_;
    std::map<int, void*> clients_;  // client_id -> connection handle
    int next_client_id_{1};
    
    // 消息队列（线程安全）
    std::mutex message_queue_mutex_;
    std::condition_variable message_queue_cv_;
    std::queue<PendingMessage> message_queue_;
    
    // 服务器配置
    std::string host_;
    uint16_t port_;
    
    // WebSocket服务器实现（使用websocketpp或简单实现）
    void* server_impl_;
};

} // namespace core
} // namespace trading

