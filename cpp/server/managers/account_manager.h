/**
 * @file account_manager.h
 * @brief 账户注册管理
 */

#pragma once

#include <string>
<<<<<<< HEAD
#include "../../adapters/okx/okx_rest_api.h"
#include "../../adapters/binance/binance_rest_api.h"
=======
#include <vector>
#include <nlohmann/json.hpp>
#include "../../adapters/okx/okx_rest_api.h"
#include "../../trading/account_registry.h"
>>>>>>> 790f266ba1027b1965537994fcbe09e85ab438e5

namespace trading {
namespace server {

<<<<<<< HEAD
/**
 * @brief 获取策略对应的 API 客户端
=======
// ==================== 错误码定义 ====================

enum class AccountErrorCode {
    SUCCESS = 0,                    // 成功
    INVALID_STRATEGY_ID = 1,        // 无效的策略ID
    INVALID_API_KEY = 2,            // 无效的API Key
    INVALID_SECRET_KEY = 3,         // 无效的Secret Key
    INVALID_PASSPHRASE = 4,         // 无效的Passphrase
    ACCOUNT_NOT_FOUND = 5,          // 账户未找到
    ACCOUNT_ALREADY_EXISTS = 6,     // 账户已存在
    REGISTRATION_FAILED = 7,        // 注册失败
    UNREGISTRATION_FAILED = 8,      // 注销失败
    UPDATE_FAILED = 9,              // 更新失败
    INTERNAL_ERROR = 10             // 内部错误
};

/**
 * @brief 账户操作结果
 */
struct AccountResult {
    AccountErrorCode code;
    std::string message;

    AccountResult(AccountErrorCode c = AccountErrorCode::SUCCESS,
                  const std::string& msg = "")
        : code(c), message(msg) {}

    bool is_success() const { return code == AccountErrorCode::SUCCESS; }

    // 转换为JSON
    nlohmann::json to_json() const {
        return {
            {"code", static_cast<int>(code)},
            {"success", is_success()},
            {"message", message}
        };
    }
};

// ==================== 常量定义 ====================

namespace constants {
    constexpr const char* MODE_TESTNET = "模拟盘";
    constexpr const char* MODE_LIVE = "实盘";
    constexpr size_t MIN_API_KEY_LENGTH = 8;
    constexpr size_t MIN_SECRET_KEY_LENGTH = 8;
    constexpr size_t MIN_PASSPHRASE_LENGTH = 1;
}

// ==================== 核心接口 ====================

// ==================== OKX 账户管理接口 ====================

/**
 * @brief 获取OKX策略对应的 API 客户端
 * @param strategy_id 策略ID
 * @return API客户端指针，失败返回nullptr
 */
okx::OKXRestAPI* get_okx_api_for_strategy(const std::string& strategy_id);

/**
 * @brief 注册OKX策略账户
 * @param strategy_id 策略ID（不能为空）
 * @param api_key API密钥（长度至少8位）
 * @param secret_key 密钥（长度至少8位）
 * @param passphrase 密码短语（不能为空）
 * @param is_testnet 是否为测试网
 * @return 操作结果
 */
AccountResult register_okx_account(const std::string& strategy_id,
                                   const std::string& api_key,
                                   const std::string& secret_key,
                                   const std::string& passphrase,
                                   bool is_testnet);

/**
 * @brief 更新OKX策略账户信息
 * @param strategy_id 策略ID
 * @param api_key 新的API密钥
 * @param secret_key 新的密钥
 * @param passphrase 新的密码短语
 * @param is_testnet 是否为测试网
 * @return 操作结果
 */
AccountResult update_okx_account(const std::string& strategy_id,
                                 const std::string& api_key,
                                 const std::string& secret_key,
                                 const std::string& passphrase,
                                 bool is_testnet);

/**
 * @brief 注销OKX策略账户
 * @param strategy_id 策略ID
 * @return 操作结果
 */
AccountResult unregister_okx_account(const std::string& strategy_id);

// ==================== Binance 账户管理接口 ====================

/**
 * @brief 获取Binance策略对应的 API 客户端
 * @param strategy_id 策略ID
 * @param market 市场类型（可选，默认使用账户的默认市场）
 * @return API客户端指针，失败返回nullptr
 */
binance::BinanceRestAPI* get_binance_api_for_strategy(
    const std::string& strategy_id,
    const std::string& market = "");

/**
 * @brief 注册Binance策略账户
 * @param strategy_id 策略ID
 * @param api_key API密钥
 * @param secret_key 密钥
 * @param is_testnet 是否为测试网
 * @param market 市场类型（SPOT/FUTURES/COIN_FUTURES）
 * @return 操作结果
 */
AccountResult register_binance_account(const std::string& strategy_id,
                                       const std::string& api_key,
                                       const std::string& secret_key,
                                       bool is_testnet,
                                       const std::string& market = "futures");

/**
 * @brief 更新Binance策略账户信息
 * @param strategy_id 策略ID
 * @param api_key 新的API密钥
 * @param secret_key 新的密钥
 * @param is_testnet 是否为测试网
 * @param market 市场类型
 * @return 操作结果
 */
AccountResult update_binance_account(const std::string& strategy_id,
                                     const std::string& api_key,
                                     const std::string& secret_key,
                                     bool is_testnet,
                                     const std::string& market = "futures");

/**
 * @brief 注销Binance策略账户
 * @param strategy_id 策略ID
 * @return 操作结果
 */
AccountResult unregister_binance_account(const std::string& strategy_id);

// ==================== 兼容性接口（向后兼容旧代码）====================

/**
 * @brief 获取策略对应的 API 客户端（默认OKX，向后兼容）
 * @deprecated 请使用 get_okx_api_for_strategy() 或 get_binance_api_for_strategy()
>>>>>>> 790f266ba1027b1965537994fcbe09e85ab438e5
 */
okx::OKXRestAPI* get_api_for_strategy(const std::string& strategy_id);

/**
<<<<<<< HEAD
 * @brief 获取OKX策略对应的 API 客户端
 */
okx::OKXRestAPI* get_okx_api_for_strategy(const std::string& strategy_id);

/**
 * @brief 获取Binance策略对应的 API 客户端
 */
binance::BinanceRestAPI* get_binance_api_for_strategy(const std::string& strategy_id);

/**
 * @brief 注册策略账户
 */
bool register_strategy_account(const std::string& strategy_id,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet);
/**
 * @brief 注销策略账户
 */
bool unregister_strategy_account(const std::string& strategy_id);

/**
 * @brief 获取已注册的策略数量
 */
size_t get_registered_strategy_count();

=======
 * @brief 注册策略账户（默认OKX，向后兼容）
 * @deprecated 请使用 register_okx_account() 或 register_binance_account()
 */
AccountResult register_strategy_account(const std::string& strategy_id,
                                        const std::string& api_key,
                                        const std::string& secret_key,
                                        const std::string& passphrase,
                                        bool is_testnet);

/**
 * @brief 更新策略账户信息（默认OKX，向后兼容）
 * @deprecated 请使用 update_okx_account() 或 update_binance_account()
 */
AccountResult update_strategy_account(const std::string& strategy_id,
                                      const std::string& api_key,
                                      const std::string& secret_key,
                                      const std::string& passphrase,
                                      bool is_testnet);

/**
 * @brief 注销策略账户（默认OKX，向后兼容）
 * @deprecated 请使用 unregister_okx_account() 或 unregister_binance_account()
 */
AccountResult unregister_strategy_account(const std::string& strategy_id);

/**
 * @brief 获取已注册的策略数量
 * @return 策略数量
 */
size_t get_registered_strategy_count();

/**
 * @brief 获取所有已注册的策略ID列表
 * @return 策略ID列表
 */
std::vector<std::string> get_registered_strategy_ids();

/**
 * @brief 检查策略是否已注册
 * @param strategy_id 策略ID
 * @return true表示已注册，false表示未注册
 */
bool is_strategy_registered(const std::string& strategy_id);

/**
 * @brief 获取所有账户信息（用于管理界面）
 * @return JSON格式的账户信息
 */
nlohmann::json get_all_accounts_info();

/**
 * @brief 批量注册策略账户
 * @param accounts JSON数组，每个元素包含策略账户信息
 * @return 成功注册的数量
 */
size_t batch_register_accounts(const nlohmann::json& accounts);

/**
 * @brief 批量注销策略账户
 * @param strategy_ids 策略ID列表
 * @return 成功注销的数量
 */
size_t batch_unregister_accounts(const std::vector<std::string>& strategy_ids);

// ==================== 辅助函数 ====================

/**
 * @brief 验证策略ID是否有效
 * @param strategy_id 策略ID
 * @return true表示有效，false表示无效
 */
bool validate_strategy_id(const std::string& strategy_id);

/**
 * @brief 验证API凭证是否有效
 * @param api_key API密钥
 * @param secret_key 密钥
 * @param passphrase 密码短语
 * @return 验证结果
 */
AccountResult validate_credentials(const std::string& api_key,
                                   const std::string& secret_key,
                                   const std::string& passphrase);

/**
 * @brief 脱敏显示API Key（仅显示前4位和后4位）
 * @param api_key 完整的API Key
 * @return 脱敏后的字符串
 */
std::string mask_api_key(const std::string& api_key);

>>>>>>> 790f266ba1027b1965537994fcbe09e85ab438e5
} // namespace server
} // namespace trading
