/**
 * @file test_risk_manager.cpp
 * @brief 风控系统测试用例
 *
 * 测试内容：
 * 1. 订单金额限制
 * 2. 订单数量限制
 * 3. 持仓限制
 * 4. 频率限制
 * 5. 每日亏损限制
 * 6. Kill Switch 功能
 * 7. 账户余额检查
 * 8. 批量订单检查
 */

#include "../trading/risk_manager.h"
#include <iostream>
#include <cassert>
#include <thread>
#include <chrono>

using namespace trading;

// 测试计数器
int passed = 0;
int failed = 0;

// 断言辅助函数
void assert_true(bool condition, const std::string& message) {
    if (!condition) {
        std::cerr << "❌ FAILED: " << message << std::endl;
        failed++;
        throw std::runtime_error(message);
    }
    std::cout << "✓ PASSED: " << message << std::endl;
    passed++;
}

// 测试1: 订单金额限制
void test_order_value_limit() {
    std::cout << "\n=== 测试1: 订单金额限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_order_value = 10000.0;  // 最大10000 USDT
    RiskManager rm(limits);

    // 测试超限订单（50000 * 1.0 = 50000 USDT）
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 1.0);
    assert_true(!result.passed, "超限订单被拒绝");
    assert_true(result.reason.find("Order value") != std::string::npos, "错误信息包含订单金额");

    // 测试正常订单（50000 * 0.1 = 5000 USDT）
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.1);
    assert_true(result.passed, "正常订单通过");
}

// 测试2: 订单数量限制
void test_order_quantity_limit() {
    std::cout << "\n=== 测试2: 订单数量限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_order_quantity = 10.0;  // 最大10个
    limits.max_order_value = 1000000.0;  // 设置足够大的订单金额限制
    limits.max_position_value = 1000000.0;  // 设置足够大的持仓限制
    limits.max_total_exposure = 10000000.0;  // 设置足够大的总敞口限制
    RiskManager rm(limits);

    // 测试超限数量
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 20.0);
    assert_true(!result.passed, "超限数量被拒绝");

    // 测试正常数量
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 5.0);
    assert_true(result.passed, "正常数量通过");
}

// 测试3: 持仓限制
void test_position_limit() {
    std::cout << "\n=== 测试3: 持仓限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_position_value = 20000.0;  // 单品种最大20000 USDT
    RiskManager rm(limits);

    // 设置当前持仓
    rm.update_position("BTC-USDT", 15000.0);

    // 测试会超过持仓限制的订单（15000 + 10000 = 25000 > 20000）
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.2);
    assert_true(!result.passed, "超过持仓限制被拒绝");

    // 测试不超过限制的订单（15000 + 2500 = 17500 < 20000）
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.05);
    assert_true(result.passed, "未超过持仓限制通过");
}

// 测试4: 频率限制
void test_rate_limit() {
    std::cout << "\n=== 测试4: 频率限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_orders_per_second = 3;  // 每秒最多3单
    RiskManager rm(limits);

    // 快速下3单
    for (int i = 0; i < 3; i++) {
        auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
        assert_true(result.passed, "前3单通过");
        rm.record_order_execution();  // 记录订单执行
    }

    // 第4单应该被拒绝
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(!result.passed, "第4单被频率限制拒绝");
    assert_true(result.reason.find("rate limit") != std::string::npos, "错误信息包含频率限制");

    // 等待1秒后应该可以继续下单
    std::this_thread::sleep_for(std::chrono::seconds(1));
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(result.passed, "等待后可以继续下单");
}

// 测试5: 每日亏损限制
void test_daily_loss_limit() {
    std::cout << "\n=== 测试5: 每日亏损限制 ===" << std::endl;

    RiskLimits limits;
    limits.daily_loss_limit = 5000.0;  // 每日最大亏损5000 USDT
    limits.max_drawdown_pct = 0.99;    // 设置很大的回撤限制，避免触发Kill Switch
    RiskManager rm(limits);

    // 设置当前亏损为-6000（超过限制）
    rm.update_daily_pnl(-6000.0);

    // 任何订单都应该被拒绝
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(!result.passed, "超过每日亏损限制被拒绝");
    assert_true(result.reason.find("Daily loss") != std::string::npos ||
                result.reason.find("Kill switch") != std::string::npos, "错误信息包含每日亏损或Kill switch");
}

// 测试6: Kill Switch 功能
void test_kill_switch() {
    std::cout << "\n=== 测试6: Kill Switch 功能 ===" << std::endl;

    RiskManager rm;

    // 激活 Kill Switch
    rm.activate_kill_switch("测试紧急止损");
    assert_true(rm.is_kill_switch_active(), "Kill Switch 已激活");

    // 任何订单都应该被拒绝
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(!result.passed, "Kill Switch 激活后订单被拒绝");
    assert_true(result.reason.find("Kill switch") != std::string::npos, "错误信息包含Kill switch");

    // 解除 Kill Switch
    rm.deactivate_kill_switch();
    assert_true(!rm.is_kill_switch_active(), "Kill Switch 已解除");

    // 订单应该可以通过
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(result.passed, "Kill Switch 解除后订单通过");
}

// 测试7: 账户余额检查
void test_account_balance() {
    std::cout << "\n=== 测试7: 账户余额检查 ===" << std::endl;

    RiskManager rm;

    // 测试余额不足
    auto result = rm.check_account_balance(500.0, 1000.0);
    assert_true(!result.passed, "余额不足被拒绝");
    assert_true(result.reason.find("balance") != std::string::npos, "错误信息包含余额");

    // 测试余额充足
    result = rm.check_account_balance(5000.0, 1000.0);
    assert_true(result.passed, "余额充足通过");
}

// 测试8: 批量订单检查
void test_batch_orders() {
    std::cout << "\n=== 测试8: 批量订单检查 ===" << std::endl;

    RiskLimits limits;
    limits.max_order_value = 10000.0;
    RiskManager rm(limits);

    // 准备批量订单
    std::vector<std::tuple<std::string, OrderSide, double, double>> orders = {
        {"BTC-USDT", OrderSide::BUY, 50000.0, 0.1},   // 5000 USDT - 通过
        {"ETH-USDT", OrderSide::BUY, 3000.0, 2.0},    // 6000 USDT - 通过
        {"BTC-USDT", OrderSide::SELL, 50000.0, 0.5}   // 25000 USDT - 拒绝
    };

    auto results = rm.check_batch_orders(orders);
    assert_true(results.size() == 3, "返回3个结果");
    assert_true(results[0].passed, "第1单通过");
    assert_true(results[1].passed, "第2单通过");
    assert_true(!results[2].passed, "第3单被拒绝");
}

// 测试9: 最大回撤保护
void test_max_drawdown() {
    std::cout << "\n=== 测试9: 最大回撤保护 ===" << std::endl;

    RiskLimits limits;
    limits.max_drawdown_pct = 0.10;  // 最大回撤10%
    RiskManager rm(limits);

    // 设置初始盈利
    rm.update_daily_pnl(10000.0);  // 峰值10000

    // 设置当前盈利为8500（回撤15%，超过10%限制）
    rm.update_daily_pnl(8500.0);

    // Kill Switch 应该被自动激活
    assert_true(rm.is_kill_switch_active(), "超过最大回撤自动激活Kill Switch");
}

// 测试10: 挂单数量限制
void test_open_orders_limit() {
    std::cout << "\n=== 测试10: 挂单数量限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_open_orders = 5;  // 最多5个挂单
    RiskManager rm(limits);

    // 设置当前挂单数为5
    rm.set_open_order_count(5);

    // 新订单应该被拒绝
    auto result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(!result.passed, "超过挂单数量限制被拒绝");
    assert_true(result.reason.find("Open orders") != std::string::npos, "错误信息包含挂单数量");

    // 减少挂单数
    rm.set_open_order_count(3);
    result = rm.check_order("BTC-USDT", OrderSide::BUY, 50000.0, 0.01);
    assert_true(result.passed, "挂单数量正常时通过");
}

// 测试11: 总敞口限制
void test_total_exposure() {
    std::cout << "\n=== 测试11: 总敞口限制 ===" << std::endl;

    RiskLimits limits;
    limits.max_total_exposure = 50000.0;  // 总敞口50000 USDT
    RiskManager rm(limits);

    // 设置多个品种的持仓
    rm.update_position("BTC-USDT", 20000.0);
    rm.update_position("ETH-USDT", 15000.0);
    rm.update_position("SOL-USDT", 10000.0);
    // 总敞口 = 20000 + 15000 + 10000 = 45000

    // 测试会超过总敞口的订单（45000 + 10000 = 55000 > 50000）
    auto result = rm.check_order("BNB-USDT", OrderSide::BUY, 500.0, 20.0);
    assert_true(!result.passed, "超过总敞口限制被拒绝");

    // 测试不超过限制的订单（45000 + 2000 = 47000 < 50000）
    result = rm.check_order("BNB-USDT", OrderSide::BUY, 500.0, 4.0);
    assert_true(result.passed, "未超过总敞口限制通过");
}

// 测试12: 风控统计信息
void test_risk_stats() {
    std::cout << "\n=== 测试12: 风控统计信息 ===" << std::endl;

    RiskManager rm;

    // 设置一些数据
    rm.update_position("BTC-USDT", 10000.0);
    rm.update_daily_pnl(1500.0);
    rm.set_open_order_count(3);

    // 获取统计信息
    auto stats = rm.get_risk_stats();

    assert_true(stats.contains("kill_switch"), "统计包含kill_switch");
    assert_true(stats.contains("open_orders"), "统计包含open_orders");
    assert_true(stats.contains("daily_pnl"), "统计包含daily_pnl");
    assert_true(stats["open_orders"] == 3, "挂单数正确");
    assert_true(stats["daily_pnl"] == 1500.0, "每日盈亏正确");

    std::cout << "风控统计: " << stats.dump(2) << std::endl;
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  风控系统测试套件" << std::endl;
    std::cout << "========================================" << std::endl;

    try { test_order_value_limit(); } catch (...) {}
    try { test_order_quantity_limit(); } catch (...) {}
    try { test_position_limit(); } catch (...) {}
    try { test_rate_limit(); } catch (...) {}
    try { test_daily_loss_limit(); } catch (...) {}
    try { test_kill_switch(); } catch (...) {}
    try { test_account_balance(); } catch (...) {}
    try { test_batch_orders(); } catch (...) {}
    try { test_max_drawdown(); } catch (...) {}
    try { test_open_orders_limit(); } catch (...) {}
    try { test_total_exposure(); } catch (...) {}
    try { test_risk_stats(); } catch (...) {}

    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试结果: " << passed << " 通过, " << failed << " 失败" << std::endl;
    std::cout << "========================================" << std::endl;

    return failed > 0 ? 1 : 0;
}
