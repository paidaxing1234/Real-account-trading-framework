/**
 * @file auth_server.cpp
 * @brief 认证服务器（持续运行）
 *
 * 启动一个带认证的ZMQ服务器，供前端通过HTTP桥接访问
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#include <csignal>
#include <zmq.hpp>
#include <nlohmann/json.hpp>
#include "../network/auth_manager.h"

using json = nlohmann::json;

std::atomic<bool> running(true);

void signal_handler(int) {
    std::cout << "\n[服务器] 收到停止信号...\n";
    running = false;
}

class AuthServer {
public:
    AuthServer() {}

    void run(const std::string& endpoint = "tcp://*:5557") {
        zmq::context_t context(1);
        zmq::socket_t socket(context, zmq::socket_type::rep);
        socket.bind(endpoint);

        std::cout << "[服务器] 认证服务启动在 " << endpoint << "\n";
        std::cout << "[服务器] 等待请求...\n\n";

        while (running) {
            zmq::message_t request;
            auto result = socket.recv(request, zmq::recv_flags::dontwait);
            if (!result) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            std::string msg_str(static_cast<char*>(request.data()), request.size());
            json response;

            try {
                auto msg = json::parse(msg_str);
                std::cout << "[请求] " << msg.value("type", "unknown") << "\n";
                response = handle_request(msg);
                std::cout << "[响应] code=" << response.value("code", 0) << "\n\n";
            } catch (const std::exception& e) {
                response = {{"status", "error"}, {"code", 500}, {"message", e.what()}};
                std::cout << "[错误] " << e.what() << "\n\n";
            }

            std::string response_str = response.dump();
            socket.send(zmq::buffer(response_str), zmq::send_flags::none);
        }

        std::cout << "[服务器] 已停止\n";
    }

private:
    json handle_request(const json& msg) {
        std::string type = msg.value("type", "");

        if (type == "login") {
            std::string username = msg.value("username", "");
            std::string password = msg.value("password", "");
            std::string token = auth_.login(username, password);

            if (token.empty()) {
                return {{"status", "error"}, {"code", 401}, {"message", "Invalid credentials"}};
            }

            trading::auth::TokenInfo info;
            auth_.verify_token(token, info);

            return {
                {"status", "success"},
                {"code", 200},
                {"token", token},
                {"user", {
                    {"username", username},
                    {"role", trading::auth::AuthManager::role_to_string(info.role)}
                }}
            };
        }

        // 需要认证的接口
        std::string token = msg.value("token", "");
        trading::auth::TokenInfo token_info;

        if (!auth_.verify_token(token, token_info)) {
            return {{"status", "error"}, {"code", 401}, {"message", "Unauthorized"}};
        }

        if (type == "logout") {
            auth_.logout(token);
            return {{"status", "success"}, {"code", 200}, {"message", "Logged out"}};
        } else if (type == "get_user_info") {
            return {
                {"status", "success"},
                {"code", 200},
                {"user", {
                    {"username", token_info.username},
                    {"role", trading::auth::AuthManager::role_to_string(token_info.role)}
                }}
            };
        } else if (type == "list_users") {
            if (token_info.role != trading::auth::UserRole::SUPER_ADMIN &&
                token_info.role != trading::auth::UserRole::ADMIN) {
                return {{"status", "error"}, {"code", 403}, {"message", "Permission denied"}};
            }
            return {{"status", "success"}, {"code", 200}, {"users", auth_.get_users()}};
        } else if (type == "change_password") {
            std::string old_pass = msg.value("old_password", "");
            std::string new_pass = msg.value("new_password", "");
            if (auth_.change_password(token_info.username, old_pass, new_pass)) {
                return {{"status", "success"}, {"code", 200}, {"message", "Password changed"}};
            }
            return {{"status", "error"}, {"code", 400}, {"message", "Invalid old password"}};
        } else if (type == "add_user") {
            if (token_info.role != trading::auth::UserRole::SUPER_ADMIN &&
                token_info.role != trading::auth::UserRole::ADMIN) {
                return {{"status", "error"}, {"code", 403}, {"message", "Permission denied"}};
            }
            std::string username = msg.value("username", "");
            std::string password = msg.value("password", "");
            std::string role_str = msg.value("role", "VIEWER");
            auto role = trading::auth::AuthManager::string_to_role(role_str);

            if (auth_.add_user(username, password, role)) {
                return {{"status", "success"}, {"code", 200}, {"message", "User created"}};
            }
            return {{"status", "error"}, {"code", 409}, {"message", "User already exists"}};
        }

        return {{"status", "error"}, {"code", 400}, {"message", "Unknown request type"}};
    }

    trading::auth::AuthManager auth_;
};

int main() {
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    std::cout << "========================================\n";
    std::cout << "    认证服务器\n";
    std::cout << "========================================\n";
    std::cout << "  默认账户:\n";
    std::cout << "    admin / admin123 (SUPER_ADMIN)\n";
    std::cout << "    viewer / viewer123 (VIEWER)\n";
    std::cout << "========================================\n\n";

    AuthServer server;
    server.run("tcp://*:5557");

    return 0;
}
