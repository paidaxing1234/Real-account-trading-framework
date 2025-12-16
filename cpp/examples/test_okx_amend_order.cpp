/**
 * @file test_okx_amend_order.cpp
 * @brief 测试OKX修改订单接口
 */

#include "adapters/okx/okx_rest_api.h"
#include <iostream>
#include <thread>
#include <chrono>
#include <cstdlib>
#include <ctime>

using namespace trading::okx;

// 默认代理设置
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// API 密钥配置（模拟盘）
const std::string API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
const std::string SECRET_KEY = "888CC77C745F1B49E75A992F38929992";
const std::string PASSPHRASE = "Sequence2025.";

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX 修改订单测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 设置代理（如果环境变量中没有设置）
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") && 
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置代理: " << DEFAULT_PROXY << std::endl;
    } else {
        const char* proxy = std::getenv("https_proxy");
        if (!proxy) proxy = std::getenv("HTTPS_PROXY");
        if (!proxy) proxy = std::getenv("all_proxy");
        if (!proxy) proxy = std::getenv("ALL_PROXY");
        std::cout << "\n[代理] 使用环境变量中的代理: " << (proxy ? proxy : "无") << std::endl;
    }
    
    // 使用硬编码的API密钥
    std::cout << "[密钥] API Key: " << API_KEY.substr(0, 8) << "..." << std::endl;
    
    // 创建API客户端（使用模拟盘）
    OKXRestAPI api(API_KEY, SECRET_KEY, PASSPHRASE, true);
    
    std::cout << "\n[1] 先下一个限价单（用于后续修改）..." << std::endl;
    
    // 先下一个限价单
    std::string inst_id = "BTC-USDT";
    std::string cl_ord_id = "amend_test_" + std::to_string(std::time(nullptr));
    
    nlohmann::json place_response = api.place_order(
        inst_id,
        "cash",
        "buy",
        "limit",
        0.001,
        50000.0,  // 设置一个较低的价格，确保不会立即成交
        cl_ord_id
    );
    
    std::cout << "下单响应: " << place_response.dump(2) << std::endl;
    
    if (place_response["code"] != "0") {
        std::cerr << "❌ 下单失败，无法继续测试" << std::endl;
        return 1;
    }
    
    std::string ord_id = place_response["data"][0]["ordId"];
    std::cout << "✅ 下单成功，订单ID: " << ord_id << std::endl;
    std::cout << "   等待2秒后修改订单..." << std::endl;
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    std::cout << "\n[2] 修改订单（修改价格和数量）..." << std::endl;
    std::cout << "    原价格: 50000, 新价格: 51000" << std::endl;
    std::cout << "    原数量: 0.001, 新数量: 0.002" << std::endl;
    
    try {
        nlohmann::json amend_response = api.amend_order(
            inst_id,
            ord_id,           // 使用ordId
            "",               // clOrdId为空
            "0.002",          // 新数量
            "51000",          // 新价格
            "",               // newPxUsd
            "",               // newPxVol
            false,            // cxlOnFail
            "",               // reqId
            "0"               // pxAmendType
        );
        
        std::cout << "\n[3] 修改订单响应:" << std::endl;
        std::cout << amend_response.dump(2) << std::endl;
        
        if (amend_response["code"] == "0") {
            std::cout << "\n✅ 修改订单成功！" << std::endl;
            
            if (amend_response.contains("data") && amend_response["data"].is_array()) {
                const auto& order_data = amend_response["data"][0];
                std::cout << "\n订单详情:" << std::endl;
                std::cout << "  ordId: " << order_data.value("ordId", "") << std::endl;
                std::cout << "  clOrdId: " << order_data.value("clOrdId", "") << std::endl;
                std::cout << "  reqId: " << order_data.value("reqId", "") << std::endl;
                std::cout << "  sCode: " << order_data.value("sCode", "") << std::endl;
                std::cout << "  sMsg: " << order_data.value("sMsg", "") << std::endl;
                
                if (order_data["sCode"] != "0") {
                    std::cout << "  ⚠️  修改失败: " << order_data.value("sMsg", "") << std::endl;
                } else {
                    std::cout << "  ✅ 修改请求已接受（实际修改结果以订单频道推送或查询订单状态为准）" << std::endl;
                }
            }
        } else {
            std::cout << "\n❌ 修改订单失败: " << amend_response.value("msg", "未知错误") << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n[4] 查询订单状态（验证修改是否生效）..." << std::endl;
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    try {
        nlohmann::json query_response = api.get_order(inst_id, ord_id);
        
        if (query_response["code"] == "0" && query_response["data"].is_array() && !query_response["data"].empty()) {
            const auto& order_info = query_response["data"][0];
            std::cout << "\n当前订单状态:" << std::endl;
            std::cout << "  价格: " << order_info.value("px", "") << std::endl;
            std::cout << "  数量: " << order_info.value("sz", "") << std::endl;
            std::cout << "  状态: " << order_info.value("state", "") << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "查询订单失败: " << e.what() << std::endl;
    }
    
    std::cout << "\n[5] 测试完成" << std::endl;
    return 0;
}
