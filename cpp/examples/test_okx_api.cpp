/**
 * @file test_okx_api.cpp
 * @brief OKX REST API 测试程序
 * 
 * 测试 get_account_instruments 接口
 */

#include "../adapters/okx/okx_rest_api.h"
#include <iostream>
#include <iomanip>

using namespace trading::okx;

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  OKX REST API - 获取交易产品信息测试" << std::endl;
    std::cout << "========================================" << std::endl;
    
    // API凭证
    const std::string API_KEY = "25fc280c-9f3a-4d65-a23d-59d42eeb7d7e";
    const std::string SECRET_KEY = "888CC77C745F1B49E75A992F38929992";
    const std::string PASSPHRASE = "Sequence2025.";
    
    try {
        // 创建REST API客户端（使用模拟盘）
        OKXRestAPI api(API_KEY, SECRET_KEY, PASSPHRASE, true);  // true = 模拟盘
        
        std::cout << "\n1️⃣ 测试：查询现货产品列表" << std::endl;
        std::cout << "   调用: get_account_instruments(\"SPOT\")" << std::endl;
        
        // 调用接口
        auto result = api.get_account_instruments("SPOT");
        
        // 检查响应
        if (result["code"] == "0") {
            std::cout << "   ✅ 请求成功！" << std::endl;
            
            // 解析数据
            auto data = result["data"];
            std::cout << "   产品数量: " << data.size() << std::endl;
            
            // 显示前5个产品的信息
            std::cout << "\n   前5个产品信息：" << std::endl;
            std::cout << "   " << std::string(80, '-') << std::endl;
            std::cout << "   " << std::setw(15) << std::left << "产品ID"
                      << std::setw(12) << "基础货币"
                      << std::setw(12) << "计价货币"
                      << std::setw(12) << "状态"
                      << std::setw(15) << "最小下单量" << std::endl;
            std::cout << "   " << std::string(80, '-') << std::endl;
            
            int count = 0;
            for (const auto& item : data) {
                if (count >= 5) break;
                
                std::cout << "   " 
                          << std::setw(15) << std::left << item["instId"].get<std::string>()
                          << std::setw(12) << item["baseCcy"].get<std::string>()
                          << std::setw(12) << item["quoteCcy"].get<std::string>()
                          << std::setw(12) << item["state"].get<std::string>()
                          << std::setw(15) << item["minSz"].get<std::string>()
                          << std::endl;
                
                count++;
            }
            std::cout << "   " << std::string(80, '-') << std::endl;
        } else {
            std::cout << "   ❌ 请求失败！" << std::endl;
            std::cout << "   错误码: " << result["code"] << std::endl;
            std::cout << "   错误信息: " << result["msg"] << std::endl;
        }
        
        // 测试2：查询特定产品
        std::cout << "\n2️⃣ 测试：查询BTC-USDT产品信息" << std::endl;
        std::cout << "   调用: get_account_instruments(\"SPOT\", \"\", \"BTC-USDT\")" << std::endl;
        
        result = api.get_account_instruments("SPOT", "", "BTC-USDT");
        
        if (result["code"] == "0" && !result["data"].empty()) {
            std::cout << "   ✅ 请求成功！" << std::endl;
            
            auto item = result["data"][0];
            std::cout << "\n   BTC-USDT 详细信息：" << std::endl;
            std::cout << "   " << std::string(50, '-') << std::endl;
            std::cout << "   产品ID:        " << item["instId"] << std::endl;
            std::cout << "   产品类型:      " << item["instType"] << std::endl;
            std::cout << "   基础货币:      " << item["baseCcy"] << std::endl;
            std::cout << "   计价货币:      " << item["quoteCcy"] << std::endl;
            std::cout << "   状态:          " << item["state"] << std::endl;
            std::cout << "   价格精度:      " << item["tickSz"] << std::endl;
            std::cout << "   数量精度:      " << item["lotSz"] << std::endl;
            std::cout << "   最小下单量:    " << item["minSz"] << std::endl;
            std::cout << "   最大限价单量:  " << item["maxLmtSz"] << std::endl;
            std::cout << "   最大市价单量:  " << item["maxMktSz"] << std::endl;
            std::cout << "   " << std::string(50, '-') << std::endl;
        } else {
            std::cout << "   ❌ 请求失败或产品不存在" << std::endl;
        }
        
        // 测试3：查询永续合约
        std::cout << "\n3️⃣ 测试：查询永续合约产品" << std::endl;
        std::cout << "   调用: get_account_instruments(\"SWAP\")" << std::endl;
        
        result = api.get_account_instruments("SWAP");
        
        if (result["code"] == "0") {
            std::cout << "   ✅ 请求成功！" << std::endl;
            std::cout << "   永续合约产品数量: " << result["data"].size() << std::endl;
            
            // 显示前3个永续合约
            std::cout << "\n   前3个永续合约：" << std::endl;
            int count = 0;
            for (const auto& item : result["data"]) {
                if (count >= 3) break;
                std::cout << "   - " << item["instId"].get<std::string>()
                          << " (结算币种: " << item["settleCcy"].get<std::string>() << ")"
                          << std::endl;
                count++;
            }
        } else {
            std::cout << "   ❌ 请求失败" << std::endl;
        }
        
    } catch (const std::exception& e) {
        std::cout << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    std::cout << "\n========================================" << std::endl;
    std::cout << "  测试完成！" << std::endl;
    std::cout << "========================================" << std::endl;
    
    return 0;
}

