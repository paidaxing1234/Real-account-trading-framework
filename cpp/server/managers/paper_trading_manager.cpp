/**
 * @file paper_trading_manager.cpp
 * @brief PaperTrading 管理模块实现
 */

#include "paper_trading_manager.h"
#include "../config/server_config.h"
#include <iostream>
#include <chrono>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>
#include <cstdio>
#include <cstdlib>

namespace trading {
namespace server {

nlohmann::json process_start_paper_strategy(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    if (g_paper_trading_running) {
        return {{"success", false}, {"message", "模拟交易已在运行中"}};
    }

    g_paper_trading_config = request;

    std::string cmd = "cd /home/llx/Real-account-trading-framework/cpp/build && ./papertrading_server > /tmp/papertrading.log 2>&1 &";

    int ret = system(cmd.c_str());
    if (ret != 0) {
        return {{"success", false}, {"message", "启动失败"}};
    }

    sleep(2);

    FILE* fp = popen("pgrep -f papertrading_server", "r");
    if (fp) {
        char pid_str[32];
        if (fgets(pid_str, sizeof(pid_str), fp)) {
            g_paper_trading_pid = atoi(pid_str);
        }
        pclose(fp);
    }

    g_paper_trading_running = true;
    g_paper_trading_start_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();

    std::cout << "[PaperTrading] 已启动 (PID: " << g_paper_trading_pid << ")\n";

    return {
        {"success", true},
        {"message", "模拟交易已启动"},
        {"data", {
            {"strategyId", "paper_trading"},
            {"startTime", g_paper_trading_start_time}
        }}
    };
}

nlohmann::json process_stop_paper_strategy(const nlohmann::json& request) {
    (void)request;
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    if (!g_paper_trading_running) {
        return {{"success", false}, {"message", "模拟交易未运行"}};
    }

    if (g_paper_trading_pid > 0) {
        kill(g_paper_trading_pid, SIGTERM);

        int status;
        waitpid(g_paper_trading_pid, &status, WNOHANG);

        std::cout << "[PaperTrading] 已停止 (PID: " << g_paper_trading_pid << ")\n";
        g_paper_trading_pid = -1;
    }

    g_paper_trading_running = false;
    g_paper_trading_config.clear();

    return {{"success", true}, {"message", "模拟交易已停止"}};
}

nlohmann::json process_get_paper_strategy_status(const nlohmann::json& request) {
    (void)request;
    std::lock_guard<std::mutex> lock(g_paper_trading_mutex);

    return {
        {"success", true},
        {"data", {
            {"isRunning", g_paper_trading_running.load()},
            {"config", g_paper_trading_config},
            {"startTime", g_paper_trading_start_time},
            {"pid", g_paper_trading_pid}
        }}
    };
}

} // namespace server
} // namespace trading
