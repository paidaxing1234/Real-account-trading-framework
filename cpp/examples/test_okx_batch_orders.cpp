/**
 * @file test_okx_batch_orders.cpp
 * @brief 测试OKX批量下单接口
 */

#include "adapters/okx/okx_rest_api.h"
#include <iostream>
#include <vector>
#include <cstdlib>
#include <chrono>

using namespace trading::okx;

// 默认代理设置
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// API 密钥配置（模拟盘）
const std::string API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
const std::string SECRET_KEY = "888CC77C745F1B49E75A992F38929992";
const std::string PASSPHRASE = "Sequence2025.";

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX 批量下单测试" << std::endl;
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
    
    std::cout << "\n[1] 准备批量下单..." << std::endl;
    
    // 构造批量订单请求
    std::vector<PlaceOrderRequest> orders;
    
    // 生成唯一的订单ID后缀（使用时间戳）
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
    std::string id_suffix = std::to_string(ms % 1000000000);  // 取后9位
    
    // 订单1：BTC-USDT限价买单
    PlaceOrderRequest order1;
    order1.inst_id = "BTC-USDT";
    order1.td_mode = "cash";
    order1.side = "buy";
    order1.ord_type = "limit";
    order1.sz = "0.001";
    order1.px = "50000";  // 设置一个较低的价格，确保不会立即成交
    order1.cl_ord_id = "batch1" + id_suffix;  // 纯字母+数字，不含下划线
    orders.push_back(order1);
    
    // 订单2：BTC-USDT限价卖单（数量调小，避免余额不足）
    PlaceOrderRequest order2;
    order2.inst_id = "BTC-USDT";
    order2.td_mode = "cash";
    order2.side = "sell";
    order2.ord_type = "limit";
    order2.sz = "0.00001";  // 调小数量，避免余额不足
    order2.px = "100000";   // 设置一个较高的价格，确保不会立即成交
    order2.cl_ord_id = "batch2" + id_suffix;  // 纯字母+数字，不含下划线
    orders.push_back(order2);
    
    // 订单3：ETH-USDT限价买单
    PlaceOrderRequest order3;
    order3.inst_id = "ETH-USDT";
    order3.td_mode = "cash";
    order3.side = "buy";
    order3.ord_type = "limit";
    order3.sz = "0.01";
    order3.px = "2000";  // 设置一个较低的价格
    order3.cl_ord_id = "batch3" + id_suffix;  // 纯字母+数字，不含下划线
    orders.push_back(order3);
    
    std::cout << "准备提交 " << orders.size() << " 个订单" << std::endl;
    for (size_t i = 0; i < orders.size(); ++i) {
        std::cout << "  订单" << (i+1) << ": " << orders[i].side 
                  << " " << orders[i].sz << " " << orders[i].inst_id 
                  << " @ " << orders[i].px << " (clOrdId: " << orders[i].cl_ord_id << ")" << std::endl;
    }
    
    std::cout << "\n[2] 发送批量下单请求..." << std::endl;
    
    try {
        nlohmann::json response = api.place_batch_orders(orders);
        
        std::cout << "\n[3] 批量下单响应:" << std::endl;
        std::cout << response.dump(2) << std::endl;
        
        // 解析响应
        // code: 0=全部成功, 1=全部失败, 2=部分成功
        std::string code = response.value("code", "");
        if (code == "0") {
            std::cout << "\n✅ 批量下单全部成功！" << std::endl;
        } else if (code == "2") {
            std::cout << "\n⚠️  批量下单部分成功: " << response.value("msg", "") << std::endl;
        } else {
            std::cout << "\n❌ 批量下单全部失败: " << response.value("msg", "未知错误") << std::endl;
        }
        
        // 显示每个订单的详情
        if (response.contains("data") && response["data"].is_array()) {
            std::cout << "\n订单详情:" << std::endl;
            int success_count = 0, fail_count = 0;
            for (size_t i = 0; i < response["data"].size(); ++i) {
                const auto& order_data = response["data"][i];
                std::cout << "  订单" << (i+1) << ":" << std::endl;
                std::cout << "    clOrdId: " << order_data.value("clOrdId", "") << std::endl;
                std::cout << "    ordId: " << order_data.value("ordId", "") << std::endl;
                std::cout << "    sCode: " << order_data.value("sCode", "") << std::endl;
                std::cout << "    sMsg: " << order_data.value("sMsg", "") << std::endl;
                
                if (order_data["sCode"] == "0") {
                    std::cout << "    ✅ 下单成功" << std::endl;
                    success_count++;
                } else {
                    std::cout << "    ❌ 下单失败: " << order_data.value("sMsg", "") << std::endl;
                    fail_count++;
                }
            }
            std::cout << "\n统计: 成功 " << success_count << " 个, 失败 " << fail_count << " 个" << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n[4] 测试完成" << std::endl;
    return 0;
}
