/**
 * @file test_auth_server.cpp
 * @brief 认证服务器集成测试
 *
 * 启动一个带认证的ZMQ服务器，然后用客户端测试各种请求
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#include <zmq.hpp>
#include <nlohmann/json.hpp>
#include "../network/auth_manager.h"

using json = nlohmann::json;

// 简单的ZMQ客户端测试
class AuthTestClient {
public:
    AuthTestClient(const std::string& endpoint)
        : context_(1), socket_(context_, zmq::socket_type::req) {
        socket_.connect(endpoint);
    }

    json send_request(const json& request) {
        std::string req_str = request.dump();
        socket_.send(zmq::buffer(req_str), zmq::send_flags::none);

        zmq::message_t reply;
        auto result = socket_.recv(reply, zmq::recv_flags::none);

        std::string reply_str(static_cast<char*>(reply.data()), reply.size());
        return json::parse(reply_str);
    }

private:
    zmq::context_t context_;
    zmq::socket_t socket_;
};

// 简单的认证服务器（不依赖AccountRegistry）
class SimpleAuthServer {
public:
    SimpleAuthServer() : running_(false) {}
    ~SimpleAuthServer() { stop(); }

    bool start(const std::string& endpoint = "tcp://*:5557") {
        if (running_) return false;
        endpoint_ = endpoint;
        running_ = true;
        thread_ = std::thread([this]() { run(); });
        return true;
    }

    void stop() {
        if (!running_) return;
        running_ = false;
        if (thread_.joinable()) thread_.join();
    }

private:
    void run() {
        zmq::context_t context(1);
        zmq::socket_t socket(context, zmq::socket_type::rep);
        socket.bind(endpoint_);

        std::cout << "[服务器] 启动在 " << endpoint_ << "\n";

        while (running_) {
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
                response = handle_request(msg);
            } catch (const std::exception& e) {
                response = {{"status", "error"}, {"code", 500}, {"message", e.what()}};
            }

            std::string response_str = response.dump();
            socket.send(zmq::buffer(response_str), zmq::send_flags::none);
        }
    }

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
            if (token_info.role != trading::auth::UserRole::SUPER_ADMIN) {
                return {{"status", "error"}, {"code", 403}, {"message", "Permission denied"}};
            }
            return {{"status", "success"}, {"code", 200}, {"users", auth_.get_users()}};
        }

        return {{"status", "error"}, {"code", 400}, {"message", "Unknown request type"}};
    }

    trading::auth::AuthManager auth_;
    std::atomic<bool> running_;
    std::thread thread_;
    std::string endpoint_;
};

void print_result(const std::string& test_name, const json& response, bool expect_success = true) {
    int code = response.value("code", 0);
    bool success = (code == 200);

    if (success == expect_success) {
        std::cout << "✅ " << test_name << " - ";
    } else {
        std::cout << "❌ " << test_name << " - ";
    }

    std::cout << response.dump() << "\n";
}

int main() {
    std::cout << "========================================\n";
    std::cout << "    认证系统集成测试\n";
    std::cout << "========================================\n\n";

    // 启动服务器
    SimpleAuthServer server;
    server.start("tcp://*:5557");
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // 创建客户端
    AuthTestClient client("tcp://localhost:5557");

    std::string admin_token;
    std::string viewer_token;

    // 测试1: 正确登录 (admin)
    {
        auto resp = client.send_request({
            {"type", "login"},
            {"username", "admin"},
            {"password", "admin123"}
        });
        print_result("Admin登录", resp);
        admin_token = resp.value("token", "");
    }

    // 测试2: 正确登录 (viewer)
    {
        auto resp = client.send_request({
            {"type", "login"},
            {"username", "viewer"},
            {"password", "viewer123"}
        });
        print_result("Viewer登录", resp);
        viewer_token = resp.value("token", "");
    }

    // 测试3: 错误密码
    {
        auto resp = client.send_request({
            {"type", "login"},
            {"username", "admin"},
            {"password", "wrongpassword"}
        });
        print_result("错误密码被拒绝", resp, false);
    }

    // 测试4: 获取用户信息
    {
        auto resp = client.send_request({
            {"type", "get_user_info"},
            {"token", admin_token}
        });
        print_result("获取用户信息", resp);
    }

    // 测试5: 无效Token
    {
        auto resp = client.send_request({
            {"type", "get_user_info"},
            {"token", "invalid_token"}
        });
        print_result("无效Token被拒绝", resp, false);
    }

    // 测试6: Admin获取用户列表
    {
        auto resp = client.send_request({
            {"type", "list_users"},
            {"token", admin_token}
        });
        print_result("Admin获取用户列表", resp);
    }

    // 测试7: Viewer获取用户列表（应该被拒绝）
    {
        auto resp = client.send_request({
            {"type", "list_users"},
            {"token", viewer_token}
        });
        print_result("Viewer无权获取用户列表", resp, false);
    }

    // 测试8: 登出
    {
        auto resp = client.send_request({
            {"type", "logout"},
            {"token", viewer_token}
        });
        print_result("Viewer登出", resp);
    }

    // 测试9: 登出后Token失效
    {
        auto resp = client.send_request({
            {"type", "get_user_info"},
            {"token", viewer_token}
        });
        print_result("登出后Token失效", resp, false);
    }

    std::cout << "\n========================================\n";
    std::cout << "    测试完成\n";
    std::cout << "========================================\n";

    server.stop();
    return 0;
}
