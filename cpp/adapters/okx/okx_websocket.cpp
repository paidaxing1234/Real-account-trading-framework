/**
 * @file okx_websocket.cpp
 * @brief OKX WebSocket 客户端实现
 * 
 * 使用 websocketpp 库实现 WebSocket 连接
 * 
 * 依赖安装:
 *   使用 standalone ASIO（推荐）:
 *     macOS: brew install websocketpp asio openssl
 *     Ubuntu: apt install libwebsocketpp-dev libasio-dev libssl-dev
 * 
 *   使用 Boost.ASIO（可能有版本兼容问题）:
 *     macOS: brew install websocketpp boost openssl
 *     Ubuntu: apt install libwebsocketpp-dev libboost-all-dev libssl-dev
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "okx_websocket.h"
#include <iostream>
#include <sstream>
#include <chrono>
#include <ctime>
#include <openssl/hmac.h>
#include <openssl/sha.h>

// WebSocket++ 头文件
#ifdef USE_WEBSOCKETPP

// 使用 standalone ASIO 时需要特殊配置
#ifdef ASIO_STANDALONE
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>

// standalone ASIO 使用不同的命名空间
namespace asio = ::asio;
typedef websocketpp::client<websocketpp::config::asio_tls_client> WsClient;
typedef std::shared_ptr<asio::ssl::context> SslContextPtr;

#else
// 使用 Boost.ASIO
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>

typedef websocketpp::client<websocketpp::config::asio_tls_client> WsClient;
typedef websocketpp::lib::shared_ptr<websocketpp::lib::asio::ssl::context> SslContextPtr;
#endif

#endif // USE_WEBSOCKETPP

namespace trading {
namespace okx {

// ==================== Base64编码辅助函数 ====================

static std::string base64_encode(const unsigned char* buffer, size_t length) {
    static const char base64_chars[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/";
    
    std::string result;
    int i = 0;
    int j = 0;
    unsigned char char_array_3[3];
    unsigned char char_array_4[4];
    
    while (length--) {
        char_array_3[i++] = *(buffer++);
        if (i == 3) {
            char_array_4[0] = (char_array_3[0] & 0xfc) >> 2;
            char_array_4[1] = ((char_array_3[0] & 0x03) << 4) + ((char_array_3[1] & 0xf0) >> 4);
            char_array_4[2] = ((char_array_3[1] & 0x0f) << 2) + ((char_array_3[2] & 0xc0) >> 6);
            char_array_4[3] = char_array_3[2] & 0x3f;
            
            for(i = 0; i < 4; i++)
                result += base64_chars[char_array_4[i]];
            i = 0;
        }
    }
    
    if (i) {
        for(j = i; j < 3; j++)
            char_array_3[j] = '\0';
        
        char_array_4[0] = (char_array_3[0] & 0xfc) >> 2;
        char_array_4[1] = ((char_array_3[0] & 0x03) << 4) + ((char_array_3[1] & 0xf0) >> 4);
        char_array_4[2] = ((char_array_3[1] & 0x0f) << 2) + ((char_array_3[2] & 0xc0) >> 6);
        
        for (j = 0; j < i + 1; j++)
            result += base64_chars[char_array_4[j]];
        
        while(i++ < 3)
            result += '=';
    }
    
    return result;
}

// ==================== WebSocket实现类 ====================

#ifdef USE_WEBSOCKETPP
/**
 * @brief WebSocket实现类（使用WebSocket++）
 */
class OKXWebSocket::Impl {
public:
    Impl() : is_connected_(false), proxy_host_("127.0.0.1"), proxy_port_(7890), use_proxy_(true) {
        // 初始化WebSocket++
        client_.clear_access_channels(websocketpp::log::alevel::all);
        client_.set_access_channels(websocketpp::log::alevel::connect);
        client_.set_access_channels(websocketpp::log::alevel::disconnect);
        
        client_.init_asio();
        
        // 设置TLS初始化回调
        client_.set_tls_init_handler([](websocketpp::connection_hdl) {
#ifdef ASIO_STANDALONE
            // 使用 standalone ASIO
            SslContextPtr ctx = std::make_shared<asio::ssl::context>(
                asio::ssl::context::tlsv12_client);
            ctx->set_default_verify_paths();
            ctx->set_verify_mode(asio::ssl::verify_none);
#else
            // 使用 Boost.ASIO
            SslContextPtr ctx = std::make_shared<boost::asio::ssl::context>(
                boost::asio::ssl::context::tlsv12_client);
            ctx->set_default_verify_paths();
            ctx->set_verify_mode(boost::asio::ssl::verify_none);
#endif
            return ctx;
        });
        
        std::cout << "[WebSocket] 默认使用 HTTP 代理: " << proxy_host_ << ":" << proxy_port_ << std::endl;
    }
    
    // 设置代理（可通过环境变量或硬编码）
    void set_proxy(const std::string& proxy_host, uint16_t proxy_port) {
        proxy_host_ = proxy_host;
        proxy_port_ = proxy_port;
        use_proxy_ = true;
        std::cout << "[WebSocket] 使用 HTTP 代理: " << proxy_host << ":" << proxy_port << std::endl;
    }
    
    bool connect(const std::string& url) {
        websocketpp::lib::error_code ec;
        connection_ = client_.get_connection(url, ec);
        
        if (ec) {
            std::cerr << "[WebSocket] 连接错误: " << ec.message() << std::endl;
            return false;
        }
        
        // 设置 HTTP 代理
        if (use_proxy_) {
            std::string proxy_uri = "http://" + proxy_host_ + ":" + std::to_string(proxy_port_);
            connection_->set_proxy(proxy_uri);
            std::cout << "[WebSocket] 代理已配置: " << proxy_uri << std::endl;
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
            is_connected_ = true;
            std::cout << "[WebSocket] ✅ 连接成功" << std::endl;
        });
        
        // 设置关闭回调
        connection_->set_close_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cout << "[WebSocket] 连接已关闭" << std::endl;
        });
        
        // 设置失败回调
        connection_->set_fail_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cerr << "[WebSocket] ❌ 连接失败" << std::endl;
        });
        
        client_.connect(connection_);
        
        // 启动IO线程
        io_thread_ = std::make_unique<std::thread>([this]() {
            client_.run();
        });
        
        // 等待连接
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        return is_connected_;
    }
    
    void disconnect() {
        if (connection_) {
            websocketpp::lib::error_code ec;
            client_.close(connection_->get_handle(), websocketpp::close::status::normal, "", ec);
        }
        
        client_.stop();
        
        if (io_thread_ && io_thread_->joinable()) {
            io_thread_->join();
        }
        
        is_connected_ = false;
    }
    
    bool send(const std::string& message) {
        if (!is_connected_) return false;
        
        websocketpp::lib::error_code ec;
        client_.send(connection_->get_handle(), message, websocketpp::frame::opcode::text, ec);
        
        if (ec) {
            std::cerr << "[WebSocket] 发送错误: " << ec.message() << std::endl;
            return false;
        }
        return true;
    }
    
    void set_message_callback(std::function<void(const std::string&)> callback) {
        message_callback_ = std::move(callback);
    }
    
    bool is_connected() const { return is_connected_; }

private:
    WsClient client_;
    WsClient::connection_ptr connection_;
    std::unique_ptr<std::thread> io_thread_;
    std::atomic<bool> is_connected_;
    std::function<void(const std::string&)> message_callback_;
    
    // 代理设置
    std::string proxy_host_ = "127.0.0.1";
    uint16_t proxy_port_ = 7890;
    bool use_proxy_ = true;  // 默认启用代理
};

#else
/**
 * @brief WebSocket占位实现（未启用WebSocket++时使用）
 * 
 * 当USE_WEBSOCKETPP未定义时，使用此占位实现
 * 实际功能需要安装websocketpp依赖后启用
 */
class OKXWebSocket::Impl {
public:
    Impl() = default;
    
    void set_proxy(const std::string& proxy_host, uint16_t proxy_port) {
        std::cout << "[WebSocket] 代理配置（占位）: " << proxy_host << ":" << proxy_port << std::endl;
    }
    
    bool connect(const std::string& url) {
        std::cout << "[WebSocket] ⚠️ WebSocket++ 未启用" << std::endl;
        std::cout << "[WebSocket] 请安装 websocketpp 并在 CMakeLists.txt 中启用 USE_WEBSOCKETPP" << std::endl;
        std::cout << "[WebSocket] URL: " << url << std::endl;
        
        // 模拟连接成功，用于测试接口
        is_connected_ = true;
        return true;
    }
    
    void disconnect() {
        is_connected_ = false;
        std::cout << "[WebSocket] 断开连接" << std::endl;
    }
    
    bool send(const std::string& message) {
        if (!is_connected_) return false;
        std::cout << "[WebSocket] 发送消息: " << message << std::endl;
        return true;
    }
    
    void set_message_callback(std::function<void(const std::string&)> callback) {
        message_callback_ = std::move(callback);
    }
    
    bool is_connected() const { return is_connected_; }
    
    // 模拟接收消息（用于测试）
    void simulate_message(const std::string& msg) {
        if (message_callback_) {
            message_callback_(msg);
        }
    }

private:
    std::atomic<bool> is_connected_{false};
    std::function<void(const std::string&)> message_callback_;
};
#endif

// ==================== OKXWebSocket 实现 ====================

OKXWebSocket::OKXWebSocket(
    const std::string& api_key,
    const std::string& secret_key,
    const std::string& passphrase,
    bool is_testnet,
    WsEndpointType endpoint_type
)
    : api_key_(api_key)
    , secret_key_(secret_key)
    , passphrase_(passphrase)
    , is_testnet_(is_testnet)
    , endpoint_type_(endpoint_type)
    , impl_(std::make_unique<Impl>())
{
    ws_url_ = build_ws_url();
}

OKXWebSocket::~OKXWebSocket() {
    disconnect();
}

std::string OKXWebSocket::build_ws_url() const {
    std::string base = is_testnet_ ? "wss://wspap.okx.com:8443" : "wss://ws.okx.com:8443";
    
    switch (endpoint_type_) {
        case WsEndpointType::PUBLIC:
            return base + "/ws/v5/public";
        case WsEndpointType::BUSINESS:
            return base + "/ws/v5/business";
        case WsEndpointType::PRIVATE:
            return base + "/ws/v5/private";
        default:
            return base + "/ws/v5/public";
    }
}

bool OKXWebSocket::connect() {
    if (is_connected_.load()) {
        std::cout << "[WebSocket] 已经连接" << std::endl;
        return true;
    }
    
    std::cout << "[WebSocket] 连接到: " << ws_url_ << std::endl;
    
    // 设置消息回调
    impl_->set_message_callback([this](const std::string& msg) {
        on_message(msg);
    });
    
    bool success = impl_->connect(ws_url_);
    is_connected_.store(success);
    is_running_.store(success);
    
    if (success) {
        // 启动心跳线程
        heartbeat_thread_ = std::make_unique<std::thread>([this]() {
            while (is_running_.load()) {
                std::this_thread::sleep_for(std::chrono::seconds(25));
                if (is_connected_.load()) {
                    send_ping();
                }
            }
        });
    }
    
    return success;
}

void OKXWebSocket::disconnect() {
    is_running_.store(false);
    is_connected_.store(false);
    
    if (heartbeat_thread_ && heartbeat_thread_->joinable()) {
        heartbeat_thread_->join();
    }
    
    if (impl_) {
        impl_->disconnect();
    }
    
    std::cout << "[WebSocket] 已断开连接" << std::endl;
}

void OKXWebSocket::login() {
    if (api_key_.empty() || secret_key_.empty() || passphrase_.empty()) {
        std::cerr << "[WebSocket] 登录需要提供 api_key, secret_key, passphrase" << std::endl;
        return;
    }
    
    std::string timestamp = get_timestamp();
    std::string sign = create_signature(timestamp);
    
    nlohmann::json login_msg = {
        {"op", "login"},
        {"args", {{
            {"apiKey", api_key_},
            {"passphrase", passphrase_},
            {"timestamp", timestamp},
            {"sign", sign}
        }}}
    };
    
    std::cout << "[WebSocket] 发送登录请求..." << std::endl;
    send_message(login_msg);
}

std::string OKXWebSocket::get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto seconds = std::chrono::duration_cast<std::chrono::seconds>(
        now.time_since_epoch()
    ).count();
    return std::to_string(seconds);
}

std::string OKXWebSocket::create_signature(const std::string& timestamp) {
    std::string message = timestamp + "GET" + "/users/self/verify";
    
    unsigned char hash[SHA256_DIGEST_LENGTH];
    HMAC(
        EVP_sha256(),
        secret_key_.c_str(),
        secret_key_.length(),
        (unsigned char*)message.c_str(),
        message.length(),
        hash,
        nullptr
    );
    
    return base64_encode(hash, SHA256_DIGEST_LENGTH);
}

bool OKXWebSocket::send_message(const nlohmann::json& msg) {
    if (!is_connected_.load()) return false;
    return impl_->send(msg.dump());
}

void OKXWebSocket::send_ping() {
    impl_->send("ping");
}

// ==================== 订阅方法 ====================

void OKXWebSocket::send_subscribe(const std::string& channel, const std::string& inst_id,
                                  const std::string& extra_key, const std::string& extra_value) {
    nlohmann::json arg = {{"channel", channel}};
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!extra_key.empty() && !extra_value.empty()) {
        arg[extra_key] = extra_value;
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = channel + ":" + inst_id;
        subscriptions_[key] = inst_id;
    }
}

void OKXWebSocket::send_unsubscribe(const std::string& channel, const std::string& inst_id,
                                    const std::string& extra_key, const std::string& extra_value) {
    nlohmann::json arg = {{"channel", channel}};
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!extra_key.empty() && !extra_value.empty()) {
        arg[extra_key] = extra_value;
    }
    
    nlohmann::json msg = {
        {"op", "unsubscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 取消订阅: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = channel + ":" + inst_id;
        subscriptions_.erase(key);
    }
}

// 公共频道
void OKXWebSocket::subscribe_ticker(const std::string& inst_id) {
    send_subscribe("tickers", inst_id);
}

void OKXWebSocket::unsubscribe_ticker(const std::string& inst_id) {
    send_unsubscribe("tickers", inst_id);
}

void OKXWebSocket::subscribe_trades(const std::string& inst_id) {
    send_subscribe("trades", inst_id);
}

void OKXWebSocket::unsubscribe_trades(const std::string& inst_id) {
    send_unsubscribe("trades", inst_id);
}

void OKXWebSocket::subscribe_orderbook(const std::string& inst_id, const std::string& channel) {
    send_subscribe(channel, inst_id);
}

void OKXWebSocket::unsubscribe_orderbook(const std::string& inst_id, const std::string& channel) {
    send_unsubscribe(channel, inst_id);
}

// K线频道
void OKXWebSocket::subscribe_kline(const std::string& inst_id, KlineInterval interval) {
    std::string channel = kline_interval_to_channel(interval);
    send_subscribe(channel, inst_id);
}

void OKXWebSocket::subscribe_kline(const std::string& inst_id, const std::string& bar) {
    KlineInterval interval = string_to_kline_interval(bar);
    subscribe_kline(inst_id, interval);
}

void OKXWebSocket::unsubscribe_kline(const std::string& inst_id, KlineInterval interval) {
    std::string channel = kline_interval_to_channel(interval);
    send_unsubscribe(channel, inst_id);
}

void OKXWebSocket::unsubscribe_kline(const std::string& inst_id, const std::string& bar) {
    KlineInterval interval = string_to_kline_interval(bar);
    unsubscribe_kline(inst_id, interval);
}

void OKXWebSocket::subscribe_trades_all(const std::string& inst_id) {
    send_subscribe("trades-all", inst_id);
}

void OKXWebSocket::unsubscribe_trades_all(const std::string& inst_id) {
    send_unsubscribe("trades-all", inst_id);
}

// 持仓总量频道
void OKXWebSocket::subscribe_open_interest(const std::string& inst_id) {
    send_subscribe("open-interest", inst_id);
}

void OKXWebSocket::unsubscribe_open_interest(const std::string& inst_id) {
    send_unsubscribe("open-interest", inst_id);
}

// 标记价格频道
void OKXWebSocket::subscribe_mark_price(const std::string& inst_id) {
    send_subscribe("mark-price", inst_id);
}

void OKXWebSocket::unsubscribe_mark_price(const std::string& inst_id) {
    send_unsubscribe("mark-price", inst_id);
}

// ==================== 私有频道 ====================

void OKXWebSocket::subscribe_orders(
    const std::string& inst_type,
    const std::string& inst_id,
    const std::string& inst_family
) {
    nlohmann::json arg = {
        {"channel", "orders"},
        {"instType", inst_type}
    };
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!inst_family.empty()) {
        arg["instFamily"] = inst_family;
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅订单频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "orders:" + inst_type;
        if (!inst_id.empty()) key += ":" + inst_id;
        subscriptions_[key] = inst_type;
    }
}

void OKXWebSocket::unsubscribe_orders(
    const std::string& inst_type,
    const std::string& inst_id,
    const std::string& inst_family
) {
    nlohmann::json arg = {
        {"channel", "orders"},
        {"instType", inst_type}
    };
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!inst_family.empty()) {
        arg["instFamily"] = inst_family;
    }
    
    nlohmann::json msg = {
        {"op", "unsubscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 取消订阅订单频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "orders:" + inst_type;
        if (!inst_id.empty()) key += ":" + inst_id;
        subscriptions_.erase(key);
    }
}

void OKXWebSocket::subscribe_positions(
    const std::string& inst_type,
    const std::string& inst_id,
    const std::string& inst_family,
    int update_interval
) {
    nlohmann::json arg = {
        {"channel", "positions"},
        {"instType", inst_type}
    };
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!inst_family.empty()) {
        arg["instFamily"] = inst_family;
    }
    
    // 如果指定了 update_interval，添加 extraParams
    if (update_interval >= 0) {
        nlohmann::json extra_params = {
            {"updateInterval", std::to_string(update_interval)}
        };
        arg["extraParams"] = extra_params.dump();
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅持仓频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "positions:" + inst_type;
        if (!inst_id.empty()) key += ":" + inst_id;
        if (!inst_family.empty()) key += ":" + inst_family;
        subscriptions_[key] = inst_type;
    }
}

void OKXWebSocket::unsubscribe_positions(
    const std::string& inst_type,
    const std::string& inst_id,
    const std::string& inst_family
) {
    nlohmann::json arg = {
        {"channel", "positions"},
        {"instType", inst_type}
    };
    
    if (!inst_id.empty()) {
        arg["instId"] = inst_id;
    }
    if (!inst_family.empty()) {
        arg["instFamily"] = inst_family;
    }
    
    nlohmann::json msg = {
        {"op", "unsubscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 取消订阅持仓频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "positions:" + inst_type;
        if (!inst_id.empty()) key += ":" + inst_id;
        subscriptions_.erase(key);
    }
}

void OKXWebSocket::subscribe_account(const std::string& ccy, int update_interval) {
    nlohmann::json arg = {
        {"channel", "account"}
    };
    
    if (!ccy.empty()) {
        arg["ccy"] = ccy;
    }
    
    // 如果指定了 update_interval，添加 extraParams
    if (update_interval == 0) {
        nlohmann::json extra_params = {
            {"updateInterval", "0"}
        };
        arg["extraParams"] = extra_params.dump();
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅账户频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "account";
        if (!ccy.empty()) key += ":" + ccy;
        subscriptions_[key] = ccy.empty() ? "all" : ccy;
    }
}

void OKXWebSocket::unsubscribe_account(const std::string& ccy) {
    if (ccy.empty()) {
        nlohmann::json msg = {
            {"op", "unsubscribe"},
            {"args", {{{"channel", "account"}}}}
        };
        send_message(msg);
    } else {
        send_unsubscribe("account", "", "ccy", ccy);
    }
}

// Spread订单频道
void OKXWebSocket::subscribe_sprd_orders(const std::string& sprd_id) {
    nlohmann::json arg = {
        {"channel", "sprd-orders"}
    };
    
    if (!sprd_id.empty()) {
        arg["sprdId"] = sprd_id;
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅Spread订单频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "sprd-orders";
        if (!sprd_id.empty()) key += ":" + sprd_id;
        subscriptions_[key] = sprd_id.empty() ? "all" : sprd_id;
    }
}

void OKXWebSocket::unsubscribe_sprd_orders(const std::string& sprd_id) {
    nlohmann::json arg = {
        {"channel", "sprd-orders"}
    };
    
    if (!sprd_id.empty()) {
        arg["sprdId"] = sprd_id;
    }
    
    nlohmann::json msg = {
        {"op", "unsubscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 取消订阅Spread订单频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "sprd-orders";
        if (!sprd_id.empty()) key += ":" + sprd_id;
        subscriptions_.erase(key);
    }
}

// Spread成交数据频道
void OKXWebSocket::subscribe_sprd_trades(const std::string& sprd_id) {
    nlohmann::json arg = {
        {"channel", "sprd-trades"}
    };
    
    if (!sprd_id.empty()) {
        arg["sprdId"] = sprd_id;
    }
    
    nlohmann::json msg = {
        {"op", "subscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 订阅Spread成交数据频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "sprd-trades";
        if (!sprd_id.empty()) key += ":" + sprd_id;
        subscriptions_[key] = sprd_id.empty() ? "all" : sprd_id;
    }
}

void OKXWebSocket::unsubscribe_sprd_trades(const std::string& sprd_id) {
    nlohmann::json arg = {
        {"channel", "sprd-trades"}
    };
    
    if (!sprd_id.empty()) {
        arg["sprdId"] = sprd_id;
    }
    
    nlohmann::json msg = {
        {"op", "unsubscribe"},
        {"args", {arg}}
    };
    
    std::cout << "[WebSocket] 取消订阅Spread成交数据频道: " << msg.dump() << std::endl;
    
    if (send_message(msg)) {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::string key = "sprd-trades";
        if (!sprd_id.empty()) key += ":" + sprd_id;
        subscriptions_.erase(key);
    }
}

// ==================== WebSocket下单实现 ====================

std::string OKXWebSocket::place_order_ws(
    const std::string& inst_id,
    const std::string& td_mode,
    const std::string& side,
    const std::string& ord_type,
    const std::string& sz,
    const std::string& px,
    const std::string& ccy,
    const std::string& cl_ord_id,
    const std::string& tag,
    const std::string& pos_side,
    bool reduce_only,
    const std::string& tgt_ccy,
    bool ban_amend,
    const std::string& request_id
) {
    // 生成请求ID
    std::string req_id = request_id;
    if (req_id.empty()) {
        req_id = std::to_string(request_id_counter_.fetch_add(1));
    }
    
    // 构建订单参数
    nlohmann::json order_arg = {
        {"instId", inst_id},
        {"tdMode", td_mode},
        {"side", side},
        {"ordType", ord_type},
        {"sz", sz}
    };
    
    // 添加可选参数
    if (!px.empty()) {
        order_arg["px"] = px;
    }
    
    if (!ccy.empty()) {
        order_arg["ccy"] = ccy;
    }
    
    if (!cl_ord_id.empty()) {
        order_arg["clOrdId"] = cl_ord_id;
    }
    
    if (!tag.empty()) {
        order_arg["tag"] = tag;
    }
    
    if (!pos_side.empty()) {
        order_arg["posSide"] = pos_side;
    }
    
    if (reduce_only) {
        order_arg["reduceOnly"] = true;
    }
    
    if (!tgt_ccy.empty()) {
        order_arg["tgtCcy"] = tgt_ccy;
    }
    
    if (ban_amend) {
        order_arg["banAmend"] = true;
    }
    
    // 构建完整的WebSocket消息
    nlohmann::json msg = {
        {"id", req_id},
        {"op", "order"},
        {"args", {order_arg}}
    };
    
    std::cout << "[WebSocket] 发送下单请求 (ID=" << req_id << "): " << msg.dump() << std::endl;
    
    if (!send_message(msg)) {
        std::cerr << "[WebSocket] ❌ 发送下单请求失败" << std::endl;
        return "";
    }
    
    return req_id;
}

std::string OKXWebSocket::place_batch_orders_ws(
    const std::vector<nlohmann::json>& orders,
    const std::string& request_id
) {
    if (orders.empty()) {
        std::cerr << "[WebSocket] ❌ 批量下单参数为空" << std::endl;
        return "";
    }
    
    if (orders.size() > 20) {
        std::cerr << "[WebSocket] ❌ 批量下单最多支持20笔订单，当前: " << orders.size() << std::endl;
        return "";
    }
    
    // 生成请求ID
    std::string req_id = request_id;
    if (req_id.empty()) {
        req_id = std::to_string(request_id_counter_.fetch_add(1));
    }
    
    // 构建完整的WebSocket消息
    nlohmann::json msg = {
        {"id", req_id},
        {"op", "batch-orders"},
        {"args", orders}
    };
    
    std::cout << "[WebSocket] 发送批量下单请求 (ID=" << req_id << "): " 
              << orders.size() << " 笔订单" << std::endl;
    
    if (!send_message(msg)) {
        std::cerr << "[WebSocket] ❌ 发送批量下单请求失败" << std::endl;
        return "";
    }
    
    return req_id;
}

std::vector<std::string> OKXWebSocket::get_subscribed_channels() const {
    std::lock_guard<std::mutex> lock(subscriptions_mutex_);
    std::vector<std::string> result;
    for (const auto& pair : subscriptions_) {
        result.push_back(pair.first);
    }
    return result;
}

// ==================== 消息处理 ====================

void OKXWebSocket::on_message(const std::string& message) {
    // 处理pong响应
    if (message == "pong") {
        return;
    }
    
    try {
        nlohmann::json data = nlohmann::json::parse(message);
        
        // 调用原始消息回调
        if (raw_callback_) {
            raw_callback_(data);
        }
        
        // 调试：打印所有包含data字段的消息（数据推送）
        if (data.contains("data") && data.contains("arg")) {
            const auto& arg = data["arg"];
            std::string channel = arg.value("channel", "");
            std::cout << "[WebSocket] 📥 收到数据推送 - 频道: " << channel;
            if (arg.contains("instId")) {
                std::cout << ", 产品: " << arg["instId"].get<std::string>();
            }
            if (arg.contains("instType")) {
                std::cout << ", 类型: " << arg["instType"].get<std::string>();
            }
            std::cout << ", 数据条数: " << data["data"].size() << std::endl;
        }
        
        // 处理下单响应（包含id和op字段）
        if (data.contains("id") && data.contains("op")) {
            std::string op = data["op"];
            std::string id = data["id"];
            std::string code = data.value("code", "");
            std::string msg = data.value("msg", "");
            
            if (op == "order" || op == "batch-orders") {
                // 打印下单响应信息
                if (code == "0") {
                    std::cout << "[WebSocket] ✅ 下单成功 (ID=" << id << ")";
                    if (data.contains("data") && !data["data"].empty()) {
                        std::cout << ", 订单数: " << data["data"].size();
                        for (const auto& order : data["data"]) {
                            std::string ord_id = order.value("ordId", "");
                            std::string s_code = order.value("sCode", "");
                            if (!ord_id.empty()) {
                                std::cout << ", ordId=" << ord_id;
                            }
                            if (s_code != "0") {
                                std::string s_msg = order.value("sMsg", "");
                                std::cout << ", 错误: " << s_msg << " (sCode=" << s_code << ")";
                            }
                        }
                    }
                    std::cout << std::endl;
                } else {
                    std::cerr << "[WebSocket] ❌ 下单失败 (ID=" << id << "): " 
                              << msg << " (code=" << code << ")" << std::endl;
                }
                
                // 调用下单回调
                if (place_order_callback_) {
                    place_order_callback_(data);
                }
                return;
            }
        }
        
        // 处理事件消息（订阅响应/错误）
        if (data.contains("event")) {
            std::string event = data["event"];
            
            if (event == "subscribe") {
                std::cout << "[WebSocket] ✅ 订阅成功: " << data["arg"].dump() << std::endl;
            } else if (event == "unsubscribe") {
                std::cout << "[WebSocket] ✅ 取消订阅成功: " << data["arg"].dump() << std::endl;
            } else if (event == "login") {
                if (data.value("code", "") == "0") {
                    is_logged_in_.store(true);
                    std::cout << "[WebSocket] ✅ 登录成功" << std::endl;
                } else {
                    std::cerr << "[WebSocket] ❌ 登录失败: " << data.value("msg", "") << std::endl;
                }
            } else if (event == "error") {
                std::cerr << "[WebSocket] ❌ 错误: " << data.value("msg", "") 
                          << " (code: " << data.value("code", "") << ")" << std::endl;
            }
            return;
        }
        
        // 处理数据推送
        if (data.contains("arg") && data.contains("data")) {
            const auto& arg = data["arg"];
            std::string channel = arg.value("channel", "");
            std::string inst_id = arg.value("instId", "");
            
            // 调试：打印收到的频道信息
            std::cout << "[WebSocket] 收到数据推送 - 频道: " << channel;
            if (!inst_id.empty()) {
                std::cout << ", 产品: " << inst_id;
            }
            std::cout << std::endl;
            
            // 根据频道类型解析数据
            if (channel == "tickers") {
                parse_ticker(data["data"], inst_id);
            } else if (channel == "trades" || channel == "trades-all") {
                parse_trade(data["data"], inst_id);
            } else if (channel.find("books") != std::string::npos) {
                parse_orderbook(data["data"], inst_id);
            } else if (channel.find("candle") != std::string::npos) {
                parse_kline(data["data"], inst_id, channel);
            } else if (channel == "orders") {
                std::cout << "[WebSocket] 解析订单数据，数据条数: " << data["data"].size() << std::endl;
                parse_order(data["data"]);
            } else if (channel == "positions") {
                std::cout << "[WebSocket] 解析持仓数据，数据条数: " << data["data"].size() << std::endl;
                if (data.contains("eventType")) {
                    std::cout << "[WebSocket] 持仓事件类型: " << data["eventType"].get<std::string>() << std::endl;
                }
                parse_position(data["data"]);
            } else if (channel == "account") {
                std::cout << "[WebSocket] 解析账户数据，数据条数: " << data["data"].size() << std::endl;
                if (data.contains("eventType")) {
                    std::string event_type = data["eventType"].get<std::string>();
                    std::cout << "[WebSocket] 账户事件类型: " << event_type;
                    if (event_type == "snapshot") {
                        std::cout << " (快照推送：首次订阅或定时推送)";
                    } else if (event_type == "event_update") {
                        std::cout << " (事件推送：下单/撤单/成交等事件触发)";
                    }
                    std::cout << std::endl;
                }
                parse_account(data["data"]);
            } else if (channel == "open-interest") {
                parse_open_interest(data["data"]);
            } else if (channel == "mark-price") {
                parse_mark_price(data["data"]);
            } else if (channel == "sprd-orders") {
                parse_sprd_order(data["data"]);
            } else if (channel == "sprd-trades") {
                parse_sprd_trade(data["data"]);
            } else {
                std::cout << "[WebSocket] ⚠️ 未识别的频道: " << channel << std::endl;
            }
        }
        
    } catch (const std::exception& e) {
        std::cerr << "[WebSocket] 解析消息失败: " << e.what() << std::endl;
    }
}

void OKXWebSocket::parse_ticker(const nlohmann::json& data, const std::string& inst_id) {
    if (!ticker_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            auto ticker = std::make_shared<TickerData>(
                inst_id,
                std::stod(item.value("last", "0")),
                "okx"
            );
            
            if (item.contains("bidPx") && !item["bidPx"].get<std::string>().empty()) {
                ticker->set_bid_price(std::stod(item["bidPx"].get<std::string>()));
            }
            if (item.contains("askPx") && !item["askPx"].get<std::string>().empty()) {
                ticker->set_ask_price(std::stod(item["askPx"].get<std::string>()));
            }
            if (item.contains("bidSz") && !item["bidSz"].get<std::string>().empty()) {
                ticker->set_bid_size(std::stod(item["bidSz"].get<std::string>()));
            }
            if (item.contains("askSz") && !item["askSz"].get<std::string>().empty()) {
                ticker->set_ask_size(std::stod(item["askSz"].get<std::string>()));
            }
            if (item.contains("vol24h") && !item["vol24h"].get<std::string>().empty()) {
                ticker->set_volume_24h(std::stod(item["vol24h"].get<std::string>()));
            }
            if (item.contains("high24h") && !item["high24h"].get<std::string>().empty()) {
                ticker->set_high_24h(std::stod(item["high24h"].get<std::string>()));
            }
            if (item.contains("low24h") && !item["low24h"].get<std::string>().empty()) {
                ticker->set_low_24h(std::stod(item["low24h"].get<std::string>()));
            }
            if (item.contains("open24h") && !item["open24h"].get<std::string>().empty()) {
                ticker->set_open_24h(std::stod(item["open24h"].get<std::string>()));
            }
            
            // 设置时间戳
            if (item.contains("ts")) {
                ticker->set_timestamp(std::stoll(item["ts"].get<std::string>()));
            }
            
            ticker_callback_(ticker);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析Ticker失败: " << e.what() << std::endl;
        }
    }
}

void OKXWebSocket::parse_trade(const nlohmann::json& data, const std::string& inst_id) {
    if (!trade_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            auto trade = std::make_shared<TradeData>(
                inst_id,
                item.value("tradeId", ""),
                std::stod(item.value("px", "0")),
                std::stod(item.value("sz", "0")),
                "okx"
            );
            
            if (item.contains("side")) {
                trade->set_side(item["side"].get<std::string>());
            }
            
            if (item.contains("ts")) {
                trade->set_timestamp(std::stoll(item["ts"].get<std::string>()));
            }
            
            trade_callback_(trade);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析Trade失败: " << e.what() << std::endl;
        }
    }
}

void OKXWebSocket::parse_orderbook(const nlohmann::json& data, const std::string& inst_id) {
    if (!orderbook_callback_ || !data.is_array() || data.empty()) return;
    
    try {
        const auto& item = data[0];
        
        std::vector<OrderBookData::PriceLevel> bids;
        std::vector<OrderBookData::PriceLevel> asks;
        
        if (item.contains("bids") && item["bids"].is_array()) {
            for (const auto& bid : item["bids"]) {
                if (bid.is_array() && bid.size() >= 2) {
                    double price = std::stod(bid[0].get<std::string>());
                    double size = std::stod(bid[1].get<std::string>());
                    bids.emplace_back(price, size);
                }
            }
        }
        
        if (item.contains("asks") && item["asks"].is_array()) {
            for (const auto& ask : item["asks"]) {
                if (ask.is_array() && ask.size() >= 2) {
                    double price = std::stod(ask[0].get<std::string>());
                    double size = std::stod(ask[1].get<std::string>());
                    asks.emplace_back(price, size);
                }
            }
        }
        
        auto orderbook = std::make_shared<OrderBookData>(inst_id, bids, asks, "okx");
        
        if (item.contains("ts")) {
            orderbook->set_timestamp(std::stoll(item["ts"].get<std::string>()));
        }
        
        orderbook_callback_(orderbook);
        
    } catch (const std::exception& e) {
        std::cerr << "[WebSocket] 解析OrderBook失败: " << e.what() << std::endl;
    }
}

void OKXWebSocket::parse_kline(const nlohmann::json& data, const std::string& inst_id, const std::string& channel) {
    if (!kline_callback_ || !data.is_array() || data.empty()) return;
    
    // 从channel提取interval（如 "candle1m" -> "1m"）
    std::string interval = channel.substr(6);  // 去掉 "candle" 前缀
    
    for (const auto& item : data) {
        try {
            // OKX K线数据格式: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            if (!item.is_array() || item.size() < 6) continue;
            
            int64_t timestamp = std::stoll(item[0].get<std::string>());
            double open = std::stod(item[1].get<std::string>());
            double high = std::stod(item[2].get<std::string>());
            double low = std::stod(item[3].get<std::string>());
            double close = std::stod(item[4].get<std::string>());
            double volume = std::stod(item[5].get<std::string>());
            
            auto kline = std::make_shared<KlineData>(
                inst_id,
                interval,
                open,
                high,
                low,
                close,
                volume,
                "okx"
            );
            
            kline->set_timestamp(timestamp);
            
            // 设置成交额（如果有）
            if (item.size() > 6 && !item[6].get<std::string>().empty()) {
                kline->set_turnover(std::stod(item[6].get<std::string>()));
            }
            
            kline_callback_(kline);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析Kline失败: " << e.what() << std::endl;
        }
    }
}

// 辅助函数：安全地解析可能为空字符串的数字字段
namespace {
    double safe_stod(const nlohmann::json& item, const std::string& key, double default_value = 0.0) {
        if (!item.contains(key)) {
            return default_value;
        }
        
        std::string value_str = item[key].get<std::string>();
        if (value_str.empty()) {
            return default_value;
        }
        
        try {
            return std::stod(value_str);
        } catch (const std::exception&) {
            return default_value;
        }
    }
    
    int64_t safe_stoll(const nlohmann::json& item, const std::string& key, int64_t default_value = 0) {
        if (!item.contains(key)) {
            return default_value;
        }
        
        std::string value_str = item[key].get<std::string>();
        if (value_str.empty()) {
            return default_value;
        }
        
        try {
            return std::stoll(value_str);
        } catch (const std::exception&) {
            return default_value;
        }
    }
}

void OKXWebSocket::parse_order(const nlohmann::json& data) {
    // 调试日志
    if (!order_callback_) {
        std::cerr << "[WebSocket] ⚠️ 订单回调未设置！" << std::endl;
        return;
    }
    
    if (!data.is_array()) {
        std::cerr << "[WebSocket] ⚠️ 订单数据不是数组格式: " << data.dump() << std::endl;
        return;
    }
    
    if (data.empty()) {
        std::cout << "[WebSocket] ⚠️ 订单数据为空数组" << std::endl;
        return;
    }
    
    std::cout << "[WebSocket] 开始解析订单数据，共 " << data.size() << " 条" << std::endl;
    
    for (const auto& item : data) {
        try {
            // 解析订单类型
            OrderType order_type = OrderType::LIMIT;
            std::string ord_type = item.value("ordType", "limit");
            if (ord_type == "market") order_type = OrderType::MARKET;
            else if (ord_type == "post_only") order_type = OrderType::POST_ONLY;
            else if (ord_type == "fok") order_type = OrderType::FOK;
            else if (ord_type == "ioc") order_type = OrderType::IOC;
            
            // 解析订单方向
            OrderSide side = item.value("side", "buy") == "buy" ? OrderSide::BUY : OrderSide::SELL;
            
            // 安全地解析数量和价格（市价单的px可能为空字符串）
            double sz = safe_stod(item, "sz", 0.0);
            double px = safe_stod(item, "px", 0.0);
            
            // 创建订单对象
            auto order = std::make_shared<Order>(
                item.value("instId", ""),
                order_type,
                side,
                sz,
                px,
                "okx"
            );
            
            order->set_client_order_id(item.value("clOrdId", ""));
            order->set_exchange_order_id(item.value("ordId", ""));
            
            // 解析订单状态
            std::string state = item.value("state", "");
            if (state == "live") {
                order->set_state(OrderState::ACCEPTED);
            } else if (state == "partially_filled") {
                order->set_state(OrderState::PARTIALLY_FILLED);
            } else if (state == "filled") {
                order->set_state(OrderState::FILLED);
            } else if (state == "canceled") {
                order->set_state(OrderState::CANCELLED);
            }
            
            // 设置成交信息（使用安全解析函数）
            double fill_sz = safe_stod(item, "fillSz", 0.0);
            if (fill_sz > 0.0) {
                order->set_filled_quantity(fill_sz);
            }
            
            double avg_px = safe_stod(item, "avgPx", 0.0);
            if (avg_px > 0.0) {
                order->set_filled_price(avg_px);
            }
            
            double fee = safe_stod(item, "fee", 0.0);
            if (fee != 0.0) {
                order->set_fee(fee);
            }
            
            if (item.contains("feeCcy")) {
                order->set_fee_currency(item["feeCcy"].get<std::string>());
            }
            
            // 设置时间（使用安全解析函数）
            int64_t c_time = safe_stoll(item, "cTime", 0);
            if (c_time > 0) {
                order->set_create_time(c_time);
            }
            
            int64_t u_time = safe_stoll(item, "uTime", 0);
            if (u_time > 0) {
                order->set_update_time(u_time);
            }
            
            // 调试：打印订单信息
            std::cout << "[WebSocket] ✅ 订单解析成功: " << order->symbol() 
                      << " | ID: " << order->exchange_order_id()
                      << " | 状态: " << order_state_to_string(order->state()) << std::endl;
            
            // 调用回调
            if (order_callback_) {
                order_callback_(order);
                std::cout << "[WebSocket] ✅ 订单回调已调用" << std::endl;
            } else {
                std::cerr << "[WebSocket] ⚠️ 订单回调为空！" << std::endl;
            }
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] ❌ 解析Order失败: " << e.what() << std::endl;
            std::cerr << "[WebSocket] 原始数据: " << item.dump(2) << std::endl;
        }
    }
}

void OKXWebSocket::parse_position(const nlohmann::json& data) {
    // 调试日志
    if (!position_callback_) {
        std::cerr << "[WebSocket] ⚠️ 持仓回调未设置！" << std::endl;
        return;
    }
    
    if (!data.is_array()) {
        std::cerr << "[WebSocket] ⚠️ 持仓数据不是数组格式: " << data.dump() << std::endl;
        return;
    }
    
    if (data.empty()) {
        std::cout << "[WebSocket] ⚠️ 持仓数据为空数组（可能没有持仓）" << std::endl;
        // 即使数据为空，也调用回调，传递空数组
        position_callback_(data);
        return;
    }
    
    std::cout << "[WebSocket] 开始解析持仓数据，共 " << data.size() << " 条" << std::endl;
    
    // 创建一个数组来存储所有持仓
    nlohmann::json positions_array = nlohmann::json::array();
    
    for (const auto& item : data) {
        try {
            // 持仓数据比较复杂，直接传递原始JSON给回调
            // 用户可以根据需要解析以下字段:
            // - instId: 产品ID
            // - posSide: 持仓方向 (long/short/net)
            // - pos: 持仓数量
            // - availPos: 可用持仓数量
            // - avgPx: 平均开仓价格
            // - upl: 未实现盈亏
            // - uplRatio: 未实现盈亏比例
            // - lever: 杠杆倍数
            // - liqPx: 预估强平价格
            // - markPx: 标记价格
            // - margin: 保证金
            // - mgnRatio: 保证金率
            // - notionalUsd: 美元价值
            // - uTime: 更新时间
            
            std::string inst_id = item.value("instId", "");
            std::string inst_type = item.value("instType", "");
            std::string pos_side = item.value("posSide", "");
            std::string pos = item.value("pos", "");
            
            std::cout << "[WebSocket] ✅ 持仓: " << inst_id 
                      << " | 类型: " << inst_type
                      << " | 方向: " << pos_side
                      << " | 数量: " << pos << std::endl;
            
            positions_array.push_back(item);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] ❌ 解析Position失败: " << e.what() << std::endl;
            std::cerr << "[WebSocket] 原始数据: " << item.dump(2) << std::endl;
        }
    }
    
    // 调用回调，传递所有持仓数据
    if (!positions_array.empty()) {
        position_callback_(positions_array);
        std::cout << "[WebSocket] ✅ 持仓回调已调用，共 " << positions_array.size() << " 个持仓" << std::endl;
    } else {
        std::cout << "[WebSocket] ⚠️ 没有有效持仓数据" << std::endl;
    }
}

void OKXWebSocket::parse_account(const nlohmann::json& data) {
    // 调试日志
    if (!account_callback_) {
        std::cerr << "[WebSocket] ⚠️ 账户回调未设置！" << std::endl;
        return;
    }
    
    if (!data.is_array()) {
        std::cerr << "[WebSocket] ⚠️ 账户数据不是数组格式: " << data.dump() << std::endl;
        return;
    }
    
    if (data.empty()) {
        std::cout << "[WebSocket] ⚠️ 账户数据为空数组" << std::endl;
        return;
    }
    
    std::cout << "[WebSocket] 开始解析账户数据，共 " << data.size() << " 条" << std::endl;
    
    for (const auto& item : data) {
        try {
            // 账户数据比较复杂，直接传递原始JSON给回调
            // 用户可以根据需要解析以下字段:
            // - totalEq: 总权益（美元）
            // - isoEq: 逐仓仓位权益（美元）
            // - adjEq: 有效保证金（美元）
            // - ordFroz: 下单冻结的保证金（美元）
            // - imr: 初始保证金（美元）
            // - mmr: 维持保证金（美元）
            // - mgnRatio: 保证金率
            // - notionalUsd: 以美元计的持仓价值
            // - details: 各币种详情数组
            //   - ccy: 币种
            //   - eq: 币种权益
            //   - cashBal: 现金余额
            //   - availEq: 可用权益
            //   - availBal: 可用余额
            //   - frozenBal: 冻结余额
            //   - ordFrozen: 下单冻结
            //   - upl: 未实现盈亏
            // - uTime: 更新时间
            
            std::string total_eq = item.value("totalEq", "");
            std::string u_time = item.value("uTime", "");
            
            std::cout << "[WebSocket] ✅ 账户更新: "
                      << "总权益=" << total_eq << " USD";
            if (!u_time.empty()) {
                std::cout << " | 更新时间=" << u_time;
            }
            std::cout << std::endl;
            
            // 统计币种数量
            if (item.contains("details") && item["details"].is_array()) {
                size_t ccy_count = item["details"].size();
                std::cout << "[WebSocket]   币种数量: " << ccy_count << " 个" << std::endl;
            }
            
            account_callback_(item);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] ❌ 解析Account失败: " << e.what() << std::endl;
            std::cerr << "[WebSocket] 原始数据: " << item.dump(2) << std::endl;
        }
    }
}

void OKXWebSocket::parse_open_interest(const nlohmann::json& data) {
    if (!open_interest_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            // 解析持仓总量数据
            // - instId: 产品ID，如 BTC-USDT-SWAP
            // - instType: 产品类型，如 SWAP
            // - oi: 持仓量（按张）
            // - oiCcy: 持仓量（按币）
            // - oiUsd: 持仓量（按USD）
            // - ts: 时间戳
            
            std::string inst_id = item.value("instId", "");
            std::string inst_type = item.value("instType", "");
            double oi = 0.0;
            double oi_ccy = 0.0;
            double oi_usd = 0.0;
            int64_t ts = 0;
            
            if (item.contains("oi") && !item["oi"].get<std::string>().empty()) {
                oi = std::stod(item["oi"].get<std::string>());
            }
            if (item.contains("oiCcy") && !item["oiCcy"].get<std::string>().empty()) {
                oi_ccy = std::stod(item["oiCcy"].get<std::string>());
            }
            if (item.contains("oiUsd") && !item["oiUsd"].get<std::string>().empty()) {
                oi_usd = std::stod(item["oiUsd"].get<std::string>());
            }
            if (item.contains("ts")) {
                ts = std::stoll(item["ts"].get<std::string>());
            }
            
            auto oi_data = std::make_shared<OpenInterestData>(
                inst_id,
                inst_type,
                oi,
                oi_ccy,
                oi_usd,
                ts
            );
            
            std::cout << "[WebSocket] 收到持仓总量: " << inst_id 
                      << " | OI: " << oi 
                      << " | OI_USD: " << oi_usd << std::endl;
            
            open_interest_callback_(oi_data);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析OpenInterest失败: " << e.what() << std::endl;
        }
    }
}

void OKXWebSocket::parse_mark_price(const nlohmann::json& data) {
    if (!mark_price_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            // 解析标记价格数据
            // - instId: 产品ID，如 BTC-USDT
            // - instType: 产品类型，如 MARGIN/SWAP/FUTURES
            // - markPx: 标记价格
            // - ts: 时间戳
            
            std::string inst_id = item.value("instId", "");
            std::string inst_type = item.value("instType", "");
            
            // 使用安全解析函数
            double mark_px = safe_stod(item, "markPx", 0.0);
            int64_t ts = safe_stoll(item, "ts", 0);
            
            auto mp_data = std::make_shared<MarkPriceData>(
                inst_id,
                inst_type,
                mark_px,
                ts
            );
            
            mark_price_callback_(mp_data);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析MarkPrice失败: " << e.what() << std::endl;
        }
    }
}

void OKXWebSocket::parse_sprd_order(const nlohmann::json& data) {
    if (!order_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            // Spread订单数据结构与普通订单类似，但使用sprdId而不是instId
            // 解析订单类型
            OrderType order_type = OrderType::LIMIT;
            std::string ord_type = item.value("ordType", "limit");
            if (ord_type == "market") order_type = OrderType::MARKET;
            else if (ord_type == "post_only") order_type = OrderType::POST_ONLY;
            else if (ord_type == "fok") order_type = OrderType::FOK;
            else if (ord_type == "ioc") order_type = OrderType::IOC;
            
            // 解析订单方向
            OrderSide side = item.value("side", "buy") == "buy" ? OrderSide::BUY : OrderSide::SELL;
            
            // Spread订单使用sprdId作为symbol
            std::string sprd_id = item.value("sprdId", "");
            
            // 安全地解析数量和价格
            double sz = safe_stod(item, "sz", 0.0);
            double px = safe_stod(item, "px", 0.0);
            
            // 创建订单对象（使用sprdId作为symbol）
            auto order = std::make_shared<Order>(
                sprd_id,
                order_type,
                side,
                sz,
                px,
                "okx"
            );
            
            order->set_client_order_id(item.value("clOrdId", ""));
            order->set_exchange_order_id(item.value("ordId", ""));
            
            // 解析订单状态
            std::string state = item.value("state", "");
            if (state == "live") {
                order->set_state(OrderState::ACCEPTED);
            } else if (state == "partially_filled") {
                order->set_state(OrderState::PARTIALLY_FILLED);
            } else if (state == "filled") {
                order->set_state(OrderState::FILLED);
            } else if (state == "canceled") {
                order->set_state(OrderState::CANCELLED);
            }
            
            // 设置成交信息（使用安全解析函数）
            double acc_fill_sz = safe_stod(item, "accFillSz", 0.0);
            if (acc_fill_sz > 0.0) {
                order->set_filled_quantity(acc_fill_sz);
            }
            
            double avg_px = safe_stod(item, "avgPx", 0.0);
            if (avg_px > 0.0) {
                order->set_filled_price(avg_px);
            }
            
            // 设置时间（使用安全解析函数）
            int64_t c_time = safe_stoll(item, "cTime", 0);
            if (c_time > 0) {
                order->set_create_time(c_time);
            }
            
            int64_t u_time = safe_stoll(item, "uTime", 0);
            if (u_time > 0) {
                order->set_update_time(u_time);
            }
            
            std::cout << "[WebSocket] 收到Spread订单: " << sprd_id 
                      << " | 订单ID: " << order->exchange_order_id()
                      << " | 状态: " << state << std::endl;
            
            order_callback_(order);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析Spread订单失败: " << e.what() << std::endl;
        }
    }
}

void OKXWebSocket::parse_sprd_trade(const nlohmann::json& data) {
    if (!spread_trade_callback_ || !data.is_array() || data.empty()) return;
    
    for (const auto& item : data) {
        try {
            std::string sprd_id = item.value("sprdId", "");
            std::string trade_id = item.value("tradeId", "");
            std::string ord_id = item.value("ordId", "");
            std::string cl_ord_id = item.value("clOrdId", "");
            std::string tag = item.value("tag", "");
            double fill_px = 0.0;
            double fill_sz = 0.0;
            std::string side = item.value("side", "");
            std::string state = item.value("state", "");
            std::string exec_type = item.value("execType", "");
            int64_t ts = 0;
            
            if (item.contains("fillPx") && !item["fillPx"].get<std::string>().empty()) {
                fill_px = std::stod(item["fillPx"].get<std::string>());
            }
            if (item.contains("fillSz") && !item["fillSz"].get<std::string>().empty()) {
                fill_sz = std::stod(item["fillSz"].get<std::string>());
            }
            if (item.contains("ts")) {
                ts = std::stoll(item["ts"].get<std::string>());
            }
            
            // 创建Spread成交数据对象
            auto trade_data = std::make_shared<SpreadTradeData>(
                sprd_id, trade_id, ord_id, fill_px, fill_sz, side, state, ts
            );
            
            trade_data->cl_ord_id = cl_ord_id;
            trade_data->tag = tag;
            trade_data->exec_type = exec_type;
            
            // 解析legs（交易的腿）
            if (item.contains("legs") && item["legs"].is_array()) {
                for (const auto& leg_item : item["legs"]) {
                    SpreadTradeLeg leg;
                    leg.inst_id = leg_item.value("instId", "");
                    
                    if (leg_item.contains("px") && !leg_item["px"].get<std::string>().empty()) {
                        leg.px = std::stod(leg_item["px"].get<std::string>());
                    }
                    if (leg_item.contains("sz") && !leg_item["sz"].get<std::string>().empty()) {
                        leg.sz = std::stod(leg_item["sz"].get<std::string>());
                    }
                    
                    // szCont可能为空字符串（现货）
                    std::string sz_cont_str = leg_item.value("szCont", "");
                    leg.sz_cont = sz_cont_str.empty() ? 0.0 : std::stod(sz_cont_str);
                    
                    leg.side = leg_item.value("side", "");
                    
                    // fillPnl可能为空
                    std::string fill_pnl_str = leg_item.value("fillPnl", "");
                    leg.fill_pnl = fill_pnl_str.empty() ? 0.0 : std::stod(fill_pnl_str);
                    
                    // fee可能为空
                    std::string fee_str = leg_item.value("fee", "");
                    leg.fee = fee_str.empty() ? 0.0 : std::stod(fee_str);
                    
                    leg.fee_ccy = leg_item.value("feeCcy", "");
                    leg.trade_id = leg_item.value("tradeId", "");
                    
                    trade_data->legs.push_back(leg);
                }
            }
            
            std::cout << "[WebSocket] 收到Spread成交: " << sprd_id 
                      << " | 交易ID: " << trade_id
                      << " | 订单ID: " << ord_id
                      << " | 状态: " << state
                      << " | 价格: " << fill_px
                      << " | 数量: " << fill_sz
                      << " | 腿数: " << trade_data->legs.size() << std::endl;
            
            spread_trade_callback_(trade_data);
            
        } catch (const std::exception& e) {
            std::cerr << "[WebSocket] 解析Spread成交失败: " << e.what() << std::endl;
            std::cerr << "[WebSocket] 原始数据: " << item.dump(2) << std::endl;
        }
    }
}

} // namespace okx
} // namespace trading

