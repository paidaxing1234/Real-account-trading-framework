/**
 * @file test_manager.cpp
 * @brief 账户管理器测试程序（简化版）
 *
 * 测试内容：
 * 1. 策略账户注册/注销
 * 2. 获取API实例
 * 3. 策略数量查询
 */

#include "../server/managers/account_manager.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <cassert>

using namespace trading::server;
using namespace trading;

// 测试计数器
int total_tests = 0;
int passed_tests = 0;
int failed_tests = 0;

// 测试宏
#define TEST_START(name) \
    std::cout << "\n========== 测试: " << name << " ==========" << std::endl; \
    total_tests++;

#define TEST_ASSERT(condition, message) \
    if (condition) { \
        std::cout << "✓ PASS: " << message << std::endl; \
        passed_tests++; \
    } else { \
        std::cout << "✗ FAIL: " << message << std::endl; \
        failed_tests++; \
    }

#define TEST_END() \
    std::cout << "========================================\n" << std::endl;

// ==================== 辅助函数 ====================

void print_summary() {
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "测试总结" << std::endl;
    std::cout << std::string(50, '=') << std::endl;
    std::cout << "总测试数: " << total_tests << std::endl;
    std::cout << "通过: " << passed_tests << " ✓" << std::endl;
    std::cout << "失败: " << failed_tests << " ✗" << std::endl;
    std::cout << "成功率: " << (total_tests > 0 ? (passed_tests * 100.0 / total_tests) : 0) << "%" << std::endl;
    std::cout << std::string(50, '=') << std::endl;
}

// ==================== 测试用例 ====================

/**
 * 测试1: 策略账户注册和注销
 */
void test_account_registration() {
    TEST_START("策略账户注册和注销");

    std::string strategy_id = "test_strategy_001";
    std::string api_key = "test_api_key_12345678";
    std::string secret_key = "test_secret_key_12345678";
    std::string passphrase = "test_passphrase";

    // 测试注册
    bool reg_result = register_strategy_account(strategy_id, api_key, secret_key, passphrase, true);
    TEST_ASSERT(reg_result, "策略账户注册应该成功");

    // 测试获取API
    okx::OKXRestAPI* api = get_api_for_strategy(strategy_id);
    TEST_ASSERT(api != nullptr, "注册后应该能获取到API实例");

    // 测试注销
    bool unreg_result = unregister_strategy_account(strategy_id);
    TEST_ASSERT(unreg_result, "策略账户注销应该成功");

    // 测试注销后获取API
    okx::OKXRestAPI* api_after = get_api_for_strategy(strategy_id);
    TEST_ASSERT(api_after == nullptr, "注销后应该获取不到API实例");

    TEST_END();
}

/**
 * 测试2: 获取API实例
 */
void test_get_api() {
    TEST_START("获取API实例");

    // 测试获取不存在策略的API
    okx::OKXRestAPI* okx_api = get_okx_api_for_strategy("non_existent_strategy");
    TEST_ASSERT(okx_api == nullptr, "获取不存在策略的OKX API应该返回nullptr");

    binance::BinanceRestAPI* binance_api = get_binance_api_for_strategy("non_existent_strategy");
    TEST_ASSERT(binance_api == nullptr, "获取不存在策略的Binance API应该返回nullptr");

    // 注册一个策略并测试
    std::string strategy_id = "test_api_strategy";
    register_strategy_account(strategy_id, "api_key_12345678", "secret_key_12345678", "passphrase", true);

    okx::OKXRestAPI* api = get_api_for_strategy(strategy_id);
    TEST_ASSERT(api != nullptr, "注册后应该能获取到API实例");

    okx::OKXRestAPI* okx_api2 = get_okx_api_for_strategy(strategy_id);
    TEST_ASSERT(okx_api2 != nullptr, "get_okx_api_for_strategy应该返回有效指针");

    // 清理
    unregister_strategy_account(strategy_id);

    TEST_END();
}

/**
 * 测试3: 策略数量查询
 */
void test_strategy_count() {
    TEST_START("策略数量查询");

    size_t initial_count = get_registered_strategy_count();
    std::cout << "初始策略数量: " << initial_count << std::endl;

    // 注册几个策略
    register_strategy_account("count_test_1", "key1_12345678", "secret1_12345678", "pass1", true);
    register_strategy_account("count_test_2", "key2_12345678", "secret2_12345678", "pass2", true);
    register_strategy_account("count_test_3", "key3_12345678", "secret3_12345678", "pass3", true);

    size_t after_reg_count = get_registered_strategy_count();
    std::cout << "注册后策略数量: " << after_reg_count << std::endl;
    TEST_ASSERT(after_reg_count >= initial_count + 3, "注册后策略数量应该增加3");

    // 注销策略
    unregister_strategy_account("count_test_1");
    unregister_strategy_account("count_test_2");
    unregister_strategy_account("count_test_3");

    size_t after_unreg_count = get_registered_strategy_count();
    std::cout << "注销后策略数量: " << after_unreg_count << std::endl;
    TEST_ASSERT(after_unreg_count == initial_count, "注销后策略数量应该恢复");

    TEST_END();
}

// ==================== 主函数 ====================

int main() {
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "账户管理器测试程序（简化版）" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    std::cout << "\n开始执行测试...\n" << std::endl;

    try {
        // 执行所有测试
        test_account_registration();
        test_get_api();
        test_strategy_count();

        // 打印测试总结
        print_summary();

        return (failed_tests == 0) ? 0 : 1;

    } catch (const std::exception& e) {
        std::cerr << "\n测试过程中发生异常: " << e.what() << std::endl;
        return 1;
    }
}
