/**
 * @file test_auth_ws_server.cpp
 * @brief 带认证的WebSocket服务器测试
 *
 * 前端可以直接通过WebSocket连接进行认证测试
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <atomic>
#include "../network/websocket_server.h"
#include "../network/auth_manager.h"

using namespace trading::core;
using namespace trading::auth;
using json = nlohmann::json;

std::atomic<bool> running(true);
AuthManager auth_manager;

// 存储已认证的客户端
std::map<int, TokenInfo> authenticated_clients;
std::mutex auth_mutex;

void signal_handler(int) {
    std::cout << "\n[服务器] 收到停止信号...\n";
    running = false;
}

// 处理客户端消息
void handle_message(WebSocketServer& server, int client_id, const json& msg) {
    std::string type = msg.value("type", "");
    json response;

    std::cout << "[请求] client=" << client_id << " type=" << type << "\n";

    // 登录接口（无需认证）
    if (type == "login") {
        std::string username = msg.value("username", "");
        std::string password = msg.value("password", "");
        std::string token = auth_manager.login(username, password);

        if (token.empty()) {
            response = {
                {"type", "login_response"},
                {"success", false},
                {"message", "用户名或密码错误"}
            };
        } else {
            TokenInfo info;
            auth_manager.verify_token(token, info);

            // 记录已认证客户端
            {
                std::lock_guard<std::mutex> lock(auth_mutex);
                authenticated_clients[client_id] = info;
            }

            response = {
                {"type", "login_response"},
                {"success", true},
                {"token", token},
                {"user", {
                    {"username", username},
                    {"role", AuthManager::role_to_string(info.role)}
                }}
            };
        }
        server.send_response(client_id, response["success"], response.value("message", ""), response);
        return;
    }

    // 其他接口需要认证
    std::string token = msg.value("token", "");
    TokenInfo token_info;

    // 先检查客户端是否已认证
    {
        std::lock_guard<std::mutex> lock(auth_mutex);
        auto it = authenticated_clients.find(client_id);
        if (it != authenticated_clients.end()) {
            token_info = it->second;
        } else if (!token.empty() && auth_manager.verify_token(token, token_info)) {
            authenticated_clients[client_id] = token_info;
        } else {
            response = {
                {"type", type + "_response"},
                {"success", false},
                {"message", "未认证，请先登录"}
            };
            server.send_response(client_id, false, "未认证", response);
            return;
        }
    }

    // 处理各种请求
    if (type == "logout") {
        auth_manager.logout(token);
        {
            std::lock_guard<std::mutex> lock(auth_mutex);
            authenticated_clients.erase(client_id);
        }
        response = {
            {"type", "logout_response"},
            {"success", true},
            {"message", "已登出"}
        };
    }
    else if (type == "get_user_info") {
        response = {
            {"type", "user_info"},
            {"success", true},
            {"user", {
                {"username", token_info.username},
                {"role", AuthManager::role_to_string(token_info.role)}
            }}
        };
    }
    else if (type == "list_users") {
        if (token_info.role != UserRole::SUPER_ADMIN && token_info.role != UserRole::ADMIN) {
            response = {
                {"type", "users_list"},
                {"success", false},
                {"message", "权限不足"}
            };
        } else {
            response = {
                {"type", "users_list"},
                {"success", true},
                {"users", auth_manager.get_users()}
            };
        }
    }
    else if (type == "change_password") {
        std::string old_pass = msg.value("old_password", "");
        std::string new_pass = msg.value("new_password", "");
        bool success = auth_manager.change_password(token_info.username, old_pass, new_pass);
        response = {
            {"type", "change_password_response"},
            {"success", success},
            {"message", success ? "密码修改成功" : "旧密码错误"}
        };
    }
    else if (type == "add_user") {
        if (token_info.role != UserRole::SUPER_ADMIN && token_info.role != UserRole::ADMIN) {
            response = {
                {"type", "add_user_response"},
                {"success", false},
                {"message", "权限不足"}
            };
        } else {
            std::string username = msg.value("username", "");
            std::string password = msg.value("password", "");
            std::string role_str = msg.value("role", "VIEWER");
            bool success = auth_manager.add_user(username, password, AuthManager::string_to_role(role_str));
            response = {
                {"type", "add_user_response"},
                {"success", success},
                {"message", success ? "用户创建成功" : "用户已存在"}
            };
        }
    }
    else {
        response = {
            {"type", "error"},
            {"success", false},
            {"message", "未知请求类型: " + type}
        };
    }

    server.send_response(client_id, response["success"], response.value("message", ""), response);
}

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "========================================\n";
    std::cout << "    带认证的WebSocket服务器\n";
    std::cout << "========================================\n";
    std::cout << "  监听地址: ws://localhost:8765\n";
    std::cout << "  默认账户:\n";
    std::cout << "    admin / admin123 (SUPER_ADMIN)\n";
    std::cout << "    viewer / viewer123 (VIEWER)\n";
    std::cout << "========================================\n\n";

    WebSocketServer server;

    // 设置消息回调
    server.set_message_callback([&server](int client_id, const json& msg) {
        handle_message(server, client_id, msg);
    });

    // 启动服务器
    if (!server.start("0.0.0.0", 8765)) {
        std::cerr << "[错误] 服务器启动失败\n";
        return 1;
    }

    std::cout << "[服务器] 按 Ctrl+C 停止\n\n";

    // 主循环
    while (running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    server.stop();
    std::cout << "[服务器] 已停止\n";

    return 0;
}
