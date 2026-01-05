/**
 * @file frontend_command_handler.cpp
 * @brief 前端 WebSocket 命令处理模块实现（含认证）
 */

#include "frontend_command_handler.h"
#include "../config/server_config.h"
#include "../managers/paper_trading_manager.h"
#include "../../network/websocket_server.h"
#include "../../network/auth_manager.h"
#include "../../core/logger.h"
#include <iostream>

using namespace trading::core;

namespace trading {
namespace server {

void handle_frontend_command(int client_id, const nlohmann::json& message) {
    try {
        std::string msg_type = message.value("type", "");
        std::string action = message.value("action", "");
        nlohmann::json data = message.value("data", nlohmann::json::object());
        std::string request_id = data.value("requestId", "");

        // ==================== 认证相关（无需登录） ====================
        if (msg_type == "login") {
            std::string username = message.value("username", "");
            std::string password = message.value("password", "");
            std::string token = g_auth_manager.login(username, password);

            if (token.empty()) {
                nlohmann::json response = {
                    {"type", "login_response"},
                    {"success", false},
                    {"message", "用户名或密码错误"}
                };
                g_frontend_server->send_response(client_id, false, "用户名或密码错误", response);
                LOG_INFO("登录失败: " + username);
            } else {
                auth::TokenInfo info;
                g_auth_manager.verify_token(token, info);

                {
                    std::lock_guard<std::mutex> lock(g_auth_mutex);
                    g_authenticated_clients[client_id] = info;
                }

                nlohmann::json response = {
                    {"type", "login_response"},
                    {"success", true},
                    {"token", token},
                    {"user", {
                        {"username", username},
                        {"role", auth::AuthManager::role_to_string(info.role)}
                    }}
                };
                g_frontend_server->send_response(client_id, true, "登录成功", response);
                LOG_INFO("登录成功: " + username + " (角色: " + auth::AuthManager::role_to_string(info.role) + ")");
            }
            return;
        }

        if (msg_type == "logout" || action == "logout") {
            std::string token = message.value("token", "");
            g_auth_manager.logout(token);
            {
                std::lock_guard<std::mutex> lock(g_auth_mutex);
                g_authenticated_clients.erase(client_id);
            }
            nlohmann::json response = {
                {"type", "logout_response"},
                {"success", true},
                {"message", "已登出"}
            };
            g_frontend_server->send_response(client_id, true, "已登出", response);
            LOG_INFO("客户端 " + std::to_string(client_id) + " 已登出");
            return;
        }

        if (msg_type == "get_user_info") {
            std::lock_guard<std::mutex> lock(g_auth_mutex);
            auto it = g_authenticated_clients.find(client_id);
            if (it != g_authenticated_clients.end()) {
                nlohmann::json response = {
                    {"type", "user_info"},
                    {"success", true},
                    {"user", {
                        {"username", it->second.username},
                        {"role", auth::AuthManager::role_to_string(it->second.role)}
                    }}
                };
                g_frontend_server->send_response(client_id, true, "", response);
            } else {
                g_frontend_server->send_response(client_id, false, "未登录", {{"type", "user_info"}});
            }
            return;
        }

        // ==================== 以下命令需要认证 ====================
        std::cout << "[前端] 收到命令: " << action << " (客户端: " << client_id << ")\n";

        nlohmann::json response;

        if (action == "start_paper_strategy") {
            response = process_start_paper_strategy(data);
        }
        else if (action == "stop_paper_strategy") {
            response = process_stop_paper_strategy(data);
        }
        else if (action == "get_paper_strategy_status") {
            response = process_get_paper_strategy_status(data);
        }
        else {
            response = {{"success", false}, {"message", "未知命令: " + action}};
        }

        if (!request_id.empty()) {
            response["requestId"] = request_id;
        }

        g_frontend_server->send_response(client_id, response["success"],
                                        response.value("message", ""), response);

    } catch (const std::exception& e) {
        std::cerr << "[前端] 处理命令异常: " << e.what() << "\n";
        g_frontend_server->send_response(client_id, false,
                                        std::string("处理命令异常: ") + e.what(), {});
    }
}

} // namespace server
} // namespace trading
