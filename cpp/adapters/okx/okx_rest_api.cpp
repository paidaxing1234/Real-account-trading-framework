/**
 * @file okx_rest_api.cpp
 * @brief OKX REST API 实现
 * 
 * 参考Python版本实现
 */

#include "okx_rest_api.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <cstring>
#include <cstdlib>
#include <chrono>
#include <openssl/hmac.h>
#include <openssl/sha.h>
#include <curl/curl.h>

namespace trading {
namespace okx {

// 辅助函数：Base64编码
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

// 辅助函数：CURL写入回调
static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}

OKXRestAPI::OKXRestAPI(
    const std::string& api_key,
    const std::string& secret_key,
    const std::string& passphrase,
    bool is_testnet
) 
    : api_key_(api_key)
    , secret_key_(secret_key)
    , passphrase_(passphrase)
{
    // REST API基础URL（实盘和模拟盘使用相同URL，通过header区分）
    base_url_ = "https://www.okx.com";
    
    // 保存是否为模拟盘标志
    is_testnet_ = is_testnet;
}

std::string OKXRestAPI::create_signature(
    const std::string& timestamp,
    const std::string& method,
    const std::string& request_path,
    const std::string& body
) {
    // 拼接待签名字符串: timestamp + method + requestPath + body
    std::string message = timestamp + method + request_path + body;
    
    // HMAC SHA256 加密
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
    
    // Base64 编码
    return base64_encode(hash, SHA256_DIGEST_LENGTH);
}

nlohmann::json OKXRestAPI::send_request(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& params
) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize CURL");
    }
    
    std::string response_string;
    std::string url = base_url_ + endpoint;
    
    // 生成ISO格式时间戳（与Python版本保持一致）
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();
    
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm* tm = std::gmtime(&t);
    
    char timestamp_buf[32];
    std::strftime(timestamp_buf, sizeof(timestamp_buf), "%Y-%m-%dT%H:%M:%S", tm);
    
    // 格式: 2024-12-08T10:30:00.123Z （毫秒部分补零到3位）
    char ms_buf[8];
    snprintf(ms_buf, sizeof(ms_buf), ".%03lldZ", (long long)(ms % 1000));
    std::string timestamp = std::string(timestamp_buf) + ms_buf;
    
    // 构造请求路径（GET请求需要包含参数）
    std::string sign_path = endpoint;
    std::string body_str;
    
    if (method == "GET" && !params.empty()) {
        // 构造query string
        std::ostringstream query;
        bool first = true;
        for (auto it = params.begin(); it != params.end(); ++it) {
            if (!first) query << "&";
            // 使用 dump() 获取正确的字符串值（去除引号）
            std::string value = it.value().dump();
            // 如果是字符串类型，去掉JSON的引号
            if (value.front() == '"' && value.back() == '"') {
                value = value.substr(1, value.length() - 2);
            }
            query << it.key() << "=" << value;
            first = false;
        }
        sign_path += "?" + query.str();
        url += "?" + query.str();
    } else if (method == "POST" && !params.empty()) {
        body_str = params.dump();
    }
    
    // 打印调试信息
    std::cout << "[DEBUG] Method: " << method << std::endl;
    std::cout << "[DEBUG] URL: " << url << std::endl;
    std::cout << "[DEBUG] Sign Path: " << sign_path << std::endl;
    std::cout << "[DEBUG] Timestamp: " << timestamp << std::endl;
    std::cout << "[DEBUG] Body: " << body_str << std::endl;
    
    // 生成签名
    std::string signature = create_signature(timestamp, method, sign_path, body_str);
    
    // 设置请求头
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, 
        ("OK-ACCESS-KEY: " + api_key_).c_str());
    headers = curl_slist_append(headers, 
        ("OK-ACCESS-SIGN: " + signature).c_str());
    headers = curl_slist_append(headers, 
        ("OK-ACCESS-TIMESTAMP: " + timestamp).c_str());
    headers = curl_slist_append(headers, 
        ("OK-ACCESS-PASSPHRASE: " + passphrase_).c_str());
    
    // 模拟盘需要额外的header（重要！）
    if (is_testnet_) {
        headers = curl_slist_append(headers, "x-simulated-trading: 1");
    }
    
    // 设置CURL选项
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);
    
    // 🔑 关键：从环境变量读取代理设置（all_proxy, http_proxy, https_proxy）
    // libcurl 默认会读取环境变量，但需要显式启用
    const char* proxy_env = std::getenv("all_proxy");
    if (!proxy_env) proxy_env = std::getenv("ALL_PROXY");
    if (!proxy_env) proxy_env = std::getenv("https_proxy");
    if (!proxy_env) proxy_env = std::getenv("HTTPS_PROXY");
    
    if (proxy_env && strlen(proxy_env) > 0) {
        std::cout << "[DEBUG] Using proxy: " << proxy_env << std::endl;
        curl_easy_setopt(curl, CURLOPT_PROXY, proxy_env);
        
        // 如果是 SOCKS 代理，需要设置代理类型
        if (strstr(proxy_env, "socks5://") || strstr(proxy_env, "socks5h://")) {
            curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_SOCKS5_HOSTNAME);
        } else if (strstr(proxy_env, "socks4://")) {
            curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_SOCKS4);
        }
    }
    
    // SSL 设置
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    
    // 超时设置
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    
    // 跟随重定向
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    
    // 设置 User-Agent
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "OKX-CPP-Client/1.0");
    
    // 调试输出（帮助排查问题）
    curl_easy_setopt(curl, CURLOPT_VERBOSE, 1L);
    
    if (method == "POST") {
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body_str.c_str());
    }
    
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
    return nlohmann::json::parse(response_string);
}

std::string OKXRestAPI::get_iso8601_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();
    
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm* tm = std::gmtime(&t);
    
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", tm);
    
    return std::string(buf) + "." + std::to_string(ms % 1000) + "Z";
}

// ==================== 交易接口 ====================

nlohmann::json OKXRestAPI::place_order(
    const std::string& inst_id,
    const std::string& td_mode,
    const std::string& side,
    const std::string& ord_type,
    double sz,
    double px,
    const std::string& cl_ord_id
) {
    nlohmann::json body = {
        {"instId", inst_id},
        {"tdMode", td_mode},
        {"side", side},
        {"ordType", ord_type},
        {"sz", std::to_string(sz)}
    };
    
    if (px > 0) {
        body["px"] = std::to_string(px);
    }
    
    if (!cl_ord_id.empty()) {
        body["clOrdId"] = cl_ord_id;
    }
    
    return send_request("POST", "/api/v5/trade/order", body);
}

nlohmann::json OKXRestAPI::cancel_order(
    const std::string& inst_id,
    const std::string& ord_id,
    const std::string& cl_ord_id
) {
    nlohmann::json body = {{"instId", inst_id}};
    
    if (!ord_id.empty()) {
        body["ordId"] = ord_id;
    }
    if (!cl_ord_id.empty()) {
        body["clOrdId"] = cl_ord_id;
    }
    
    return send_request("POST", "/api/v5/trade/cancel-order", body);
}

nlohmann::json OKXRestAPI::cancel_batch_orders(
    const std::vector<std::string>& ord_ids,
    const std::string& inst_id
) {
    nlohmann::json orders = nlohmann::json::array();
    for (const auto& ord_id : ord_ids) {
        orders.push_back({
            {"instId", inst_id},
            {"ordId", ord_id}
        });
    }
    
    return send_request("POST", "/api/v5/trade/cancel-batch-orders", orders);
}

nlohmann::json OKXRestAPI::get_order(
    const std::string& inst_id,
    const std::string& ord_id,
    const std::string& cl_ord_id
) {
    nlohmann::json params = {{"instId", inst_id}};
    
    if (!ord_id.empty()) {
        params["ordId"] = ord_id;
    }
    if (!cl_ord_id.empty()) {
        params["clOrdId"] = cl_ord_id;
    }
    
    return send_request("GET", "/api/v5/trade/order", params);
}

nlohmann::json OKXRestAPI::get_pending_orders(
    const std::string& inst_type,
    const std::string& inst_id
) {
    nlohmann::json params;
    
    if (!inst_type.empty()) {
        params["instType"] = inst_type;
    }
    if (!inst_id.empty()) {
        params["instId"] = inst_id;
    }
    
    return send_request("GET", "/api/v5/trade/orders-pending", params);
}

// ==================== 账户接口 ====================

nlohmann::json OKXRestAPI::get_account_balance(const std::string& ccy) {
    nlohmann::json params;
    
    if (!ccy.empty()) {
        params["ccy"] = ccy;
    }
    
    return send_request("GET", "/api/v5/account/balance", params);
}

nlohmann::json OKXRestAPI::get_positions(
    const std::string& inst_type,
    const std::string& inst_id
) {
    nlohmann::json params;
    
    if (!inst_type.empty()) {
        params["instType"] = inst_type;
    }
    if (!inst_id.empty()) {
        params["instId"] = inst_id;
    }
    
    return send_request("GET", "/api/v5/account/positions", params);
}

nlohmann::json OKXRestAPI::get_account_instruments(
    const std::string& inst_type,
    const std::string& inst_family,
    const std::string& inst_id
) {
    // 构造请求参数
    nlohmann::json params = {{"instType", inst_type}};
    
    // 可选参数
    if (!inst_family.empty()) {
        params["instFamily"] = inst_family;
    }
    if (!inst_id.empty()) {
        params["instId"] = inst_id;
    }
    
    // 发送GET请求
    return send_request("GET", "/api/v5/account/instruments", params);
}

// ==================== 市场数据接口 ====================

nlohmann::json OKXRestAPI::get_candles(
    const std::string& inst_id,
    const std::string& bar,
    int64_t after,
    int64_t before,
    int limit
) {
    nlohmann::json params = {
        {"instId", inst_id},
        {"bar", bar}
    };
    
    if (after > 0) {
        params["after"] = std::to_string(after);
    }
    if (before > 0) {
        params["before"] = std::to_string(before);
    }
    if (limit > 0) {
        params["limit"] = std::to_string(limit);
    }
    
    return send_request("GET", "/api/v5/market/candles", params);
}

} // namespace okx
} // namespace trading

