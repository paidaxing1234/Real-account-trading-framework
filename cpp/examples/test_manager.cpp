/**
 * @file test_manager.cpp
 * @brief 账户管理器测试程序
 *
 * 测试内容：
 * 1. OKX账户注册/更新/注销
 * 2. Binance账户注册/更新/注销（多市场）
 * 3. 参数验证（无效策略ID、无效凭证）
 * 4. 批量操作
 * 5. 查询功能
 * 6. API密钥脱敏
 * 7. 向后兼容接口
 * 8. 错误处理
 */

#include "../server/managers/account_manager.h"
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/binance/binance_rest_api.h"
#include "../core/logger.h"
#include <iostream>
#include <cassert>
#include <vector>

using namespace trading::server;
using namespace trading::core;
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

void print_account_info(const nlohmann::json& info) {
    std::cout << "账户信息:\n" << info.dump(2) << std::endl;
}

// ==================== 测试用例 ====================

/**
 * 测试1: 参数验证功能
 */
void test_parameter_validation() {
    TEST_START("参数验证");

    // 测试策略ID验证
    TEST_ASSERT(validate_strategy_id("valid_strategy_123"), "有效的策略ID应该通过验证");
    TEST_ASSERT(validate_strategy_id("strategy-with-dash"), "带连字符的策略ID应该通过验证");
    TEST_ASSERT(!validate_strategy_id(""), "空策略ID应该验证失败");
    TEST_ASSERT(!validate_strategy_id("invalid@strategy"), "包含非法字符的策略ID应该验证失败");
    TEST_ASSERT(!validate_strategy_id("strategy with space"), "包含空格的策略ID应该验证失败");

    // 测试API密钥脱敏
    std::string api_key = "1234567890abcdef";
    std::string masked = mask_api_key(api_key);
    TEST_ASSERT(masked == "1234****cdef", "API密钥应该正确脱敏");
    TEST_ASSERT(mask_api_key("short") == "****", "短API密钥应该完全脱敏");

    // 测试OKX凭证验证
    AccountResult result1 = validate_credentials("valid_key_12345", "valid_secret_12345", "passphrase");
    TEST_ASSERT(result1.is_success(), "有效的OKX凭证应该通过验证");

    AccountResult result2 = validate_credentials("short", "valid_secret_12345", "passphrase");
    TEST_ASSERT(!result2.is_success() && result2.code == AccountErrorCode::INVALID_API_KEY,
                "过短的API Key应该验证失败");

    AccountResult result3 = validate_credentials("valid_key_12345", "short", "passphrase");
    TEST_ASSERT(!result3.is_success() && result3.code == AccountErrorCode::INVALID_SECRET_KEY,
                "过短的Secret Key应该验证失败");

    AccountResult result4 = validate_credentials("valid_key_12345", "valid_secret_12345", "");
    TEST_ASSERT(!result4.is_success() && result4.code == AccountErrorCode::INVALID_PASSPHRASE,
                "空Passphrase应该验证失败");

    TEST_END();
}

/**
 * 测试2: OKX账户管理
 */
void test_okx_account_management() {
    TEST_START("OKX账户管理");

    std::string strategy_id = "test_okx_strategy";
    std::string api_key = "test_okx_api_key_12345";
    std::string secret_key = "test_okx_secret_key_12345";
    std::string passphrase = "test_passphrase";

    // 测试注册
    AccountResult reg_result = register_okx_account(strategy_id, api_key, secret_key, passphrase, true);
    TEST_ASSERT(reg_result.is_success(), "OKX账户注册应该成功");

    // 测试重复注册
    AccountResult dup_result = register_okx_account(strategy_id, api_key, secret_key, passphrase, true);
    TEST_ASSERT(!dup_result.is_success() && dup_result.code == AccountErrorCode::ACCOUNT_ALREADY_EXISTS,
                "重复注册应该返回账户已存在错误");

    // 测试查询
    TEST_ASSERT(is_strategy_registered(strategy_id), "注册后应该能查询到策略");

    // 测试获取API
    okx::OKXRestAPI* api = get_okx_api_for_strategy(strategy_id);
    TEST_ASSERT(api != nullptr, "应该能获取到OKX API实例");

    // 测试更新
    std::string new_api_key = "new_okx_api_key_12345";
    AccountResult upd_result = update_okx_account(strategy_id, new_api_key, secret_key, passphrase, true);
    TEST_ASSERT(upd_result.is_success(), "OKX账户更新应该成功");

    // 测试注销
    AccountResult unreg_result = unregister_okx_account(strategy_id);
    TEST_ASSERT(unreg_result.is_success(), "OKX账户注销应该成功");

    // 测试注销后查询
    TEST_ASSERT(!is_strategy_registered(strategy_id), "注销后应该查询不到策略");

    // 测试注销不存在的账户
    AccountResult unreg_fail = unregister_okx_account("non_existent_strategy");
    TEST_ASSERT(!unreg_fail.is_success() && unreg_fail.code == AccountErrorCode::ACCOUNT_NOT_FOUND,
                "注销不存在的账户应该返回未找到错误");

    TEST_END();
}

/**
 * 测试3: Binance账户管理
 */
void test_binance_account_management() {
    TEST_START("Binance账户管理");

    std::string strategy_id = "test_binance_strategy";
    std::string api_key = "test_binance_api_key_12345";
    std::string secret_key = "test_binance_secret_key_12345";

    // 测试注册（FUTURES市场）
    AccountResult reg_result = register_binance_account(strategy_id, api_key, secret_key, true, "futures");
    TEST_ASSERT(reg_result.is_success(), "Binance账户注册应该成功");

    // 测试查询
    TEST_ASSERT(is_strategy_registered(strategy_id), "注册后应该能查询到策略");

    // 测试获取API（默认市场）
    binance::BinanceRestAPI* api1 = get_binance_api_for_strategy(strategy_id);
    TEST_ASSERT(api1 != nullptr, "应该能获取到Binance API实例（默认市场）");

    // 测试获取API（指定市场）
    binance::BinanceRestAPI* api2 = get_binance_api_for_strategy(strategy_id, "spot");
    TEST_ASSERT(api2 != nullptr, "应该能获取到Binance API实例（SPOT市场）");

    binance::BinanceRestAPI* api3 = get_binance_api_for_strategy(strategy_id, "coin_futures");
    TEST_ASSERT(api3 != nullptr, "应该能获取到Binance API实例（COIN_FUTURES市场）");

    // 测试更新
    std::string new_api_key = "new_binance_api_key_12345";
    AccountResult upd_result = update_binance_account(strategy_id, new_api_key, secret_key, true, "spot");
    TEST_ASSERT(upd_result.is_success(), "Binance账户更新应该成功");

    // 测试注销
    AccountResult unreg_result = unregister_binance_account(strategy_id);
    TEST_ASSERT(unreg_result.is_success(), "Binance账户注销应该成功");

    TEST_END();
}

/**
 * 测试4: 批量操作
 */
void test_batch_operations() {
    TEST_START("批量操作");

    // 准备批量注册数据
    nlohmann::json accounts = nlohmann::json::array();

    // OKX账户
    accounts.push_back({
        {"strategy_id", "batch_okx_1"},
        {"exchange", "okx"},
        {"api_key", "batch_okx_key_1_12345"},
        {"secret_key", "batch_okx_secret_1_12345"},
        {"passphrase", "pass1"},
        {"is_testnet", true}
    });

    accounts.push_back({
        {"strategy_id", "batch_okx_2"},
        {"exchange", "okx"},
        {"api_key", "batch_okx_key_2_12345"},
        {"secret_key", "batch_okx_secret_2_12345"},
        {"passphrase", "pass2"},
        {"is_testnet", true}
    });

    // Binance账户
    accounts.push_back({
        {"strategy_id", "batch_binance_1"},
        {"exchange", "binance"},
        {"api_key", "batch_binance_key_1_12345"},
        {"secret_key", "batch_binance_secret_1_12345"},
        {"is_testnet", true},
        {"market", "futures"}
    });

    accounts.push_back({
        {"strategy_id", "batch_binance_2"},
        {"exchange", "binance"},
        {"api_key", "batch_binance_key_2_12345"},
        {"secret_key", "batch_binance_secret_2_12345"},
        {"is_testnet", true},
        {"market", "spot"}
    });

    // 测试批量注册
    size_t success_count = batch_register_accounts(accounts);
    TEST_ASSERT(success_count == 4, "批量注册应该成功注册4个账户");

    // 验证注册结果
    TEST_ASSERT(is_strategy_registered("batch_okx_1"), "batch_okx_1应该已注册");
    TEST_ASSERT(is_strategy_registered("batch_okx_2"), "batch_okx_2应该已注册");
    TEST_ASSERT(is_strategy_registered("batch_binance_1"), "batch_binance_1应该已注册");
    TEST_ASSERT(is_strategy_registered("batch_binance_2"), "batch_binance_2应该已注册");

    // 测试批量注销
    std::vector<std::string> strategy_ids = {
        "batch_okx_1", "batch_okx_2", "batch_binance_1", "batch_binance_2"
    };
    size_t unreg_count = batch_unregister_accounts(strategy_ids);
    TEST_ASSERT(unreg_count == 4, "批量注销应该成功注销4个账户");

    // 验证注销结果
    TEST_ASSERT(!is_strategy_registered("batch_okx_1"), "batch_okx_1应该已注销");
    TEST_ASSERT(!is_strategy_registered("batch_binance_1"), "batch_binance_1应该已注销");

    TEST_END();
}

/**
 * 测试5: 查询功能
 */
void test_query_functions() {
    TEST_START("查询功能");

    // 先注册一些账户
    register_okx_account("query_okx_1", "key1_12345678", "secret1_12345678", "pass1", true);
    register_okx_account("query_okx_2", "key2_12345678", "secret2_12345678", "pass2", true);
    register_binance_account("query_binance_1", "key3_12345678", "secret3_12345678", true, "futures");

    // 测试获取策略数量
    size_t count = get_registered_strategy_count();
    TEST_ASSERT(count >= 3, "应该至少有3个已注册策略");

    // 测试获取策略ID列表
    std::vector<std::string> ids = get_registered_strategy_ids();
    TEST_ASSERT(ids.size() >= 3, "策略ID列表应该至少包含3个ID");

    bool found_okx = false, found_binance = false;
    for (const auto& id : ids) {
        if (id == "query_okx_1" || id == "query_okx_2") found_okx = true;
        if (id == "query_binance_1") found_binance = true;
    }
    TEST_ASSERT(found_okx, "策略ID列表应该包含OKX策略");
    TEST_ASSERT(found_binance, "策略ID列表应该包含Binance策略");

    // 测试获取所有账户信息
    nlohmann::json all_info = get_all_accounts_info();
    TEST_ASSERT(all_info.contains("summary"), "账户信息应该包含summary字段");
    TEST_ASSERT(all_info.contains("okx"), "账户信息应该包含okx字段");
    TEST_ASSERT(all_info.contains("binance"), "账户信息应该包含binance字段");

    std::cout << "\n当前账户信息:" << std::endl;
    print_account_info(all_info);

    // 清理
    unregister_okx_account("query_okx_1");
    unregister_okx_account("query_okx_2");
    unregister_binance_account("query_binance_1");

    TEST_END();
}

/**
 * 测试6: 向后兼容接口
 */
void test_backward_compatibility() {
    TEST_START("向后兼容接口");

    std::string strategy_id = "compat_test_strategy";
    std::string api_key = "compat_api_key_12345";
    std::string secret_key = "compat_secret_key_12345";
    std::string passphrase = "compat_pass";

    // 测试旧的注册接口（应该调用OKX注册）
    AccountResult reg_result = register_strategy_account(strategy_id, api_key, secret_key, passphrase, true);
    TEST_ASSERT(reg_result.is_success(), "向后兼容的注册接口应该成功");

    // 测试旧的获取API接口（应该返回OKX API）
    okx::OKXRestAPI* api = get_api_for_strategy(strategy_id);
    TEST_ASSERT(api != nullptr, "向后兼容的获取API接口应该返回有效指针");

    // 测试旧的更新接口
    AccountResult upd_result = update_strategy_account(strategy_id, api_key, secret_key, passphrase, true);
    TEST_ASSERT(upd_result.is_success(), "向后兼容的更新接口应该成功");

    // 测试旧的注销接口
    AccountResult unreg_result = unregister_strategy_account(strategy_id);
    TEST_ASSERT(unreg_result.is_success(), "向后兼容的注销接口应该成功");

    TEST_END();
}

/**
 * 测试7: 错误处理
 */
void test_error_handling() {
    TEST_START("错误处理");

    // 测试无效策略ID
    AccountResult result1 = register_okx_account("", "key_12345678", "secret_12345678", "pass", true);
    TEST_ASSERT(!result1.is_success() && result1.code == AccountErrorCode::INVALID_STRATEGY_ID,
                "空策略ID应该返回INVALID_STRATEGY_ID错误");

    AccountResult result2 = register_okx_account("invalid@id", "key_12345678", "secret_12345678", "pass", true);
    TEST_ASSERT(!result2.is_success() && result2.code == AccountErrorCode::INVALID_STRATEGY_ID,
                "非法字符策略ID应该返回INVALID_STRATEGY_ID错误");

    // 测试无效凭证
    AccountResult result3 = register_okx_account("valid_id", "short", "secret_12345678", "pass", true);
    TEST_ASSERT(!result3.is_success() && result3.code == AccountErrorCode::INVALID_API_KEY,
                "过短的API Key应该返回INVALID_API_KEY错误");

    AccountResult result4 = register_okx_account("valid_id", "key_12345678", "short", "pass", true);
    TEST_ASSERT(!result4.is_success() && result4.code == AccountErrorCode::INVALID_SECRET_KEY,
                "过短的Secret Key应该返回INVALID_SECRET_KEY错误");

    AccountResult result5 = register_okx_account("valid_id", "key_12345678", "secret_12345678", "", true);
    TEST_ASSERT(!result5.is_success() && result5.code == AccountErrorCode::INVALID_PASSPHRASE,
                "空Passphrase应该返回INVALID_PASSPHRASE错误");

    // 测试更新不存在的账户（应该自动创建）
    AccountResult result6 = update_okx_account("new_strategy", "key_12345678", "secret_12345678", "pass", true);
    TEST_ASSERT(result6.is_success(), "更新不存在的账户应该自动创建");
    unregister_okx_account("new_strategy");

    // 测试获取不存在的API
    okx::OKXRestAPI* api1 = get_okx_api_for_strategy("non_existent_strategy");
    TEST_ASSERT(api1 == nullptr, "获取不存在策略的API应该返回nullptr");

    binance::BinanceRestAPI* api2 = get_binance_api_for_strategy("non_existent_strategy");
    TEST_ASSERT(api2 == nullptr, "获取不存在策略的Binance API应该返回nullptr");

    TEST_END();
}

/**
 * 测试8: AccountResult JSON转换
 */
void test_account_result_json() {
    TEST_START("AccountResult JSON转换");

    AccountResult success_result(AccountErrorCode::SUCCESS, "操作成功");
    nlohmann::json success_json = success_result.to_json();
    TEST_ASSERT(success_json["code"] == 0, "成功结果的code应该为0");
    TEST_ASSERT(success_json["success"] == true, "成功结果的success应该为true");
    TEST_ASSERT(success_json["message"] == "操作成功", "成功结果的message应该正确");

    AccountResult error_result(AccountErrorCode::INVALID_API_KEY, "API Key无效");
    nlohmann::json error_json = error_result.to_json();
    TEST_ASSERT(error_json["code"] == 2, "错误结果的code应该为2");
    TEST_ASSERT(error_json["success"] == false, "错误结果的success应该为false");
    TEST_ASSERT(error_json["message"] == "API Key无效", "错误结果的message应该正确");

    TEST_END();
}

// ==================== 主函数 ====================

int main() {
    std::cout << "\n" << std::string(50, '=') << std::endl;
    std::cout << "账户管理器测试程序" << std::endl;
    std::cout << std::string(50, '=') << std::endl;

    // 初始化日志系统
    Logger::instance().init("logs", "test_manager", LogLevel::INFO);
    Logger::instance().set_console_output(true);

    std::cout << "\n开始执行测试...\n" << std::endl;

    try {
        // 执行所有测试
        test_parameter_validation();
        test_okx_account_management();
        test_binance_account_management();
        test_batch_operations();
        test_query_functions();
        test_backward_compatibility();
        test_error_handling();
        test_account_result_json();

        // 打印测试总结
        print_summary();

        // 关闭日志系统
        Logger::instance().shutdown();

        return (failed_tests == 0) ? 0 : 1;

    } catch (const std::exception& e) {
        std::cerr << "\n测试过程中发生异常: " << e.what() << std::endl;
        Logger::instance().shutdown();
        return 1;
    }
}
