/**
 * @file test_okx_algo_order.cpp
 * @brief OKX 策略委托下单API测试程序
 * 
 * 测试内容：
 * 1. 单向止盈止损委托 (conditional)
 * 2. 计划委托 (trigger) + 修改订单 + 撤销
 * 3. 计划委托带止盈止损 + 撤销
 * 4. 移动止盈止损委托 (move_order_stop) + 撤销
 * 5. 时间加权委托 (twap) + 撤销
 * 6. 双向止盈止损委托 (oco)
 * 7. 追逐限价委托 (chase) + 撤销
 * 8. 查询策略委托订单（单个查询 + 列表查询）
 * 9. 批量撤销策略委托
 * 
 * 编译运行：
 *   cd build && make test_okx_algo_order && ./test_okx_algo_order
 */

#include <iostream>
#include <chrono>
#include <cstdlib>
#include <thread>
#include "../adapters/okx/okx_rest_api.h"

using namespace trading::okx;

// 默认代理设置
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// 生成唯一的订单ID
std::string gen_algo_id(const std::string& prefix) {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    return prefix + std::to_string(ms % 1000000000);
}

void print_separator(const std::string& title) {
    std::cout << "\n========================================\n";
    std::cout << "  " << title << "\n";
    std::cout << "========================================\n";
}

void wait_interval(int seconds = 5) {
    std::cout << "\n⏳ 等待 " << seconds << " 秒后继续下一个测试...\n";
    for (int i = seconds; i > 0; i--) {
        std::cout << "\r剩余时间: " << i << " 秒  " << std::flush;
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    std::cout << "\r✓ 等待完成，开始下一个测试\n";
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  OKX 策略委托下单API测试\n";
    std::cout << "========================================\n";
    
    // 设置代理
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") && 
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置代理: " << DEFAULT_PROXY << "\n";
    }
    
    // API配置 (模拟盘)
    std::string api_key = "5dee6507-e02d-4bfd-9558-d81783d84cb7";
    std::string secret_key = "9B0E54A9843943331EFD0C40547179C8";
    std::string passphrase = "Wbl20041209..";
    bool is_testnet = true;
    
    std::cout << "\n配置信息:\n";
    std::cout << "  API Key: " << api_key.substr(0, 8) << "...\n";
    std::cout << "  模式: " << (is_testnet ? "模拟盘" : "实盘") << "\n";
    
    // 初始化API
    OKXRestAPI api(api_key, secret_key, passphrase, is_testnet);
    
    try {
        // ==================== 测试1: 单向止盈止损委托 (conditional) ====================
        print_separator("测试1: 单向止盈止损委托");
        
        std::string algo_id_1 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_1 << "\n";
        
        // 下一个止盈止损委托
        // 注意：这需要先有持仓才能触发
        PlaceAlgoOrderRequest req1;
        req1.inst_id = "BTC-USDT-SWAP";
        req1.td_mode = "cross";
        req1.side = "buy";
        req1.ord_type = "conditional";
        req1.sz = "1";
        req1.pos_side = "long";
        req1.algo_cl_ord_id = algo_id_1;
        
        // 止盈：当价格涨到 110000 时，以市价平仓
        req1.tp_trigger_px = "110000";
        req1.tp_ord_px = "-1";  // -1 表示市价
        req1.tp_trigger_px_type = "last";
        
        // 止损：当价格跌到 85000 时，以市价平仓
        req1.sl_trigger_px = "85000";
        req1.sl_ord_px = "-1";
        req1.sl_trigger_px_type = "last";
        
        auto resp1 = api.place_algo_order(req1);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp1.code << "\n";
        std::cout << "  msg: " << resp1.msg << "\n";
        std::cout << "  algoId: " << resp1.algo_id << "\n";
        std::cout << "  algoClOrdId: " << resp1.algo_cl_ord_id << "\n";
        std::cout << "  sCode: " << resp1.s_code << "\n";
        std::cout << "  sMsg: " << resp1.s_msg << "\n";
        std::cout << "  成功: " << (resp1.is_success() ? "是" : "否") << "\n";
        
        // ==================== 测试2: 计划委托 (trigger) ====================
        print_separator("测试2: 计划委托");
        
        std::string algo_id_2 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_2 << "\n";
        
        // 当价格跌到 85000 时，自动以市价买入
        auto resp2 = api.place_trigger_order(
            "BTC-USDT-SWAP",  // 产品ID
            "cross",          // 全仓模式
            "buy",            // 买入
            "1",              // 1张
            "85000",          // 触发价
            "-1",             // 委托价（-1表示市价）
            "long"            // 开多
        );
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp2.code << "\n";
        std::cout << "  msg: " << resp2.msg << "\n";
        std::cout << "  algoId: " << resp2.algo_id << "\n";
        std::cout << "  sCode: " << resp2.s_code << "\n";
        std::cout << "  sMsg: " << resp2.s_msg << "\n";
        std::cout << "  成功: " << (resp2.is_success() ? "是" : "否") << "\n";
        
        // 如果下单成功，尝试修改订单
        if (resp2.is_success() && !resp2.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试修改策略委托订单（触发价改为84000）...\n";
            auto amend_result = api.amend_trigger_order(
                "BTC-USDT-SWAP",
                resp2.algo_id,
                "84000",  // 新触发价
                "-1"      // 新委托价（市价）
            );
            std::cout << "修改响应:\n";
            std::cout << "  code: " << amend_result.code << "\n";
            std::cout << "  algoId: " << amend_result.algo_id << "\n";
            std::cout << "  sCode: " << amend_result.s_code << "\n";
            std::cout << "  sMsg: " << amend_result.s_msg << "\n";
            std::cout << "  成功: " << (amend_result.is_success() ? "是" : "否") << "\n";
            
            wait_interval();  // 修改后等待
            
            // 修改后再撤单
            std::cout << "\n尝试撤销策略委托订单...\n";
            auto cancel_result = api.cancel_algo_order("BTC-USDT-SWAP", resp2.algo_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试3: 计划委托带止盈止损 ====================
        print_separator("测试3: 计划委托带止盈止损");
        
        std::string algo_id_3 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_3 << "\n";
        
        PlaceAlgoOrderRequest req3;
        req3.inst_id = "BTC-USDT-SWAP";
        req3.td_mode = "cross";
        req3.side = "buy";
        req3.ord_type = "trigger";
        req3.sz = "1";
        req3.pos_side = "long";
        req3.trigger_px = "85000";      // 触发价
        req3.order_px = "-1";           // 市价
        req3.trigger_px_type = "last";
        req3.algo_cl_ord_id = algo_id_3;
        
        // 附带止盈止损
        AttachAlgoOrder attach_tp_sl;
        attach_tp_sl.tp_trigger_px = "95000";   // 止盈触发价
        attach_tp_sl.tp_ord_px = "-1";          // 止盈市价
        attach_tp_sl.sl_trigger_px = "80000";   // 止损触发价
        attach_tp_sl.sl_ord_px = "-1";          // 止损市价
        req3.attach_algo_ords.push_back(attach_tp_sl);
        
        auto resp3 = api.place_algo_order(req3);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp3.code << "\n";
        std::cout << "  msg: " << resp3.msg << "\n";
        std::cout << "  algoId: " << resp3.algo_id << "\n";
        std::cout << "  sCode: " << resp3.s_code << "\n";
        std::cout << "  sMsg: " << resp3.s_msg << "\n";
        std::cout << "  成功: " << (resp3.is_success() ? "是" : "否") << "\n";
        
        // 如果下单成功，尝试撤单
        if (resp3.is_success() && !resp3.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试撤销策略委托订单...\n";
            auto cancel_result = api.cancel_algo_order("BTC-USDT-SWAP", resp3.algo_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试4: 移动止盈止损 ====================
        print_separator("测试4: 移动止盈止损");
        
        std::string algo_id_4 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_4 << "\n";
        
        // 移动止盈止损：回调幅度 5%
        auto resp4 = api.place_move_stop_order(
            "BTC-USDT-SWAP",  // 产品ID
            "cross",          // 全仓模式
            "buy",            // 买入方向（平空仓）
            "1",              // 1张
            "0.05",           // 回调幅度 5%
            "",               // 激活价格（不填则下单后立即激活）
            "short"           // 平空仓
        );
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp4.code << "\n";
        std::cout << "  msg: " << resp4.msg << "\n";
        std::cout << "  algoId: " << resp4.algo_id << "\n";
        std::cout << "  sCode: " << resp4.s_code << "\n";
        std::cout << "  sMsg: " << resp4.s_msg << "\n";
        std::cout << "  成功: " << (resp4.is_success() ? "是" : "否") << "\n";
        
        // 如果下单成功，尝试撤单
        if (resp4.is_success() && !resp4.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试撤销策略委托订单...\n";
            auto cancel_result = api.cancel_algo_order("BTC-USDT-SWAP", resp4.algo_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试5: 时间加权委托 (TWAP) ====================
        print_separator("测试5: 时间加权委托");
        
        std::string algo_id_5 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_5 << "\n";
        
        PlaceAlgoOrderRequest req5;
        req5.inst_id = "BTC-USDT-SWAP";
        req5.td_mode = "cross";
        req5.side = "buy";
        req5.ord_type = "twap";
        req5.sz = "10";              // 总数量 10张
        req5.pos_side = "long";
        req5.algo_cl_ord_id = algo_id_5;
        
        // TWAP参数
        req5.sz_limit = "2";         // 单笔数量 2张
        req5.px_limit = "100000";    // 限制价
        req5.time_interval = "10";   // 下单间隔 10秒
        req5.px_spread = "100";      // 价距 100 USDT
        
        auto resp5 = api.place_algo_order(req5);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp5.code << "\n";
        std::cout << "  msg: " << resp5.msg << "\n";
        std::cout << "  algoId: " << resp5.algo_id << "\n";
        std::cout << "  sCode: " << resp5.s_code << "\n";
        std::cout << "  sMsg: " << resp5.s_msg << "\n";
        std::cout << "  成功: " << (resp5.is_success() ? "是" : "否") << "\n";
        
        // 如果下单成功，尝试撤单
        if (resp5.is_success() && !resp5.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试撤销策略委托订单...\n";
            auto cancel_result = api.cancel_algo_order("BTC-USDT-SWAP", resp5.algo_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试6: 双向止盈止损 (OCO) ====================
        print_separator("测试6: 双向止盈止损 (OCO)");
        
        std::string algo_id_6 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_6 << "\n";
        
        PlaceAlgoOrderRequest req6;
        req6.inst_id = "BTC-USDT-SWAP";
        req6.td_mode = "cross";
        req6.side = "buy";
        req6.ord_type = "oco";
        req6.sz = "1";
        req6.pos_side = "long";
        req6.algo_cl_ord_id = algo_id_6;
        
        // 止盈和止损都必须设置
        req6.tp_trigger_px = "110000";
        req6.tp_ord_px = "-1";
        req6.sl_trigger_px = "85000";
        req6.sl_ord_px = "-1";
        
        auto resp6 = api.place_algo_order(req6);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp6.code << "\n";
        std::cout << "  msg: " << resp6.msg << "\n";
        std::cout << "  algoId: " << resp6.algo_id << "\n";
        std::cout << "  sCode: " << resp6.s_code << "\n";
        std::cout << "  sMsg: " << resp6.s_msg << "\n";
        std::cout << "  成功: " << (resp6.is_success() ? "是" : "否") << "\n";
        
        // ==================== 测试7: 追逐限价委托 (Chase) ====================
        print_separator("测试7: 追逐限价委托 (Chase)");
        
        std::string algo_id_7 = gen_algo_id("cpp");
        std::cout << "生成策略订单ID: " << algo_id_7 << "\n";
        
        PlaceAlgoOrderRequest req7;
        req7.inst_id = "BTC-USDT-SWAP";
        req7.td_mode = "cross";
        req7.side = "buy";
        req7.ord_type = "chase";
        req7.sz = "1";
        req7.pos_side = "long";
        req7.algo_cl_ord_id = algo_id_7;
        
        // 追逐限价委托参数
        req7.chase_type = "distance";    // 追逐类型：距离
        req7.chase_val = "10";           // 追逐值：距离买一价 10 USDT
        req7.reduce_only = false;
        
        auto resp7 = api.place_algo_order(req7);
        
        std::cout << "响应:\n";
        std::cout << "  code: " << resp7.code << "\n";
        std::cout << "  msg: " << resp7.msg << "\n";
        std::cout << "  algoId: " << resp7.algo_id << "\n";
        std::cout << "  sCode: " << resp7.s_code << "\n";
        std::cout << "  sMsg: " << resp7.s_msg << "\n";
        std::cout << "  成功: " << (resp7.is_success() ? "是" : "否") << "\n";
        
        // 如果下单成功，尝试撤单
        if (resp7.is_success() && !resp7.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试撤销策略委托订单...\n";
            auto cancel_result = api.cancel_algo_order("BTC-USDT-SWAP", resp7.algo_id);
            std::cout << "撤单响应:\n" << cancel_result.dump(2) << "\n";
        }
        
        // ==================== 测试8: 查询策略委托订单 ====================
        print_separator("测试8: 查询策略委托订单");
        
        // 先创建一个订单用于查询
        std::string query_algo_id = gen_algo_id("query");
        auto query_resp = api.place_trigger_order(
            "BTC-USDT-SWAP", "cross", "buy", "1", "83000", "-1", "long"
        );
        
        std::cout << "创建查询测试订单: algoId=" << query_resp.algo_id 
                  << " (成功: " << (query_resp.is_success() ? "是" : "否") << ")\n";
        
        if (query_resp.is_success() && !query_resp.algo_id.empty()) {
            wait_interval();  // 下单后等待
            
            // 查询单个订单
            std::cout << "\n1. 查询单个策略委托订单...\n";
            auto order_info = api.get_algo_order(query_resp.algo_id);
            std::cout << "订单信息:\n" << order_info.dump(2) << "\n";
            
            // 查询未完成订单列表
            std::cout << "\n2. 查询未完成计划委托列表...\n";
            auto pending_orders = api.get_algo_orders_pending(
                "trigger",           // 订单类型
                "SWAP",             // 产品类型
                "BTC-USDT-SWAP",    // 产品ID
                "",                 // after
                "",                 // before
                10                  // limit
            );
            std::cout << "未完成订单数量: " << pending_orders["data"].size() << "\n";
            if (pending_orders["data"].size() > 0) {
                std::cout << "第一个订单:\n" << pending_orders["data"][0].dump(2) << "\n";
            }
            
            // 查询历史订单列表
            std::cout << "\n3. 查询历史已撤销订单列表...\n";
            auto history_orders = api.get_algo_orders_history(
                "trigger",           // 订单类型
                "canceled",          // 订单状态：已撤销
                "",                  // algoId（与state二选一）
                "SWAP",             // 产品类型
                "BTC-USDT-SWAP",    // 产品ID
                "",                 // after
                "",                 // before
                5                   // limit
            );
            std::cout << "历史已撤销订单数量: " << history_orders["data"].size() << "\n";
            if (history_orders["data"].size() > 0) {
                std::cout << "第一个历史订单:\n" << history_orders["data"][0].dump(2) << "\n";
            }
            
            wait_interval();  // 查询后等待
            
            // 撤销测试订单
            std::cout << "\n撤销测试订单...\n";
            auto cancel_query = api.cancel_algo_order("BTC-USDT-SWAP", query_resp.algo_id);
            std::cout << "撤单结果: " << cancel_query.dump(2) << "\n";
        }
        
        // ==================== 测试9: 批量撤销策略委托 ====================
        print_separator("测试9: 批量撤销策略委托");
        
        std::cout << "创建多个策略委托订单用于批量撤销测试...\n";
        
        // 创建第一个订单
        std::string batch_algo_id_1 = gen_algo_id("batch");
        auto batch_resp1 = api.place_trigger_order(
            "BTC-USDT-SWAP", "cross", "buy", "1", "85000", "-1", "long"
        );
        
        // 创建第二个订单
        std::string batch_algo_id_2 = gen_algo_id("batch");
        auto batch_resp2 = api.place_trigger_order(
            "BTC-USDT-SWAP", "cross", "buy", "1", "84000", "-1", "long"
        );
        
        std::cout << "订单1 algoId: " << batch_resp1.algo_id << " (成功: " 
                  << (batch_resp1.is_success() ? "是" : "否") << ")\n";
        std::cout << "订单2 algoId: " << batch_resp2.algo_id << " (成功: " 
                  << (batch_resp2.is_success() ? "是" : "否") << ")\n";
        
        // 批量撤销
        if (batch_resp1.is_success() && batch_resp2.is_success()) {
            wait_interval();  // 下单后等待
            
            std::cout << "\n尝试批量撤销策略委托订单...\n";
            
            std::vector<nlohmann::json> cancel_orders;
            cancel_orders.push_back({
                {"instId", "BTC-USDT-SWAP"},
                {"algoId", batch_resp1.algo_id}
            });
            cancel_orders.push_back({
                {"instId", "BTC-USDT-SWAP"},
                {"algoId", batch_resp2.algo_id}
            });
            
            auto batch_cancel_result = api.cancel_algo_orders(cancel_orders);
            std::cout << "批量撤单响应:\n" << batch_cancel_result.dump(2) << "\n";
        }
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << "\n";
        return 1;
    }
    
    print_separator("测试完成");
    std::cout << "\n✅ 所有测试完成!\n";
    std::cout << "\n注意事项:\n";
    std::cout << "  - 止盈止损委托需要有对应的持仓才能生效\n";
    std::cout << "  - 计划委托在价格达到触发价时才会下单\n";
    std::cout << "  - 移动止盈止损会跟踪价格变动\n";
    std::cout << "  - 时间加权委托会分批执行大额订单\n";
    std::cout << "  - 追逐限价委托会跟随深度变动进行改单\n\n";
    
    return 0;
}

