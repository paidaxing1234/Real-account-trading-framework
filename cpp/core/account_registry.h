#pragma once

/**
 * @file account_registry.h
 * @brief 账户注册管理器 - 多账户/多策略支持
 *
 * 功能：
 * - 策略账户注册/注销
 * - 默认账户管理
 * - 线程安全的账户查询
 * - 支持OKX和Binance
 *
 * @author Sequence Team
 * @date 2026-01
 */

#include <string>
#include <map>
#include <memory>
#include <mutex>
#include <chrono>
#include "../adapters/okx/okx_rest_api.h"
#include "../adapters/binance/binance_rest_api.h"

namespace trading {

// ==================== 交易所类型 ====================

enum class ExchangeType {
    OKX,
    BINANCE
};

inline std::string exchange_type_to_string(ExchangeType type) {
    switch (type) {
        case ExchangeType::OKX: return "OKX";
        case ExchangeType::BINANCE: return "Binance";
        default: return "Unknown";
    }
}

inline ExchangeType string_to_exchange_type(const std::string& str) {
    if (str == "okx" || str == "OKX") return ExchangeType::OKX;
    if (str == "binance" || str == "BINANCE" || str == "Binance") return ExchangeType::BINANCE;
    return ExchangeType::OKX;  // 默认
}

// ==================== 账户信息 ====================

/**
 * @brief 账户信息基类
 */
struct AccountInfoBase {
    std::string api_key;
    std::string secret_key;
    std::string passphrase;  // OKX需要，Binance不需要
    bool is_testnet;
    ExchangeType exchange_type;
    int64_t register_time;

    AccountInfoBase()
        : is_testnet(true)
        , exchange_type(ExchangeType::OKX)
        , register_time(0) {}

    virtual ~AccountInfoBase() = default;
};

/**
 * @brief OKX账户信息
 */
struct OKXAccountInfo : public AccountInfoBase {
    std::unique_ptr<okx::OKXRestAPI> api;

    OKXAccountInfo(const std::string& key, const std::string& secret,
                   const std::string& pass, bool testnet) {
        api_key = key;
        secret_key = secret;
        passphrase = pass;
        is_testnet = testnet;
        exchange_type = ExchangeType::OKX;
        register_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();

        api = std::make_unique<okx::OKXRestAPI>(api_key, secret_key, passphrase, is_testnet);
    }
};

/**
 * @brief Binance账户信息
 */
struct BinanceAccountInfo : public AccountInfoBase {
    std::unique_ptr<binance::BinanceRestAPI> api;

    BinanceAccountInfo(const std::string& key, const std::string& secret, bool testnet) {
        api_key = key;
        secret_key = secret;
        is_testnet = testnet;
        exchange_type = ExchangeType::BINANCE;
        register_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();

        api = std::make_unique<binance::BinanceRestAPI>(
            api_key, secret_key,
            binance::MarketType::SPOT,
            is_testnet
        );
    }
};

// ==================== 账户注册管理器 ====================

/**
 * @brief 账户注册管理器
 *
 * 线程安全的多账户管理，支持：
 * - 策略独立账户
 * - 默认账户（未注册策略使用）
 * - OKX和Binance
 */
class AccountRegistry {
public:
    AccountRegistry() = default;
    ~AccountRegistry() = default;

    // 禁止拷贝
    AccountRegistry(const AccountRegistry&) = delete;
    AccountRegistry& operator=(const AccountRegistry&) = delete;

    // ==================== OKX账户管理 ====================

    /**
     * @brief 注册OKX策略账户
     */
    bool register_okx_account(const std::string& strategy_id,
                              const std::string& api_key,
                              const std::string& secret_key,
                              const std::string& passphrase,
                              bool is_testnet) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto account = std::make_shared<OKXAccountInfo>(api_key, secret_key, passphrase, is_testnet);
        okx_accounts_[strategy_id] = account;

        return true;
    }

    /**
     * @brief 设置OKX默认账户
     */
    void set_default_okx_account(const std::string& api_key,
                                 const std::string& secret_key,
                                 const std::string& passphrase,
                                 bool is_testnet) {
        std::lock_guard<std::mutex> lock(mutex_);
        default_okx_account_ = std::make_shared<OKXAccountInfo>(
            api_key, secret_key, passphrase, is_testnet
        );
    }

    /**
     * @brief 获取OKX策略账户API
     */
    okx::OKXRestAPI* get_okx_api(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);

        // 查找策略账户
        auto it = okx_accounts_.find(strategy_id);
        if (it != okx_accounts_.end() && it->second && it->second->api) {
            return it->second->api.get();
        }

        // 使用默认账户
        if (default_okx_account_ && default_okx_account_->api) {
            return default_okx_account_->api.get();
        }

        return nullptr;
    }

    // ==================== Binance账户管理 ====================

    /**
     * @brief 注册Binance策略账户
     */
    bool register_binance_account(const std::string& strategy_id,
                                  const std::string& api_key,
                                  const std::string& secret_key,
                                  bool is_testnet) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto account = std::make_shared<BinanceAccountInfo>(api_key, secret_key, is_testnet);
        binance_accounts_[strategy_id] = account;

        return true;
    }

    /**
     * @brief 设置Binance默认账户
     */
    void set_default_binance_account(const std::string& api_key,
                                     const std::string& secret_key,
                                     bool is_testnet) {
        std::lock_guard<std::mutex> lock(mutex_);
        default_binance_account_ = std::make_shared<BinanceAccountInfo>(
            api_key, secret_key, is_testnet
        );
    }

    /**
     * @brief 获取Binance策略账户API
     */
    binance::BinanceRestAPI* get_binance_api(const std::string& strategy_id) {
        std::lock_guard<std::mutex> lock(mutex_);

        // 查找策略账户
        auto it = binance_accounts_.find(strategy_id);
        if (it != binance_accounts_.end() && it->second && it->second->api) {
            return it->second->api.get();
        }

        // 使用默认账户
        if (default_binance_account_ && default_binance_account_->api) {
            return default_binance_account_->api.get();
        }

        return nullptr;
    }

    // ==================== 通用接口 ====================

    /**
     * @brief 注册账户（自动识别交易所）
     */
    bool register_account(const std::string& strategy_id,
                         ExchangeType exchange,
                         const std::string& api_key,
                         const std::string& secret_key,
                         const std::string& passphrase,
                         bool is_testnet) {
        if (exchange == ExchangeType::OKX) {
            return register_okx_account(strategy_id, api_key, secret_key, passphrase, is_testnet);
        } else if (exchange == ExchangeType::BINANCE) {
            return register_binance_account(strategy_id, api_key, secret_key, is_testnet);
        }
        return false;
    }

    /**
     * @brief 注销账户
     */
    bool unregister_account(const std::string& strategy_id, ExchangeType exchange) {
        std::lock_guard<std::mutex> lock(mutex_);

        if (exchange == ExchangeType::OKX) {
            auto it = okx_accounts_.find(strategy_id);
            if (it != okx_accounts_.end()) {
                okx_accounts_.erase(it);
                return true;
            }
        } else if (exchange == ExchangeType::BINANCE) {
            auto it = binance_accounts_.find(strategy_id);
            if (it != binance_accounts_.end()) {
                binance_accounts_.erase(it);
                return true;
            }
        }

        return false;
    }

    /**
     * @brief 获取已注册账户数量
     */
    size_t count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return okx_accounts_.size() + binance_accounts_.size();
    }

    /**
     * @brief 获取OKX账户数量
     */
    size_t okx_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return okx_accounts_.size();
    }

    /**
     * @brief 获取Binance账户数量
     */
    size_t binance_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return binance_accounts_.size();
    }

    /**
     * @brief 检查策略是否已注册
     */
    bool is_registered(const std::string& strategy_id, ExchangeType exchange) const {
        std::lock_guard<std::mutex> lock(mutex_);

        if (exchange == ExchangeType::OKX) {
            return okx_accounts_.find(strategy_id) != okx_accounts_.end();
        } else if (exchange == ExchangeType::BINANCE) {
            return binance_accounts_.find(strategy_id) != binance_accounts_.end();
        }

        return false;
    }

    /**
     * @brief 清空所有账户
     */
    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        okx_accounts_.clear();
        binance_accounts_.clear();
        default_okx_account_.reset();
        default_binance_account_.reset();
    }

private:
    mutable std::mutex mutex_;

    // OKX账户
    std::map<std::string, std::shared_ptr<OKXAccountInfo>> okx_accounts_;
    std::shared_ptr<OKXAccountInfo> default_okx_account_;

    // Binance账户
    std::map<std::string, std::shared_ptr<BinanceAccountInfo>> binance_accounts_;
    std::shared_ptr<BinanceAccountInfo> default_binance_account_;
};

} // namespace trading
