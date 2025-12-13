/**
 * @file zmq_server.cpp
 * @brief ZeroMQ 服务端实现
 * 
 * 实现说明：
 * 
 * 1. IPC 通道原理：
 *    - 使用 Unix Domain Socket，数据不经过 TCP/IP 协议栈
 *    - 内核直接在两个进程间拷贝数据
 *    - 延迟约 30-100μs（比 TCP localhost 快 3-5 倍）
 * 
 * 2. ZeroMQ 消息模式：
 *    - PUB-SUB：发布-订阅，一对多广播
 *    - PUSH-PULL：推送-拉取，多对一汇聚
 * 
 * 3. 非阻塞接收：
 *    - 使用 ZMQ_DONTWAIT 标志
 *    - 没有消息时立即返回，不阻塞主线程
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "zmq_server.h"
#include <iostream>
#include <cstdio>  // for remove()

namespace trading {
namespace server {

// ============================================================
// 构造函数和析构函数
// ============================================================

ZmqServer::ZmqServer()
    : context_(1)  // 1 个 I/O 线程，对于 IPC 足够了
{
    // context 在这里初始化
    // socket 在 start() 中创建
    std::cout << "[ZmqServer] 初始化完成\n";
}

ZmqServer::~ZmqServer() {
    // 确保停止
    stop();
    std::cout << "[ZmqServer] 销毁完成\n";
}

// ============================================================
// 生命周期管理
// ============================================================

bool ZmqServer::start() {
    if (running_.load()) {
        std::cout << "[ZmqServer] 已经在运行中\n";
        return true;
    }
    
    try {
        // ========================================
        // 创建行情发布 socket (PUB)
        // ========================================
        // PUB socket 用于一对多广播
        // 所有连接到这个地址的 SUB socket 都会收到消息
        market_pub_ = std::make_unique<zmq::socket_t>(context_, zmq::socket_type::pub);
        
        // 设置 socket 选项
        // LINGER = 0: 关闭时不等待未发送的消息
        int linger = 0;
        market_pub_->set(zmq::sockopt::linger, linger);
        
        // 绑定到 IPC 地址
        // 如果文件已存在，先删除
        std::remove("/tmp/trading_md.ipc");
        market_pub_->bind(IpcAddresses::MARKET_DATA);
        std::cout << "[ZmqServer] 行情通道已绑定: " << IpcAddresses::MARKET_DATA << "\n";
        
        // ========================================
        // 创建订单接收 socket (PULL)
        // ========================================
        // PULL socket 用于接收多个客户端的消息
        // 消息会自动负载均衡（每条消息只有一个 PULL 收到）
        order_pull_ = std::make_unique<zmq::socket_t>(context_, zmq::socket_type::pull);
        order_pull_->set(zmq::sockopt::linger, linger);
        
        // 绑定到 IPC 地址
        std::remove("/tmp/trading_order.ipc");
        order_pull_->bind(IpcAddresses::ORDER);
        std::cout << "[ZmqServer] 订单通道已绑定: " << IpcAddresses::ORDER << "\n";
        
        // ========================================
        // 创建回报发布 socket (PUB)
        // ========================================
        report_pub_ = std::make_unique<zmq::socket_t>(context_, zmq::socket_type::pub);
        report_pub_->set(zmq::sockopt::linger, linger);
        
        std::remove("/tmp/trading_report.ipc");
        report_pub_->bind(IpcAddresses::REPORT);
        std::cout << "[ZmqServer] 回报通道已绑定: " << IpcAddresses::REPORT << "\n";
        
        running_.store(true);
        std::cout << "[ZmqServer] 服务已启动\n";
        return true;
        
    } catch (const zmq::error_t& e) {
        std::cerr << "[ZmqServer] 启动失败: " << e.what() << "\n";
        stop();
        return false;
    }
}

void ZmqServer::stop() {
    if (!running_.load()) {
        return;
    }
    
    running_.store(false);
    
    // 关闭所有 socket
    // 注意：必须先关闭 socket，再销毁 context
    if (market_pub_) {
        market_pub_->close();
        market_pub_.reset();
    }
    
    if (order_pull_) {
        order_pull_->close();
        order_pull_.reset();
    }
    
    if (report_pub_) {
        report_pub_->close();
        report_pub_.reset();
    }
    
    // 清理 IPC 文件
    std::remove("/tmp/trading_md.ipc");
    std::remove("/tmp/trading_order.ipc");
    std::remove("/tmp/trading_report.ipc");
    
    std::cout << "[ZmqServer] 服务已停止\n";
    std::cout << "[ZmqServer] 统计 - 行情: " << market_msg_count_ 
              << ", 订单: " << order_recv_count_ 
              << ", 回报: " << report_msg_count_ << "\n";
}

// ============================================================
// 行情发布
// ============================================================

bool ZmqServer::publish_ticker(const nlohmann::json& ticker_data) {
    return publish_market(ticker_data, MessageType::TICKER);
}

bool ZmqServer::publish_depth(const nlohmann::json& depth_data) {
    return publish_market(depth_data, MessageType::DEPTH);
}

bool ZmqServer::publish_market(const nlohmann::json& data, MessageType msg_type) {
    if (!running_.load() || !market_pub_) {
        return false;
    }
    
    // 序列化 JSON 为字符串
    std::string msg = data.dump();
    
    // 发送消息
    if (send_message(*market_pub_, msg)) {
        market_msg_count_++;
        return true;
    }
    return false;
}

// ============================================================
// 订单接收
// ============================================================

bool ZmqServer::recv_order(std::string& order_msg) {
    if (!running_.load() || !order_pull_) {
        return false;
    }
    
    return recv_message(*order_pull_, order_msg);
}

bool ZmqServer::recv_order_json(nlohmann::json& order) {
    std::string msg;
    if (!recv_order(msg)) {
        return false;
    }
    
    try {
        order = nlohmann::json::parse(msg);
        order_recv_count_++;
        return true;
    } catch (const nlohmann::json::exception& e) {
        std::cerr << "[ZmqServer] JSON 解析失败: " << e.what() << "\n";
        return false;
    }
}

int ZmqServer::poll_orders() {
    int count = 0;
    nlohmann::json order;
    
    // 循环接收所有待处理的订单
    while (recv_order_json(order)) {
        if (order_callback_) {
            order_callback_(order);
        }
        count++;
    }
    
    return count;
}

// ============================================================
// 回报发布
// ============================================================

bool ZmqServer::publish_report(const nlohmann::json& report_data) {
    if (!running_.load() || !report_pub_) {
        return false;
    }
    
    std::string msg = report_data.dump();
    
    if (send_message(*report_pub_, msg)) {
        report_msg_count_++;
        return true;
    }
    return false;
}

// ============================================================
// 私有辅助函数
// ============================================================

bool ZmqServer::send_message(zmq::socket_t& socket, const std::string& data) {
    try {
        // 创建 ZeroMQ 消息
        zmq::message_t message(data.data(), data.size());
        
        // 发送消息
        // send() 对于 PUB socket 是非阻塞的
        auto result = socket.send(message, zmq::send_flags::none);
        
        return result.has_value();
        
    } catch (const zmq::error_t& e) {
        std::cerr << "[ZmqServer] 发送失败: " << e.what() << "\n";
        return false;
    }
}

bool ZmqServer::recv_message(zmq::socket_t& socket, std::string& data) {
    try {
        zmq::message_t message;
        
        // 非阻塞接收
        // ZMQ_DONTWAIT: 没有消息时立即返回，不等待
        auto result = socket.recv(message, zmq::recv_flags::dontwait);
        
        if (!result.has_value()) {
            // 没有消息
            return false;
        }
        
        // 提取数据
        data = std::string(static_cast<char*>(message.data()), message.size());
        return true;
        
    } catch (const zmq::error_t& e) {
        // EAGAIN 表示没有消息，不是错误
        if (e.num() != EAGAIN) {
            std::cerr << "[ZmqServer] 接收失败: " << e.what() << "\n";
        }
        return false;
    }
}

} // namespace server
} // namespace trading

