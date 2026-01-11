/**
 * @file account_manager.h
 * @brief 账户注册管理 - 支持 OKX 和 Binance
 */

#pragma once

#include <string>
#include "../../adapters/okx/okx_rest_api.h"
#include "../../adapters/binance/binance_rest_api.h"

namespace trading {
namespace server {

// ==================== OKX 账户管理 ====================

/**
 * @brief 获取 OKX 策略对应的 API 客户端
 */
okx::OKXRestAPI* get_okx_api_for_strategy(const std::string& strategy_id);

/**
 * @brief 注册 OKX 策略账户
 */
bool register_okx_strategy_account(const std::string& strategy_id,
                                   const std::string& api_key,
                                   const std::string& secret_key,
                                   const std::string& passphrase,
                                   bool is_testnet);

/**
 * @brief 注销 OKX 策略账户
 */
bool unregister_okx_strategy_account(const std::string& strategy_id);

// ==================== Binance 账户管理 ====================

/**
 * @brief 获取 Binance 策略对应的 API 客户端（使用默认市场）
 */
binance::BinanceRestAPI* get_binance_api_for_strategy(const std::string& strategy_id);

/**
 * @brief 获取 Binance 策略对应的 API 客户端（指定市场）
 */
binance::BinanceRestAPI* get_binance_api_for_strategy(const std::string& strategy_id,
                                                       binance::MarketType market);

/**
 * @brief 注册 Binance 策略账户
 */
bool register_binance_strategy_account(const std::string& strategy_id,
                                       const std::string& api_key,
                                       const std::string& secret_key,
                                       bool is_testnet,
                                       binance::MarketType market = binance::MarketType::FUTURES);

/**
 * @brief 注销 Binance 策略账户
 */
bool unregister_binance_strategy_account(const std::string& strategy_id);

// ==================== 通用接口 ====================

/**
 * @brief 注册策略账户（支持 OKX 和 Binance）
 *
 * @param strategy_id 策略ID
 * @param exchange 交易所名称 ("okx" 或 "binance")
 * @param api_key API Key
 * @param secret_key Secret Key
 * @param passphrase Passphrase（OKX 必需，Binance 传空字符串）
 * @param is_testnet 是否为测试网
 * @return 注册是否成功
 */
bool register_strategy_account(const std::string& strategy_id,
                               const std::string& exchange,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet);

/**
 * @brief 注销策略账户
 */
bool unregister_strategy_account(const std::string& strategy_id, const std::string& exchange);

/**
 * @brief 获取已注册的策略数量
 */
size_t get_registered_strategy_count();

/**
 * @brief 获取 OKX 账户数量
 */
size_t get_okx_account_count();

/**
 * @brief 获取 Binance 账户数量
 */
size_t get_binance_account_count();

// ==================== 兼容旧接口 ====================

// 保留旧的 OKX 专用接口（向后兼容）
[[deprecated("Use get_okx_api_for_strategy instead")]]
inline okx::OKXRestAPI* get_api_for_strategy(const std::string& strategy_id) {
    return get_okx_api_for_strategy(strategy_id);
}

// 旧版注册接口（默认 OKX）
[[deprecated("Use register_strategy_account with exchange parameter instead")]]
bool register_strategy_account(const std::string& strategy_id,
                               const std::string& api_key,
                               const std::string& secret_key,
                               const std::string& passphrase,
                               bool is_testnet);

// 旧版注销接口（默认 OKX）
[[deprecated("Use unregister_strategy_account with exchange parameter instead")]]
bool unregister_strategy_account(const std::string& strategy_id);

} // namespace server
} // namespace trading
