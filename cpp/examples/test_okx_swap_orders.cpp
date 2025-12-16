/**
 * @file test_okx_swap_orders.cpp
 * @brief 测试OKX BTC永续合约下单和批量下单接口
 * 
 * 测试内容：
 * 1. BTC-USDT-SWAP 永续合约单个下单
 * 2. BTC-USDT-SWAP 永续合约批量下单
 * 
 * 注意事项：
 * - 永续合约交易模式：cross（全仓）或 isolated（逐仓）
 * - 合约数量单位：张（如1张、10张）
 * - 需要足够的保证金
 * 
 * 编译运行：
 *   cd build && make test_okx_swap_orders && ./test_okx_swap_orders
 */

#include "adapters/okx/okx_rest_api.h"
#include <iostream>
#include <vector>
#include <cstdlib>
#include <chrono>
#include <thread>

using namespace trading::okx;

// 默认代理设置
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// API 密钥配置（模拟盘）
const std::string API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
const std::string SECRET_KEY = "888CC77C745F1B49E75A992F38929992";
const std::string PASSPHRASE = "Sequence2025.";

// 生成唯一的订单ID
std::string gen_order_id(const std::string& prefix) {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    return prefix + std::to_string(ms % 1000000000);
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX BTC永续合约下单测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 设置代理
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") && 
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置代理: " << DEFAULT_PROXY << std::endl;
    }
    
    std::cout << "[密钥] API Key: " << API_KEY.substr(0, 8) << "..." << std::endl;
    
    // 创建API客户端（使用模拟盘）
    OKXRestAPI api(API_KEY, SECRET_KEY, PASSPHRASE, true);
    
    // ==================== 测试1: 单个永续合约下单 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试1: BTC永续合约单个下单" << std::endl;
    std::cout << "========================================" << std::endl;
    
    std::string swap_inst_id = "BTC-USDT-SWAP";
    std::string order_id_1 = gen_order_id("swap");
    
    std::cout << "\n[1] 下单参数:" << std::endl;
    std::cout << "    产品ID: " << swap_inst_id << std::endl;
    std::cout << "    交易模式: cross (全仓)" << std::endl;
    std::cout << "    方向: buy (开多)" << std::endl;
    std::cout << "    订单类型: limit (限价单)" << std::endl;
    std::cout << "    数量: 1 张" << std::endl;
    std::cout << "    价格: 50000 USDT (低于当前价，不会成交)" << std::endl;
    std::cout << "    订单ID: " << order_id_1 << std::endl;
    
    try {
        // 使用新接口下单
        PlaceOrderRequest req1;
        req1.inst_id = swap_inst_id;
        req1.td_mode = "cross";      // 全仓模式
        req1.side = "buy";           // 买入
        req1.ord_type = "limit";     // 限价单
        req1.sz = "1";               // 1张合约
        req1.px = "50000";           // 价格设置较低，确保不成交
        req1.cl_ord_id = order_id_1;
        // 注意：如果是双向持仓模式，需要设置 posSide
        // req1.pos_side = "long";   // 开多
        
        auto resp1 = api.place_order_advanced(req1);
        
        std::cout << "\n[2] 下单响应:" << std::endl;
        std::cout << "    code: " << resp1.code << std::endl;
        std::cout << "    msg: " << resp1.msg << std::endl;
        std::cout << "    ordId: " << resp1.ord_id << std::endl;
        std::cout << "    sCode: " << resp1.s_code << std::endl;
        std::cout << "    sMsg: " << resp1.s_msg << std::endl;
        
        if (resp1.is_success()) {
            std::cout << "\n✅ 永续合约下单成功!" << std::endl;
            
            // 撤单
            std::cout << "\n[3] 撤单..." << std::endl;
            auto cancel_result = api.cancel_order(swap_inst_id, resp1.ord_id);
            if (cancel_result["code"] == "0") {
                std::cout << "✅ 撤单成功" << std::endl;
            } else {
                std::cout << "⚠️  撤单结果: " << cancel_result.dump(2) << std::endl;
            }
        } else {
            std::cout << "\n❌ 永续合约下单失败: " << resp1.s_msg << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    // ==================== 测试2: 批量永续合约下单 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试2: BTC永续合约批量下单" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // 生成唯一的订单ID后缀
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
    std::string id_suffix = std::to_string(ms % 1000000000);
    
    std::vector<PlaceOrderRequest> orders;
    
    // 订单1：BTC永续合约限价买单（开多）
    PlaceOrderRequest order1;
    order1.inst_id = "BTC-USDT-SWAP";
    order1.td_mode = "cross";        // 全仓
    order1.side = "buy";             // 买入
    order1.ord_type = "limit";
    order1.sz = "1";                 // 1张
    order1.px = "50000";             // 低价，不成交
    order1.cl_ord_id = "swapbuy1" + id_suffix;
    orders.push_back(order1);
    
    // 订单2：BTC永续合约限价买单（开多，不同价格）
    PlaceOrderRequest order2;
    order2.inst_id = "BTC-USDT-SWAP";
    order2.td_mode = "cross";
    order2.side = "buy";
    order2.ord_type = "limit";
    order2.sz = "1";
    order2.px = "51000";
    order2.cl_ord_id = "swapbuy2" + id_suffix;
    orders.push_back(order2);
    
    // 订单3：BTC永续合约限价卖单（开空）
    PlaceOrderRequest order3;
    order3.inst_id = "BTC-USDT-SWAP";
    order3.td_mode = "cross";
    order3.side = "sell";            // 卖出（开空）
    order3.ord_type = "limit";
    order3.sz = "1";
    order3.px = "150000";            // 高价，不成交
    order3.cl_ord_id = "swapsell1" + id_suffix;
    orders.push_back(order3);
    
    std::cout << "\n[1] 准备批量下单..." << std::endl;
    std::cout << "准备提交 " << orders.size() << " 个永续合约订单" << std::endl;
    for (size_t i = 0; i < orders.size(); ++i) {
        std::cout << "  订单" << (i+1) << ": " << orders[i].side 
                  << " " << orders[i].sz << "张 " << orders[i].inst_id 
                  << " @ " << orders[i].px << " (clOrdId: " << orders[i].cl_ord_id << ")" << std::endl;
    }
    
    std::cout << "\n[2] 发送批量下单请求..." << std::endl;
    
    try {
        nlohmann::json response = api.place_batch_orders(orders);
        
        std::cout << "\n[3] 批量下单响应:" << std::endl;
        std::cout << response.dump(2) << std::endl;
        
        // 解析响应
        std::string code = response.value("code", "");
        if (code == "0") {
            std::cout << "\n✅ 批量下单全部成功！" << std::endl;
        } else if (code == "2") {
            std::cout << "\n⚠️  批量下单部分成功: " << response.value("msg", "") << std::endl;
        } else {
            std::cout << "\n❌ 批量下单失败: " << response.value("msg", "未知错误") << std::endl;
        }
        
        // 显示每个订单的详情
        std::vector<std::string> success_ord_ids;
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
                    success_ord_ids.push_back(order_data.value("ordId", ""));
                } else {
                    std::cout << "    ❌ 下单失败: " << order_data.value("sMsg", "") << std::endl;
                    fail_count++;
                }
            }
            std::cout << "\n统计: 成功 " << success_count << " 个, 失败 " << fail_count << " 个" << std::endl;
        }
        
        // 撤销成功的订单
        if (!success_ord_ids.empty()) {
            std::cout << "\n[4] 撤销成功的订单..." << std::endl;
            for (const auto& ord_id : success_ord_ids) {
                if (!ord_id.empty()) {
                    auto cancel_result = api.cancel_order("BTC-USDT-SWAP", ord_id);
                    if (cancel_result["code"] == "0") {
                        std::cout << "  ✅ 订单 " << ord_id << " 撤单成功" << std::endl;
                    } else {
                        std::cout << "  ⚠️  订单 " << ord_id << " 撤单: " 
                                  << cancel_result.value("msg", "") << std::endl;
                    }
                }
            }
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
    }
    
    // ==================== 测试3: 查询永续合约挂单 ====================
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试3: 查询永续合约挂单" << std::endl;
    std::cout << "========================================" << std::endl;
    
    try {
        auto pending = api.get_pending_orders("SWAP", "BTC-USDT-SWAP");
        
        if (pending["code"] == "0" && pending["data"].is_array()) {
            std::cout << "\n当前挂单数量: " << pending["data"].size() << std::endl;
            
            if (pending["data"].size() > 0) {
                std::cout << "\n挂单列表:" << std::endl;
                for (size_t i = 0; i < pending["data"].size() && i < 5; ++i) {
                    const auto& order = pending["data"][i];
                    std::cout << "  " << (i+1) << ". " 
                              << order.value("side", "") << " "
                              << order.value("sz", "") << "张 @ "
                              << order.value("px", "") << " "
                              << "状态:" << order.value("state", "") << std::endl;
                }
            } else {
                std::cout << "  (无挂单)" << std::endl;
            }
        } else {
            std::cout << "查询失败: " << pending.dump(2) << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "查询异常: " << e.what() << std::endl;
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成" << std::endl;
    std::cout << "========================================" << std::endl;
    
    std::cout << "\n💡 提示:" << std::endl;
    std::cout << "  - BTC-USDT-SWAP 是BTC/USDT永续合约" << std::endl;
    std::cout << "  - 合约数量单位是"张"，1张约等于一定数量的BTC" << std::endl;
    std::cout << "  - cross=全仓模式，isolated=逐仓模式" << std::endl;
    std::cout << "  - 如果是双向持仓模式，需要设置posSide(long/short)" << std::endl;
    
    return 0;
}

