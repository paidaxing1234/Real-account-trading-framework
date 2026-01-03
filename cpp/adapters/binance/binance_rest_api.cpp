/**
 * @file binance_rest_api.cpp
 * @brief Binance REST API 实现
 * 
 * 实现币安现货、U本位合约、币本位合约的REST API接口
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#include "binance_rest_api.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <cstring>
#include <chrono>
#include <openssl/hmac.h>
#include <openssl/sha.h>
#include <curl/curl.h>

namespace trading {
namespace binance {

// ==================== 辅助函数 ====================

// CURL写入回调
static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}

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

// ==================== BinanceRestAPI实现 ====================

BinanceRestAPI::BinanceRestAPI(
    const std::string& api_key,
    const std::string& secret_key,
    MarketType market_type,
    bool is_testnet
)
    : api_key_(api_key)
    , secret_key_(secret_key)
    , market_type_(market_type)
    , is_testnet_(is_testnet)
{
    // 设置基础URL
    if (is_testnet) {
        // 测试网URL
        switch (market_type) {
            case MarketType::SPOT:
                base_url_ = "https://testnet.binance.vision";
                break;
            case MarketType::FUTURES:
                // Futures Demo Testnet (per user-provided docs)
                base_url_ = "https://demo-fapi.binance.com";
                break;
            case MarketType::COIN_FUTURES:
                // 币本位合约测试网域名在不同文档中可能不同，这里先沿用旧值
                // 如需切换，可按需改成 demo-dapi 域名
                base_url_ = "https://testnet.binancefuture.com";
                break;
        }
    } else {
        // 主网URL
        switch (market_type) {
            case MarketType::SPOT:
                base_url_ = "https://api.binance.com";
                break;
            case MarketType::FUTURES:
                base_url_ = "https://fapi.binance.com";
                break;
            case MarketType::COIN_FUTURES:
                base_url_ = "https://dapi.binance.com";
                break;
        }
    }
}

std::string BinanceRestAPI::create_signature(const std::string& query_string) {
    return hmac_sha256(secret_key_, query_string);
}

std::string BinanceRestAPI::create_query_string(const nlohmann::json& params) {
    if (params.empty()) return "";
    
    std::ostringstream oss;
    bool first = true;
    
    for (auto it = params.begin(); it != params.end(); ++it) {
        if (!first) oss << "&";
        
        std::string value = it.value().dump();
        // 去除JSON字符串的引号
        if (value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.length() - 2);
        }
        
        oss << it.key() << "=" << value;
        first = false;
    }
    
    return oss.str();
}

int64_t BinanceRestAPI::get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();
    return ms;
}

nlohmann::json BinanceRestAPI::send_request(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& params,
    bool need_signature
) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize CURL");
    }
    
    std::string response_string;
    std::string url = base_url_ + endpoint;
    
    // 构造查询字符串
    std::string query_string = create_query_string(params);
    
    // 如果需要签名
    if (need_signature) {
        // 添加时间戳
        if (!query_string.empty()) {
            query_string += "&";
        }
        query_string += "timestamp=" + std::to_string(get_timestamp());
        
        // 创建签名
        std::string signature = create_signature(query_string);
        query_string += "&signature=" + signature;
    }
    
    // GET请求：参数拼接到URL
    if (method == "GET" || method == "DELETE") {
        if (!query_string.empty()) {
            url += "?" + query_string;
        }
    }
    
    // 🔍 调试：打印完整 URL（包含签名）
    std::cout << "[BinanceRestAPI] " << method << " " << url << std::endl;
    
    // 设置请求头
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    
    if (!api_key_.empty()) {
        headers = curl_slist_append(headers, ("X-MBX-APIKEY: " + api_key_).c_str());
    }
    
    // 设置CURL选项
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);
    
    // POST/PUT请求：参数放在body中
    if (method == "POST") {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        if (!query_string.empty()) {
            // 🔍 调试：打印 POST body（包含签名）
            std::cout << "[BinanceRestAPI] POST Body: " << query_string << std::endl;
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, query_string.c_str());
        }
    } else if (method == "PUT") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PUT");
        if (!query_string.empty()) {
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, query_string.c_str());
        }
    } else if (method == "DELETE") {
        curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "DELETE");
    }
    
    // 代理设置（从环境变量读取）
    const char* proxy_env = std::getenv("https_proxy");
    if (!proxy_env) proxy_env = std::getenv("HTTPS_PROXY");
    if (proxy_env && strlen(proxy_env) > 0) {
        curl_easy_setopt(curl, CURLOPT_PROXY, proxy_env);
    }
    
    // SSL设置
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    
    // 超时设置
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    
    // 执行请求
    CURLcode res = curl_easy_perform(curl);
    
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    
    if (res != CURLE_OK) {
        throw std::runtime_error(
            std::string("CURL request failed: ") + curl_easy_strerror(res)
        );
    }
    
    // 解析JSON响应
    auto j = nlohmann::json::parse(response_string);

    // Binance 错误响应通常为: {"code": -2015, "msg": "..."}
    // 成功响应一般不包含 code 字段（现货/合约均如此）
    if (j.is_object() && j.contains("code")) {
        try {
            const int code = j["code"].get<int>();
            const std::string msg = j.value("msg", "");
            throw std::runtime_error("Binance API error: code=" + std::to_string(code) + " msg=" + msg);
        } catch (const nlohmann::json::exception&) {
            // code 字段类型异常时也抛出原始内容
            throw std::runtime_error("Binance API error (unexpected code field): " + j.dump());
        }
    }

    return j;
}

// ==================== 市场数据接口（已测试） ====================

bool BinanceRestAPI::test_connectivity() {
    try {
        std::string endpoint = (market_type_ == MarketType::SPOT) ? 
            "/api/v3/ping" : "/fapi/v1/ping";
        auto result = send_request("GET", endpoint);
        return true;
    } catch (...) {
        return false;
    }
}

int64_t BinanceRestAPI::get_server_time() {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/time" : "/fapi/v1/time";
    auto result = send_request("GET", endpoint);
    return result["serverTime"].get<int64_t>();
}

nlohmann::json BinanceRestAPI::get_exchange_info(const std::string& symbol) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/exchangeInfo" : "/fapi/v1/exchangeInfo";
    
    nlohmann::json params;
    if (!symbol.empty()) {
        params["symbol"] = symbol;
    }
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_depth(const std::string& symbol, int limit) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/depth" : "/fapi/v1/depth";
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"limit", limit}
    };
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_recent_trades(const std::string& symbol, int limit) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/trades" : "/fapi/v1/trades";
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"limit", limit}
    };
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_klines(
    const std::string& symbol,
    const std::string& interval,
    int64_t start_time,
    int64_t end_time,
    int limit
) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/klines" : "/fapi/v1/klines";
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"interval", interval}
    };
    
    if (start_time > 0) params["startTime"] = start_time;
    if (end_time > 0) params["endTime"] = end_time;
    if (limit > 0) params["limit"] = limit;
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_ticker_24hr(const std::string& symbol) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/ticker/24hr" : "/fapi/v1/ticker/24hr";
    
    nlohmann::json params;
    if (!symbol.empty()) {
        params["symbol"] = symbol;
    }
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_ticker_price(const std::string& symbol) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/ticker/price" : "/fapi/v1/ticker/price";
    
    nlohmann::json params;
    if (!symbol.empty()) {
        params["symbol"] = symbol;
    }
    
    return send_request("GET", endpoint, params);
}

nlohmann::json BinanceRestAPI::get_funding_rate(const std::string& symbol, int limit) {
    if (market_type_ == MarketType::SPOT) {
        throw std::runtime_error("Funding rate is only available for futures");
    }
    
    nlohmann::json params = {
        {"symbol", symbol}
    };
    
    if (limit > 0) params["limit"] = limit;
    
    return send_request("GET", "/fapi/v1/fundingRate", params);
}

// ==================== 辅助方法实现 ====================

std::string BinanceRestAPI::order_side_to_string(OrderSide side) {
    return side == OrderSide::BUY ? "BUY" : "SELL";
}

std::string BinanceRestAPI::order_type_to_string(OrderType type) {
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

std::string BinanceRestAPI::time_in_force_to_string(TimeInForce tif) {
    switch (tif) {
        case TimeInForce::GTC: return "GTC";
        case TimeInForce::IOC: return "IOC";
        case TimeInForce::FOK: return "FOK";
        case TimeInForce::GTX: return "GTX";
        default: return "GTC";
    }
}

std::string BinanceRestAPI::position_side_to_string(PositionSide ps) {
    switch (ps) {
        case PositionSide::BOTH: return "BOTH";
        case PositionSide::LONG: return "LONG";
        case PositionSide::SHORT: return "SHORT";
        default: return "BOTH";
    }
}

// ==================== 交易接口实现 ====================

nlohmann::json BinanceRestAPI::place_order(
    const std::string& symbol,
    OrderSide side,
    OrderType type,
    const std::string& quantity,
    const std::string& price,
    TimeInForce time_in_force,
    PositionSide position_side,
    const std::string& client_order_id
) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/order" : "/fapi/v1/order";
    
    nlohmann::json params = {
        {"symbol", symbol},
        {"side", order_side_to_string(side)},
        {"type", order_type_to_string(type)},
        {"quantity", quantity}
    };
    
    // 限价单必须提供价格
    if (!price.empty()) {
        params["price"] = price;
    }
    
    // Time in force
    if (type == OrderType::LIMIT) {
        params["timeInForce"] = time_in_force_to_string(time_in_force);
    }
    
    // 客户自定义订单ID
    if (!client_order_id.empty()) {
        params["newClientOrderId"] = client_order_id;
    }
    
    // 合约特有参数
    if (market_type_ != MarketType::SPOT) {
        params["positionSide"] = position_side_to_string(position_side);
    }
    
    return send_request("POST", endpoint, params, true);
}

nlohmann::json BinanceRestAPI::cancel_order(
    const std::string& symbol,
    int64_t order_id,
    const std::string& client_order_id
) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/order" : "/fapi/v1/order";
    
    nlohmann::json params = {{"symbol", symbol}};
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    return send_request("DELETE", endpoint, params, true);
}

nlohmann::json BinanceRestAPI::get_order(
    const std::string& symbol,
    int64_t order_id,
    const std::string& client_order_id
) {
    std::string endpoint = (market_type_ == MarketType::SPOT) ? 
        "/api/v3/order" : "/fapi/v1/order";
    
    nlohmann::json params = {{"symbol", symbol}};
    
    if (order_id > 0) {
        params["orderId"] = order_id;
    }
    if (!client_order_id.empty()) {
        params["origClientOrderId"] = client_order_id;
    }
    
    return send_request("GET", endpoint, params, true);
}

void BinanceRestAPI::set_proxy(const std::string& proxy_host, uint16_t proxy_port) {
    // 代理通过环境变量设置，这里只是提供接口
    std::string proxy = "http://" + proxy_host + ":" + std::to_string(proxy_port);
    setenv("https_proxy", proxy.c_str(), 1);
}

} // namespace binance
} // namespace trading

