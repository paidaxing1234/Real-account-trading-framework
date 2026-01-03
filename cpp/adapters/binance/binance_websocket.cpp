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
        // 测试网
        if (conn_type_ == WsConnectionType::TRADING) {
            // WebSocket 交易 API 测试网
            if (market_type_ == MarketType::FUTURES) {
                // 合约测试网 ws-fapi（文档确认有）
                return "wss://testnet.binancefuture.com/ws-fapi/v1";
            } else {
                // SPOT 测试网 ws-api
                return "wss://ws-api.testnet.binance.vision/ws-api/v3";
            }
        } else {
            // 行情推送测试网
            if (market_type_ == MarketType::FUTURES) {
                return "wss://fstream.binancefuture.com/ws";
            }
            if (market_type_ == MarketType::COIN_FUTURES) {
                return "wss://dstream.binancefuture.com/ws";
            }
            return "wss://stream.testnet.binance.vision/ws";
        }
    } else {
        // 主网
        if (conn_type_ == WsConnectionType::TRADING) {
            // WebSocket 交易 API 主网
            if (market_type_ == MarketType::FUTURES || market_type_ == MarketType::COIN_FUTURES) {
                // 合约主网 ws-fapi
                return "wss://ws-fapi.binance.com/ws-fapi/v1";
            } else {
                // SPOT 主网 ws-api
                return "wss://ws-api.binance.com:443/ws-api/v3";
            }
        } else {
            // 行情推送主网
            if (market_type_ == MarketType::FUTURES) {
                return "wss://fstream.binance.com/ws";
            } else if (market_type_ == MarketType::COIN_FUTURES) {
                return "wss://dstream.binance.com/ws";
            } else {
                return "wss://stream.binance.com:9443/ws";
            }
        }
    }
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

        // 1. 部分频道可能直接返回数组（如 !miniTicker@arr / !ticker@arr）
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
                } else if (event_type == "markPriceUpdate") {
                    parse_mark_price(item);
                }
            }
            return;
        }
        
        // 2. WebSocket Trading API 响应（有 id + status 字段）
        if (data.contains("id") && data.contains("status")) {
            if (order_response_callback_) {
                order_response_callback_(data);
            }
            return;
        }
        
        // 3. 行情数据流（有 e 字段）
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
            } else if (event_type == "markPriceUpdate") {
                parse_mark_price(data);
            }
        } else {
            // 4. depth<levels> 快照没有 e 字段：{ lastUpdateId, bids, asks }
            if (data.contains("lastUpdateId") && (data.contains("bids") || data.contains("asks"))) {
                parse_depth(data);
            }
        }
        
        // 4. Ping/Pong
        if (data.contains("ping")) {
            nlohmann::json pong = {{"pong", data["ping"]}};
            send_message(pong);
        }
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析消息失败: " << e.what() << std::endl;
        std::cerr << "[BinanceWebSocket] 原始消息: " << message << std::endl;
    }
}

// ==================== WebSocket Trading API ====================

std::string BinanceWebSocket::generate_request_id() {
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

std::string BinanceWebSocket::position_side_to_string(PositionSide ps) {
    switch (ps) {
        case PositionSide::BOTH: return "BOTH";
        case PositionSide::LONG: return "LONG";
        case PositionSide::SHORT: return "SHORT";
        default: return "BOTH";
    }
}

std::string BinanceWebSocket::place_order_ws(
    const std::string& symbol,
    OrderSide side,
    OrderType type,
    const std::string& quantity,
    const std::string& price,
    TimeInForce time_in_force,
    PositionSide position_side,
    const std::string& client_order_id
) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法下单" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    // 构造请求参数
    nlohmann::json params = {
        {"apiKey", api_key_},                    // ⭐ 必填（WebSocket Trading API）
        {"symbol", symbol},
        {"side", order_side_to_string(side)},
        {"type", order_type_to_string(type)},
        {"quantity", quantity},
        {"timestamp", get_timestamp()}
    };
    
    // 限价单必须提供价格
    if (!price.empty() && type == OrderType::LIMIT) {
        params["price"] = price;
        params["timeInForce"] = time_in_force_to_string(time_in_force);
    }
    
    // 客户自定义订单ID
    if (!client_order_id.empty()) {
        params["newClientOrderId"] = client_order_id;
    }
    
    // 合约特有参数（SPOT ws-api 不支持，会导致 -1104）
    if (market_type_ != MarketType::SPOT) {
        params["positionSide"] = position_side_to_string(position_side);
    }
    
    // ⭐ 关键：按文档要求，签名 payload 必须按 key 字母序排序
    std::vector<std::pair<std::string, std::string>> sorted_params;
    for (auto it = params.begin(); it != params.end(); ++it) {
        std::string value = it.value().dump();
        // 去除JSON字符串的引号
        if (value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.length() - 2);
        }
        sorted_params.push_back({it.key(), value});
    }
    std::sort(sorted_params.begin(), sorted_params.end());
    
    // 构造查询字符串
    std::ostringstream query;
    bool first = true;
    for (const auto& kv : sorted_params) {
        if (!first) query << "&";
        query << kv.first << "=" << kv.second;
        first = false;
    }
    std::string query_str = query.str();
    
    // 生成签名
    std::string signature = create_signature(query_str);
    params["signature"] = signature;
    
    // 构造完整请求
    nlohmann::json request = {
        {"id", req_id},
        {"method", "order.place"},
        {"params", params}
    };
    
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
        {"apiKey", api_key_},               // ⭐ 必填
        {"symbol", symbol},
        {"timestamp", get_timestamp()}
    };
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    // 创建查询字符串
    std::ostringstream query;
    bool first = true;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (!first) query << "&";
        std::string value = it.value().dump();
        if (value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.length() - 2);
        }
        query << it.key() << "=" << value;
        first = false;
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
        {"apiKey", api_key_},               // ⭐ 必填
        {"symbol", symbol},
        {"timestamp", get_timestamp()}
    };
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    // 创建查询字符串
    std::ostringstream query;
    bool first = true;
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (!first) query << "&";
        std::string value = it.value().dump();
        if (value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.length() - 2);
        }
        query << it.key() << "=" << value;
        first = false;
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

std::string BinanceWebSocket::modify_order_ws(
    const std::string& symbol,
    OrderSide side,
    const std::string& quantity,
    const std::string& price,
    int64_t order_id,
    const std::string& client_order_id,
    PositionSide position_side
) {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法修改订单" << std::endl;
        return "";
    }
    
    std::string req_id = generate_request_id();
    
    nlohmann::json params = {
        {"apiKey", api_key_},                    // ⭐ 必填
        {"symbol", symbol},
        {"side", order_side_to_string(side)},
        {"quantity", quantity},
        {"price", price},
        {"timestamp", get_timestamp()}
    };
    
    // orderId / origClientOrderId 二选一
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    // 合约特有参数
    if (market_type_ != MarketType::SPOT) {
        params["positionSide"] = position_side_to_string(position_side);
        params["origType"] = "LIMIT";  // 修改订单文档示例里有这个字段
    }
    
    // 按字母序排序（用于签名）
    std::vector<std::pair<std::string, std::string>> sorted_params;
    for (auto it = params.begin(); it != params.end(); ++it) {
        std::string value = it.value().dump();
        if (value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.length() - 2);
        }
        sorted_params.push_back({it.key(), value});
    }
    std::sort(sorted_params.begin(), sorted_params.end());
    
    // 构造查询字符串
    std::ostringstream query;
    bool first = true;
    for (const auto& kv : sorted_params) {
        if (!first) query << "&";
        query << kv.first << "=" << kv.second;
        first = false;
    }
    
    std::string signature = create_signature(query.str());
    params["signature"] = signature;
    
    nlohmann::json request = {
        {"id", req_id},
        {"method", "order.modify"},
        {"params", params}
    };
    
    send_message(request);
    
    return req_id;
}

// ==================== 行情订阅（已测试） ====================

void BinanceWebSocket::subscribe_trade(const std::string& symbol) {
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
    std::string stream = symbol.empty() ? "!miniTicker@arr" : symbol + "@miniTicker";
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
}

void BinanceWebSocket::subscribe_ticker(const std::string& symbol) {
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
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {symbol + "@bookTicker"}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
}

void BinanceWebSocket::subscribe_mark_price(const std::string& symbol, int update_speed) {
    std::string stream = symbol + "@markPrice";
    if (update_speed == 1000) {
        stream += "@1s";
    }
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅标记价格: " << stream << std::endl;
}

void BinanceWebSocket::subscribe_all_mark_prices(int update_speed) {
    std::string stream = "!markPrice@arr";
    if (update_speed == 1000) {
        stream += "@1s";
    }
    
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅全市场标记价格: " << stream << std::endl;
}

void BinanceWebSocket::unsubscribe(const std::string& stream_name) {
    nlohmann::json unsub_msg = {
        {"method", "UNSUBSCRIBE"},
        {"params", {stream_name}},
        {"id", request_id_counter_.fetch_add(1)}
    };
    
    send_message(unsub_msg);
}

// ==================== 消息解析（已测试的行情推送） ====================

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
            safe_stod(k, "o", 0.0),  // open - 开盘价
            safe_stod(k, "h", 0.0),  // high - 最高价
            safe_stod(k, "l", 0.0),  // low - 最低价
            safe_stod(k, "c", 0.0),  // close - 收盘价
            safe_stod(k, "v", 0.0),  // volume - 成交量
            "binance"                // exchange
        );
        
        // 设置时间戳（K线起始时间）
        kline->set_timestamp(safe_stoll(k, "t", 0));
        
        // ⭐ 关键：K线是否完结（"x": true/false）
        // false = 未完结（还在当前 interval 内，会继续更新）
        // true  = 已完结（进入下一根K线了）
        kline->set_confirmed(k.value("x", false));
        
        // 成交额（可选）
        double turnover = safe_stod(k, "q", 0.0);
        if (turnover > 0.0) {
            kline->set_turnover(turnover);
        }
        
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

void BinanceWebSocket::parse_mark_price(const nlohmann::json& data) {
    if (!mark_price_callback_) return;
    
    try {
        auto mp = std::make_shared<MarkPriceData>();
        mp->symbol = data.value("s", "");
        mp->mark_price = safe_stod(data, "p", 0.0);
        mp->index_price = safe_stod(data, "i", 0.0);
        mp->funding_rate = safe_stod(data, "r", 0.0);
        mp->next_funding_time = safe_stoll(data, "T", 0);
        mp->timestamp = safe_stoll(data, "E", 0);
        
        mark_price_callback_(mp);
        
    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析markPrice失败: " << e.what() << std::endl;
    }
}

} // namespace binance
} // namespace trading

