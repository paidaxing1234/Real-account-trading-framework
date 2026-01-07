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
#include <fstream>
#include <sstream>
#include <regex>
#include <filesystem>
#include <dirent.h>
#include <set>
#include <algorithm>

using namespace trading::core;

namespace trading {
namespace server {

// 解析单行日志
nlohmann::json parse_log_line(const std::string& line) {
    // 格式: [2026-01-07 01:27:26.775] [INFO ] [source] message
    std::regex log_regex(R"(\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] \[(\w+)\s*\] \[(\w+)\] (.*))");
    std::smatch match;

    if (std::regex_match(line, match, log_regex)) {
        std::string timestamp_str = match[1].str();
        std::string level = match[2].str();
        std::string source = match[3].str();
        std::string message = match[4].str();

        // 转换级别为小写
        for (auto& c : level) c = std::tolower(c);
        if (level == "warn") level = "warning";

        // 解析时间戳为毫秒
        std::tm tm = {};
        int ms = 0;
        sscanf(timestamp_str.c_str(), "%d-%d-%d %d:%d:%d.%d",
               &tm.tm_year, &tm.tm_mon, &tm.tm_mday,
               &tm.tm_hour, &tm.tm_min, &tm.tm_sec, &ms);
        tm.tm_year -= 1900;
        tm.tm_mon -= 1;
        auto time_point = std::chrono::system_clock::from_time_t(std::mktime(&tm));
        auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
            time_point.time_since_epoch()).count() + ms;

        return {
            {"timestamp", timestamp},
            {"level", level},
            {"source", source},
            {"message", message}
        };
    }
    return nlohmann::json();
}

// 读取日志文件
nlohmann::json read_log_files(const std::string& date, const std::string& source_filter,
                              const std::string& level_filter, int limit, int offset) {
    nlohmann::json logs = nlohmann::json::array();
    std::string log_dir = "logs";

    // 获取日志文件列表
    std::vector<std::string> log_files;
    DIR* dir = opendir(log_dir.c_str());
    if (dir) {
        struct dirent* entry;
        while ((entry = readdir(dir)) != nullptr) {
            std::string filename = entry->d_name;
            if (filename.find(".log") != std::string::npos) {
                // 如果指定了日期，只读取该日期的文件
                if (!date.empty()) {
                    if (filename.find(date) != std::string::npos) {
                        log_files.push_back(log_dir + "/" + filename);
                    }
                } else {
                    log_files.push_back(log_dir + "/" + filename);
                }
            }
        }
        closedir(dir);
    }

    // 按文件名排序（日期排序）
    std::sort(log_files.begin(), log_files.end());

    int total_count = 0;
    int skipped = 0;

    for (const auto& filepath : log_files) {
        std::ifstream file(filepath);
        if (!file.is_open()) continue;

        std::string line;
        while (std::getline(file, line)) {
            if (line.empty()) continue;

            auto log_entry = parse_log_line(line);
            if (log_entry.empty()) continue;

            // 来源过滤
            if (!source_filter.empty() && log_entry["source"] != source_filter) continue;

            // 级别过滤
            if (!level_filter.empty() && log_entry["level"] != level_filter) continue;

            total_count++;

            // 分页
            if (skipped < offset) {
                skipped++;
                continue;
            }

            if (limit > 0 && (int)logs.size() >= limit) continue;

            logs.push_back(log_entry);
        }
    }

    return {
        {"logs", logs},
        {"total", total_count},
        {"offset", offset},
        {"limit", limit}
    };
}

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
        Logger::instance().info("system", "收到命令: " + action + " (客户端: " + std::to_string(client_id) + ")");

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
        else if (action == "set_log_config") {
            // 处理日志配置命令
            std::string level = data.value("level", "info");
            LogLevel log_level = LogLevel::INFO;
            if (level == "debug") log_level = LogLevel::DEBUG;
            else if (level == "info") log_level = LogLevel::INFO;
            else if (level == "warning") log_level = LogLevel::WARN;
            else if (level == "error") log_level = LogLevel::ERROR;

            Logger::instance().set_level(log_level);
            response = {{"success", true}, {"message", "日志级别已设置为: " + level}};
        }
        else if (action == "frontend_log") {
            // 前端发送的日志，记录到后端
            std::string level = data.value("level", "info");
            std::string message = data.value("message", "");
            Logger::instance().info("frontend", message);
            response = {{"success", true}, {"message", "日志已记录"}};
        }
        else if (action == "get_logs") {
            // 读取本地日志文件
            std::string date = data.value("date", "");  // 格式: 20260107
            std::string source = data.value("source", "");
            std::string level = data.value("level", "");
            int limit = data.value("limit", 500);
            int offset = data.value("offset", 0);

            auto logs_data = read_log_files(date, source, level, limit, offset);
            response = {
                {"success", true},
                {"type", "logs_data"},
                {"data", logs_data}
            };
        }
        else if (action == "get_log_dates") {
            // 获取可用的日志日期列表
            nlohmann::json dates = nlohmann::json::array();
            std::string log_dir = "logs";

            DIR* dir = opendir(log_dir.c_str());
            if (dir) {
                struct dirent* entry;
                std::regex date_regex(R"(.*_(\d{8})\.log)");
                std::set<std::string> date_set;

                while ((entry = readdir(dir)) != nullptr) {
                    std::string filename = entry->d_name;
                    std::smatch match;
                    if (std::regex_match(filename, match, date_regex)) {
                        date_set.insert(match[1].str());
                    }
                }
                closedir(dir);

                for (const auto& d : date_set) {
                    dates.push_back(d);
                }
            }

            response = {
                {"success", true},
                {"type", "log_dates"},
                {"dates", dates}
            };
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
