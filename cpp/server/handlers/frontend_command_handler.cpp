/**
 * @file frontend_command_handler.cpp
 * @brief 前端 WebSocket 命令处理模块实现（含认证）
 */

#include "frontend_command_handler.h"
#include "../config/server_config.h"

#include "order_processor.h"  // 包含 g_risk_manager, g_account_monitor 声明
#include "../managers/account_monitor.h"  // AccountCredentials
#include "../../network/websocket_server.h"
#include "../../network/auth_manager.h"
#include "../../core/logger.h"
#include "../../trading/account_registry.h"
#include "../../trading/strategy_config_loader.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <regex>
#include <filesystem>
#include <dirent.h>
#include <set>
#include <deque>
#include <algorithm>
#include <iomanip>
#include <sys/stat.h>

using namespace trading::core;

namespace trading {
namespace server {

// Debug 日志：写入 frontend.txt
static void frontend_debug(const std::string& msg) {
    static std::mutex dbg_mtx;
    std::lock_guard<std::mutex> lock(dbg_mtx);
    std::ofstream f("/home/xyc/Real-account-trading-framework-main/Real-account-trading-framework-main/cpp/logs/frontend.txt", std::ios::app);
    if (f.is_open()) {
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
        char buf[32];
        std::strftime(buf, sizeof(buf), "%H:%M:%S", std::localtime(&t));
        f << "[" << buf << "." << std::setfill('0') << std::setw(3) << ms.count() << "] " << msg << "\n";
        f.flush();
    }
}

// 获取可执行文件所在目录（cpp/build/），配置默认路径相对于此目录
static std::string get_exe_dir() {
    std::filesystem::path exe_path = std::filesystem::canonical("/proc/self/exe");
    return exe_path.parent_path().string();  // cpp/build/
}

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

        frontend_debug(">>> 收到消息 client=" + std::to_string(client_id) + " type=" + msg_type + " action=" + action + " requestId=" + request_id);

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

        if (action == "set_log_config") {
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
        else if (action == "get_strategy_log_files") {
            // 获取策略日志文件列表
            std::string strategy_id = data.value("strategyId", "");
            std::string strategy_log_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_log_dir;
            nlohmann::json files = nlohmann::json::array();

            DIR* dir = opendir(strategy_log_dir.c_str());
            if (dir) {
                struct dirent* entry;
                while ((entry = readdir(dir)) != nullptr) {
                    std::string filename = entry->d_name;
                    if (filename.size() < 4 || filename.substr(filename.size() - 4) != ".log") continue;
                    if (!strategy_id.empty() && filename.find(strategy_id) == std::string::npos) continue;

                    // 获取文件大小
                    std::string filepath = strategy_log_dir + "/" + filename;
                    struct stat st;
                    long file_size = 0;
                    if (stat(filepath.c_str(), &st) == 0) {
                        file_size = st.st_size;
                    }
                    files.push_back({{"filename", filename}, {"size", file_size}});
                }
                closedir(dir);
            }

            response = {
                {"success", true},
                {"type", "strategy_log_files"},
                {"data", files}
            };
        }
        else if (action == "get_strategy_logs") {
            // 读取策略日志内容
            std::string filename = data.value("filename", "");
            int tail_lines = data.value("tailLines", 200);
            std::string strategy_log_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_log_dir;
            std::string filepath = strategy_log_dir + "/" + filename;

            // 安全检查：防止路径遍历
            if (filename.find("..") != std::string::npos || filename.find("/") != std::string::npos) {
                response = {{"success", false}, {"message", "非法文件名"}};
            } else {
                std::ifstream file(filepath);
                if (!file.is_open()) {
                    response = {{"success", false}, {"message", "日志文件不存在: " + filename}};
                } else {
                    // 读取最后 tail_lines 行
                    std::deque<std::string> lines;
                    std::string line;
                    while (std::getline(file, line)) {
                        lines.push_back(line);
                        if ((int)lines.size() > tail_lines) {
                            lines.pop_front();
                        }
                    }
                    file.close();

                    nlohmann::json log_lines = nlohmann::json::array();
                    for (const auto& l : lines) {
                        log_lines.push_back(l);
                    }

                    response = {
                        {"success", true},
                        {"type", "strategy_logs"},
                        {"data", {{"filename", filename}, {"lines", log_lines}, {"totalLines", (int)log_lines.size()}}}
                    };
                }
            }
        }
        else if (action == "list_strategy_files") {
            // 列出策略源代码文件
            std::string strategy_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_source_dir;
            nlohmann::json files = nlohmann::json::array();

            std::function<void(const std::string&, const std::string&)> scan_dir;
            scan_dir = [&](const std::string& dir_path, const std::string& prefix) {
                DIR* dir = opendir(dir_path.c_str());
                if (!dir) return;
                struct dirent* entry;
                while ((entry = readdir(dir)) != nullptr) {
                    std::string name = entry->d_name;
                    if (name == "." || name == ".." || name == "__pycache__" || name == "logs") continue;
                    std::string full_path = dir_path + "/" + name;
                    std::string rel_path = prefix.empty() ? name : prefix + "/" + name;
                    struct stat st;
                    if (stat(full_path.c_str(), &st) == 0) {
                        if (S_ISDIR(st.st_mode)) {
                            scan_dir(full_path, rel_path);
                        } else if (name.size() > 3 && name.substr(name.size() - 3) == ".py") {
                            files.push_back({{"filename", rel_path}, {"size", st.st_size}});
                        }
                    }
                }
                closedir(dir);
            };
            scan_dir(strategy_dir, "");

            response = {
                {"success", true},
                {"type", "strategy_files"},
                {"data", files}
            };
        }
        else if (action == "get_strategy_source") {
            // 读取策略源代码
            std::string filename = data.value("filename", "");
            std::string strategy_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_source_dir;
            std::string filepath = strategy_dir + "/" + filename;

            // 安全检查
            if (filename.find("..") != std::string::npos) {
                response = {{"success", false}, {"message", "非法文件名"}};
            } else if (filename.substr(filename.size() - 3) != ".py") {
                response = {{"success", false}, {"message", "只能查看Python策略文件"}};
            } else {
                std::ifstream file(filepath);
                if (!file.is_open()) {
                    response = {{"success", false}, {"message", "文件不存在: " + filename}};
                } else {
                    std::stringstream ss;
                    ss << file.rdbuf();
                    file.close();
                    response = {
                        {"success", true},
                        {"type", "strategy_source"},
                        {"data", {{"filename", filename}, {"content", ss.str()}}}
                    };
                }
            }
        }
        else if (action == "save_strategy_source") {
            // 保存策略源代码
            std::string filename = data.value("filename", "");
            std::string content = data.value("content", "");
            std::string strategy_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_source_dir;
            std::string filepath = strategy_dir + "/" + filename;

            // 安全检查
            if (filename.find("..") != std::string::npos) {
                response = {{"success", false}, {"message", "非法文件名"}};
            } else if (filename.substr(filename.size() - 3) != ".py") {
                response = {{"success", false}, {"message", "只能保存Python策略文件"}};
            } else {
                // 备份原文件
                std::string backup_path = filepath + ".bak";
                std::ifstream src(filepath, std::ios::binary);
                if (src.is_open()) {
                    std::ofstream dst(backup_path, std::ios::binary);
                    dst << src.rdbuf();
                    src.close();
                    dst.close();
                }

                // 保存新内容
                std::ofstream file(filepath);
                if (!file.is_open()) {
                    response = {{"success", false}, {"message", "无法写入文件: " + filename}};
                } else {
                    file << content;
                    file.close();
                    response = {
                        {"success", true},
                        {"type", "save_strategy_source"},
                        {"message", "保存成功"}
                    };
                }
            }
        }
        else if (action == "get_risk_status") {
            // 获取风控状态
            auto stats = g_risk_manager.get_risk_stats();
            response["success"] = true;
            response["type"] = "risk_status";
            response["data"] = stats;

            bool kill_switch_active = stats["kill_switch"].get<bool>();
            LOG_INFO("查询风控状态: kill_switch=" + std::to_string(kill_switch_active));
        }
        else if (action == "deactivate_kill_switch") {
            // 解除kill switch
            if (g_risk_manager.is_kill_switch_active()) {
                g_risk_manager.deactivate_kill_switch();
                response["success"] = true;
                response["message"] = "Kill switch已解除，交易已恢复";
                LOG_INFO("Kill switch已通过前端命令解除");
            } else {
                response["success"] = true;
                response["message"] = "Kill switch当前未激活";
            }
        }
        else if (action == "register_account") {
            // 注册账户（添加交易所 API 凭证）
            std::string strategy_id = data.value("strategy_id", "");
            std::string account_id = data.value("account_id", "");
            std::string exchange = data.value("exchange", "okx");
            std::string api_key = data.value("api_key", "");
            std::string secret_key = data.value("secret_key", "");
            std::string passphrase = data.value("passphrase", "");
            bool is_testnet = data.value("is_testnet", true);

            LOG_INFO("[账户注册] 策略: " + strategy_id + " | 账户: " + account_id + " | 交易所: " + exchange);

            if (api_key.empty() || secret_key.empty()) {
                response = {{"success", false}, {"message", "缺少必要参数 (api_key, secret_key)"}};
            } else {
                ExchangeType ex_type = string_to_exchange_type(exchange);
                bool success = false;

                if (strategy_id.empty()) {
                    // 注册为默认账户
                    if (ex_type == ExchangeType::OKX) {
                        g_account_registry.set_default_okx_account(api_key, secret_key, passphrase, is_testnet, account_id);
                        success = true;
                    } else if (ex_type == ExchangeType::BINANCE) {
                        g_account_registry.set_default_binance_account(api_key, secret_key, is_testnet, binance::MarketType::FUTURES, account_id);
                        success = true;
                    }
                } else {
                    success = g_account_registry.register_account(
                        strategy_id, ex_type, api_key, secret_key, passphrase, is_testnet, account_id
                    );
                }

                if (success) {
                    // 验证 API 有效性
                    std::string check_id = strategy_id.empty() ? "" : strategy_id;
                    bool api_valid = false;
                    std::string error_msg;

                    if (!check_id.empty()) {
                        try {
                            api_valid = g_account_registry.health_check(check_id, ex_type);
                            if (!api_valid) {
                                error_msg = "API 验证失败，请检查 API Key 和权限设置";
                            }
                        } catch (const std::exception& e) {
                            error_msg = std::string("API 验证异常: ") + e.what();
                        }
                    } else {
                        // 默认账户也验证
                        try {
                            if (ex_type == ExchangeType::OKX) {
                                auto* api = g_account_registry.get_okx_api("");
                                if (api) {
                                    auto result = api->get_account_balance();
                                    api_valid = result.contains("code") && result["code"].get<std::string>() == "0";
                                    if (!api_valid) {
                                        error_msg = result.contains("msg") ? result["msg"].get<std::string>() : "API 验证失败";
                                    }
                                }
                            } else if (ex_type == ExchangeType::BINANCE) {
                                auto* api = g_account_registry.get_binance_api("");
                                if (api) {
                                    int64_t t = api->get_server_time();
                                    api_valid = (t > 0);
                                    if (!api_valid) error_msg = "无法连接 Binance 服务器";
                                }
                            }
                        } catch (const std::exception& e) {
                            error_msg = std::string("API 验证异常: ") + e.what();
                        }
                    }

                    if (!api_valid) {
                        // API 无效，回滚注册
                        if (!strategy_id.empty()) {
                            g_account_registry.unregister_account(strategy_id, ex_type);
                        }
                        response = {{"success", false}, {"message", error_msg}};
                        LOG_INFO("[账户注册] ✗ API 验证失败: " + error_msg);
                    } else {
                        // API 有效，添加到账户监控器
                        if (g_account_monitor && !strategy_id.empty()) {
                            if (ex_type == ExchangeType::OKX) {
                                auto* api = g_account_registry.get_okx_api(strategy_id);
                                if (api) {
                                    trading::server::AccountCredentials credentials(api_key, secret_key, passphrase, is_testnet);
                                    g_account_monitor->register_okx_account(strategy_id, api, &credentials, account_id);
                                }
                            } else if (ex_type == ExchangeType::BINANCE) {
                                auto* api = g_account_registry.get_binance_api(strategy_id);
                                if (api) {
                                    trading::server::AccountCredentials credentials(api_key, secret_key, "", is_testnet);
                                    g_account_monitor->register_binance_account(strategy_id, api, &credentials, account_id);
                                }
                            }
                        }

                        response = {{"success", true}, {"message", "账户注册成功，API 验证通过"}};
                        LOG_INFO("[账户注册] ✓ " + (strategy_id.empty() ? "默认账户" : strategy_id) + " 注册成功，API 验证通过");
                    }
                } else {
                    response = {{"success", false}, {"message", "注册失败"}};
                    LOG_INFO("[账户注册] ✗ " + strategy_id + " 注册失败");
                }
            }
        }
        else if (action == "unregister_account") {
            // 注销账户
            std::string strategy_id = data.value("strategy_id", "");
            std::string exchange = data.value("exchange", "okx");

            if (strategy_id.empty()) {
                response = {{"success", false}, {"message", "缺少 strategy_id"}};
            } else {
                ExchangeType ex_type = string_to_exchange_type(exchange);
                bool success = g_account_registry.unregister_account(strategy_id, ex_type);

                if (success && g_account_monitor) {
                    if (ex_type == ExchangeType::OKX) {
                        g_account_monitor->unregister_okx_account(strategy_id);
                    } else if (ex_type == ExchangeType::BINANCE) {
                        g_account_monitor->unregister_binance_account(strategy_id);
                    }
                }

                response["success"] = success;
                response["message"] = success ? "账户注销成功" : "策略未找到";
                LOG_INFO("[账户注销] " + strategy_id + " " + (success ? "成功" : "失败"));
            }
        }
        else if (action == "list_accounts") {
            // 列出所有已注册账户
            auto accounts_info = g_account_registry.get_all_accounts_info();
            LOG_INFO("[list_accounts] 返回账户数据: " + accounts_info.dump());
            response = {
                {"success", true},
                {"type", "accounts_list"},
                {"data", accounts_info}
            };
        }
        else if (action == "list_strategy_configs") {
            frontend_debug("[list_strategy_configs] 进入处理");
            // 列出所有策略配置文件
            std::string config_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_config_dir;
            frontend_debug("[list_strategy_configs] 原始路径: " + config_dir);
            // 规范化路径，解析 .. 等
            try {
                config_dir = std::filesystem::canonical(config_dir).string();
            } catch (const std::exception& e) {
                frontend_debug("[list_strategy_configs] canonical失败: " + std::string(e.what()));
            }
            frontend_debug("[list_strategy_configs] 最终路径: " + config_dir);
            frontend_debug("[list_strategy_configs] 路径存在: " + std::string(std::filesystem::exists(config_dir) ? "是" : "否"));
            nlohmann::json configs_json = nlohmann::json::array();

            try {
                if (std::filesystem::exists(config_dir) && std::filesystem::is_directory(config_dir)) {
                    for (const auto& entry : std::filesystem::directory_iterator(config_dir)) {
                        if (entry.is_regular_file() && entry.path().extension() == ".json") {
                            try {
                                std::ifstream file(entry.path().string());
                                nlohmann::json config;
                                file >> config;

                                // 返回配置摘要（不暴露密钥）
                                nlohmann::json item;
                                item["filename"] = entry.path().filename().string();
                                item["strategy_id"] = config.value("strategy_id", entry.path().stem().string());
                                item["account_id"] = config.value("account_id", "");
                                item["strategy_name"] = config.value("strategy_name", "");
                                item["exchange"] = config.value("exchange", "okx");
                                item["is_testnet"] = config.value("is_testnet", true);
                                item["enabled"] = config.value("enabled", true);
                                item["description"] = config.value("description", "");
                                if (config.contains("params")) {
                                    item["params"] = config["params"];
                                }
                                configs_json.push_back(item);
                            } catch (const std::exception& e) {
                                LOG_INFO("[list_strategy_configs] 跳过无效配置: " + entry.path().filename().string() + " - " + e.what());
                            }
                        }
                    }
                }
            } catch (const std::exception& e) {
                LOG_INFO("[list_strategy_configs] 扫描目录失败: " + std::string(e.what()));
            }

            response = {
                {"success", true},
                {"data", configs_json}
            };
            LOG_INFO("[list_strategy_configs] 返回 " + std::to_string(configs_json.size()) + " 个配置");
        }
        else if (action == "create_strategy") {
            // 创建策略：用填写的 strategy_id, account_id 覆盖选中的配置文件
            std::string config_file = data.value("config_file", "");
            std::string strategy_id = data.value("strategy_id", "");
            std::string account_id = data.value("account_id", "");
            std::string strategy_name = data.value("strategy_name", "");
            std::string description = data.value("description", "");

            if (config_file.empty() || strategy_id.empty()) {
                response = {{"success", false}, {"message", "缺少必要参数 (config_file, strategy_id)"}};
            } else {
                std::string config_dir = get_exe_dir() + "/" + trading::config::ConfigCenter::instance().server().strategy_config_dir;
                std::string config_path = config_dir + "/" + config_file;

                try {
                    // 读取原配置
                    std::ifstream infile(config_path);
                    if (!infile.is_open()) {
                        response = {{"success", false}, {"message", "配置文件不存在: " + config_file}};
                    } else {
                        nlohmann::json config;
                        infile >> config;
                        infile.close();

                        // 覆盖字段
                        config["strategy_id"] = strategy_id;
                        if (!account_id.empty()) {
                            config["account_id"] = account_id;
                        }
                        if (!strategy_name.empty()) {
                            config["strategy_name"] = strategy_name;
                        }
                        if (!description.empty()) {
                            config["description"] = description;
                        }

                        // 从已注册账户中查找API Key信息并覆盖
                        auto accounts_info = g_account_registry.get_all_accounts_info();
                        bool found_account = false;

                        // 在 OKX 账户中查找
                        if (accounts_info.contains("okx")) {
                            for (const auto& acc : accounts_info["okx"]) {
                                std::string acc_id = acc.value("account_id", "");
                                std::string sid = acc.value("strategy_id", "");
                                if ((!account_id.empty() && acc_id == account_id) || sid == account_id) {
                                    config["exchange"] = "okx";
                                    config["is_testnet"] = acc.value("is_testnet", true);
                                    found_account = true;
                                    break;
                                }
                            }
                        }

                        // 在 Binance 账户中查找
                        if (!found_account && accounts_info.contains("binance")) {
                            for (const auto& acc : accounts_info["binance"]) {
                                std::string acc_id = acc.value("account_id", "");
                                std::string sid = acc.value("strategy_id", "");
                                if ((!account_id.empty() && acc_id == account_id) || sid == account_id) {
                                    config["exchange"] = "binance";
                                    config["is_testnet"] = acc.value("is_testnet", true);
                                    found_account = true;
                                    break;
                                }
                            }
                        }

                        // 写回配置文件
                        std::ofstream outfile(config_path);
                        if (!outfile.is_open()) {
                            response = {{"success", false}, {"message", "无法写入配置文件: " + config_file}};
                        } else {
                            outfile << config.dump(2);
                            outfile.close();

                            // 重新加载配置
                            trading::StrategyConfigManager::instance().load_configs(config_dir);

                            response = {{"success", true}, {"message", "策略创建成功"}};
                            LOG_INFO("[create_strategy] ✓ " + strategy_id + " (配置文件: " + config_file + ", 账户: " + account_id + ")");
                        }
                    }
                } catch (const std::exception& e) {
                    response = {{"success", false}, {"message", "创建失败: " + std::string(e.what())}};
                    LOG_INFO("[create_strategy] ✗ 失败: " + std::string(e.what()));
                }
            }
        }
        else {
            response = {{"success", false}, {"message", "未知命令: " + action}};
        }

        if (!request_id.empty()) {
            response["requestId"] = request_id;
        }

        frontend_debug("<<< 发送响应 action=" + action + " requestId=" + request_id + " success=" + std::string(response.value("success", false) ? "true" : "false") + " data_keys=" + std::to_string(response.size()));

        g_frontend_server->send_response(client_id, response.value("success", false),
                                        response.value("message", ""), response);

    } catch (const std::exception& e) {
        frontend_debug("!!! 异常 " + std::string(e.what()));
        std::cerr << "[前端] 处理命令异常: " << e.what() << "\n";
        g_frontend_server->send_response(client_id, false,
                                        std::string("处理命令异常: ") + e.what(), {});
    }
}

} // namespace server
} // namespace trading
