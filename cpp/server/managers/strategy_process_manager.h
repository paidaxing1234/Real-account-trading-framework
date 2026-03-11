/**
 * @file strategy_process_manager.h
 * @brief 策略进程管理器 - 独立于 AccountRegistry，追踪策略运行状态
 *
 * 通过心跳机制检测策略进程是否存活，支持前端中止策略（kill进程）。
 * 账户注册和策略运行是独立的生命周期：
 * - 策略停止 → 账户仍然注册
 * - 注销账户 → 需要手动操作
 */

#pragma once

#include <string>
#include <map>
#include <set>
#include <mutex>
#include <chrono>
#include <signal.h>
#include <sys/types.h>
#include <nlohmann/json.hpp>

namespace trading {
namespace server {

struct StrategyProcessInfo {
    std::string strategy_id;
    std::string account_id;
    std::string exchange;
    pid_t pid = 0;
    std::string status = "running";  // "running" | "stopped" | "error"
    std::string start_command;       // 启动命令行（用于重启）
    std::string work_dir;            // 工作目录
    int64_t start_time = 0;
    int64_t last_heartbeat = 0;

    nlohmann::json to_json() const {
        return {
            {"strategy_id", strategy_id},
            {"account_id", account_id},
            {"exchange", exchange},
            {"pid", pid},
            {"status", status},
            {"start_command", start_command},
            {"work_dir", work_dir},
            {"start_time", start_time},
            {"last_heartbeat", last_heartbeat}
        };
    }
};

class StrategyProcessManager {
public:
    /**
     * @brief 注册一个策略进程（Python 策略启动时调用）
     */
    void register_strategy(const std::string& strategy_id, pid_t pid,
                           const std::string& account_id,
                           const std::string& exchange,
                           const std::string& start_command = "",
                           const std::string& work_dir = "") {
        std::lock_guard<std::mutex> lock(mutex_);
        auto now_ms = current_timestamp_ms();

        StrategyProcessInfo info;
        info.strategy_id = strategy_id;
        info.account_id = account_id;
        info.exchange = exchange;
        info.pid = pid;
        info.status = "running";
        info.start_command = start_command;
        info.work_dir = work_dir;
        info.start_time = now_ms;
        info.last_heartbeat = now_ms;

        strategies_[strategy_id] = info;
    }

    /**
     * @brief 移除策略（注销时调用）
     */
    void unregister_strategy(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        strategies_.erase(strategy_id);
    }

    /**
     * @brief 记录心跳
     */
    void record_heartbeat(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = strategies_.find(strategy_id);
        if (it != strategies_.end()) {
            it->second.last_heartbeat = current_timestamp_ms();
            // 如果之前是 stopped/error 但又收到心跳，说明策略重新启动了
            if (it->second.status != "running") {
                it->second.status = "running";
            }
        }
    }

    /**
     * @brief 中止策略进程（前端调用）
     * @return true 如果成功发送 SIGTERM
     */
    bool stop_strategy(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = strategies_.find(strategy_id);
        if (it == strategies_.end()) {
            return false;
        }

        if (it->second.pid > 0 && it->second.status == "running") {
            int ret = kill(it->second.pid, SIGTERM);
            it->second.status = "stopped";
            return (ret == 0);
        }

        it->second.status = "stopped";
        return true;
    }

    /**
     * @brief 重新启动策略进程（前端调用）
     * @return {success, message, pid}
     */
    std::tuple<bool, std::string, pid_t> start_strategy(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = strategies_.find(strategy_id);
        if (it == strategies_.end()) {
            return {false, "策略未找到", 0};
        }

        if (it->second.status == "running") {
            return {false, "策略已在运行中", it->second.pid};
        }

        if (it->second.start_command.empty()) {
            return {false, "无启动命令记录，请手动运行 Python 策略脚本", 0};
        }

        // fork + exec 在后台启动策略
        std::string cmd = it->second.start_command;
        std::string cwd = it->second.work_dir;

        pid_t child = fork();
        if (child < 0) {
            return {false, "fork 失败: " + std::string(strerror(errno)), 0};
        }

        if (child == 0) {
            // 子进程
            // 关闭从父进程继承的所有非标准文件描述符（避免占用 WebSocket 端口等）
            for (int fd = 3; fd < 1024; fd++) {
                close(fd);
            }
            // 切换工作目录
            if (!cwd.empty()) {
                if (chdir(cwd.c_str()) != 0) {
                    _exit(1);
                }
            }
            // 脱离父进程的会话，成为独立后台进程
            setsid();
            // 关闭标准输入，重定向输出到 /dev/null（策略自己有日志文件）
            close(STDIN_FILENO);
            // 用 sh -c 执行完整命令行
            execl("/bin/sh", "sh", "-c", cmd.c_str(), nullptr);
            _exit(1);  // exec 失败
        }

        // 父进程：更新策略信息
        auto now_ms = current_timestamp_ms();
        it->second.pid = child;
        it->second.status = "running";
        it->second.start_time = now_ms;
        it->second.last_heartbeat = now_ms;

        return {true, "策略已启动, PID=" + std::to_string(child), child};
    }

    /**
     * @brief 检查心跳超时，标记无心跳的策略为 stopped
     * @param timeout_sec 心跳超时时间（秒）
     */
    void check_heartbeats(int timeout_sec = 15) {
        std::lock_guard<std::mutex> lock(mutex_);
        auto now_ms = current_timestamp_ms();
        int64_t timeout_ms = timeout_sec * 1000LL;

        for (auto& [sid, info] : strategies_) {
            if (info.status == "running") {
                if (now_ms - info.last_heartbeat > timeout_ms) {
                    // 额外检查进程是否还存在
                    if (info.pid > 0 && kill(info.pid, 0) != 0) {
                        info.status = "stopped";
                    } else if (info.pid <= 0) {
                        info.status = "stopped";
                    }
                    // 如果 kill(pid, 0) == 0 说明进程还在，可能只是心跳延迟，
                    // 但超时足够长（15s），仍然标记为 stopped
                    else {
                        info.status = "stopped";
                    }
                }
            }
        }
    }

    /**
     * @brief 获取运行中的策略数量
     */
    size_t running_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        size_t count = 0;
        for (const auto& [sid, info] : strategies_) {
            if (info.status == "running") {
                count++;
            }
        }
        return count;
    }

    /**
     * @brief 获取唯一账户数量（去重 account_id）
     * 只统计有运行中策略或已注册的账户
     */
    size_t unique_account_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::set<std::string> accounts;
        for (const auto& [sid, info] : strategies_) {
            if (!info.account_id.empty()) {
                accounts.insert(info.account_id);
            }
        }
        return accounts.size();
    }

    /**
     * @brief 获取所有策略信息（供前端展示）
     */
    nlohmann::json get_all_info() const {
        std::lock_guard<std::mutex> lock(mutex_);
        nlohmann::json result = nlohmann::json::array();
        for (const auto& [sid, info] : strategies_) {
            result.push_back(info.to_json());
        }
        return result;
    }

    /**
     * @brief 获取所有策略数量（含已停止的）
     */
    size_t total_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return strategies_.size();
    }

    /**
     * @brief 获取策略对应的 account_id
     */
    std::string get_account_id(const std::string& strategy_id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = strategies_.find(strategy_id);
        if (it != strategies_.end()) {
            return it->second.account_id;
        }
        return "";
    }

    /**
     * @brief 停止并删除指定账户下的所有策略
     * @param account_id 账户ID
     * @return 被删除的策略ID列表
     */
    std::vector<std::string> stop_and_remove_by_account(const std::string& account_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<std::string> removed;

        for (auto it = strategies_.begin(); it != strategies_.end(); ) {
            if (it->second.account_id == account_id) {
                // 先停止运行中的进程
                if (it->second.pid > 0 && it->second.status == "running") {
                    kill(it->second.pid, SIGTERM);
                }
                removed.push_back(it->first);
                it = strategies_.erase(it);
            } else {
                ++it;
            }
        }

        return removed;
    }

private:
    static int64_t current_timestamp_ms() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }

    std::map<std::string, StrategyProcessInfo> strategies_;
    mutable std::mutex mutex_;
};

} // namespace server
} // namespace trading
