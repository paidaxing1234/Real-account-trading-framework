/**
 * @file test_okx_funding_rate.cpp
 * @brief OKX REST API - 获取永续合约资金费率测试
 * 
 * 测试 get_funding_rate 接口
 * 
 * 功能说明：
 * - 获取永续合约当前资金费率
 * - 限速：10次/2s
 * - 限速规则：IP + Instrument ID
 * 
 * API文档：
 * https://www.okx.com/docs-v5/zh/#order-book-trading-market-data-get-funding-rate
 */

#include "../adapters/okx/okx_rest_api.h"
#include <iostream>
#include <iomanip>
#include <ctime>

using namespace trading::okx;

// 将毫秒时间戳转换为可读时间
std::string timestamp_to_string(int64_t timestamp_ms) {
    time_t timestamp_sec = timestamp_ms / 1000;
    std::tm* tm = std::gmtime(&timestamp_sec);
    
    char buffer[100];
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", tm);
    return std::string(buffer) + " UTC";
}

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX REST API - 获取资金费率测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // API凭证（资金费率接口是公开接口，不需要认证，但为了统一接口，还是传入）
    const std::string API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string SECRET_KEY = "888CC77C745F1B49E75A992F38929992";
    const std::string PASSPHRASE = "Sequence2025.";
    
    try {
        // 创建REST API客户端（使用实盘，资金费率是公开数据）
        OKXRestAPI api(API_KEY, SECRET_KEY, PASSPHRASE, false);  // false = 实盘
        
        // 测试1：获取BTC-USDT-SWAP的资金费率
        std::cout << "\n1️⃣ 测试：获取 BTC-USDT-SWAP 资金费率" << std::endl;
        std::cout << "   调用: get_funding_rate(\"BTC-USDT-SWAP\")" << std::endl;
        
        auto result = api.get_funding_rate("BTC-USDT-SWAP");
        
        // 检查响应
        if (result["code"] == "0") {
            std::cout << "   ✅ 请求成功！" << std::endl;
            
            // 解析数据
            if (!result["data"].empty()) {
                auto data = result["data"][0];
                
                std::cout << "\n   📊 BTC-USDT-SWAP 资金费率信息：" << std::endl;
                std::cout << "   " << std::string(80, '=') << std::endl;
                
                // 基本信息
                std::cout << "   产品ID:           " << data["instId"] << std::endl;
                std::cout << "   产品类型:         " << data["instType"] << std::endl;
                std::cout << "   收取逻辑:         " << data["method"] << std::endl;
                std::cout << "   公式类型:         " << data["formulaType"] << std::endl;
                
                std::cout << "   " << std::string(80, '-') << std::endl;
                
                // 当前资金费率
                double funding_rate = std::stod(data["fundingRate"].get<std::string>());
                std::cout << "   当前资金费率:     " << std::fixed << std::setprecision(8) 
                          << funding_rate << " (" << (funding_rate * 100) << "%)" << std::endl;
                
                // 下一期预测资金费率（如果有）
                std::string next_funding_rate_str = data["nextFundingRate"].get<std::string>();
                if (!next_funding_rate_str.empty()) {
                    double next_funding_rate = std::stod(next_funding_rate_str);
                    std::cout << "   下期预测费率:     " << std::fixed << std::setprecision(8) 
                              << next_funding_rate << " (" << (next_funding_rate * 100) << "%)" << std::endl;
                } else {
                    std::cout << "   下期预测费率:     (暂无数据)" << std::endl;
                }
                
                // 费率范围
                double min_funding_rate = std::stod(data["minFundingRate"].get<std::string>());
                double max_funding_rate = std::stod(data["maxFundingRate"].get<std::string>());
                std::cout << "   费率下限:         " << std::fixed << std::setprecision(8) 
                          << min_funding_rate << " (" << (min_funding_rate * 100) << "%)" << std::endl;
                std::cout << "   费率上限:         " << std::fixed << std::setprecision(8) 
                          << max_funding_rate << " (" << (max_funding_rate * 100) << "%)" << std::endl;
                
                std::cout << "   " << std::string(80, '-') << std::endl;
                
                // 时间信息
                int64_t funding_time = std::stoll(data["fundingTime"].get<std::string>());
                int64_t next_funding_time = std::stoll(data["nextFundingTime"].get<std::string>());
                std::cout << "   资金费时间:       " << timestamp_to_string(funding_time) << std::endl;
                std::cout << "   下期费时间:       " << timestamp_to_string(next_funding_time) << std::endl;
                
                // 计算收取频率（小时）
                int64_t interval_ms = next_funding_time - funding_time;
                double interval_hours = interval_ms / (1000.0 * 3600.0);
                std::cout << "   收取频率:         " << std::fixed << std::setprecision(0) 
                          << interval_hours << " 小时" << std::endl;
                
                std::cout << "   " << std::string(80, '-') << std::endl;
                
                // 结算信息
                std::cout << "   结算状态:         " << data["settState"] << std::endl;
                double sett_funding_rate = std::stod(data["settFundingRate"].get<std::string>());
                std::cout << "   结算费率:         " << std::fixed << std::setprecision(8) 
                          << sett_funding_rate << " (" << (sett_funding_rate * 100) << "%)" << std::endl;
                
                // 溢价指数（如果有）
                std::string premium_str = data["premium"].get<std::string>();
                if (!premium_str.empty()) {
                    double premium = std::stod(premium_str);
                    std::cout << "   溢价指数:         " << std::fixed << std::setprecision(8) 
                              << premium << " (" << (premium * 100) << "%)" << std::endl;
                }
                
                // 更新时间
                int64_t ts = std::stoll(data["ts"].get<std::string>());
                std::cout << "   更新时间:         " << timestamp_to_string(ts) << std::endl;
                
                std::cout << "   " << std::string(80, '=') << std::endl;
            }
        } else {
            std::cout << "   ❌ 请求失败！" << std::endl;
            std::cout << "   错误码: " << result["code"] << std::endl;
            std::cout << "   错误信息: " << result["msg"] << std::endl;
        }
        
        // 测试2：获取ETH-USDT-SWAP的资金费率
        std::cout << "\n2️⃣ 测试：获取 ETH-USDT-SWAP 资金费率" << std::endl;
        std::cout << "   调用: get_funding_rate(\"ETH-USDT-SWAP\")" << std::endl;
        
        result = api.get_funding_rate("ETH-USDT-SWAP");
        
        if (result["code"] == "0" && !result["data"].empty()) {
            std::cout << "   ✅ 请求成功！" << std::endl;
            
            auto data = result["data"][0];
            double funding_rate = std::stod(data["fundingRate"].get<std::string>());
            int64_t funding_time = std::stoll(data["fundingTime"].get<std::string>());
            int64_t next_funding_time = std::stoll(data["nextFundingTime"].get<std::string>());
            double interval_hours = (next_funding_time - funding_time) / (1000.0 * 3600.0);
            
            std::cout << "   产品:             " << data["instId"] << std::endl;
            std::cout << "   当前资金费率:     " << std::fixed << std::setprecision(8) 
                      << funding_rate << " (" << (funding_rate * 100) << "%)" << std::endl;
            std::cout << "   资金费时间:       " << timestamp_to_string(funding_time) << std::endl;
            std::cout << "   收取频率:         " << std::fixed << std::setprecision(0) 
                      << interval_hours << " 小时" << std::endl;
        } else {
            std::cout << "   ❌ 请求失败" << std::endl;
        }
        
        // 测试3：获取BTC-USD-SWAP的资金费率（币本位合约）
        std::cout << "\n3️⃣ 测试：获取 BTC-USD-SWAP 资金费率（币本位）" << std::endl;
        std::cout << "   调用: get_funding_rate(\"BTC-USD-SWAP\")" << std::endl;
        
        result = api.get_funding_rate("BTC-USD-SWAP");
        
        if (result["code"] == "0" && !result["data"].empty()) {
            std::cout << "   ✅ 请求成功！" << std::endl;
            
            auto data = result["data"][0];
            double funding_rate = std::stod(data["fundingRate"].get<std::string>());
            int64_t funding_time = std::stoll(data["fundingTime"].get<std::string>());
            
            std::cout << "   产品:             " << data["instId"] << std::endl;
            std::cout << "   当前资金费率:     " << std::fixed << std::setprecision(8) 
                      << funding_rate << " (" << (funding_rate * 100) << "%)" << std::endl;
            std::cout << "   资金费时间:       " << timestamp_to_string(funding_time) << std::endl;
        } else {
            std::cout << "   ❌ 请求失败" << std::endl;
        }
        
        // 测试4：获取所有永续合约的资金费率（仅显示前5个）
        std::cout << "\n4️⃣ 测试：获取所有永续合约资金费率（显示前5个）" << std::endl;
        std::cout << "   调用: get_funding_rate(\"ANY\")" << std::endl;
        
        result = api.get_funding_rate("ANY");
        
        if (result["code"] == "0") {
            std::cout << "   ✅ 请求成功！" << std::endl;
            std::cout << "   返回合约数量: " << result["data"].size() << std::endl;
            
            std::cout << "\n   前5个合约的资金费率：" << std::endl;
            std::cout << "   " << std::string(100, '-') << std::endl;
            std::cout << "   " << std::setw(20) << std::left << "产品ID"
                      << std::setw(15) << "资金费率(%)"
                      << std::setw(15) << "收取频率"
                      << std::setw(35) << "下次收费时间" << std::endl;
            std::cout << "   " << std::string(100, '-') << std::endl;
            
            int count = 0;
            for (const auto& item : result["data"]) {
                if (count >= 5) break;
                
                double rate = std::stod(item["fundingRate"].get<std::string>());
                int64_t funding_time = std::stoll(item["fundingTime"].get<std::string>());
                int64_t next_funding_time = std::stoll(item["nextFundingTime"].get<std::string>());
                double interval_hours = (next_funding_time - funding_time) / (1000.0 * 3600.0);
                
                std::cout << "   " 
                          << std::setw(20) << std::left << item["instId"].get<std::string>()
                          << std::setw(15) << std::fixed << std::setprecision(6) << (rate * 100)
                          << std::setw(15) << (std::to_string((int)interval_hours) + "小时")
                          << std::setw(35) << timestamp_to_string(next_funding_time)
                          << std::endl;
                
                count++;
            }
            std::cout << "   " << std::string(100, '-') << std::endl;
        } else {
            std::cout << "   ❌ 请求失败" << std::endl;
        }
        
        // 提示信息
        std::cout << "\n💡 注意事项：" << std::endl;
        std::cout << "   1. 资金费率是永续合约特有的机制，用于锚定合约价格和现货价格" << std::endl;
        std::cout << "   2. 正资金费率：多头支付空头；负资金费率：空头支付多头" << std::endl;
        std::cout << "   3. OKX会根据市场波动调整收取频率（8/6/4/2/1小时）" << std::endl;
        std::cout << "   4. 请关注fundingTime和nextFundingTime字段确定收取频率" << std::endl;
        std::cout << "   5. 限速：10次/2s（按IP + Instrument ID）" << std::endl;
        
    } catch (const std::exception& e) {
        std::cout << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成！" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}
