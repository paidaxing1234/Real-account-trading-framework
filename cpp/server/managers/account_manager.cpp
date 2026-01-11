/**
 * @file account_manager.cpp
 * @brief 账户注册管理实现 - 支持 OKX 和 Binance
 */

#include "account_manager.h"
#include "../config/server_config.h"
#include "../../trading/account_registry.h"
#include <iostream>
#include <algorithm>

namespace trading {
namespace server {

// ==================== OKX 账户管理 ====================

okx::OKXRestAPI* get_okx_api_for_strategy(const std::string& strategy_id) {
    okx::OKXRestAPI* api = g_account_registry.get_okx_api(strategy_id);
    if (!api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册 OKX 账户，且无默认账户\n";
    }
    return api;
}

bool register_okx_strategy_account(const std::string& strategy_id,
                                   const std::string& api_key,
                                   const std::string& secret_key,
                                   const std::string& passphrase,
                                   bool is_testnet) {
    bool success = g_account_registry.register_okx_account(
        strategy_id, api_key, secret_key, passphrase, is_testnet
    );

    if (success) {
        std::cout << "[账户] ✓ OKX 策略 " << strategy_id << " 注册成功"
                  << " | 模式: " << (is_testnet ? "模拟盘" : "实盘")
                  << " | API Key: " << api_key.substr(0, 8) << "...\n";
    }

    return success;
}

bool unregister_okx_strategy_account(const std::string& strategy_id) {
    bool success = g_account_registry.unregister_account(strategy_id, ExchangeType::OKX);

    if (success) {
        std::cout << "[账户] ✓ OKX 策略 " << strategy_id << " 已注销\n";
    } else {
        std::cout << "[账户] OKX 策略 " << strategy_id << " 未找到\n";
    }

    return success;
}

// ==================== Binance 账户管理 ====================

binance::BinanceRestAPI* get_binance_api_for_strategy(const std::string& strategy_id) {
    binance::BinanceRestAPI* api = g_account_registry.get_binance_api(strategy_id);
    if (!api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册 Binance 账户，且无默认账户\n";
    }
    return api;
}

binance::BinanceRestAPI* get_binance_api_for_strategy(const std::string& strategy_id,
                                                       binance::MarketType market) {
    binance::BinanceRestAPI* api = g_account_registry.get_binance_api(strategy_id, market);
    if (!api) {
        std::cout << "[账户] 策略 " << strategy_id << " 未注册 Binance 账户，且无默认账户\n";
    }
    return api;
}

bool register_binance_strategy_account(const std::string& strategy_id,
                                       const std::string& api_key,
                                       const std::string& secret_key,
                                       bool is_testnet,
                                       binance::MarketType market) {
    bool success = g_account_registry.register_binance_account(
        strategy_id, api_key, secret_key, is_testnet, market
    );

    if (success) {
        std::string market_str = "FUTURES";
        if (market == binance::MarketType::SPOT) market_str = "SPOT";
        else if (market == binance::MarketType::COIN_FUTURES) market_str = "COIN_FUTURES";

        std::cout << "[账户] ✓ Binance 策略 " << strategy_id << " 注册成功"
                  << " | 市场: " << market_str
                  << " | 模式: " << (is_testnet ? "测试网" : "主网")
                  << " | API Key: " << api_key.substr(0, 8) << "...\n";
    }

    return success;
}

bool unregister_binance_strategy_account(const std::string& strategy_id) {
    bool success = g_account_registry.unregister_account(strategy_id, ExchangeType::BINANCE);

    if (success) {
        std::cout << "[账户] ✓ Binance 策略 " << strategy_id << " 已注销\n";
    } else {
        std::cout << "[账户] Binance 策略 " << strategy_id << " 未找到\n";
    }

    return success;
}

// ==================== 通用接口 ====================

bool register_strategy_account(const std::string& strategy_id,
                               const std::string& exchange,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet) {
    // 转换为小写进行比较
    std::string exchange_lower = exchange;
    std::transform(exchange_lower.begin(), exchange_lower.end(),
                   exchange_lower.begin(), ::tolower);

    std::cout << "[AccountManager] 注册账户 Request: Strategy=" << strategy_id
              << ", Exchange=" << exchange << std::endl;

    if (exchange_lower == "okx") {
        return register_okx_strategy_account(
            strategy_id, api_key, secret_key, passphrase, is_testnet
        );
    }
    else if (exchange_lower == "binance") {
        // Binance 不需要 passphrase
        return register_binance_strategy_account(
            strategy_id, api_key, secret_key, is_testnet, binance::MarketType::FUTURES
        );
    }

    std::cerr << "[AccountManager] 不支持的交易所: " << exchange << std::endl;
    return false;
}

bool unregister_strategy_account(const std::string& strategy_id, const std::string& exchange) {
    std::string exchange_lower = exchange;
    std::transform(exchange_lower.begin(), exchange_lower.end(),
                   exchange_lower.begin(), ::tolower);

    if (exchange_lower == "okx") {
        return unregister_okx_strategy_account(strategy_id);
    }
    else if (exchange_lower == "binance") {
        return unregister_binance_strategy_account(strategy_id);
    }

    std::cerr << "[AccountManager] 不支持的交易所: " << exchange << std::endl;
    return false;
}

size_t get_registered_strategy_count() {
    return g_account_registry.count();
}

size_t get_okx_account_count() {
    return g_account_registry.okx_count();
}

size_t get_binance_account_count() {
    return g_account_registry.binance_count();
}

// ==================== 兼容旧接口 ====================

// 旧版注册接口（默认 OKX）
bool register_strategy_account(const std::string& strategy_id,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet) {
    return register_okx_strategy_account(strategy_id, api_key, secret_key, passphrase, is_testnet);
}

// 旧版注销接口（默认 OKX）
bool unregister_strategy_account(const std::string& strategy_id) {
    return unregister_okx_strategy_account(strategy_id);
}

} // namespace server
} // namespace trading
