/**
 * @file papertrading_config.h
 * @brief 模拟交易配置管理
 * 
 * 功能：
 * 1. 从JSON配置文件加载配置
 * 2. 提供配置访问接口
 * 3. 支持默认值和配置验证
 * 
 * @author Sequence Team
 * @date 2025-12
 */

#pragma once

#include <string>
#include <map>
#include <nlohmann/json.hpp>

namespace trading {
namespace papertrading {

/**
 * @brief 模拟交易配置
 */
class PaperTradingConfig {
public:
    /**
     * @brief 构造函数
     * @param config_file 配置文件路径（可选，如果为空则使用默认值）
     */
    explicit PaperTradingConfig(const std::string& config_file = "");
    
    /**
     * @brief 从文件加载配置
     * @param config_file 配置文件路径
     * @return true 成功，false 失败
     */
    bool load_from_file(const std::string& config_file);
    
    /**
     * @brief 使用默认配置
     */
    void use_defaults();
    
    /**
     * @brief 验证配置有效性
     * @return true 有效，false 无效
     */
    bool validate() const;
    
    // ==================== 账户配置 ====================
    
    /**
     * @brief 获取初始USDT余额
     */
    double initial_balance() const { return initial_balance_; }
    
    /**
     * @brief 设置初始USDT余额
     */
    void set_initial_balance(double balance) { initial_balance_ = balance; }
    
    /**
     * @brief 获取默认杠杆倍数
     */
    double default_leverage() const { return default_leverage_; }
    
    // ==================== 手续费配置 ====================
    
    /**
     * @brief 获取Maker手续费率（挂单）
     */
    double maker_fee_rate() const { return maker_fee_rate_; }
    
    /**
     * @brief 获取Taker手续费率（市价单）
     */
    double taker_fee_rate() const { return taker_fee_rate_; }
    
    // ==================== 交易配置 ====================
    
    /**
     * @brief 获取市价单滑点
     */
    double market_order_slippage() const { return market_order_slippage_; }
    
    /**
     * @brief 获取默认合约面值
     */
    double default_contract_value() const { return default_contract_value_; }
    
    /**
     * @brief 获取指定交易对的合约面值
     * @param symbol 交易对
     * @return 合约面值，如果未配置则返回默认值
     */
    double get_contract_value(const std::string& symbol) const;
    
    /**
     * @brief 获取指定交易对的杠杆倍数
     * @param symbol 交易对
     * @return 杠杆倍数，如果未配置则返回默认值
     */
    double get_leverage(const std::string& symbol) const;
    
    // ==================== 行情配置 ====================
    
    /**
     * @brief 是否使用测试网
     */
    bool is_testnet() const { return is_testnet_; }
    
    /**
     * @brief 设置是否使用测试网
     */
    void set_testnet(bool testnet) { is_testnet_ = testnet; }
    
    // ==================== 调试和日志 ====================
    
    /**
     * @brief 打印配置信息
     */
    void print() const;
    
    /**
     * @brief 转换为JSON
     */
    nlohmann::json to_json() const;

private:
    // 账户配置
    double initial_balance_;          // 初始USDT余额
    double default_leverage_;          // 默认杠杆倍数
    
    // 手续费配置
    double maker_fee_rate_;            // Maker手续费率（挂单）
    double taker_fee_rate_;            // Taker手续费率（市价单）
    
    // 交易配置
    double market_order_slippage_;     // 市价单滑点
    double default_contract_value_;    // 默认合约面值
    
    // 行情配置
    bool is_testnet_;                  // 是否使用测试网
    
    // 交易对特定配置
    std::map<std::string, double> symbol_contract_values_;  // 交易对 -> 合约面值
    std::map<std::string, double> symbol_leverages_;         // 交易对 -> 杠杆倍数
    
    // 从JSON加载配置
    void load_from_json(const nlohmann::json& j);
};

} // namespace papertrading
} // namespace trading

