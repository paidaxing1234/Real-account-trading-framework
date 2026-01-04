/**
 * @file papertrading_config.cpp
 * @brief 模拟交易配置管理实现
 */

#include "papertrading_config.h"
#include <fstream>
#include <iostream>
#include <iomanip>

namespace trading {
namespace papertrading {

PaperTradingConfig::PaperTradingConfig(const std::string& config_file) {
    if (config_file.empty()) {
        use_defaults();
    } else {
        if (!load_from_file(config_file)) {
            std::cerr << "[警告] 配置文件加载失败，使用默认配置" << std::endl;
            use_defaults();
        }
    }
}

bool PaperTradingConfig::load_from_file(const std::string& config_file) {
    std::ifstream file(config_file);
    if (!file.is_open()) {
        std::cerr << "[错误] 无法打开配置文件: " << config_file << std::endl;
        return false;
    }
    
    try {
        nlohmann::json j;
        file >> j;
        load_from_json(j);
        
        if (!validate()) {
            std::cerr << "[错误] 配置验证失败" << std::endl;
            return false;
        }
        
        std::cout << "[配置] 成功加载配置文件: " << config_file << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "[错误] 解析配置文件失败: " << e.what() << std::endl;
        return false;
    }
}

void PaperTradingConfig::use_defaults() {
    // 账户配置
    initial_balance_ = 100000.0;        // 10万USDT
    default_leverage_ = 1.0;            // 1倍杠杆（无杠杆）
    
    // 手续费配置（OKX标准费率）
    maker_fee_rate_ = 0.0002;           // 0.02%
    taker_fee_rate_ = 0.0005;           // 0.05%
    
    // 交易配置
    market_order_slippage_ = 0.0001;   // 0.01%
    default_contract_value_ = 1.0;     // 1张 = 1个币
    
    // 行情配置
    is_testnet_ = true;                 // 默认使用测试网
    
    // 清空交易对特定配置
    symbol_contract_values_.clear();
    symbol_leverages_.clear();
}

bool PaperTradingConfig::validate() const {
    // 验证余额
    if (initial_balance_ <= 0) {
        std::cerr << "[验证] 初始余额必须大于0" << std::endl;
        return false;
    }
    
    // 验证杠杆
    if (default_leverage_ < 1.0 || default_leverage_ > 125.0) {
        std::cerr << "[验证] 杠杆倍数必须在1-125之间" << std::endl;
        return false;
    }
    
    // 验证手续费率
    if (maker_fee_rate_ < 0 || maker_fee_rate_ > 0.01) {
        std::cerr << "[验证] Maker手续费率必须在0-1%之间" << std::endl;
        return false;
    }
    if (taker_fee_rate_ < 0 || taker_fee_rate_ > 0.01) {
        std::cerr << "[验证] Taker手续费率必须在0-1%之间" << std::endl;
        return false;
    }
    
    // 验证滑点
    if (market_order_slippage_ < 0 || market_order_slippage_ > 0.01) {
        std::cerr << "[验证] 滑点必须在0-1%之间" << std::endl;
        return false;
    }
    
    // 验证合约面值
    if (default_contract_value_ <= 0) {
        std::cerr << "[验证] 合约面值必须大于0" << std::endl;
        return false;
    }
    
    // 验证交易对特定配置
    for (const auto& pair : symbol_leverages_) {
        if (pair.second < 1.0 || pair.second > 125.0) {
            std::cerr << "[验证] 交易对 " << pair.first << " 的杠杆倍数无效" << std::endl;
            return false;
        }
    }
    
    for (const auto& pair : symbol_contract_values_) {
        if (pair.second <= 0) {
            std::cerr << "[验证] 交易对 " << pair.first << " 的合约面值无效" << std::endl;
            return false;
        }
    }
    
    return true;
}

double PaperTradingConfig::get_contract_value(const std::string& symbol) const {
    auto it = symbol_contract_values_.find(symbol);
    if (it != symbol_contract_values_.end()) {
        return it->second;
    }
    return default_contract_value_;
}

double PaperTradingConfig::get_leverage(const std::string& symbol) const {
    auto it = symbol_leverages_.find(symbol);
    if (it != symbol_leverages_.end()) {
        return it->second;
    }
    return default_leverage_;
}

void PaperTradingConfig::print() const {
    std::cout << "\n========================================\n";
    std::cout << "   模拟交易配置\n";
    std::cout << "========================================\n";
    std::cout << std::fixed << std::setprecision(6);
    std::cout << "\n[账户配置]\n";
    std::cout << "  初始余额: " << initial_balance_ << " USDT\n";
    std::cout << "  默认杠杆: " << default_leverage_ << "x\n";
    std::cout << "\n[手续费配置]\n";
    std::cout << "  Maker费率(挂单): " << (maker_fee_rate_ * 100) << "%\n";
    std::cout << "  Taker费率(市价): " << (taker_fee_rate_ * 100) << "%\n";
    std::cout << "\n[交易配置]\n";
    std::cout << "  市价单滑点: " << (market_order_slippage_ * 100) << "%\n";
    std::cout << "  默认合约面值: " << default_contract_value_ << "\n";
    std::cout << "\n[行情配置]\n";
    std::cout << "  使用测试网: " << (is_testnet_ ? "是" : "否") << "\n";
    
    if (!symbol_contract_values_.empty()) {
        std::cout << "\n[交易对合约面值]\n";
        for (const auto& pair : symbol_contract_values_) {
            std::cout << "  " << pair.first << ": " << pair.second << "\n";
        }
    }
    
    if (!symbol_leverages_.empty()) {
        std::cout << "\n[交易对杠杆倍数]\n";
        for (const auto& pair : symbol_leverages_) {
            std::cout << "  " << pair.first << ": " << pair.second << "x\n";
        }
    }
    
    std::cout << "========================================\n\n";
}

nlohmann::json PaperTradingConfig::to_json() const {
    nlohmann::json j;
    j["account"] = {
        {"initial_balance", initial_balance_},
        {"default_leverage", default_leverage_}
    };
    j["fees"] = {
        {"maker_fee_rate", maker_fee_rate_},
        {"taker_fee_rate", taker_fee_rate_}
    };
    j["trading"] = {
        {"market_order_slippage", market_order_slippage_},
        {"default_contract_value", default_contract_value_}
    };
    j["market_data"] = {
        {"is_testnet", is_testnet_}
    };
    
    if (!symbol_contract_values_.empty()) {
        j["symbol_contract_values"] = symbol_contract_values_;
    }
    
    if (!symbol_leverages_.empty()) {
        j["symbol_leverages"] = symbol_leverages_;
    }
    
    return j;
}

void PaperTradingConfig::load_from_json(const nlohmann::json& j) {
    // 账户配置
    if (j.contains("account")) {
        const auto& account = j["account"];
        initial_balance_ = account.value("initial_balance", 100000.0);
        default_leverage_ = account.value("default_leverage", 1.0);
    } else {
        initial_balance_ = 100000.0;
        default_leverage_ = 1.0;
    }
    
    // 手续费配置
    if (j.contains("fees")) {
        const auto& fees = j["fees"];
        maker_fee_rate_ = fees.value("maker_fee_rate", 0.0002);
        taker_fee_rate_ = fees.value("taker_fee_rate", 0.0005);
    } else {
        maker_fee_rate_ = 0.0002;
        taker_fee_rate_ = 0.0005;
    }
    
    // 交易配置
    if (j.contains("trading")) {
        const auto& trading = j["trading"];
        market_order_slippage_ = trading.value("market_order_slippage", 0.0001);
        default_contract_value_ = trading.value("default_contract_value", 1.0);
    } else {
        market_order_slippage_ = 0.0001;
        default_contract_value_ = 1.0;
    }
    
    // 行情配置
    if (j.contains("market_data")) {
        const auto& market_data = j["market_data"];
        is_testnet_ = market_data.value("is_testnet", true);
    } else {
        is_testnet_ = true;
    }
    
    // 交易对特定配置
    symbol_contract_values_.clear();
    if (j.contains("symbol_contract_values")) {
        for (const auto& item : j["symbol_contract_values"].items()) {
            symbol_contract_values_[item.key()] = item.value().get<double>();
        }
    }
    
    symbol_leverages_.clear();
    if (j.contains("symbol_leverages")) {
        for (const auto& item : j["symbol_leverages"].items()) {
            symbol_leverages_[item.key()] = item.value().get<double>();
        }
    }
}

bool PaperTradingConfig::save_to_file(const std::string& filename) const {
    try {
        nlohmann::json j = to_json();
        std::ofstream file(filename);
        if (!file.is_open()) {
            std::cerr << "[错误] 无法打开文件进行写入: " << filename << std::endl;
            return false;
        }
        file << std::setw(4) << j << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "[错误] 保存配置失败: " << e.what() << std::endl;
        return false;
    }
}

} // namespace papertrading
} // namespace trading

