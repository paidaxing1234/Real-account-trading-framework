/**
 * @file papertrading_server.h
 * @brief 模拟交易服务器（实时模式）
 *
 * 功能：
 * 1. 通过ZMQ订阅主服务器的实盘行情
 * 2. 接收策略订单请求（ZMQ PULL）
 * 3. 模拟执行订单（本地引擎）
 * 4. 发布订单回报（ZMQ PUB）
 * 5. 发布行情数据（ZMQ PUB）
 *
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

// 然后包含其他必要的头文件
#include "../network/zmq_server.h"
#include "papertrading_config.h"
#include <zmq.hpp>

// 最后包含可能包含旧类型定义的头文件（使用前向声明避免直接包含）
// 注意：这些头文件在 .cpp 文件中包含，避免在头文件中包含
#include <memory>
#include <atomic>
#include <thread>
#include <string>
#include <vector>
#include <map>
#include <mutex>
#include <set>

// 前向声明
namespace trading {
namespace papertrading {
class MockAccountEngine;
class OrderExecutionEngine;
}
}

namespace trading {
namespace papertrading {

/**
 * @brief 模拟交易服务器（实时模式）
 * 
 * 使用实盘行情数据，但订单执行完全模拟
 */
class PaperTradingServer {
public:
    /**
     * @brief 构造函数（使用配置对象）
     * @param config 配置对象
     */
    explicit PaperTradingServer(const PaperTradingConfig& config);
    
    /**
     * @brief 构造函数（兼容旧接口，使用默认配置）
     * @param initial_balance 初始USDT余额
     * @param is_testnet 是否使用测试网（仅用于获取行情）
     * @deprecated 建议使用 PaperTradingServer(const PaperTradingConfig&) 构造函数
     */
    PaperTradingServer(double initial_balance, bool is_testnet);
    
    ~PaperTradingServer();
    
    // ==================== 生命周期管理 ====================
    
    /**
     * @brief 启动服务器
     */
    bool start();
    
    /**
     * @brief 停止服务器
     */
    void stop();
    
    /**
     * @brief 检查是否运行中
     */
    bool is_running() const { return running_.load(); }

private:
    // ==================== 初始化方法 ====================
    void init_zmq_server();
    void init_zmq_market_data_client();

    // ==================== 消息处理 ====================
    void handle_order_request(const nlohmann::json& order_json);
    void handle_cancel_request(const nlohmann::json& cancel_json);
    void handle_cancel_all_request(const nlohmann::json& cancel_all_json);
    nlohmann::json handle_query_request(const nlohmann::json& query_json);
    void handle_subscribe_request(const nlohmann::json& sub_json);

    // ==================== ZMQ行情回调 ====================
    void on_market_data_update(const nlohmann::json& data);

    // ==================== 订单执行引擎回调 ====================
    void on_order_report(const nlohmann::json& report);

    // ==================== 成员变量 ====================
    std::atomic<bool> running_{false};
    
    // 配置
    PaperTradingConfig config_;
    
    // 模拟引擎
    std::shared_ptr<MockAccountEngine> mock_account_engine_;
    std::unique_ptr<OrderExecutionEngine> order_execution_engine_;
    
    // 最新成交价缓存（用于市价单执行）
    std::map<std::string, double> last_trade_prices_;  // symbol -> price
    std::mutex prices_mutex_;
    
    // ZMQ服务器
    std::unique_ptr<server::ZmqServer> zmq_server_;

    // ZMQ订阅socket（订阅主服务器行情）
    std::unique_ptr<zmq::context_t> zmq_context_;
    std::unique_ptr<zmq::socket_t> market_data_sub_;

    // 订阅管理
    std::mutex subscribed_symbols_mutex_;
    std::set<std::string> subscribed_trades_;
    std::map<std::string, std::set<std::string>> subscribed_klines_;  // symbol -> intervals
    std::map<std::string, std::set<std::string>> subscribed_orderbooks_;  // symbol -> channels
    std::set<std::string> subscribed_funding_rates_;
    
    // 工作线程
    std::thread order_thread_;
    std::thread query_thread_;
    std::thread subscribe_thread_;
    std::thread market_data_thread_;
};

} // namespace papertrading
} // namespace trading

