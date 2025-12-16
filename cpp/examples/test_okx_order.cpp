/**
 * @file test_okx_order.cpp
 * @brief OKX 下单API测试程序
 * 
 * 测试内容：
 * 1. 简单限价下单
 * 2. 市价下单
 * 3. 带止盈止损下单
 * 4. 完整参数下单
 * 
 * 编译运行：
 *   cd build && make test_okx_order && ./test_okx_order
 */

#include <iostream>
#include <chrono>
#include <cstdlib>
#include "../adapters/okx/okx_rest_api.h"

using namespace trading::okx;

// 默认代理设置（如果需要代理连接OKX）
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// 生成唯一的订单ID (字母+数字，无特殊字符)
std::string gen_order_id(const std::string& prefix) {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    return prefix + std::to_string(ms % 1000000000);  // 取后9位
}

void print_separator(const std::string& title) {
    std::cout << "\n========================================\n";
    std::cout << "  " << title << "\n";
    std::cout << "========================================\n";
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  OKX 下单API测试\n";
    std::cout << "========================================\n";
    
    // 设置代理（如果环境变量中没有设置）
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") && 
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置代理: " << DEFAULT_PROXY << "\n";
    } else {
        const char* proxy = std::getenv("https_proxy");
        if (!proxy) proxy = std::getenv("HTTPS_PROXY");
        if (!proxy) proxy = std::getenv("all_proxy");
        if (!proxy) proxy = std::getenv("ALL_PROXY");
        std::cout << "\n[代理] 使用环境变量中的代理: " << (proxy ? proxy : "无") << "\n";
    }
    
    // API配置 (模拟盘)
    std::string api_key = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    std::string secret_key = "888CC77C745F1B49E75A992F38929992";
    std::string passphrase = "Sequence2025.";
    bool is_testnet = true;  // 模拟盘
    
    std::cout << "\n配置信息:\n";
    std::cout << "  API Key: " << api_key.substr(0, 8) << "...\n";
    std::cout << "  模式: " << (is_testnet ? "模拟盘" : "实盘") << "\n";
    
    // 初始化API
    OKXRestAPI api(api_key, secret_key, passphrase, is_testnet);
    
    try {
        // ==================== 测试1: 查询账户余额 ====================
        print_separator("测试1: 查询账户余额");
        
        auto balance = api.get_account_balance("USDT");
        std::cout << "响应:\n" << balance.dump(2) << "\n";
        
        // ==================== 测试2: 简单限价下单 ====================
        print_separator("测试2: 简单限价下单 (旧接口)");
        
        // 使用旧接口下单 (向后兼容)
        // 注意: clOrdId 只能包含字母和数字，不能有下划线等特殊字符
        std::string order_id_1 = gen_order_id("cpp");
        std::cout << "生成订单ID: " << order_id_1 << "\n";
        
        auto result1 = api.place_order(
            "BTC-USDT",     // 产品ID
            "cash",         // 交易模式: 现货
            "buy",          // 方向: 买入
            "limit",        // 类型: 限价单
            0.0001,         // 数量
            30000.0,        // 价格 (设置一个不会成交的低价)
            order_id_1      // 客户订单ID (动态生成)
        );
        
        std::cout << "响应:\n" << result1.dump(2) << "\n";
        
        // 如果下单成功，尝试撤单
        if (result1["code"] == "0" && result1.contains("data") && !result1["data"].empty()) {
            std::string ord_id = result1["data"][0]["ordId"];
            std::cout << "\n✅ 下单成功! ordId: " << ord_id << "\n";
            
            // 撤单
            std::cout << "\n尝试撤单...\n";
            auto cancel_result = api.cancel_order("BTC-USDT", ord_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试3: 完整参数下单 ====================
        print_separator("测试3: 完整参数下单 (新接口)");
        
        std::string order_id_2 = gen_order_id("cpp");
        std::cout << "生成订单ID: " << order_id_2 << "\n";
        
        PlaceOrderRequest req;
        req.inst_id = "BTC-USDT";
        req.td_mode = "cash";
        req.side = "buy";
        req.ord_type = "limit";
        req.sz = "0.0001";
        req.px = "30000";
        req.cl_ord_id = order_id_2;
        req.tag = "cpptest";
        
        auto resp2 = api.place_order_advanced(req);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp2.code << "\n";
        std::cout << "  msg: " << resp2.msg << "\n";
        std::cout << "  ordId: " << resp2.ord_id << "\n";
        std::cout << "  clOrdId: " << resp2.cl_ord_id << "\n";
        std::cout << "  sCode: " << resp2.s_code << "\n";
        std::cout << "  sMsg: " << resp2.s_msg << "\n";
        std::cout << "  成功: " << (resp2.is_success() ? "是" : "否") << "\n";
        
        if (resp2.is_success()) {
            std::cout << "\n✅ 下单成功!\n";
            
            // 撤单
            std::cout << "\n尝试撤单...\n";
            auto cancel_result = api.cancel_order("BTC-USDT", resp2.ord_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试4: 带止盈止损下单 ====================
        print_separator("测试4: 带止盈止损下单");
        
        // 注意: 止盈止损只在订单完全成交后才会生效
        // 这里使用一个不会成交的价格来测试API调用
        std::string order_id_3 = gen_order_id("cpp");
        std::cout << "生成订单ID: " << order_id_3 << "\n";
        
        auto resp3 = api.place_order_with_tp_sl(
            "BTC-USDT",     // 产品ID
            "cash",         // 交易模式
            "buy",          // 方向
            "limit",        // 类型
            "0.0001",       // 数量
            "30000",        // 价格
            "55000",        // 止盈触发价
            "-1",           // 止盈委托价 (-1=市价)
            "28000",        // 止损触发价
            "-1",           // 止损委托价 (-1=市价)
            order_id_3      // 客户订单ID (动态生成)
        );
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp3.code << "\n";
        std::cout << "  ordId: " << resp3.ord_id << "\n";
        std::cout << "  sCode: " << resp3.s_code << "\n";
        std::cout << "  sMsg: " << resp3.s_msg << "\n";
        
        if (resp3.is_success()) {
            std::cout << "\n✅ 带止盈止损下单成功!\n";
            
            // 撤单
            std::cout << "\n尝试撤单...\n";
            auto cancel_result = api.cancel_order("BTC-USDT", resp3.ord_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        } else {
            std::cout << "\n⚠️  下单失败: " << resp3.s_msg << "\n";
            std::cout << "注意: 止盈止损可能不支持所有交易模式\n";
        }
        
        // ==================== 测试5: 查询订单 ====================
        print_separator("测试5: 查询挂单");
        
        auto pending = api.get_pending_orders("SPOT", "BTC-USDT");
        std::cout << "挂单列表:\n" << pending.dump(2) << "\n";
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << "\n";
        return 1;
    }
    
    print_separator("测试完成");
    std::cout << "\n✅ 所有测试完成!\n\n";
    
    return 0;
}

