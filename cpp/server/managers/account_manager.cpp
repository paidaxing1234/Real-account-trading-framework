/**
 * @file account_manager.cpp
 * @brief 账户注册管理实现
 */

#include "account_manager.h"
#include "../config/server_config.h"
#include "../../trading/account_registry.h"
#include <iostream>

namespace trading {
namespace server {

okx::OKXRestAPI* get_api_for_strategy(const std::string& strategy_id) {
    okx::OKXRestAPI* api = g_account_registry.get_okx_api(strategy_id);
    if (!api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册账户，且无默认账户\n";
    }
    return api;
}

bool register_strategy_account(const std::string& strategy_id,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet) {
    bool success = g_account_registry.register_okx_account(
        strategy_id, api_key, secret_key, passphrase, is_testnet
    );

    if (success) {
        std::cout << "[账户] ✓ 策略 " << strategy_id << " 注册成功"
                  << " | 模式: " << (is_testnet ? "模拟盘" : "实盘")
                  << " | API Key: " << api_key.substr(0, 8) << "...\n";
    }

    return success;
}

bool unregister_strategy_account(const std::string& strategy_id) {
    bool success = g_account_registry.unregister_account(strategy_id, ExchangeType::OKX);

    if (success) {
        std::cout << "[账户] ✓ 策略 " << strategy_id << " 已注销\n";
    } else {
        std::cout << "[账户] 策略 " << strategy_id << " 未找到\n";
    }

    return success;
}

size_t get_registered_strategy_count() {
    return g_account_registry.count();
}

} // namespace server
} // namespace trading
