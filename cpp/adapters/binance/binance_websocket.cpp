/**
 * @file binance_websocket.cpp
 * @brief Binance WebSocket 客户端实现
 * 
 * 使用 websocketpp 库实现 WebSocket 连接
 * 完全对标 OKX WebSocket 的实现结构
 * 
 * 依赖安装:
 *   使用 standalone ASIO（推荐）:
 *     macOS: brew install websocketpp asio openssl
 *     Ubuntu: apt install libwebsocketpp-dev libasio-dev libssl-dev
 * 
 *   使用 Boost.ASIO:
 *     macOS: brew install websocketpp boost openssl
 *     Ubuntu: apt install libwebsocketpp-dev libboost-all-dev libssl-dev
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "binance_websocket.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <ctime>
#include <algorithm>
#include <openssl/hmac.h>
#include <openssl/sha.h>

// WebSocket++ 头文件
#ifdef USE_WEBSOCKETPP

// 使用 standalone ASIO
#ifdef ASIO_STANDALONE
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>

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
namespace binance {

// ==================== 辅助函数 ====================

// HMAC SHA256签名
static std::string hmac_sha256(const std::string& key, const std::string& data) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    
    HMAC(
        EVP_sha256(),
        key.c_str(),
        key.length(),
        (unsigned char*)data.c_str(),
        data.length(),
        hash,
        nullptr
    );
    
    // 转换为十六进制字符串
    std::ostringstream oss;
    for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        oss << std::hex << std::setw(2) << std::setfill('0') << (int)hash[i];
    }
    
    return oss.str();
}

// 安全的字符串转double
static double safe_stod(const nlohmann::json& j, const std::string& key, double default_val = 0.0) {
    if (!j.contains(key)) return default_val;
    
    try {
        if (j[key].is_string()) {
            std::string str = j[key].get<std::string>();
            if (str.empty()) return default_val;
            return std::stod(str);
        } else if (j[key].is_number()) {
            return j[key].get<double>();
        }
    } catch (...) {
        return default_val;
    }
    return default_val;
}

// 安全的字符串转int64_t
static int64_t safe_stoll(const nlohmann::json& j, const std::string& key, int64_t default_val = 0) {
    if (!j.contains(key)) return default_val;
    
    try {
        if (j[key].is_string()) {
            std::string str = j[key].get<std::string>();
            if (str.empty()) return default_val;
            return std::stoll(str);
        } else if (j[key].is_number()) {
            return j[key].get<int64_t>();
        }
    } catch (...) {
        return default_val;
    }
    return default_val;
}

// ==================== WebSocket实现类（pImpl模式） ====================

#ifdef USE_WEBSOCKETPP
/**
 * @brief WebSocket实现类（使用WebSocket++）
 * 
 * 与OKXWebSocket::Impl结构完全一致
 */
class BinanceWebSocket::Impl {
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
            SslContextPtr ctx = std::make_shared<asio::ssl::context>(
                asio::ssl::context::tlsv12_client);
            ctx->set_default_verify_paths();
            ctx->set_verify_mode(asio::ssl::verify_none);
#else
            SslContextPtr ctx = std::make_shared<boost::asio::ssl::context>(
                boost::asio::ssl::context::tlsv12_client);
            ctx->set_default_verify_paths();
            ctx->set_verify_mode(boost::asio::ssl::verify_none);
#endif
            return ctx;
        });
        
        std::cout << "[BinanceWebSocket] 默认使用 HTTP 代理: " << proxy_host_ << ":" << proxy_port_ << std::endl;
    }
    
    void set_proxy(const std::string& proxy_host, uint16_t proxy_port) {
        proxy_host_ = proxy_host;
        proxy_port_ = proxy_port;
        use_proxy_ = true;
        std::cout << "[BinanceWebSocket] 使用 HTTP 代理: " << proxy_host << ":" << proxy_port << std::endl;
    }
    
    bool connect(const std::string& url) {
        websocketpp::lib::error_code ec;
        connection_ = client_.get_connection(url, ec);
        
        if (ec) {
            std::cerr << "[BinanceWebSocket] 连接错误: " << ec.message() << std::endl;
            return false;
        }
        
        // 设置 HTTP 代理
        if (use_proxy_) {
            std::string proxy_uri = "http://" + proxy_host_ + ":" + std::to_string(proxy_port_);
            connection_->set_proxy(proxy_uri);
            std::cout << "[BinanceWebSocket] 代理已配置: " << proxy_uri << std::endl;
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
            std::cout << "[BinanceWebSocket] ✅ 连接成功" << std::endl;
        });
        
        // 设置关闭回调
        connection_->set_close_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cout << "[BinanceWebSocket] 连接已关闭" << std::endl;
        });
        
        // 设置失败回调
        connection_->set_fail_handler([this](websocketpp::connection_hdl) {
            is_connected_ = false;
            std::cerr << "[BinanceWebSocket] ❌ 连接失败" << std::endl;
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
            std::cerr << "[BinanceWebSocket] 发送错误: " << ec.message() << std::endl;
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
 */
class BinanceWebSocket::Impl {
public:
    Impl() = default;
    
    void set_proxy(const std::string& proxy_host, uint16_t proxy_port) {
        std::cout << "[BinanceWebSocket] 代理配置（占位）: " << proxy_host << ":" << proxy_port << std::endl;
    }
    
    bool connect(const std::string& url) {
        std::cout << "[BinanceWebSocket] ⚠️ WebSocket++ 未启用" << std::endl;
        std::cout << "[BinanceWebSocket] 请安装 websocketpp 并在 CMakeLists.txt 中启用 USE_WEBSOCKETPP" << std::endl;
        std::cout << "[BinanceWebSocket] URL: " << url << std::endl;
        
        is_connected_ = true;
        return true;
    }
    
    void disconnect() {
        is_connected_ = false;
        std::cout << "[BinanceWebSocket] 断开连接" << std::endl;
    }
    
    bool send(const std::string& message) {
        if (!is_connected_) return false;
        std::cout << "[BinanceWebSocket] 发送消息: " << message << std::endl;
        return true;
    }
    
    void set_message_callback(std::function<void(const std::string&)> callback) {
        message_callback_ = std::move(callback);
    }
    
    bool is_connected() const { return is_connected_; }

private:
    std::atomic<bool> is_connected_{false};
    std::function<void(const std::string&)> message_callback_;
};

#endif // USE_WEBSOCKETPP

// ==================== BinanceWebSocket实现 ====================

BinanceWebSocket::BinanceWebSocket(
    const std::string& api_key,
    const std::string& secret_key,
    WsConnectionType conn_type,
    MarketType market_type,
    bool is_testnet
)
    : api_key_(api_key)
    , secret_key_(secret_key)
    , conn_type_(conn_type)
    , market_type_(market_type)
    , is_testnet_(is_testnet)
    , impl_(std::make_unique<Impl>())
{
    ws_url_ = build_ws_url();
    std::cout << "[BinanceWebSocket] 初始化 (连接类型=" << (int)conn_type_ << ")" << std::endl;
    std::cout << "[BinanceWebSocket] URL: " << ws_url_ << std::endl;
}

BinanceWebSocket::~BinanceWebSocket() {
    disconnect();
}

std::string BinanceWebSocket::build_ws_url() const {
    if (is_testnet_) {
        // 测试网URL（Spot Test Network）
        // 官方域名区分：
        // - Trading WS API:  ws-api.testnet.binance.vision
        // - Market Streams: stream.testnet.binance.vision
        switch (conn_type_) {
            case WsConnectionType::TRADING:
                return "wss://ws-api.testnet.binance.vision/ws-api/v3";
            case WsConnectionType::MARKET:
            case WsConnectionType::USER_DATA:
                return "wss://stream.testnet.binance.vision/ws";
        }
    } else {
        // 主网URL
        switch (conn_type_) {
            case WsConnectionType::TRADING:
                return "wss://ws-api.binance.com:443/ws-api/v3";
            case WsConnectionType::MARKET:
            case WsConnectionType::USER_DATA:
                if (market_type_ == MarketType::FUTURES) {
                    return "wss://fstream.binance.com/ws";
                } else if (market_type_ == MarketType::COIN_FUTURES) {
                    return "wss://dstream.binance.com/ws";
                } else {
                    return "wss://stream.binance.com:9443/ws";
                }
        }
    }
    
    return "wss://stream.binance.com:9443/ws";
}

bool BinanceWebSocket::connect() {
    if (is_connected_.load()) {
        std::cout << "[BinanceWebSocket] 已经连接" << std::endl;
        return true;
    }
    
    std::cout << "[BinanceWebSocket] 正在连接: " << ws_url_ << std::endl;
    
    // 设置消息回调
    impl_->set_message_callback([this](const std::string& message) {
        on_message(message);
    });
    
    // 连接WebSocket
    if (!impl_->connect(ws_url_)) {
        std::cerr << "[BinanceWebSocket] 连接失败" << std::endl;
        return false;
    }
    
    is_connected_.store(true);
    is_running_.store(true);
    
    // 对于行情流，连接后需要发送订阅请求
    // 对于交易API，连接后即可发送请求
    
    std::cout << "[BinanceWebSocket] 连接成功" << std::endl;
    return true;
}

void BinanceWebSocket::disconnect() {
    if (!is_connected_.load()) return;
    
    std::cout << "[BinanceWebSocket] 断开连接..." << std::endl;
    
    is_running_.store(false);
    is_connected_.store(false);
    
    impl_->disconnect();
    
    std::cout << "[BinanceWebSocket] 已断开连接" << std::endl;
}

bool BinanceWebSocket::send_message(const nlohmann::json& msg) {
    if (!is_connected_.load()) {
        std::cerr << "[BinanceWebSocket] 未连接，无法发送消息" << std::endl;
        return false;
    }
    
    std::string msg_str = msg.dump();
    // std::cout << "[BinanceWebSocket] 发送: " << msg_str << std::endl;
    
    return impl_->send(msg_str);
}

void BinanceWebSocket::on_message(const std::string& message) {
    try {
        auto data = nlohmann::json::parse(message);
        
        // 调试输出（可选）
        if (raw_callback_) {
            raw_callback_(data);
        }

        // 0. 部分频道可能直接返回数组（如 !miniTicker@arr / !ticker@arr）
        if (data.is_array()) {
            for (const auto& item : data) {
                if (!item.is_object()) continue;
                if (raw_callback_) raw_callback_(item);
                if (!item.contains("e")) continue;
                std::string event_type = item["e"].get<std::string>();
                if (event_type == "trade") {
                    parse_trade(item);
                } else if (event_type == "kline") {
                    parse_kline(item);
                } else if (event_type == "24hrTicker" || event_type == "24hrMiniTicker") {
                    parse_ticker(item);
                } else if (event_type == "depthUpdate") {
                    parse_depth(item);
                } else if (event_type == "bookTicker") {
                    parse_book_ticker(item);
                } else if (event_type == "executionReport") {
                    parse_order_update(item);
                } else if (event_type == "outboundAccountPosition") {
                    parse_account_update(item);
                }
            }
            return;
        }
        
        // 处理不同类型的消息
        
        // 1. WebSocket API响应（有id字段）
        if (data.contains("id")) {
            // 交易API的响应
            if (order_response_callback_) {
                order_response_callback_(data);
            }
            return;
        }
        
        // 2. 行情数据流（有stream字段或e字段）
        if (data.contains("e")) {
            std::string event_type = data["e"].get<std::string>();
            
            if (event_type == "trade") {
                parse_trade(data);
            } else if (event_type == "kline") {
                parse_kline(data);
            } else if (event_type == "24hrTicker" || event_type == "24hrMiniTicker") {
                parse_ticker(data);
            } else if (event_type == "depthUpdate") {
                parse_depth(data);
            } else if (event_type == "bookTicker") {
                parse_book_ticker(data);
            } else if (event_type == "executionReport") {
                // 订单更新
                parse_order_update(data);
            } else if (event_type == "outboundAccountPosition") {
                // 账户余额更新
                parse_account_update(data);
            }
        } else {
            // 3. depth<levels> 快照没有 e 字段：{ lastUpdateId, bids, asks }
            if (data.contains("lastUpdateId") && (data.contains("bids") || data.contains("asks"))) {
                parse_depth(data);
            }
        }
        
        // 4. Ping/Pong
        if (data.contains("ping")) {
            // 发送pong
            nlohmann::json pong = {{"pong", data["ping"]}};
            send_message(pong);
        }
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析消息失败: " << e.what() << std::endl;
        std::cerr << "[BinanceWebSocket] 原始消息: " << message << std::endl;
    }
}

// ==================== WebSocket交易API ====================

std::string BinanceWebSocket::generate_request_id() {
    // 生成唯一请求ID（UUID格式或递增ID）
    uint64_t id = request_id_counter_.fetch_add(1);
    return "req_" + std::to_string(id);
}

std::string BinanceWebSocket::create_signature(const std::string& query_string) {
    return hmac_sha256(secret_key_, query_string);
}

int64_t BinanceWebSocket::get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();
    return ms;
}

std::string BinanceWebSocket::order_side_to_string(OrderSide side) {
    return side == OrderSide::BUY ? "BUY" : "SELL";
}

std::string BinanceWebSocket::order_type_to_string(OrderType type) {
    switch (type) {
        case OrderType::LIMIT: return "LIMIT";
        case OrderType::MARKET: return "MARKET";
        case OrderType::STOP_LOSS: return "STOP_LOSS";
        case OrderType::STOP_LOSS_LIMIT: return "STOP_LOSS_LIMIT";
        case OrderType::TAKE_PROFIT: return "TAKE_PROFIT";
        case OrderType::TAKE_PROFIT_LIMIT: return "TAKE_PROFIT_LIMIT";
        case OrderType::LIMIT_MAKER: return "LIMIT_MAKER";
        default: return "LIMIT";
    }
}

std::string BinanceWebSocket::time_in_force_to_string(TimeInForce tif) {
    switch (tif) {
        case TimeInForce::GTC: return "GTC";
        case TimeInForce::IOC: return "IOC";
        case TimeInForce::FOK: return "FOK";
        case TimeInForce::GTX: return "GTX";
        default: return "GTC";
    }
}

std::string BinanceWebSocket::place_order_ws(
    const std::string& symbol,
    OrderSide side,
    OrderType type,
    const std::string& quantity,
    const std::string& price,
    TimeInForce time_in_force,
    const std::string& client_order_id
) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法下单" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    // 构造请求参数
    nlohmann::json params = {
        {"symbol", symbol},
        {"side", order_side_to_string(side)},
        {"type", order_type_to_string(type)},
        {"apiKey", api_key_}
    };
    
    // 数量
    params["quantity"] = quantity;
    
    // 价格（限价单必填）
    if (!price.empty() && type == OrderType::LIMIT) {
        params["price"] = price;
        params["timeInForce"] = time_in_force_to_string(time_in_force);
    }
    
    // 客户自定义订单ID
    if (!client_order_id.empty()) {
        params["newClientOrderId"] = client_order_id;
    }
    
    // 添加时间戳
    int64_t timestamp = get_timestamp();
    params["timestamp"] = timestamp;
    
    // 创建查询字符串（用于签名）
    std::ostringstream query;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (it != params.begin()) query << "&";
        query << it.key() << "=" << it.value().dump();
    }
    std::string query_str = query.str();
    
    // 移除JSON字符串的引号
    // 简化处理：这里应该更仔细地处理
    
    // 生成签名
    std::string signature = create_signature(query_str);
    params["signature"] = signature;
    
    // 构造完整请求
    nlohmann::json request = {
        {"id", req_id},
        {"method", "order.place"},
        {"params", params}
    };
    
    // 发送请求
    send_message(request);
    
    return req_id;
}

std::string BinanceWebSocket::cancel_order_ws(
    const std::string& symbol,
    int64_t order_id,
    const std::string& client_order_id
) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法撤单" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"apiKey", api_key_},
        {"timestamp", get_timestamp()}
    };
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    // 生成签名
    std::ostringstream query;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (it != params.begin()) query << "&";
        query << it.key() << "=" << it.value().dump();
    }
    std::string signature = create_signature(query.str());
    params["signature"] = signature;
    
    nlohmann::json request = {
        {"id", req_id},
        {"method", "order.cancel"},
        {"params", params}
    };
    
    send_message(request);
    
    return req_id;
}

std::string BinanceWebSocket::cancel_all_orders_ws(const std::string& symbol) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法撤单" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"apiKey", api_key_},
        {"timestamp", get_timestamp()}
    };
    
    // 生成签名
    std::ostringstream query;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (it != params.begin()) query << "&";
        query << it.key() << "=" << it.value().dump();
    }
    std::string signature = create_signature(query.str());
    params["signature"] = signature;
    
    nlohmann::json request = {
        {"id", req_id},
        {"method", "openOrders.cancelAll"},
        {"params", params}
    };
    
    send_message(request);
    
    return req_id;
}

std::string BinanceWebSocket::query_order_ws(
    const std::string& symbol,
    int64_t order_id,
    const std::string& client_order_id
) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法查询" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"apiKey", api_key_},
        {"timestamp", get_timestamp()}
    };
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    // 生成签名
    std::ostringstream query;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (it != params.begin()) query << "&";
        query << it.key() << "=" << it.value().dump();
    }
    std::string signature = create_signature(query.str());
    params["signature"] = signature;
    
    nlohmann::json request = {
        {"id", req_id},
        {"method", "order.status"},
        {"params", params}
    };
    
    send_message(request);
    
    return req_id;
}

// ==================== 行情订阅 ====================

void BinanceWebSocket::subscribe_trade(const std::string& symbol) {
    if (conn_type_ != WsConnectionType::MARKET) {
        std::cerr << "[BinanceWebSocket] 错误：非行情连接无法订阅" << std::endl;
        return;
    }
    
    // Binance行情流格式: <symbol>@trade
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {symbol + "@trade"}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅逐笔成交: " << symbol << std::endl;
}

void BinanceWebSocket::subscribe_kline(const std::string& symbol, const std::string& interval) {
    if (conn_type_ != WsConnectionType::MARKET) {
        std::cerr << "[BinanceWebSocket] 错误：非行情连接无法订阅" << std::endl;
        return;
    }
    
    // Binance行情流格式: <symbol>@kline_<interval>
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {symbol + "@kline_" + interval}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅K线: " << symbol << "@" << interval << std::endl;
}

void BinanceWebSocket::subscribe_mini_ticker(const std::string& symbol) {
    if (conn_type_ != WsConnectionType::MARKET) return;
    
    std::string stream = symbol.empty() ? "!miniTicker@arr" : symbol + "@miniTicker";
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
}

void BinanceWebSocket::subscribe_ticker(const std::string& symbol) {
    if (conn_type_ != WsConnectionType::MARKET) return;
    
    std::string stream = symbol.empty() ? "!ticker@arr" : symbol + "@ticker";
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅Ticker: " << symbol << std::endl;
}

void BinanceWebSocket::subscribe_depth(
    const std::string& symbol,
    int levels,
    int update_speed
) {
    if (conn_type_ != WsConnectionType::MARKET) return;

    // depth<levels> 快照可能不带 symbol 字段，记录一下用于兜底
    last_depth_symbol_ = symbol;
    
    // Binance深度流格式: <symbol>@depth<levels>@<update_speed>ms
    std::string stream = symbol + "@depth" + std::to_string(levels);
    if (update_speed == 100) {
        stream += "@100ms";
    }
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅深度: " << stream << std::endl;
}

void BinanceWebSocket::subscribe_book_ticker(const std::string& symbol) {
    if (conn_type_ != WsConnectionType::MARKET) return;
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {symbol + "@bookTicker"}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
}

void BinanceWebSocket::unsubscribe(const std::string& stream_name) {
    nlohmann::json unsub_msg = {
        {"method", "UNSUBSCRIBE"},
        {"params", {stream_name}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(unsub_msg);
}

void BinanceWebSocket::subscribe_user_data(const std::string& listen_key) {
    (void)listen_key;
    if (conn_type_ != WsConnectionType::USER_DATA) {
        std::cerr << "[BinanceWebSocket] 错误：非用户数据连接" << std::endl;
        return;
    }
    
    // 用户数据流通过URL连接，不需要发送订阅消息
    // URL格式: wss://stream.binance.com/ws/<listenKey>
    std::cout << "[BinanceWebSocket] 用户数据流已订阅（通过listenKey）" << std::endl;
}

// ==================== 消息解析 ====================

void BinanceWebSocket::parse_trade(const nlohmann::json& data) {
    if (!trade_callback_) return;
    
    try {
        std::string symbol = data.value("s", "");
        std::string trade_id = std::to_string(safe_stoll(data, "t", 0));  // 交易ID
        double price = safe_stod(data, "p", 0.0);
        double quantity = safe_stod(data, "q", 0.0);
        int64_t timestamp = safe_stoll(data, "T", 0);
        bool is_buyer_maker = data.value("m", false);  // true: 买方是 maker
        
        auto trade = std::make_shared<TradeData>(
            symbol,
            trade_id,
            price,
            quantity,
            "binance"
        );
        
        // 设置时间戳
        trade->set_timestamp(timestamp);

        // Binance trade stream:
        //   m = true  => buyer is maker => taker is SELL
        //   m = false => buyer is taker => taker is BUY
        trade->set_is_buyer_maker(is_buyer_maker);
        trade->set_side(is_buyer_maker ? "SELL" : "BUY");
        
        trade_callback_(trade);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析trade失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_kline(const nlohmann::json& data) {
    if (!kline_callback_) return;
    
    try {
        std::string symbol = data.value("s", "");
        auto k = data["k"];
        
        // 从K线数据中获取interval（如果有）
        std::string interval = k.value("i", "1m");
        
        auto kline = std::make_shared<KlineData>(
            symbol,
            interval,
            safe_stod(k, "o", 0.0),  // open
            safe_stod(k, "h", 0.0),  // high
            safe_stod(k, "l", 0.0),  // low
            safe_stod(k, "c", 0.0),  // close
            safe_stod(k, "v", 0.0),  // volume
            "binance"                // exchange
        );
        
        // 设置时间戳
        kline->set_timestamp(safe_stoll(k, "t", 0));
        
        kline_callback_(kline);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析kline失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_ticker(const nlohmann::json& data) {
    if (!ticker_callback_) return;
    
    try {
        std::string symbol = data.value("s", "");
        double last_price = safe_stod(data, "c", 0.0);
        
        auto ticker = std::make_shared<TickerData>(symbol, last_price, "binance");
        ticker->set_bid_price(safe_stod(data, "b", 0.0));
        ticker->set_ask_price(safe_stod(data, "a", 0.0));
        ticker->set_high_24h(safe_stod(data, "h", 0.0));
        ticker->set_low_24h(safe_stod(data, "l", 0.0));
        ticker->set_volume_24h(safe_stod(data, "v", 0.0));
        ticker->set_timestamp(safe_stoll(data, "E", 0));
        
        ticker_callback_(ticker);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析ticker失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_depth(const nlohmann::json& data) {
    if (!orderbook_callback_) return;
    
    try {
        std::string symbol = data.value("s", last_depth_symbol_);
        
        // 收集买卖盘数据
        std::vector<OrderBookData::PriceLevel> bids;
        std::vector<OrderBookData::PriceLevel> asks;
        
        // 两种格式：
        // 1) depthUpdate: b / a
        // 2) depth<levels> 快照: bids / asks
        if (data.contains("b")) {
            for (const auto& bid : data["b"]) {
                double price = std::stod(bid[0].get<std::string>());
                double qty = std::stod(bid[1].get<std::string>());
                bids.push_back({price, qty});
            }
        } else if (data.contains("bids")) {
            for (const auto& bid : data["bids"]) {
                double price = std::stod(bid[0].get<std::string>());
                double qty = std::stod(bid[1].get<std::string>());
                bids.push_back({price, qty});
            }
        }
        
        if (data.contains("a")) {
            for (const auto& ask : data["a"]) {
                double price = std::stod(ask[0].get<std::string>());
                double qty = std::stod(ask[1].get<std::string>());
                asks.push_back({price, qty});
            }
        } else if (data.contains("asks")) {
            for (const auto& ask : data["asks"]) {
                double price = std::stod(ask[0].get<std::string>());
                double qty = std::stod(ask[1].get<std::string>());
                asks.push_back({price, qty});
            }
        }
        
        // 创建OrderBookData对象
        auto orderbook = std::make_shared<OrderBookData>(symbol, bids, asks, "binance");
        orderbook->set_timestamp(safe_stoll(data, "E", 0));
        
        orderbook_callback_(orderbook);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析depth失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_book_ticker(const nlohmann::json& data) {
    if (!ticker_callback_) return;
    
    try {
        std::string symbol = data.value("s", "");
        double bid = safe_stod(data, "b", 0.0);
        double ask = safe_stod(data, "a", 0.0);
        
        double last = 0.0;
        if (bid > 0.0 && ask > 0.0) last = (bid + ask) / 2.0;
        else if (bid > 0.0) last = bid;
        else last = ask;
        
        auto ticker = std::make_shared<TickerData>(symbol, last, "binance");
        if (bid > 0.0) ticker->set_bid_price(bid);
        if (ask > 0.0) ticker->set_ask_price(ask);
        ticker->set_timestamp(safe_stoll(data, "E", 0));
        
        ticker_callback_(ticker);
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析bookTicker失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_order_update(const nlohmann::json& data) {
    if (!order_update_callback_) return;
    
    try {
        // 解析订单信息
        std::string symbol = data.value("s", "");
        std::string client_order_id = data.value("c", "");
        int64_t order_id = safe_stoll(data, "i", 0);
        
        // 解析订单类型和方向
        std::string order_type_str = data.value("o", "LIMIT");
        std::string side_str = data.value("S", "BUY");
        
        // 将 Binance OrderType 转换为 core OrderType
        ::trading::OrderType order_type = ::trading::OrderType::LIMIT;
        if (order_type_str == "MARKET") {
            order_type = ::trading::OrderType::MARKET;
        } else if (order_type_str == "LIMIT_MAKER") {
            order_type = ::trading::OrderType::POST_ONLY;
        }
        // 其他类型（STOP_LOSS等）在core中没有对应，使用LIMIT
        
        ::trading::OrderSide side = (side_str == "BUY") ? 
            ::trading::OrderSide::BUY : ::trading::OrderSide::SELL;
        
        // 价格和数量
        double price = safe_stod(data, "p", 0.0);
        double quantity = safe_stod(data, "q", 0.0);
        
        // 创建Order对象（使用正确的构造函数）
        auto order = std::make_shared<Order>(
            symbol,
            order_type,
            side,
            quantity,
            price,
            "binance"
        );
        
        // 设置订单ID和客户订单ID
        order->set_client_order_id(client_order_id);
        if (order_id > 0) {
            order->set_exchange_order_id(std::to_string(order_id));
        }
        
        // 解析订单状态
        std::string status = data.value("X", "");
        if (status == "NEW") {
            order->set_state(::trading::OrderState::SUBMITTED);
        } else if (status == "FILLED") {
            order->set_state(::trading::OrderState::FILLED);
        } else if (status == "CANCELED") {
            order->set_state(::trading::OrderState::CANCELLED);
        } else if (status == "PARTIALLY_FILLED") {
            order->set_state(::trading::OrderState::PARTIALLY_FILLED);
        } else if (status == "REJECTED") {
            order->set_state(::trading::OrderState::REJECTED);
        }
        
        // 已成交数量
        order->set_filled_quantity(safe_stod(data, "z", 0.0));
        
        order_update_callback_(order);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析订单更新失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_account_update(const nlohmann::json& data) {
    if (!account_update_callback_) return;
    
    try {
        account_update_callback_(data);
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析账户更新失败: " << e.what() << std::endl;
    }
}

} // namespace binance
} // namespace trading

