/**
 * @file websocket_server.cpp
 * @brief WebSocket服务器实现（独立线程运行）
 * 
 * 所有操作都在独立线程中执行，确保不阻塞主线程
 */

#include "websocket_server.h"
#include <iostream>
#include <chrono>
#include <sstream>

namespace trading {
namespace core {

WebSocketServer::WebSocketServer()
    : server_impl_(nullptr)
{
}

WebSocketServer::~WebSocketServer() {
    stop();
}

bool WebSocketServer::start(const std::string& host, uint16_t port) {
    if (running_.load()) {
        std::cerr << "[WebSocketServer] 服务器已在运行中" << std::endl;
        return false;
    }
    
    host_ = host;
    port_ = port;
    
    std::cout << "[WebSocketServer] 正在启动WebSocket服务器..." << std::endl;
    std::cout << "[WebSocketServer] 监听地址: ws://" << host << ":" << port << std::endl;
    
    running_.store(true);
    stopped_.store(false);
    
    // 启动服务器线程（独立线程，不阻塞主线程）
    server_thread_ = std::make_unique<std::thread>(&WebSocketServer::server_thread_func, this);
    
    // 启动快照推送线程（独立线程）
    snapshot_thread_ = std::make_unique<std::thread>(&WebSocketServer::snapshot_thread_func, this);
    
    // 等待服务器线程初始化完成
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    std::cout << "[WebSocketServer] WebSocket服务器已启动（独立线程运行）" << std::endl;
    
    return true;
}

void WebSocketServer::stop() {
    if (!running_.load() || stopped_.load()) {
        return;
    }
    
    std::cout << "[WebSocketServer] 正在停止WebSocket服务器..." << std::endl;
    
    stopped_.store(true);
    running_.store(false);
    
    // 通知消息队列线程退出
    message_queue_cv_.notify_all();
    
    // 等待线程退出
    if (server_thread_ && server_thread_->joinable()) {
        server_thread_->join();
        server_thread_.reset();
    }
    
    if (snapshot_thread_ && snapshot_thread_->joinable()) {
        snapshot_thread_->join();
        snapshot_thread_.reset();
    }
    
    // 清理客户端连接
    {
        std::lock_guard<std::mutex> lock(clients_mutex_);
        clients_.clear();
    }
    
    std::cout << "[WebSocketServer] WebSocket服务器已停止" << std::endl;
}

void WebSocketServer::set_message_callback(MessageCallback callback) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    message_callback_ = std::move(callback);
}

void WebSocketServer::set_snapshot_generator(SnapshotGenerator generator) {
    std::lock_guard<std::mutex> lock(callback_mutex_);
    snapshot_generator_ = std::move(generator);
}

void WebSocketServer::set_snapshot_interval(int interval_ms) {
    snapshot_interval_ms_ = interval_ms;
}

void WebSocketServer::send_response(int client_id, bool success, const std::string& message, const nlohmann::json& data) {
    nlohmann::json response = {
        {"type", "response"},
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count()},
        {"data", {
            {"success", success},
            {"message", message}
        }}
    };
    
    // 合并data
    if (!data.empty()) {
        for (auto& [key, value] : data.items()) {
            response["data"][key] = value;
        }
    }
    
    // 异步发送（添加到消息队列）
    {
        std::lock_guard<std::mutex> lock(message_queue_mutex_);
        message_queue_.push({client_id, response});
    }
    message_queue_cv_.notify_one();
}

void WebSocketServer::send_event(const std::string& event_type, const nlohmann::json& data) {
    nlohmann::json event = {
        {"type", "event"},
        {"event_type", event_type},
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count()},
        {"data", data}
    };
    
    // 异步广播（添加到消息队列，client_id=-1表示广播）
    {
        std::lock_guard<std::mutex> lock(message_queue_mutex_);
        message_queue_.push({-1, event});
    }
    message_queue_cv_.notify_one();
}

void WebSocketServer::send_log(const std::string& level, const std::string& message) {
    nlohmann::json log_msg = {
        {"type", "log"},
        {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count()},
        {"data", {
            {"level", level},
            {"source", "backend"},
            {"message", message}
        }}
    };
    
    // 异步广播（添加到消息队列）
    {
        std::lock_guard<std::mutex> lock(message_queue_mutex_);
        message_queue_.push({-1, log_msg});
    }
    message_queue_cv_.notify_one();
}

void WebSocketServer::server_thread_func() {
    std::cout << "[WebSocketServer] 服务器线程启动（独立线程）" << std::endl;
    
    // TODO: 实现WebSocket服务器逻辑
    // 1. 创建WebSocket服务器（使用websocketpp、uWebSockets等）
    // 2. 监听连接
    // 3. 处理消息接收和发送
    
    // 当前占位实现：处理消息队列
    while (running_.load()) {
        // 处理消息队列
        process_message_queue();
        
        // 处理WebSocket连接和消息
        // TODO: 实现实际的WebSocket服务器逻辑
        
        // 短暂休眠，避免CPU占用过高
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    
    std::cout << "[WebSocketServer] 服务器线程退出" << std::endl;
}

void WebSocketServer::snapshot_thread_func() {
    std::cout << "[WebSocketServer] 快照线程启动（独立线程）" << std::endl;
    
    while (running_.load()) {
        SnapshotGenerator generator;
        
        // 获取快照生成器（线程安全）
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            generator = snapshot_generator_;
        }
        
        if (generator) {
            try {
                nlohmann::json snapshot = generator();
                
                nlohmann::json message = {
                    {"type", "snapshot"},
                    {"timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::system_clock::now().time_since_epoch()
                    ).count()},
                    {"data", snapshot}
                };
                
                // 异步广播快照
                {
                    std::lock_guard<std::mutex> lock(message_queue_mutex_);
                    message_queue_.push({-1, message});
                }
                message_queue_cv_.notify_one();
                
            } catch (const std::exception& e) {
                std::cerr << "[WebSocketServer] 生成快照失败: " << e.what() << std::endl;
            }
        }
        
        // 按配置的频率休眠
        std::this_thread::sleep_for(std::chrono::milliseconds(snapshot_interval_ms_));
    }
    
    std::cout << "[WebSocketServer] 快照线程退出" << std::endl;
}

void WebSocketServer::process_message_queue() {
    std::unique_lock<std::mutex> lock(message_queue_mutex_);
    
    // 等待消息或超时
    message_queue_cv_.wait_for(lock, std::chrono::milliseconds(100), [this]() {
        return !message_queue_.empty() || !running_.load();
    });
    
    // 处理所有待发送的消息
    while (!message_queue_.empty()) {
        PendingMessage msg = message_queue_.front();
        message_queue_.pop();
        
        lock.unlock();
        
        // 发送消息
        if (msg.client_id == -1) {
            // 广播
            broadcast_internal(msg.message);
        } else {
            // 发送给指定客户端
            send_to_client_internal(msg.client_id, msg.message);
        }
        
        lock.lock();
    }
}

void WebSocketServer::handle_client_message(int client_id, const std::string& message) {
    try {
        nlohmann::json json_msg = nlohmann::json::parse(message);
        
        MessageCallback callback;
        {
            std::lock_guard<std::mutex> lock(callback_mutex_);
            callback = message_callback_;
        }
        
        if (callback) {
            callback(client_id, json_msg);
        }
    } catch (const std::exception& e) {
        std::cerr << "[WebSocketServer] 解析消息失败: " << e.what() << std::endl;
    }
}

void WebSocketServer::broadcast_internal(const nlohmann::json& message) {
    std::lock_guard<std::mutex> lock(clients_mutex_);
    
    // TODO: 广播给所有连接的客户端
    // 实际实现中，这里应该遍历所有客户端连接并发送消息
    
    std::string msg_str = message.dump();
    if (msg_str.length() > 100) {
        std::cout << "[WebSocketServer] 广播消息: " << msg_str.substr(0, 100) << "..." << std::endl;
    } else {
        std::cout << "[WebSocketServer] 广播消息: " << msg_str << std::endl;
    }
}

void WebSocketServer::send_to_client_internal(int client_id, const nlohmann::json& message) {
    std::lock_guard<std::mutex> lock(clients_mutex_);
    
    // TODO: 发送给指定客户端
    // 实际实现中，这里应该查找客户端连接并发送消息
    
    auto it = clients_.find(client_id);
    if (it != clients_.end()) {
        std::string msg_str = message.dump();
        if (msg_str.length() > 100) {
            std::cout << "[WebSocketServer] 发送消息给客户端 " << client_id 
                      << ": " << msg_str.substr(0, 100) << "..." << std::endl;
        } else {
            std::cout << "[WebSocketServer] 发送消息给客户端 " << client_id 
                      << ": " << msg_str << std::endl;
        }
    } else {
        std::cerr << "[WebSocketServer] 客户端 " << client_id << " 不存在" << std::endl;
    }
}

} // namespace core
} // namespace trading

