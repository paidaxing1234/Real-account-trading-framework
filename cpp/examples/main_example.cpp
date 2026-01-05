/**
 * @file main_example.cpp
 * @brief 实盘交易框架示例程序
 * 
 * 演示如何使用框架：
 * 1. 创建事件引擎
 * 2. 启动各个组件（适配器、账户管理、记录器）
 * 3. 启动策略
 * 4. 运行交易
 */

#include "../core/event_engine.h"
#include "../trading/order.h"
#include "../core/data.h"
#include "../strategies/demo_strategy.h"
#include "../utils/account_manager.h"
#include "../utils/recorder.h"
// #include "../adapters/okx/okx_adapter.h"  // 需要实现后取消注释

#include <iostream>
#include <memory>
#include <thread>
#include <chrono>
#include <signal.h>

using namespace trading;

// 全局标志位（用于优雅退出）
std::atomic<bool> g_running{true};

void signal_handler(int signal) {
    std::cout << "\n接收到信号 " << signal << "，准备退出..." << std::endl;
    g_running = false;
}

int main(int argc, char* argv[]) {
    std::cout << "==================================================" << std::endl;
    std::cout << "       C++ 实盘交易框架 - 示例程序" << std::endl;
    std::cout << "==================================================" << std::endl;
    
    // 注册信号处理
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // 1. 创建事件引擎
    std::cout << "\n[1] 创建事件引擎..." << std::endl;
    auto engine = std::make_unique<EventEngine>();
    
    // 2. 创建各个组件
    std::cout << "[2] 创建组件..." << std::endl;
    
    // 账户管理器
    auto account_manager = std::make_unique<AccountManager>();
    account_manager->set_balance(10000.0);  // 初始余额
    
    // 数据记录器
    auto recorder = std::make_unique<Recorder>("trading_demo.log");
    
    // OKX适配器（需要实现后取消注释）
    // auto okx_adapter = std::make_unique<okx::OKXAdapter>(
    //     "your_api_key",
    //     "your_secret_key",
    //     "your_passphrase",
    //     true  // 使用测试网
    // );
    
    // 策略
    auto strategy = std::make_unique<DemoStrategy>(
        "BTC-USDT-SWAP",  // 交易对
        100.0,            // 网格间距
        0.01,             // 每次交易数量
        5                 // 网格层数
    );
    
    // 3. 启动所有组件
    std::cout << "[3] 启动组件..." << std::endl;
    
    account_manager->start(engine.get());
    recorder->start(engine.get());
    // okx_adapter->start(engine.get());  // 需要实现后取消注释
    strategy->start(engine.get());
    
    std::cout << "[4] 所有组件已启动，开始运行..." << std::endl;
    std::cout << "\n提示：按 Ctrl+C 退出\n" << std::endl;
    
    // 4. 模拟行情推送（实际应该由OKX适配器推送）
    std::cout << "[测试模式] 模拟行情推送..." << std::endl;
    
    int count = 0;
    double base_price = 50000.0;
    
    while (g_running) {
        // 模拟行情波动
        double price = base_price + (count % 100) * 10;
        
        auto ticker = std::make_shared<TickerData>("BTC-USDT-SWAP", price);
        ticker->set_bid_price(price - 1.0);
        ticker->set_ask_price(price + 1.0);
        ticker->set_timestamp(Event::current_timestamp());
        
        // 推送行情事件
        engine->put(ticker);
        
        // 每5秒打印一次状态
        if (count % 50 == 0) {
            auto pos = account_manager->get_position("BTC-USDT-SWAP");
            std::cout << "\n[状态] 价格: " << price 
                      << " | 持仓: " << pos.quantity
                      << " | 未实现盈亏: " << pos.unrealized_pnl
                      << " | 已实现盈亏: " << pos.realized_pnl << std::endl;
        }
        
        count++;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    
    // 5. 停止所有组件
    std::cout << "\n[5] 停止所有组件..." << std::endl;
    
    strategy->stop();
    // okx_adapter->stop();  // 需要实现后取消注释
    recorder->stop();
    account_manager->stop();
    
    std::cout << "[6] 程序已退出" << std::endl;
    
    return 0;
}

