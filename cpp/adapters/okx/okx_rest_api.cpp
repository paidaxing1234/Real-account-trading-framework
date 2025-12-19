/**
 * @file okx_rest_api.cpp
 * @brief OKX REST API 实现
 * 
 * 参考Python版本实现，支持完整的下单参数（包括止盈止损）
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

// ==================== 辅助函数 ====================

// Base64编码
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

// CURL写入回调
static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}

// ==================== 数据结构实现 ====================

nlohmann::json AttachAlgoOrder::to_json() const {
    nlohmann::json j;
    
    // 附带止盈止损的订单ID（改单时使用）
    if (!attach_algo_id.empty()) {
        j["attachAlgoId"] = attach_algo_id;
    }
    
    // 客户自定义策略订单ID
    if (!attach_algo_cl_ord_id.empty()) {
        j["attachAlgoClOrdId"] = attach_algo_cl_ord_id;
    }
    
    // 止盈参数
    if (!tp_trigger_px.empty()) {
        j["tpTriggerPx"] = tp_trigger_px;
    }
    if (!tp_trigger_ratio.empty()) {
        j["tpTriggerRatio"] = tp_trigger_ratio;
    }
    if (!tp_ord_px.empty()) {
        j["tpOrdPx"] = tp_ord_px;
    }
    if (!tp_ord_kind.empty()) {
        j["tpOrdKind"] = tp_ord_kind;
    }
    if (!tp_trigger_px_type.empty()) {
        j["tpTriggerPxType"] = tp_trigger_px_type;
    }
    
    // 止损参数
    if (!sl_trigger_px.empty()) {
        j["slTriggerPx"] = sl_trigger_px;
    }
    if (!sl_trigger_ratio.empty()) {
        j["slTriggerRatio"] = sl_trigger_ratio;
    }
    if (!sl_ord_px.empty()) {
        j["slOrdPx"] = sl_ord_px;
    }
    if (!sl_trigger_px_type.empty()) {
        j["slTriggerPxType"] = sl_trigger_px_type;
    }
    
    // 分批止盈参数
    if (!sz.empty()) {
        j["sz"] = sz;
    }
    if (!amend_px_on_trigger_type.empty()) {
        j["amendPxOnTriggerType"] = amend_px_on_trigger_type;
    }
    
    return j;
}

nlohmann::json PlaceOrderRequest::to_json() const {
    nlohmann::json body;
    
    // 必填参数
    body["instId"] = inst_id;
    body["tdMode"] = td_mode;
    body["side"] = side;
    body["ordType"] = ord_type;
    body["sz"] = sz;
    
    // 可选参数
    if (!ccy.empty()) {
        body["ccy"] = ccy;
    }
    if (!cl_ord_id.empty()) {
        body["clOrdId"] = cl_ord_id;
    }
    if (!tag.empty()) {
        body["tag"] = tag;
    }
    if (!pos_side.empty()) {
        body["posSide"] = pos_side;
    }
    if (!px.empty()) {
        body["px"] = px;
    }
    if (!px_usd.empty()) {
        body["pxUsd"] = px_usd;
    }
    if (!px_vol.empty()) {
        body["pxVol"] = px_vol;
    }
    
    if (reduce_only) {
        body["reduceOnly"] = true;
    }
    if (!tgt_ccy.empty()) {
        body["tgtCcy"] = tgt_ccy;
    }
    if (ban_amend) {
        body["banAmend"] = true;
    }
    if (!px_amend_type.empty()) {
        body["pxAmendType"] = px_amend_type;
    }
    if (!trade_quote_ccy.empty()) {
        body["tradeQuoteCcy"] = trade_quote_ccy;
    }
    if (!stp_mode.empty()) {
        body["stpMode"] = stp_mode;
    }
    
    // 止盈止损
    if (!attach_algo_ords.empty()) {
        nlohmann::json algo_array = nlohmann::json::array();
        for (const auto& algo : attach_algo_ords) {
            algo_array.push_back(algo.to_json());
        }
        body["attachAlgoOrds"] = algo_array;
    }
    
    return body;
}

PlaceOrderResponse PlaceOrderResponse::from_json(const nlohmann::json& j) {
    PlaceOrderResponse resp;
    
    resp.code = j.value("code", "");
    resp.msg = j.value("msg", "");
    
    // 解析data数组
    if (j.contains("data") && j["data"].is_array() && !j["data"].empty()) {
        const auto& data = j["data"][0];
        resp.ord_id = data.value("ordId", "");
        resp.cl_ord_id = data.value("clOrdId", "");
        resp.tag = data.value("tag", "");
        
        // 时间戳解析
        std::string ts_str = data.value("ts", "0");
        resp.ts = std::stoll(ts_str);
        
        resp.s_code = data.value("sCode", "");
        resp.s_msg = data.value("sMsg", "");
    }
    
    // 网关时间
    std::string in_time_str = j.value("inTime", "0");
    std::string out_time_str = j.value("outTime", "0");
    resp.in_time = std::stoll(in_time_str);
    resp.out_time = std::stoll(out_time_str);
    
    return resp;
}

// ==================== OKXRestAPI实现 ====================

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
    
    // 调试信息已关闭
    // std::cout << "[DEBUG] Method: " << method << std::endl;
    // std::cout << "[DEBUG] URL: " << url << std::endl;
    
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
    
    // 禁用 Expect: 100-continue（有些代理不支持）
    headers = curl_slist_append(headers, "Expect:");
    
    // 设置CURL选项
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_string);
    
    // 🔑 关键：从环境变量读取代理设置（all_proxy, http_proxy, https_proxy）
    const char* proxy_env = std::getenv("all_proxy");
    if (!proxy_env) proxy_env = std::getenv("ALL_PROXY");
    if (!proxy_env) proxy_env = std::getenv("https_proxy");
    if (!proxy_env) proxy_env = std::getenv("HTTPS_PROXY");
    
    if (proxy_env && strlen(proxy_env) > 0) {
        // std::cout << "[DEBUG] Using proxy: " << proxy_env << std::endl;
        curl_easy_setopt(curl, CURLOPT_PROXY, proxy_env);
        
        // 如果是 SOCKS 代理，需要设置代理类型
        if (strstr(proxy_env, "socks5://") || strstr(proxy_env, "socks5h://")) {
            curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_SOCKS5_HOSTNAME);
        } else if (strstr(proxy_env, "socks4://")) {
            curl_easy_setopt(curl, CURLOPT_PROXYTYPE, CURLPROXY_SOCKS4);
        }
    }
    
    // SSL 设置
    // 检查是否禁用SSL验证（仅用于调试）
    const char* skip_ssl = std::getenv("OKX_SKIP_SSL_VERIFY");
    if (skip_ssl && (strcmp(skip_ssl, "1") == 0 || strcmp(skip_ssl, "true") == 0)) {
        // std::cout << "[DEBUG] ⚠️ SSL验证已禁用（仅用于调试）" << std::endl;
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
    } else {
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    }
    
    // 设置TLS版本（最低TLS 1.2）
    curl_easy_setopt(curl, CURLOPT_SSLVERSION, CURL_SSLVERSION_TLSv1_2);
    
    // 如果使用代理，设置代理SSL选项
    if (proxy_env && strlen(proxy_env) > 0) {
        // 对于HTTP代理的HTTPS隧道，需要这些设置
        curl_easy_setopt(curl, CURLOPT_HTTPPROXYTUNNEL, 1L);
        
        // 注意: CURLOPT_PROXY_SSL_* 和 CURLOPT_PROXY_CONNECTTIMEOUT 
        // 需要 curl 7.52.0+ / 7.78.0+，旧版本使用通用超时设置即可
#if LIBCURL_VERSION_NUM >= 0x073400  // 7.52.0
        curl_easy_setopt(curl, CURLOPT_PROXY_SSL_VERIFYPEER, 0L);
        curl_easy_setopt(curl, CURLOPT_PROXY_SSL_VERIFYHOST, 0L);
#endif
        // CURLOPT_CONNECTTIMEOUT 对代理连接也生效
    }
    
    // 超时设置
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    
    // 设置TCP keepalive
    curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);
    
    // 跟随重定向
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    
    // 设置 User-Agent
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "OKX-CPP-Client/1.0");
    
    // 强制使用 IPv4（有些代理对IPv6支持不好）
    curl_easy_setopt(curl, CURLOPT_IPRESOLVE, CURL_IPRESOLVE_V4);
    
    // 调试输出已关闭（帮助排查问题时可开启）
    curl_easy_setopt(curl, CURLOPT_VERBOSE, 0L);
    
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

PlaceOrderResponse OKXRestAPI::place_order_advanced(const PlaceOrderRequest& request) {
    // 转换请求为JSON
    nlohmann::json body = request.to_json();
    
    // 发送请求
    nlohmann::json response = send_request("POST", "/api/v5/trade/order", body);
    
    // 解析响应
    return PlaceOrderResponse::from_json(response);
}

PlaceOrderResponse OKXRestAPI::place_order_with_tp_sl(
    const std::string& inst_id,
    const std::string& td_mode,
    const std::string& side,
    const std::string& ord_type,
    const std::string& sz,
    const std::string& px,
    const std::string& tp_trigger_px,
    const std::string& tp_ord_px,
    const std::string& sl_trigger_px,
    const std::string& sl_ord_px,
    const std::string& cl_ord_id
) {
    // 构造请求
    PlaceOrderRequest req;
    req.inst_id = inst_id;
    req.td_mode = td_mode;
    req.side = side;
    req.ord_type = ord_type;
    req.sz = sz;
    req.px = px;
    req.cl_ord_id = cl_ord_id;
    
    // 添加止盈止损
    if (!tp_trigger_px.empty() || !sl_trigger_px.empty()) {
        AttachAlgoOrder algo;
        
        if (!tp_trigger_px.empty()) {
            algo.tp_trigger_px = tp_trigger_px;
            algo.tp_ord_px = tp_ord_px;
        }
        
        if (!sl_trigger_px.empty()) {
            algo.sl_trigger_px = sl_trigger_px;
            algo.sl_ord_px = sl_ord_px;
        }
        
        req.attach_algo_ords.push_back(algo);
    }
    
    return place_order_advanced(req);
}

nlohmann::json OKXRestAPI::place_batch_orders(const std::vector<PlaceOrderRequest>& orders) {
    // 检查订单数量（最多20个）
    if (orders.size() > 20) {
        throw std::invalid_argument("批量下单最多支持20个订单");
    }
    
    // 将订单请求转换为JSON数组
    nlohmann::json orders_json = nlohmann::json::array();
    for (const auto& order : orders) {
        orders_json.push_back(order.to_json());
    }
    
    // 发送批量下单请求
    return send_request("POST", "/api/v5/trade/batch-orders", orders_json);
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

nlohmann::json OKXRestAPI::amend_order(
    const std::string& inst_id,
    const std::string& ord_id,
    const std::string& cl_ord_id,
    const std::string& new_sz,
    const std::string& new_px,
    const std::string& new_px_usd,
    const std::string& new_px_vol,
    bool cxl_on_fail,
    const std::string& req_id,
    const std::string& px_amend_type,
    const std::vector<AttachAlgoOrder>& attach_algo_ords
) {
    nlohmann::json body = {{"instId", inst_id}};
    
    // ordId和clOrdId必须传一个，优先使用ordId
    if (!ord_id.empty()) {
        body["ordId"] = ord_id;
    } else if (!cl_ord_id.empty()) {
        body["clOrdId"] = cl_ord_id;
    } else {
        throw std::invalid_argument("ordId和clOrdId必须传一个");
    }
    
    // 可选参数
    if (!new_sz.empty()) {
        body["newSz"] = new_sz;
    }
    if (!new_px.empty()) {
        body["newPx"] = new_px;
    }
    if (!new_px_usd.empty()) {
        body["newPxUsd"] = new_px_usd;
    }
    if (!new_px_vol.empty()) {
        body["newPxVol"] = new_px_vol;
    }
    if (cxl_on_fail) {
        body["cxlOnFail"] = true;
    }
    if (!req_id.empty()) {
        body["reqId"] = req_id;
    }
    if (!px_amend_type.empty()) {
        body["pxAmendType"] = px_amend_type;
    }
    
    // 附带止盈止损信息
    if (!attach_algo_ords.empty()) {
        nlohmann::json algo_ords = nlohmann::json::array();
        for (const auto& algo : attach_algo_ords) {
            nlohmann::json algo_json = algo.to_json();
            
            // 修改订单时，止盈止损字段名需要加"new"前缀
            nlohmann::json new_algo_json;
            
            if (algo_json.contains("attachAlgoClOrdId")) {
                new_algo_json["attachAlgoClOrdId"] = algo_json["attachAlgoClOrdId"];
            }
            if (algo_json.contains("attachAlgoId")) {
                new_algo_json["attachAlgoId"] = algo_json["attachAlgoId"];
            }
            if (algo_json.contains("tpTriggerPx")) {
                new_algo_json["newTpTriggerPx"] = algo_json["tpTriggerPx"];
            }
            if (algo_json.contains("tpTriggerRatio")) {
                new_algo_json["newTpTriggerRatio"] = algo_json["tpTriggerRatio"];
            }
            if (algo_json.contains("tpOrdPx")) {
                new_algo_json["newTpOrdPx"] = algo_json["tpOrdPx"];
            }
            if (algo_json.contains("tpOrdKind")) {
                new_algo_json["newTpOrdKind"] = algo_json["tpOrdKind"];
            }
            if (algo_json.contains("tpTriggerPxType")) {
                new_algo_json["newTpTriggerPxType"] = algo_json["tpTriggerPxType"];
            }
            if (algo_json.contains("slTriggerPx")) {
                new_algo_json["newSlTriggerPx"] = algo_json["slTriggerPx"];
            }
            if (algo_json.contains("slTriggerRatio")) {
                new_algo_json["newSlTriggerRatio"] = algo_json["slTriggerRatio"];
            }
            if (algo_json.contains("slOrdPx")) {
                new_algo_json["newSlOrdPx"] = algo_json["slOrdPx"];
            }
            if (algo_json.contains("slTriggerPxType")) {
                new_algo_json["newSlTriggerPxType"] = algo_json["slTriggerPxType"];
            }
            if (algo_json.contains("sz")) {
                new_algo_json["sz"] = algo_json["sz"];
            }
            if (algo_json.contains("amendPxOnTriggerType")) {
                new_algo_json["amendPxOnTriggerType"] = algo_json["amendPxOnTriggerType"];
            }
            
            algo_ords.push_back(new_algo_json);
        }
        body["attachAlgoOrds"] = algo_ords;
    }
    
    return send_request("POST", "/api/v5/trade/amend-order", body);
}

nlohmann::json OKXRestAPI::amend_batch_orders(const std::vector<nlohmann::json>& orders) {
    // 检查订单数量（最多20个）
    if (orders.size() > 20) {
        throw std::invalid_argument("批量修改订单最多支持20个订单");
    }
    
    // 验证每个订单的必要字段
    for (const auto& order : orders) {
        if (!order.contains("instId")) {
            throw std::invalid_argument("每个订单必须包含instId");
        }
        if (!order.contains("ordId") && !order.contains("clOrdId")) {
            throw std::invalid_argument("每个订单必须包含ordId或clOrdId");
        }
    }
    
    // 将订单数组转换为JSON
    nlohmann::json orders_json = nlohmann::json::array();
    for (const auto& order : orders) {
        orders_json.push_back(order);
    }
    
    // 发送批量修改订单请求
    return send_request("POST", "/api/v5/trade/amend-batch-orders", orders_json);
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
