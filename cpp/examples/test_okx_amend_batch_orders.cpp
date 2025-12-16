/**
 * @file test_okx_amend_batch_orders.cpp
 * @brief 测试OKX批量修改订单接口
 * 
 * 测试内容：
 * 1. 先批量下单（创建多个订单）
 * 2. 批量修改这些订单（修改价格和数量）
 * 3. 验证修改结果
 * 
 * 编译运行：
 *   cd build && make test_okx_amend_batch_orders && ./test_okx_amend_batch_orders
 */

#include "adapters/okx/okx_rest_api.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <thread>
#include <chrono>
#include <ctime>

using namespace trading::okx;

// 查找 api-key.txt 文件的辅助函数
std::string find_api_key_file() {
    // 尝试多个可能的位置
    std::vector<std::string> paths = {
        "api-key.txt",                    // 当前目录
        "../api-key.txt",                 // 上一级目录（cpp目录）
        "../../api-key.txt",              // 上两级目录
        "cpp/api-key.txt",                // cpp子目录
        "Real-account-trading-framework/cpp/api-key.txt"  // 完整路径
    };
    
    for (const auto& path : paths) {
        std::ifstream test_file(path);
        if (test_file.is_open()) {
            test_file.close();
            return path;
        }
    }
    
    return "";  // 未找到
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX 批量修改订单测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 查找并读取API密钥
    std::string key_file_path = find_api_key_file();
    if (key_file_path.empty()) {
        std::cerr << "❌ 无法找到 api-key.txt 文件" << std::endl;
        std::cerr << "   请确保 api-key.txt 文件存在于以下位置之一：" << std::endl;
        std::cerr << "   - 当前目录 (build/)" << std::endl;
        std::cerr << "   - 上一级目录 (cpp/)" << std::endl;
        std::cerr << "   文件格式：每行一个值（API Key、Secret Key、Passphrase）" << std::endl;
        return 1;
    }
    
    std::ifstream key_file(key_file_path);
    if (!key_file.is_open()) {
        std::cerr << "❌ 无法打开 api-key.txt 文件: " << key_file_path << std::endl;
        return 1;
    }
    
    std::string api_key, secret_key, passphrase;
    std::getline(key_file, api_key);
    std::getline(key_file, secret_key);
    std::getline(key_file, passphrase);
    key_file.close();
    
    // 创建API客户端（使用模拟盘）
    OKXRestAPI api(api_key, secret_key, passphrase, true);
    
    std::cout << "\n[1] 先批量下单（创建多个订单用于后续修改）..." << std::endl;
    
    // 构造批量订单请求
    std::vector<PlaceOrderRequest> orders;
    std::string base_cl_ord_id = "batch_amend_" + std::to_string(std::time(nullptr));
    
    // 订单1：BTC-USDT限价买单
    PlaceOrderRequest order1;
    order1.inst_id = "BTC-USDT";
    order1.td_mode = "cash";
    order1.side = "buy";
    order1.ord_type = "limit";
    order1.sz = "0.001";
    order1.px = "50000";  // 设置一个较低的价格，确保不会立即成交
    order1.cl_ord_id = base_cl_ord_id + "_1";
    orders.push_back(order1);
    
    // 订单2：BTC-USDT限价买单
    PlaceOrderRequest order2;
    order2.inst_id = "BTC-USDT";
    order2.td_mode = "cash";
    order2.side = "buy";
    order2.ord_type = "limit";
    order2.sz = "0.001";
    order2.px = "50000";
    order2.cl_ord_id = base_cl_ord_id + "_2";
    orders.push_back(order2);
    
    // 订单3：ETH-USDT限价买单
    PlaceOrderRequest order3;
    order3.inst_id = "ETH-USDT";
    order3.td_mode = "cash";
    order3.side = "buy";
    order3.ord_type = "limit";
    order3.sz = "0.01";
    order3.px = "2000";  // 设置一个较低的价格
    order3.cl_ord_id = base_cl_ord_id + "_3";
    orders.push_back(order3);
    
    std::cout << "准备提交 " << orders.size() << " 个订单" << std::endl;
    for (size_t i = 0; i < orders.size(); ++i) {
        std::cout << "  订单" << (i+1) << ": " << orders[i].side 
                  << " " << orders[i].sz << " " << orders[i].inst_id 
                  << " @ " << orders[i].px << " (clOrdId: " << orders[i].cl_ord_id << ")" << std::endl;
    }
    
    std::vector<std::string> ord_ids;
    std::vector<std::string> cl_ord_ids;
    
    try {
        nlohmann::json place_response = api.place_batch_orders(orders);
        
        std::cout << "\n批量下单响应:" << std::endl;
        std::cout << place_response.dump(2) << std::endl;
        
        if (place_response["code"] != "0") {
            std::cerr << "❌ 批量下单失败: " << place_response.value("msg", "未知错误") << std::endl;
            return 1;
        }
        
        std::cout << "\n✅ 批量下单成功！" << std::endl;
        
        // 收集订单ID
        if (place_response.contains("data") && place_response["data"].is_array()) {
            for (const auto& order_data : place_response["data"]) {
                std::string ord_id = order_data.value("ordId", "");
                std::string cl_ord_id = order_data.value("clOrdId", "");
                std::string s_code = order_data.value("sCode", "");
                
                if (s_code == "0" && !ord_id.empty()) {
                    ord_ids.push_back(ord_id);
                    cl_ord_ids.push_back(cl_ord_id);
                    std::cout << "  ✅ 订单成功: ordId=" << ord_id << ", clOrdId=" << cl_ord_id << std::endl;
                } else {
                    std::cout << "  ⚠️  订单失败: " << order_data.value("sMsg", "") << std::endl;
                }
            }
        }
        
        if (ord_ids.empty()) {
            std::cerr << "❌ 没有成功下单的订单，无法继续测试" << std::endl;
            return 1;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 批量下单异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n[2] 等待2秒后批量修改订单..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    std::cout << "\n[3] 批量修改订单（修改价格和数量）..." << std::endl;
    std::cout << "    原价格: 50000/2000, 新价格: 51000/2100" << std::endl;
    std::cout << "    原数量: 0.001/0.01, 新数量: 0.002/0.02" << std::endl;
    
    // 构造批量修改订单请求
    std::vector<nlohmann::json> amend_orders;
    
    // 修改订单1（使用ordId）
    if (ord_ids.size() > 0) {
        nlohmann::json amend1;
        amend1["instId"] = "BTC-USDT";
        amend1["ordId"] = ord_ids[0];
        amend1["newPx"] = "51000";  // 新价格
        amend1["newSz"] = "0.002";   // 新数量
        amend1["cxlOnFail"] = false;
        amend1["pxAmendType"] = "0";
        amend_orders.push_back(amend1);
    }
    
    // 修改订单2（使用clOrdId）
    if (cl_ord_ids.size() > 1) {
        nlohmann::json amend2;
        amend2["instId"] = "BTC-USDT";
        amend2["clOrdId"] = cl_ord_ids[1];
        amend2["newPx"] = "51000";
        amend2["newSz"] = "0.002";
        amend2["cxlOnFail"] = false;
        amend2["pxAmendType"] = "0";
        amend_orders.push_back(amend2);
    }
    
    // 修改订单3（ETH-USDT）
    if (ord_ids.size() > 2) {
        nlohmann::json amend3;
        amend3["instId"] = "ETH-USDT";
        amend3["ordId"] = ord_ids[2];
        amend3["newPx"] = "2100";   // 新价格
        amend3["newSz"] = "0.02";    // 新数量
        amend3["cxlOnFail"] = false;
        amend3["pxAmendType"] = "0";
        amend_orders.push_back(amend3);
    }
    
    std::cout << "准备修改 " << amend_orders.size() << " 个订单" << std::endl;
    
    try {
        nlohmann::json amend_response = api.amend_batch_orders(amend_orders);
        
        std::cout << "\n[4] 批量修改订单响应:" << std::endl;
        std::cout << amend_response.dump(2) << std::endl;
        
        if (amend_response["code"] == "0") {
            std::cout << "\n✅ 批量修改订单请求已接受！" << std::endl;
            
            if (amend_response.contains("data") && amend_response["data"].is_array()) {
                std::cout << "\n修改结果详情:" << std::endl;
                for (size_t i = 0; i < amend_response["data"].size(); ++i) {
                    const auto& order_data = amend_response["data"][i];
                    std::cout << "  订单" << (i+1) << ":" << std::endl;
                    std::cout << "    ordId: " << order_data.value("ordId", "") << std::endl;
                    std::cout << "    clOrdId: " << order_data.value("clOrdId", "") << std::endl;
                    std::cout << "    reqId: " << order_data.value("reqId", "") << std::endl;
                    std::cout << "    sCode: " << order_data.value("sCode", "") << std::endl;
                    std::cout << "    sMsg: " << order_data.value("sMsg", "") << std::endl;
                    
                    if (order_data["sCode"] != "0") {
                        std::cout << "    ⚠️  修改失败: " << order_data.value("sMsg", "") << std::endl;
                    } else {
                        std::cout << "    ✅ 修改请求已接受（实际修改结果以订单频道推送或查询订单状态为准）" << std::endl;
                    }
                }
            }
        } else {
            std::cout << "\n❌ 批量修改订单失败: " << amend_response.value("msg", "未知错误") << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 批量修改订单异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n[5] 等待1秒后查询订单状态（验证修改是否生效）..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    // 查询所有订单状态
    for (size_t i = 0; i < ord_ids.size() && i < 3; ++i) {
        try {
            std::string inst_id = (i < 2) ? "BTC-USDT" : "ETH-USDT";
            nlohmann::json query_response = api.get_order(inst_id, ord_ids[i]);
            
            if (query_response["code"] == "0" && query_response["data"].is_array() && !query_response["data"].empty()) {
                const auto& order_info = query_response["data"][0];
                std::cout << "\n订单" << (i+1) << " 当前状态:" << std::endl;
                std::cout << "  ordId: " << order_info.value("ordId", "") << std::endl;
                std::cout << "  价格: " << order_info.value("px", "") << std::endl;
                std::cout << "  数量: " << order_info.value("sz", "") << std::endl;
                std::cout << "  状态: " << order_info.value("state", "") << std::endl;
            }
        } catch (const std::exception& e) {
            std::cerr << "查询订单" << (i+1) << "失败: " << e.what() << std::endl;
        }
    }
    
    std::cout << "\n[6] 测试完成" << std::endl;
    std::cout << "\n💡 提示: 如果订单未成交，可以手动在OKX模拟盘上查看订单状态" << std::endl;
    return 0;
}

