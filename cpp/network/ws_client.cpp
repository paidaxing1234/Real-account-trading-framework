/**
 * @file ws_client.cpp
 * @brief 公共 WebSocket 客户端实现
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
        : config_(config), is_connected_(false), stopped_(false) {
        client_.clear_access_channels(websocketpp::log::alevel::all);
        client_.set_access_channels(websocketpp::log::alevel::connect);
        client_.set_access_channels(websocketpp::log::alevel::disconnect);

        client_.init_asio();

        // 设置 TLS 初始化回调
        client_.set_tls_init_handler([this](websocketpp::connection_hdl) {
            return create_ssl_context();
        });

        if (config_.use_proxy) {
            std::cout << "[WebSocketClient] 默认使用 HTTP 代理: "
                      << config_.proxy_host << ":" << config_.proxy_port << std::endl;
        }
    }

    ~Impl() {
        safe_stop();
    }

    SslContextPtr create_ssl_context() {
#ifdef ASIO_STANDALONE
        SslContextPtr ctx = std::make_shared<asio::ssl::context>(
            asio::ssl::context::tlsv12_client);
        ctx->set_default_verify_paths();
        if (config_.verify_ssl) {
            ctx->set_verify_mode(asio::ssl::verify_peer);
        } else {
            ctx->set_verify_mode(asio::ssl::verify_none);
        }
#else
        SslContextPtr ctx = std::make_shared<boost::asio::ssl::context>(
            boost::asio::ssl::context::tlsv12_client);
        ctx->set_default_verify_paths();
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
        // 清理旧连接
        if (io_thread_) {
            clear_callbacks();
            try { client_.stop(); } catch (...) {}
            if (io_thread_->joinable()) {
                io_thread_->join();
            }
            io_thread_.reset();
            connection_ = nullptr;

            try {
                client_.reset();
            } catch (const std::exception& e) {
                std::cerr << "[WebSocketClient] ASIO 重置失败: " << e.what() << std::endl;
                return false;
            }

            client_.set_tls_init_handler([this](websocketpp::connection_hdl) {
                return create_ssl_context();
            });
        }

        websocketpp::lib::error_code ec;
        connection_ = client_.get_connection(url, ec);

        if (ec) {
            std::cerr << "[WebSocketClient] 连接错误: " << ec.message() << std::endl;
            return false;
        }

        // 设置代理
        if (config_.use_proxy) {
            std::string proxy_uri = "http://" + config_.proxy_host + ":" + std::to_string(config_.proxy_port);
            connection_->set_proxy(proxy_uri);
        }

        // 设置消息回调
        connection_->set_message_handler(
            [this](websocketpp::connection_hdl, WsClient::message_ptr msg) {
                if (message_callback_) {
                    message_callback_(msg->get_payload());
                }
            });

        // 设置打开回调
        connection_->set_open_handler([this](websocketpp::connection_hdl) {
            {
                std::lock_guard<std::mutex> lock(connect_mutex_);
                is_connected_ = true;
            }
            connect_cv_.notify_one();
            std::cout << "[WebSocketClient] 连接成功" << std::endl;
        });

        // 设置关闭回调
        connection_->set_close_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cout << "[WebSocketClient] 连接已关闭" << std::endl;
            if (close_callback_) {
                close_callback_();
            }
        });

        // 设置失败回调
        connection_->set_fail_handler([this](websocketpp::connection_hdl) {
            {
                std::lock_guard<std::mutex> lock(connect_mutex_);
                is_connected_ = false;
            }
            connect_cv_.notify_one();
            std::cerr << "[WebSocketClient] 连接失败" << std::endl;
            if (fail_callback_) {
                fail_callback_();
            }
        });

        client_.connect(connection_);

        // 启动 IO 线程
        io_thread_ = std::make_unique<std::thread>([this]() {
            client_.run();
        });

        // 等待连接完成
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

        return is_connected_;
    }

    void disconnect() {
        if (connection_) {
            websocketpp::lib::error_code ec;
            client_.close(connection_->get_handle(), websocketpp::close::status::normal, "", ec);
            connection_ = nullptr;
        }

        client_.stop();

        if (io_thread_ && io_thread_->joinable()) {
            io_thread_->join();
            io_thread_.reset();
        }

        is_connected_ = false;
    }

    bool send(const std::string& message) {
        if (!is_connected_) return false;

        websocketpp::lib::error_code ec;
        client_.send(connection_->get_handle(), message, websocketpp::frame::opcode::text, ec);

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
            return;  // 已经停止过了
        }

        clear_callbacks();
        try { client_.stop(); } catch (...) {}
        if (io_thread_ && io_thread_->joinable()) {
            io_thread_->join();
            io_thread_.reset();
        }
        connection_ = nullptr;
        is_connected_ = false;
    }

    bool is_connected() const { return is_connected_; }

    const WebSocketConfig& get_config() const { return config_; }

private:
    WebSocketConfig config_;
    WsClient client_;
    WsClient::connection_ptr connection_;
    std::unique_ptr<std::thread> io_thread_;
    std::atomic<bool> is_connected_;
    std::atomic<bool> stopped_;  // 防止 safe_stop 被多次调用

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