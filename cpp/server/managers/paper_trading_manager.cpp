/**
 * @file paper_trading_manager.cpp
 * @brief PaperTrading 管理模块实现 - 支持多策略
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
#include <sstream>
#include <map>

namespace trading {
namespace server {

// 策略信息结构
struct StrategyInfo {
    pid_t pid;
    nlohmann::json config;
    int64_t startTime;
};

// 多策略存储
static std::map<std::string, StrategyInfo> g_strategies;
static std::mutex g_strategies_mutex;

nlohmann::json process_start_paper_strategy(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_strategies_mutex);

    // 确保 papertrading_server 在运行
    FILE* fp = popen("pgrep -f papertrading_server", "r");
    bool server_running = false;
    if (fp) {
        char pid_str[32];
        if (fgets(pid_str, sizeof(pid_str), fp)) {
            g_paper_trading_pid = atoi(pid_str);
            server_running = true;
        }
        pclose(fp);
    }

    if (!server_running) {
        // 启动 papertrading_server
        std::string cmd = "cd /home/llx/Real-account-trading-framework/cpp/build && ./papertrading_server > /tmp/papertrading.log 2>&1 &";
        int ret = system(cmd.c_str());
        if (ret != 0) {
            return {{"success", false}, {"message", "启动 papertrading_server 失败"}};
        }
        sleep(2);

        // 获取 PID
        fp = popen("pgrep -f papertrading_server", "r");
        if (fp) {
            char pid_str[32];
            if (fgets(pid_str, sizeof(pid_str), fp)) {
                g_paper_trading_pid = atoi(pid_str);
            }
            pclose(fp);
        }
        std::cout << "[PaperTrading] papertrading_server 已启动 (PID: " << g_paper_trading_pid << ")\n";
    }

    // 获取策略ID
    std::string strategy_id = request.value("strategyId", "");
    if (strategy_id.empty()) {
        strategy_id = "paper_grid_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
    }

    // 检查策略是否已存在
    if (g_strategies.find(strategy_id) != g_strategies.end()) {
        return {{"success", false}, {"message", "策略已存在: " + strategy_id}};
    }

    // 启动策略脚本
    std::string strategy = request.value("strategy", "grid");
    pid_t strategy_pid = -1;

    if (strategy == "grid") {
        std::string symbol = request.value("symbol", "BTC-USDT-SWAP");
        int grid_num = request.value("gridNum", 10);
        double grid_spread = request.value("gridSpread", 0.002);
        double order_amount = request.value("orderAmount", 100.0);

        std::ostringstream strategy_cmd;
        strategy_cmd << "cd /home/llx/Real-account-trading-framework/cpp/strategies && "
                     << "python3 -u grid_strategy_paper.py "
                     << "--strategy-id " << strategy_id << " "
                     << "--symbol " << symbol << " "
                     << "--grid-num " << grid_num << " "
                     << "--grid-spread " << grid_spread << " "
                     << "--order-amount " << order_amount << " "
                     << "> /tmp/" << strategy_id << ".log 2>&1 &";

        std::cout << "[PaperTrading] 启动Python策略:\n"
                  << "  命令: python3 grid_strategy_paper.py\n"
                  << "  策略ID: " << strategy_id << "\n"
                  << "  交易对: " << symbol << "\n"
                  << "  网格数: " << grid_num << "\n"
                  << "  网格间距: " << (grid_spread * 100) << "%\n"
                  << "  单格金额: " << order_amount << " USDT\n"
                  << "  日志文件: /tmp/" << strategy_id << ".log\n";

        system(strategy_cmd.str().c_str());
        sleep(1);

        // 获取策略进程 PID
        std::string pgrep_cmd = "pgrep -f 'strategy-id " + strategy_id + "'";
        FILE* sfp = popen(pgrep_cmd.c_str(), "r");
        if (sfp) {
            char spid_str[32];
            if (fgets(spid_str, sizeof(spid_str), sfp)) {
                strategy_pid = atoi(spid_str);
            }
            pclose(sfp);
        }

        std::cout << "[PaperTrading] 策略已启动: " << strategy_id << " (PID: " << strategy_pid << ")\n";
    }

    // 记录策略信息
    int64_t start_time = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();

    g_strategies[strategy_id] = {strategy_pid, request, start_time};
    g_paper_trading_running = true;

    return {
        {"success", true},
        {"message", "策略已启动"},
        {"data", {
            {"strategyId", strategy_id},
            {"startTime", start_time}
        }}
    };
}

nlohmann::json process_stop_paper_strategy(const nlohmann::json& request) {
    std::lock_guard<std::mutex> lock(g_strategies_mutex);

    std::string strategy_id = request.value("strategyId", "");

    // 如果指定了策略ID，只停止该策略
    if (!strategy_id.empty()) {
        auto it = g_strategies.find(strategy_id);
        if (it == g_strategies.end()) {
            return {{"success", false}, {"message", "策略不存在: " + strategy_id}};
        }

        if (it->second.pid > 0) {
            kill(it->second.pid, SIGTERM);
            int status;
            waitpid(it->second.pid, &status, WNOHANG);
            std::cout << "[PaperTrading] 策略已停止: " << strategy_id << " (PID: " << it->second.pid << ")\n";
        }

        g_strategies.erase(it);

        // 如果没有策略了，停止 papertrading_server
        if (g_strategies.empty()) {
            if (g_paper_trading_pid > 0) {
                kill(g_paper_trading_pid, SIGTERM);
                int status;
                waitpid(g_paper_trading_pid, &status, WNOHANG);
                std::cout << "[PaperTrading] papertrading_server 已停止\n";
                g_paper_trading_pid = -1;
            }
            g_paper_trading_running = false;
        }

        return {{"success", true}, {"message", "策略已停止: " + strategy_id}};
    }

    // 停止所有策略
    for (auto& [id, info] : g_strategies) {
        if (info.pid > 0) {
            kill(info.pid, SIGTERM);
            int status;
            waitpid(info.pid, &status, WNOHANG);
            std::cout << "[PaperTrading] 策略已停止: " << id << "\n";
        }
    }
    g_strategies.clear();

    // 停止 papertrading_server
    if (g_paper_trading_pid > 0) {
        kill(g_paper_trading_pid, SIGTERM);
        int status;
        waitpid(g_paper_trading_pid, &status, WNOHANG);
        std::cout << "[PaperTrading] papertrading_server 已停止\n";
        g_paper_trading_pid = -1;
    }

    g_paper_trading_running = false;

    return {{"success", true}, {"message", "所有策略已停止"}};
}

nlohmann::json process_get_paper_strategy_status(const nlohmann::json& request) {
    (void)request;
    std::lock_guard<std::mutex> lock(g_strategies_mutex);

    nlohmann::json strategies_array = nlohmann::json::array();
    for (const auto& [id, info] : g_strategies) {
        nlohmann::json strategy_info = info.config;
        strategy_info["strategyId"] = id;
        strategy_info["startTime"] = info.startTime;
        strategy_info["pid"] = info.pid;
        strategies_array.push_back(strategy_info);
    }

    return {
        {"success", true},
        {"data", {
            {"isRunning", !g_strategies.empty()},
            {"strategies", strategies_array},
            {"serverPid", g_paper_trading_pid}
        }}
    };
}

} // namespace server
} // namespace trading
