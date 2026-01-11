/**
 * @file binance_websocket.cpp
 * @brief Binance WebSocket 客户端实现
 *
 * 使用公共 WebSocketClient 实现 WebSocket 连接
 *
 * @author Sequence Team
 * @date 2024-12
 */

#include "binance_websocket.h"
#include "../../network/ws_client.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <thread>
#include <ctime>
#include <algorithm>
#include <openssl/hmac.h>
#include <openssl/sha.h>

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

// ==================== BinanceWebSocket实现 ====================

BinanceWebSocket::BinanceWebSocket(
    const std::string& api_key,
    const std::string& secret_key,
    WsConnectionType conn_type,
    MarketType market_type,
    bool is_testnet,
    const core::WebSocketConfig& ws_config
)
    : api_key_(api_key)
    , secret_key_(secret_key)
    , conn_type_(conn_type)
    , market_type_(market_type)
    , is_testnet_(is_testnet)
    , listen_key_("")
    , ws_config_(ws_config)
    , impl_(std::make_shared<core::WebSocketClient>(ws_config))
{
    ws_url_ = build_ws_url();

    std::cout << "[BinanceWebSocket] 初始化 (连接类型=" << (int)conn_type_ << ")" << std::endl;
    std::cout << "[BinanceWebSocket] URL: " << ws_url_ << std::endl;
}

BinanceWebSocket::~BinanceWebSocket() {
    stop_auto_refresh_listen_key();
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
        } else if (conn_type_ == WsConnectionType::USER) {
            std::string base;
            if (market_type_ == MarketType::FUTURES) {
                base = "wss://fstream.binancefuture.com/ws";
            } else if (market_type_ == MarketType::COIN_FUTURES) {
                base = "wss://dstream.binancefuture.com/ws";
            } else {
                base = "wss://stream.testnet.binance.vision/ws";
            }
            if (listen_key_.empty()) return base;
            return base + "/" + listen_key_;
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
        } else if (conn_type_ == WsConnectionType::USER) {
            std::string base;
            if (market_type_ == MarketType::FUTURES) {
                base = "wss://fstream.binance.com/ws";
            } else if (market_type_ == MarketType::COIN_FUTURES) {
                base = "wss://dstream.binance.com/ws";
            } else {
                base = "wss://stream.binance.com:9443/ws";
            }
            if (listen_key_.empty()) return base;
            return base + "/" + listen_key_;
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

bool BinanceWebSocket::connect_user_stream(const std::string& listen_key) {
    listen_key_ = listen_key;
    ws_url_ = build_ws_url();
    std::cout << "[BinanceWebSocket] 🔗 准备连接用户数据流" << std::endl;
    std::cout << "[BinanceWebSocket] 📍 URL: " << ws_url_ << std::endl;
    std::cout << "[BinanceWebSocket] 🔑 listenKey: " << listen_key << std::endl;
    bool result = connect();
    if (result) {
        std::cout << "[BinanceWebSocket] ✅ 用户数据流连接成功" << std::endl;
    } else {
        std::cerr << "[BinanceWebSocket] ❌ 用户数据流连接失败" << std::endl;
    }
    return result;
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

    // 设置关闭回调（支持自动重连）
    impl_->set_close_callback([this]() {
        is_connected_.store(false);
        is_running_.store(false);
        if (reconnect_enabled_.load()) {
            need_reconnect_.store(true);
            std::cout << "[BinanceWebSocket] 连接断开，将由监控线程处理重连" << std::endl;
        } else {
            std::cout << "[BinanceWebSocket] 连接已关闭" << std::endl;
        }
    });

    // 设置失败回调（支持自动重连）
    impl_->set_fail_callback([this]() {
        is_connected_.store(false);
        is_running_.store(false);
        if (reconnect_enabled_.load()) {
            need_reconnect_.store(true);
            std::cout << "[BinanceWebSocket] 连接失败，将由监控线程处理重连" << std::endl;
        } else {
            std::cout << "[BinanceWebSocket] 连接失败" << std::endl;
        }
    });

    // 连接WebSocket
    if (!impl_->connect(ws_url_)) {
        std::cerr << "[BinanceWebSocket] 连接失败" << std::endl;
        return false;
    }

    is_connected_.store(true);
    is_running_.store(true);

    // 启动重连监控线程（如果启用了自动重连）
    if (reconnect_enabled_.load() && !reconnect_monitor_thread_) {
        reconnect_monitor_thread_ = std::make_unique<std::thread>([this]() {
            std::cout << "[BinanceWebSocket] 重连监控线程已启动" << std::endl;
            while (reconnect_enabled_.load()) {
                // 使用条件变量等待，可被快速唤醒
                {
                    std::unique_lock<std::mutex> lock(reconnect_mutex_);
                    reconnect_cv_.wait_for(lock, std::chrono::milliseconds(500), [this]() {
                        return need_reconnect_.load() || !reconnect_enabled_.load();
                    });
                }

                // 检查是否需要退出
                if (!reconnect_enabled_.load()) {
                    break;
                }

                if (need_reconnect_.load()) {
                    std::cout << "[BinanceWebSocket] 检测到需要重连..." << std::endl;

                    // 等待一段时间再重连（可被中断）
                    // ⭐ 重要：等待足够长的时间让 websocketpp 完成内部清理
                    {
                        std::unique_lock<std::mutex> lock(reconnect_mutex_);
                        if (reconnect_cv_.wait_for(lock, std::chrono::seconds(5), [this]() {
                            return !reconnect_enabled_.load();
                        })) {
                            break;  // 被要求退出
                        }
                    }

                    // 重置重连标志
                    need_reconnect_.store(false);

                    // ===== 安全重连：不主动调用 disconnect() =====
                    // websocketpp 在连接断开后可能还在进行内部清理
                    // 直接调用 disconnect() 可能导致 double free
                    // 让 connect() 方法自己处理旧连接的清理

                    // 1. ⭐ 先清除回调，防止在重连过程中触发旧回调
                    impl_->clear_callbacks();

                    // 2. 不主动调用 disconnect()，避免 double free
                    // impl_->connect() 内部会安全地清理旧连接
                    std::cout << "[BinanceWebSocket] 准备重新建立连接..." << std::endl;

                    // 3. 等待底层 socket 完全释放 (TIME_WAIT)
                    std::this_thread::sleep_for(std::chrono::seconds(2));

                    // 4. 重新设置回调
                    impl_->set_message_callback([this](const std::string& message) {
                        on_message(message);
                    });

                    impl_->set_close_callback([this]() {
                        is_connected_.store(false);
                        is_running_.store(false);
                        if (reconnect_enabled_.load()) {
                            need_reconnect_.store(true);
                            reconnect_cv_.notify_all();
                        }
                    });

                    impl_->set_fail_callback([this]() {
                        is_connected_.store(false);
                        is_running_.store(false);
                        if (reconnect_enabled_.load()) {
                            need_reconnect_.store(true);
                            reconnect_cv_.notify_all();
                        }
                    });

                    // 5. 复用 impl_ 进行连接（ws_client.cpp 中会安全地清理旧连接并调用 client_.reset()）
                    std::cout << "[BinanceWebSocket] 尝试重新连接..." << std::endl;
                    if (impl_->connect(ws_url_)) {
                        is_connected_.store(true);
                        is_running_.store(true);
                        std::cout << "[BinanceWebSocket] ✅ 重连成功" << std::endl;

                        // 等待连接完全建立
                        std::this_thread::sleep_for(std::chrono::milliseconds(500));

                        // 重新订阅
                        resubscribe_all();
                    } else {
                        std::cerr << "[BinanceWebSocket] ❌ 重连失败，稍后重试" << std::endl;
                        need_reconnect_.store(true);
                    }
                }
            }
            std::cout << "[BinanceWebSocket] 重连监控线程已退出" << std::endl;
        });
    }

    std::cout << "[BinanceWebSocket] 连接成功" << std::endl;
    return true;
}

void BinanceWebSocket::disconnect() {
    // 防止重复断开
    bool expected = false;
    if (!is_disconnected_.compare_exchange_strong(expected, true)) {
        // 已经断开过了，直接返回
        return;
    }

    std::cout << "[BinanceWebSocket] 断开连接..." << std::endl;

    // 禁用重连，防止断开后又重连
    reconnect_enabled_.store(false);
    need_reconnect_.store(false);
    is_running_.store(false);
    is_connected_.store(false);

    // 唤醒重连监控线程，使其快速退出
    reconnect_cv_.notify_all();

    // 等待重连监控线程退出
    if (reconnect_monitor_thread_ && reconnect_monitor_thread_->joinable()) {
        reconnect_monitor_thread_->join();
        reconnect_monitor_thread_.reset();
    }

    if (impl_) {
        // ⭐ 先清除回调，防止断开过程中触发回调导致问题
        impl_->clear_callbacks();
        // 直接重置 impl_，这会触发其析构函数的 shutdown()
        // 这样在 BinanceWebSocket 析构时就不会再有 impl_ 需要处理
        impl_.reset();
    }

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
        
        // 用户数据流：打印所有收到的消息（用于调试）
        if (conn_type_ == WsConnectionType::USER) {
            if (data.contains("e")) {
                std::string event_type = data["e"].get<std::string>();
                std::cout << "[BinanceWebSocket] 📥 收到用户数据流事件: " << event_type << std::endl;
            } else {
                std::cout << "[BinanceWebSocket] 📥 收到用户数据流消息（无e字段）: " << message.substr(0, 200) << std::endl;
            }
        }
        
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
                } else if (event_type == "ACCOUNT_UPDATE") {
                    if (conn_type_ == WsConnectionType::USER) {
                        std::cout << "[BinanceWebSocket] ✅ 数组格式中检测到 ACCOUNT_UPDATE 事件" << std::endl;
                    }
                    parse_account_update(item);
                } else if (event_type == "ORDER_TRADE_UPDATE") {
                    // 订单成交更新事件（也是用户数据流的一部分）
                    if (conn_type_ == WsConnectionType::USER) {
                        std::cout << "[BinanceWebSocket] ✅ 数组格式中检测到 ORDER_TRADE_UPDATE 事件" << std::endl;
                    }
                    parse_order_trade_update(item);
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
            } else if (event_type == "ACCOUNT_UPDATE") {
                if (conn_type_ == WsConnectionType::USER) {
                    std::cout << "[BinanceWebSocket] ✅ 检测到 ACCOUNT_UPDATE 事件" << std::endl;
                }
                parse_account_update(data);
            } else if (event_type == "ORDER_TRADE_UPDATE") {
                // 订单成交更新事件（也是用户数据流的一部分）
                if (conn_type_ == WsConnectionType::USER) {
                    std::cout << "[BinanceWebSocket] ✅ 检测到 ORDER_TRADE_UPDATE 事件" << std::endl;
                }
                parse_order_trade_update(data);
            } else {
                // 未知事件类型（用户数据流）
                if (conn_type_ == WsConnectionType::USER) {
                    std::cout << "[BinanceWebSocket] ⚠️ 未知的用户数据流事件类型: " << event_type << std::endl;
                    std::cout << "[BinanceWebSocket] 📋 完整消息: " << data.dump() << std::endl;
                }
            }
        } else {
            // 4. depth<levels> 快照没有 e 字段：{ lastUpdateId, bids, asks }
            if (data.contains("lastUpdateId") && (data.contains("bids") || data.contains("asks"))) {
                parse_depth(data);
            } else if (conn_type_ == WsConnectionType::USER) {
                // 用户数据流中可能有其他格式的消息
                std::cout << "[BinanceWebSocket] ⚠️ 用户数据流收到无e字段的消息: " << message.substr(0, 200) << std::endl;
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
    
    // ⭐ 按字母序排序参数（Binance签名要求）
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
    
    // ⭐ 按字母序排序参数（Binance签名要求）
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

std::string BinanceWebSocket::start_user_data_stream_ws() {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法生成 listenKey" << std::endl;
        return "";
    }
    std::string req_id = generate_request_id();
    nlohmann::json request = {
        {"id", req_id},
        {"method", "userDataStream.start"},
        {"params", {{"apiKey", api_key_}}}
    };
    send_message(request);
    return req_id;
}

std::string BinanceWebSocket::ping_user_data_stream_ws() {
    if (conn_type_ != WsConnectionType::TRADING) {
        std::cerr << "[BinanceWebSocket] 错误：非交易API连接无法续期 listenKey" << std::endl;
        return "";
    }
    std::string req_id = generate_request_id();
    nlohmann::json request = {
        {"id", req_id},
        {"method", "userDataStream.ping"},
        {"params", {{"apiKey", api_key_}}}
    };
    send_message(request);
    return req_id;
}

// ==================== 行情订阅（已测试） ====================

void BinanceWebSocket::subscribe_trade(const std::string& symbol) {
    // Binance行情流格式: <symbol>@trade
    std::string stream = symbol + "@trade";

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
    }

    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅逐笔成交: " << symbol << std::endl;
}

void BinanceWebSocket::subscribe_streams_batch(const std::vector<std::string>& streams) {
    if (streams.empty()) return;

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        for (const auto& stream : streams) {
            subscriptions_[stream] = stream;
        }
    }

    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", streams},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 批量订阅: " << streams.size() << " 个stream\n";
}

void BinanceWebSocket::subscribe_trades_batch(const std::vector<std::string>& symbols) {
    if (symbols.empty()) return;

    std::vector<std::string> streams;
    streams.reserve(symbols.size());
    for (const auto& sym : symbols) {
        streams.push_back(sym + "@trade");
    }

    subscribe_streams_batch(streams);
}

void BinanceWebSocket::subscribe_klines_batch(const std::vector<std::string>& symbols, const std::string& interval) {
    if (symbols.empty()) return;

    std::vector<std::string> streams;
    streams.reserve(symbols.size());
    for (const auto& sym : symbols) {
        streams.push_back(sym + "@kline_" + interval);
    }

    subscribe_streams_batch(streams);
}

void BinanceWebSocket::subscribe_depths_batch(const std::vector<std::string>& symbols, int levels, int update_speed) {
    if (symbols.empty()) return;

    std::vector<std::string> streams;
    streams.reserve(symbols.size());
    for (const auto& sym : symbols) {
        streams.push_back(sym + "@depth" + std::to_string(levels) + "@" + std::to_string(update_speed) + "ms");
    }

    subscribe_streams_batch(streams);
}

void BinanceWebSocket::subscribe_kline(const std::string& symbol, const std::string& interval) {
    // Binance行情流格式: <symbol>@kline_<interval>
    std::string stream = symbol + "@kline_" + interval;

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
    }

    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] 订阅K线: " << symbol << "@" << interval << std::endl;
}

void BinanceWebSocket::subscribe_mini_ticker(const std::string& symbol) {
    std::string stream = symbol.empty() ? "!miniTicker@arr" : symbol + "@miniTicker";

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
    }

    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
}

void BinanceWebSocket::subscribe_ticker(const std::string& symbol) {
    std::string stream = symbol.empty() ? "!ticker@arr" : symbol + "@ticker";

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
    }

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

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
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
    std::string stream = symbol + "@bookTicker";

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
    }

    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", {stream}},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
}

void BinanceWebSocket::subscribe_mark_price(const std::string& symbol, int update_speed) {
    std::string stream = symbol + "@markPrice";
    if (update_speed == 1000) {
        stream += "@1s";
    }

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
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

    // 记录订阅状态
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_[stream] = stream;
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
    // 移除订阅记录
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        subscriptions_.erase(stream_name);
    }

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
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";

        trade_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析trade失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_kline(const nlohmann::json& data) {
    if (!kline_callback_) return;

    try {
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";

        kline_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析kline失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_ticker(const nlohmann::json& data) {
    if (!ticker_callback_) return;

    try {
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";

        ticker_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析ticker失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_depth(const nlohmann::json& data) {
    if (!orderbook_callback_) return;

    try {
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";
        // 如果没有symbol字段，使用last_depth_symbol_
        if (!raw_data.contains("s") && !last_depth_symbol_.empty()) {
            raw_data["symbol"] = last_depth_symbol_;
        }

        orderbook_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析depth失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_book_ticker(const nlohmann::json& data) {
    if (!ticker_callback_) return;

    try {
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";

        ticker_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析bookTicker失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_mark_price(const nlohmann::json& data) {
    if (!mark_price_callback_) return;

    try {
        // 直接传递原始JSON，添加exchange信息
        nlohmann::json raw_data = data;
        raw_data["exchange"] = "binance";

        mark_price_callback_(raw_data);

    } catch (const std::exception& e) {
        std::cerr << "[BinanceWebSocket] 解析markPrice失败: " << e.what() << std::endl;
    }
}

void BinanceWebSocket::parse_account_update(const nlohmann::json& data) {
    if (!account_update_callback_) {
        std::cerr << "[BinanceWebSocket] ⚠️ ACCOUNT_UPDATE 回调未设置" << std::endl;
        return;
    }
    
    // 调试输出
    if (conn_type_ == WsConnectionType::USER) {
        std::cout << "[BinanceWebSocket] 📨 收到 ACCOUNT_UPDATE 事件" << std::endl;
    }
    
    account_update_callback_(data);
}

void BinanceWebSocket::parse_order_trade_update(const nlohmann::json& data) {
    if (!order_trade_update_callback_) {
        // 如果没有设置回调，至少打印一下
        if (conn_type_ == WsConnectionType::USER) {
            std::cout << "[BinanceWebSocket] ⚠️ ORDER_TRADE_UPDATE 回调未设置，但收到事件" << std::endl;
            std::cout << "[BinanceWebSocket] 📋 ORDER_TRADE_UPDATE 内容: " << data.dump(2) << std::endl;
        }
        return;
    }
    
    // 调试输出
    if (conn_type_ == WsConnectionType::USER) {
        std::cout << "[BinanceWebSocket] 📨 收到 ORDER_TRADE_UPDATE 事件" << std::endl;
    }
    
    order_trade_update_callback_(data);
}

void BinanceWebSocket::start_auto_refresh_listen_key(
    BinanceRestAPI* rest_api,
    int interval_seconds
) {
    if (conn_type_ != WsConnectionType::USER) {
        std::cerr << "[BinanceWebSocket] ⚠️ 只有用户数据流连接才需要刷新 listenKey" << std::endl;
        return;
    }
    
    if (listen_key_.empty()) {
        std::cerr << "[BinanceWebSocket] ⚠️ listenKey 为空，无法启动自动刷新" << std::endl;
        return;
    }
    
    if (refresh_running_.load()) {
        std::cout << "[BinanceWebSocket] ⚠️ 自动刷新已在运行" << std::endl;
        return;
    }
    
    rest_api_for_refresh_ = rest_api;
    refresh_interval_seconds_ = interval_seconds;
    refresh_running_.store(true);
    
    refresh_thread_ = std::make_unique<std::thread>([this]() {
        std::cout << "[BinanceWebSocket] 🔄 启动自动刷新 listenKey（间隔: " 
                  << refresh_interval_seconds_ << "秒）" << std::endl;
        
        while (refresh_running_.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(refresh_interval_seconds_));
            
            if (!refresh_running_.load()) break;
            
            try {
                if (rest_api_for_refresh_) {
                    rest_api_for_refresh_->keepalive_listen_key(listen_key_);
                    std::cout << "[BinanceWebSocket] ✅ listenKey 已刷新" << std::endl;
                }
            } catch (const std::exception& e) {
                std::cerr << "[BinanceWebSocket] ❌ 刷新 listenKey 失败: " << e.what() << std::endl;
            }
        }
        
        std::cout << "[BinanceWebSocket] 🔄 自动刷新 listenKey 已停止" << std::endl;
    });
}

void BinanceWebSocket::stop_auto_refresh_listen_key() {
    if (!refresh_running_.load()) {
        return;
    }

    refresh_running_.store(false);

    if (refresh_thread_ && refresh_thread_->joinable()) {
        refresh_thread_->join();
        refresh_thread_.reset();
    }

    rest_api_for_refresh_ = nullptr;
}

// ==================== 自动重连 ====================

void BinanceWebSocket::set_auto_reconnect(bool enabled) {
    reconnect_enabled_.store(enabled);
    if (!enabled) {
        need_reconnect_.store(false);
    }
}

void BinanceWebSocket::resubscribe_all() {
    std::vector<std::string> streams;

    // 先获取订阅列表，避免死锁
    {
        std::lock_guard<std::mutex> lock(subscriptions_mutex_);
        std::cout << "[BinanceWebSocket] 重连后重新订阅... (共 " << subscriptions_.size() << " 个频道)" << std::endl;

        if (subscriptions_.empty()) {
            std::cout << "[BinanceWebSocket] ⚠️ 订阅列表为空，无需重新订阅" << std::endl;
            return;
        }

        for (const auto& sub : subscriptions_) {
            streams.push_back(sub.first);
        }
    }

    // 在锁外发送订阅请求（直接发送，不调用 subscribe_streams_batch 避免重复加锁）
    nlohmann::json sub_msg = {
        {"method", "SUBSCRIBE"},
        {"params", streams},
        {"id", request_id_counter_.fetch_add(1)}
    };

    send_message(sub_msg);
    std::cout << "[BinanceWebSocket] ✅ 已重新订阅 " << streams.size() << " 个频道" << std::endl;
}

} // namespace binance
} // namespace trading
