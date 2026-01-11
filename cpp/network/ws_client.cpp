/**
 * @file ws_client.cpp
 * @brief 公共 WebSocket 客户端实现
 *
 * 核心修复：每次重连都销毁旧的 WsClient 实例，创建全新实例
 * 避免 ASIO + SSL 的内存问题（stream truncated 导致的 double-free）
 *
 * @author Sequence Team
 * @date 2024-12
 */

#include "ws_client.h"
#include <iostream>
#include <thread>
#include <atomic>
#include <mutex>
#include <condition_variable>

#ifdef USE_WEBSOCKETPP

#ifdef ASIO_STANDALONE
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>
namespace asio = ::asio;
typedef websocketpp::client<websocketpp::config::asio_tls_client> WsClient;
typedef std::shared_ptr<asio::ssl::context> SslContextPtr;
#else
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>
typedef websocketpp::client<websocketpp::config::asio_tls_client> WsClient;
typedef websocketpp::lib::shared_ptr<websocketpp::lib::asio::ssl::context> SslContextPtr;
#endif

namespace trading {
namespace core {

class WebSocketClient::Impl {
public:
    explicit Impl(const WebSocketConfig& config)
        : config_(config), is_connected_(false), stopped_(true), ping_running_(false) {
        // 构造时不初始化 client，延迟到 connect 时初始化
        if (config_.use_proxy) {
            std::cout << "[WebSocketClient] 默认使用 HTTP 代理: "
                      << config_.proxy_host << ":" << config_.proxy_port << std::endl;
        }
    }

    ~Impl() {
        safe_stop();
    }

    // 初始化全新的 Client 实例
    void init_client_instance() {
        // 1. 创建新实例
        client_ptr_ = std::make_unique<WsClient>();

        // 2. 配置日志级别 (静默模式，防止日志刷屏)
        client_ptr_->clear_access_channels(websocketpp::log::alevel::all);
        client_ptr_->clear_error_channels(websocketpp::log::elevel::all);
        client_ptr_->set_access_channels(websocketpp::log::alevel::connect);
        client_ptr_->set_access_channels(websocketpp::log::alevel::disconnect);

        // 3. 初始化 ASIO
        client_ptr_->init_asio();

        // 4. 设置 SSL/TLS 上下文
        client_ptr_->set_tls_init_handler([this](websocketpp::connection_hdl) {
            return create_ssl_context();
        });
    }

    SslContextPtr create_ssl_context() {
#ifdef ASIO_STANDALONE
        SslContextPtr ctx = std::make_shared<asio::ssl::context>(
            asio::ssl::context::tlsv12_client);
        ctx->set_default_verify_paths();
        ctx->set_options(asio::ssl::context::default_workarounds |
                         asio::ssl::context::no_sslv2 |
                         asio::ssl::context::no_sslv3 |
                         asio::ssl::context::single_dh_use);
        if (config_.verify_ssl) {
            ctx->set_verify_mode(asio::ssl::verify_peer);
        } else {
            ctx->set_verify_mode(asio::ssl::verify_none);
        }
#else
        SslContextPtr ctx = std::make_shared<boost::asio::ssl::context>(
            boost::asio::ssl::context::tlsv12_client);
        ctx->set_default_verify_paths();
        ctx->set_options(boost::asio::ssl::context::default_workarounds |
                         boost::asio::ssl::context::no_sslv2 |
                         boost::asio::ssl::context::no_sslv3 |
                         boost::asio::ssl::context::single_dh_use);
        if (config_.verify_ssl) {
            ctx->set_verify_mode(boost::asio::ssl::verify_peer);
        } else {
            ctx->set_verify_mode(boost::asio::ssl::verify_none);
        }
#endif
        return ctx;
    }

    void set_proxy(const std::string& host, uint16_t port) {
        config_.proxy_host = host;
        config_.proxy_port = port;
        config_.use_proxy = true;
    }

    bool connect(const std::string& url) {
        // 1. 完全停止并清理旧环境
        safe_stop();
        stopped_.store(false);

        // 2. 初始化全新的 Client 对象 (核心修复：避免复用旧的 ASIO 上下文)
        try {
            init_client_instance();
        } catch (const std::exception& e) {
            std::cerr << "[WebSocketClient] Init Failed: " << e.what() << std::endl;
            return false;
        }

        // 3. 创建连接
        websocketpp::lib::error_code ec;
        WsClient::connection_ptr new_con = client_ptr_->get_connection(url, ec);

        if (ec) {
            std::cerr << "[WebSocketClient] 连接错误: " << ec.message() << std::endl;
            return false;
        }

        // 保存连接指针
        {
            std::lock_guard<std::mutex> lock(connection_mutex_);
            connection_ = new_con;
        }

        // 设置代理
        if (config_.use_proxy) {
            std::string proxy_uri = "http://" + config_.proxy_host + ":" + std::to_string(config_.proxy_port);
            new_con->set_proxy(proxy_uri);
        }

        // 设置消息回调
        new_con->set_message_handler(
            [this](websocketpp::connection_hdl, WsClient::message_ptr msg) {
                if (message_callback_) {
                    try {
                        message_callback_(msg->get_payload());
                    } catch (const std::exception& e) {
                        std::cerr << "[WebSocketClient] Message Callback Error: " << e.what() << std::endl;
                    }
                }
            });

        // 设置打开回调
        new_con->set_open_handler([this](websocketpp::connection_hdl) {
            {
                std::lock_guard<std::mutex> lock(connect_mutex_);
                is_connected_ = true;
            }
            connect_cv_.notify_one();
            std::cout << "[WebSocketClient] 连接成功" << std::endl;
        });

        // 设置关闭回调
        new_con->set_close_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cout << "[WebSocketClient] 连接已关闭" << std::endl;

            // 清理连接指针
            {
                std::lock_guard<std::mutex> lock(connection_mutex_);
                connection_.reset();
            }

            if (close_callback_) {
                close_callback_();
            }
        });

        // 设置失败回调
        new_con->set_fail_handler([this](websocketpp::connection_hdl) {
            {
                std::lock_guard<std::mutex> lock(connect_mutex_);
                is_connected_ = false;
            }
            connect_cv_.notify_one();
            std::cerr << "[WebSocketClient] 连接失败" << std::endl;

            // 清理连接指针
            {
                std::lock_guard<std::mutex> lock(connection_mutex_);
                connection_.reset();
            }

            if (fail_callback_) {
                fail_callback_();
            }
        });

        // 4. 发起连接
        try {
            client_ptr_->connect(new_con);
        } catch (const std::exception& e) {
            std::cerr << "[WebSocketClient] Connect Call Failed: " << e.what() << std::endl;
            return false;
        }

        // 5. 启动 IO 线程
        io_thread_ = std::make_unique<std::thread>([this]() {
            try {
                client_ptr_->run();
            } catch (const std::exception& e) {
                std::cerr << "[WebSocketClient] IO Loop Exception: " << e.what() << std::endl;
            } catch (...) {
                std::cerr << "[WebSocketClient] IO Loop Unknown Crash" << std::endl;
            }
            // 线程退出时，确保 connected 状态为 false
            is_connected_.store(false);
        });

        // 6. 等待连接完成
        {
            std::unique_lock<std::mutex> lock(connect_mutex_);
            bool connected = connect_cv_.wait_for(
                lock,
                std::chrono::seconds(config_.connect_timeout_sec),
                [this]() { return is_connected_.load(); }
            );
            if (!connected) {
                std::cerr << "[WebSocketClient] 连接超时" << std::endl;
            }
        }

        // 7. 连接成功后启动 ping 线程
        if (is_connected_ && config_.ping_interval_sec > 0) {
            start_ping_thread();
        }

        return is_connected_;
    }

    void disconnect() {
        safe_stop();
    }

    bool send(const std::string& message) {
        if (!is_connected_.load()) return false;

        // 加锁获取连接指针的副本，防止多线程竞争
        WsClient::connection_ptr con_copy;
        {
            std::lock_guard<std::mutex> lock(connection_mutex_);
            con_copy = connection_;
        }

        if (!con_copy || !client_ptr_) return false;

        websocketpp::lib::error_code ec;
        try {
            client_ptr_->send(con_copy->get_handle(), message, websocketpp::frame::opcode::text, ec);
        } catch (const std::exception& e) {
            std::cerr << "[WebSocketClient] 发送异常: " << e.what() << std::endl;
            return false;
        }

        if (ec) {
            std::cerr << "[WebSocketClient] 发送错误: " << ec.message() << std::endl;
            return false;
        }
        return true;
    }

    void set_message_callback(std::function<void(const std::string&)> callback) {
        message_callback_ = std::move(callback);
    }

    void set_close_callback(std::function<void()> callback) {
        close_callback_ = std::move(callback);
    }

    void set_fail_callback(std::function<void()> callback) {
        fail_callback_ = std::move(callback);
    }

    void clear_callbacks() {
        message_callback_ = nullptr;
        close_callback_ = nullptr;
        fail_callback_ = nullptr;
    }

    void safe_stop() {
        // 确保只执行一次
        bool expected = false;
        if (!stopped_.compare_exchange_strong(expected, true)) {
            // 如果已经停止过，只需要等待线程退出
            if (io_thread_ && io_thread_->joinable()) {
                io_thread_->join();
                io_thread_.reset();
            }
            return;
        }

        // 1. 先停止 ping 线程
        stop_ping_thread();

        // 2. 关闭 WebSocket 连接
        {
            std::lock_guard<std::mutex> lock(connection_mutex_);
            if (connection_ && is_connected_.load() && client_ptr_) {
                websocketpp::lib::error_code ec;
                try {
                    client_ptr_->close(connection_->get_handle(),
                                       websocketpp::close::status::normal,
                                       "shutdown", ec);
                } catch (...) {}
            }
            connection_.reset();
        }
        is_connected_.store(false);

        // 3. 停止 ASIO 循环
        if (client_ptr_) {
            try {
                client_ptr_->stop();
            } catch (...) {}
        }

        // 4. 等待 IO 线程结束（必须先 join 再 reset）
        if (io_thread_ && io_thread_->joinable()) {
            io_thread_->join();
        }
        io_thread_.reset();

        // 5. 彻底销毁 Client 实例 (关键!)
        // 这会触发所有底层 SSL Context 和 socket 的析构
        client_ptr_.reset();
    }

    bool is_connected() const { return is_connected_; }

    const WebSocketConfig& get_config() const { return config_; }

private:
    void start_ping_thread() {
        if (ping_running_.load()) return;

        ping_running_.store(true);
        ping_thread_ = std::make_unique<std::thread>([this]() {
            while (ping_running_.load() && is_connected_.load()) {
                // 使用小间隔循环，以便能快速响应停止请求
                for (int i = 0; i < config_.ping_interval_sec * 10 && ping_running_.load(); ++i) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
                }

                if (!ping_running_.load() || !is_connected_.load()) break;

                // 发送 WebSocket ping frame（使用互斥锁保护 connection_）
                WsClient::connection_ptr con_copy;
                {
                    std::lock_guard<std::mutex> lock(connection_mutex_);
                    con_copy = connection_;
                }

                if (con_copy && client_ptr_) {
                    try {
                        websocketpp::lib::error_code ec;
                        client_ptr_->ping(con_copy->get_handle(), "keepalive", ec);
                        if (ec) {
                            std::cerr << "[WebSocketClient] Ping 发送失败: " << ec.message() << std::endl;
                        }
                    } catch (const std::exception& e) {
                        std::cerr << "[WebSocketClient] Ping 异常: " << e.what() << std::endl;
                    }
                }
            }
        });
    }

    void stop_ping_thread() {
        ping_running_.store(false);
        if (ping_thread_ && ping_thread_->joinable()) {
            ping_thread_->join();
            ping_thread_.reset();
        }
    }

    WebSocketConfig config_;

    // 使用 unique_ptr 管理 Client，每次重连都创建新实例
    std::unique_ptr<WsClient> client_ptr_;

    // 连接句柄
    WsClient::connection_ptr connection_;
    mutable std::mutex connection_mutex_;  // 保护 connection_ 指针

    std::unique_ptr<std::thread> io_thread_;
    std::unique_ptr<std::thread> ping_thread_;

    std::atomic<bool> is_connected_;
    std::atomic<bool> stopped_;
    std::atomic<bool> ping_running_;

    std::function<void(const std::string&)> message_callback_;
    std::function<void()> close_callback_;
    std::function<void()> fail_callback_;

    std::mutex connect_mutex_;
    std::condition_variable connect_cv_;
};

// WebSocketClient 公共接口实现
WebSocketClient::WebSocketClient(const WebSocketConfig& config)
    : impl_(std::make_unique<Impl>(config)) {}

WebSocketClient::~WebSocketClient() = default;

bool WebSocketClient::connect(const std::string& url) {
    return impl_->connect(url);
}

void WebSocketClient::disconnect() {
    impl_->disconnect();
}

bool WebSocketClient::send(const std::string& message) {
    return impl_->send(message);
}

bool WebSocketClient::is_connected() const {
    return impl_->is_connected();
}

void WebSocketClient::set_message_callback(std::function<void(const std::string&)> callback) {
    impl_->set_message_callback(std::move(callback));
}

void WebSocketClient::set_close_callback(std::function<void()> callback) {
    impl_->set_close_callback(std::move(callback));
}

void WebSocketClient::set_fail_callback(std::function<void()> callback) {
    impl_->set_fail_callback(std::move(callback));
}

void WebSocketClient::safe_stop() {
    impl_->safe_stop();
}

void WebSocketClient::clear_callbacks() {
    impl_->clear_callbacks();
}

void WebSocketClient::set_proxy(const std::string& host, uint16_t port) {
    impl_->set_proxy(host, port);
}

const WebSocketConfig& WebSocketClient::get_config() const {
    return impl_->get_config();
}

} // namespace core
} // namespace trading

#else
// WebSocket++ 未启用时编译错误
#error "USE_WEBSOCKETPP must be defined to use WebSocketClient"
#endif
