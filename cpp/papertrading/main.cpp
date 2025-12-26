/**
 * @file main.cpp
 * @brief 模拟交易服务器主程序入口
 * 
 * 功能：
 * 1. 启动模拟交易服务器
 * 2. 连接WebSocket获取实盘行情（只读）
 * 3. 接收策略订单请求并模拟执行
 * 4. 发布订单回报和行情数据
 * 
 * 使用方法：
 *   ./papertrading_server [选项]
 * 
 * 选项：
 *   --balance BALANCE    初始USDT余额（默认: 100000）
 *   --testnet            使用测试网行情（默认）
 *   --prod               使用实盘行情
 *   -h, --help           显示帮助
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include "papertrading_server.h"
#include "../server/zmq_server.h"
#include <iostream>
#include <string>
#include <csignal>
#include <cstring>
#include <atomic>
#include <thread>
#include <chrono>

using namespace trading;
using namespace trading::papertrading;
using namespace trading::server;
using namespace std::chrono;

// ============================================================
// 全局状态
// ============================================================

std::atomic<bool> g_running{true};
std::unique_ptr<PaperTradingServer> g_server;

// ============================================================
// 信号处理
// ============================================================

void signal_handler(int signum) {
    std::cout << "\n[Main] 收到信号 " << signum << "，正在停止...\n";
    g_running.store(false);
    if (g_server) {
        g_server->stop();
    }
}

// ============================================================
// 命令行参数解析
// ============================================================

void print_usage(const char* prog) {
    std::cout << "用法: " << prog << " [选项]\n"
              << "\n"
              << "选项:\n"
              << "  --balance BALANCE    初始USDT余额（默认: 100000）\n"
              << "  --testnet            使用测试网行情（默认）\n"
              << "  --prod               使用实盘行情\n"
              << "  -h, --help           显示帮助\n"
              << "\n"
              << "示例:\n"
              << "  " << prog << " --balance 50000 --testnet\n"
              << "  " << prog << " --balance 100000 --prod\n";
}

void parse_args(int argc, char* argv[], double& initial_balance, bool& is_testnet) {
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        
        if (arg == "-h" || arg == "--help") {
            print_usage(argv[0]);
            exit(0);
        }
        else if (arg == "--balance" && i + 1 < argc) {
            initial_balance = std::stod(argv[++i]);
        }
        else if (arg == "--testnet") {
            is_testnet = true;
        }
        else if (arg == "--prod") {
            is_testnet = false;
        }
        else {
            std::cerr << "未知选项: " << arg << "\n";
            print_usage(argv[0]);
            exit(1);
        }
    }
}

// ============================================================
// 主函数
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "========================================\n";
    std::cout << "    Sequence 模拟交易服务器\n";
    std::cout << "    Paper Trading Server\n";
    std::cout << "========================================\n\n";
    
    // 默认配置
    double initial_balance = 100000.0;
    bool is_testnet = true;
    
    // 解析命令行参数
    parse_args(argc, argv, initial_balance, is_testnet);
    
    // 打印配置
    std::cout << "[配置]\n";
    std::cout << "  初始余额: " << initial_balance << " USDT\n";
    std::cout << "  行情来源: " << (is_testnet ? "测试网" : "实盘") << "\n";
    std::cout << "\n";
    
    // 注册信号处理
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);
    
    // 创建并启动服务器
    try {
        g_server = std::make_unique<PaperTradingServer>(initial_balance, is_testnet);
        
        if (!g_server->start()) {
            std::cerr << "[错误] 服务器启动失败\n";
            return 1;
        }
        
        std::cout << "\n========================================\n";
        std::cout << "  模拟交易服务器启动完成！\n";
        std::cout << "  等待策略连接...\n";
        std::cout << "  按 Ctrl+C 停止\n";
        std::cout << "========================================\n\n";
        
        // 打印ZMQ通道信息
        std::cout << "[ZMQ通道]\n";
        std::cout << "  行情: " << IpcAddresses::MARKET_DATA << "\n";
        std::cout << "  订单: " << IpcAddresses::ORDER << "\n";
        std::cout << "  回报: " << IpcAddresses::REPORT << "\n";
        std::cout << "  查询: " << IpcAddresses::QUERY << "\n";
        std::cout << "  订阅: " << IpcAddresses::SUBSCRIBE << "\n";
        std::cout << "\n";
        
        // 主循环：等待直到收到停止信号
        while (g_running.load() && g_server->is_running()) {
            std::this_thread::sleep_for(milliseconds(100));
        }
        
        // 停止服务器
        std::cout << "\n[Main] 正在停止服务器...\n";
        g_server->stop();
        g_server.reset();
        
        std::cout << "\n========================================\n";
        std::cout << "  模拟交易服务器已停止\n";
        std::cout << "========================================\n";
        
        return 0;
        
    } catch (const std::exception& e) {
        std::cerr << "[错误] 异常: " << e.what() << "\n";
        return 1;
    }
}

