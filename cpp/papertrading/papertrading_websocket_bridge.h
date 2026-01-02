/**
 * @file papertrading_websocket_bridge.h
 * @brief PaperTrading WebSocket桥接层
 * 
 * 功能：将前端的WebSocket请求转换为PaperTrading服务器的操作
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include "papertrading_server.h"
#include <string>
#include <functional>
#include <nlohmann/json.hpp>

namespace trading {
namespace papertrading {

/**
 * @brief WebSocket桥接层
 * 
 * 处理前端WebSocket消息，转换为PaperTrading服务器操作
 */
class PaperTradingWebSocketBridge {
public:
    using MessageHandler = std::function<void(int client_id, const nlohmann::json& message)>;
    using SnapshotGenerator = std::function<nlohmann::json()>;
    
    /**
     * @brief 构造函数
     * @param server PaperTrading服务器指针
     */
    explicit PaperTradingWebSocketBridge(PaperTradingServer* server);
    
    /**
     * @brief 处理前端消息
     */
    void handle_message(int client_id, const nlohmann::json& message);
    
    /**
     * @brief 生成快照数据
     */
    nlohmann::json generate_snapshot();
    
    /**
     * @brief 设置消息发送回调
     */
    void set_send_callback(std::function<void(int, const nlohmann::json&)> callback) {
        send_callback_ = callback;
    }
    
private:
    PaperTradingServer* server_;
    std::function<void(int, const nlohmann::json&)> send_callback_;
    
    // 命令处理函数
    void handle_reset_account(int client_id, const nlohmann::json& data);
    void handle_update_config(int client_id, const nlohmann::json& data);
    void handle_query_account(int client_id, const nlohmann::json& data);
    void handle_close_position(int client_id, const nlohmann::json& data);
    void handle_cancel_order(int client_id, const nlohmann::json& data);
    
    // 发送响应
    void send_response(int client_id, bool success, const std::string& message, const nlohmann::json& data = {});
};

} // namespace papertrading
} // namespace trading

