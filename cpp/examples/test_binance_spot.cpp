/**
 * @file test_binance_spot.cpp
 * @brief 币安现货API测试程序
 * 
 * 测试币安现货交易接口：
 * - 连接测试
 * - 获取服务器时间
 * - 获取交易对信息
 * - 获取最新价格
 * - 查询账户信息（需要API密钥）
 * 
 * @author Sequence Team
 * @date 2024-12
 */

#include "../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <iomanip>

using namespace trading::binance;

int main() {
    std::cout << "========================================" << std::endl;
    std::cout << "  Binance 现货 API 测试" << std::endl;
    std::cout << "========================================\n" << std::endl;
    
    // API密钥（如果没有，可以只测试公开接口）
    const std::string API_KEY = "";
    const std::string SECRET_KEY = "";
    
    try {
        // 创建API客户端（现货市场）
        BinanceRestAPI api(API_KEY, SECRET_KEY, MarketType::SPOT, false);
        
        // 测试1：连接测试
        std::cout << "1️⃣  测试连接..." << std::endl;
        if (api.test_connectivity()) {
            std::cout << "   ✅ 连接成功！\n" << std::endl;
        } else {
            std::cout << "   ❌ 连接失败\n" << std::endl;
            return 1;
        }
        
        // 测试2：获取服务器时间
        std::cout << "2️⃣  获取服务器时间..." << std::endl;
        auto server_time = api.get_server_time();
        std::cout << "   服务器时间: " << server_time << " (毫秒时间戳)\n" << std::endl;
        
        // 测试3：获取交易对信息
        std::cout << "3️⃣  获取 BTCUSDT 交易对信息..." << std::endl;
        auto exchange_info = api.get_exchange_info("BTCUSDT");
        
        if (exchange_info.contains("symbols") && !exchange_info["symbols"].empty()) {
            auto symbol_info = exchange_info["symbols"][0];
            std::cout << "   交易对: " << symbol_info["symbol"] << std::endl;
            std::cout << "   状态: " << symbol_info["status"] << std::endl;
            std::cout << "   基础货币: " << symbol_info["baseAsset"] << std::endl;
            std::cout << "   计价货币: " << symbol_info["quoteAsset"] << std::endl;
        }
        std::cout << std::endl;
        
        // 测试4：获取最新价格
        std::cout << "4️⃣  获取最新价格..." << std::endl;
        auto btc_price = api.get_ticker_price("BTCUSDT");
        std::cout << "   BTCUSDT 价格: $" << btc_price["price"] << std::endl;
        
        auto eth_price = api.get_ticker_price("ETHUSDT");
        std::cout << "   ETHUSDT 价格: $" << eth_price["price"] << "\n" << std::endl;
        
        // 测试5：获取24小时价格变动
        std::cout << "5️⃣  获取 24小时 价格变动..." << std::endl;
        auto ticker_24hr = api.get_ticker_24hr("BTCUSDT");
        std::cout << "   交易对: " << ticker_24hr["symbol"] << std::endl;
        std::cout << "   最高价: $" << ticker_24hr["highPrice"] << std::endl;
        std::cout << "   最低价: $" << ticker_24hr["lowPrice"] << std::endl;
        std::cout << "   成交量: " << ticker_24hr["volume"] << " BTC" << std::endl;
        std::cout << "   涨跌幅: " << ticker_24hr["priceChangePercent"] << "%\n" << std::endl;
        
        // 测试6：获取深度信息
        std::cout << "6️⃣  获取深度信息（前5档）..." << std::endl;
        auto depth = api.get_depth("BTCUSDT", 5);
        
        std::cout << "   卖盘（Asks）:" << std::endl;
        for (int i = depth["asks"].size() - 1; i >= 0; i--) {
            auto ask = depth["asks"][i];
            std::cout << "      " << std::setw(12) << ask[0] 
                      << "  |  " << ask[1] << std::endl;
        }
        
        std::cout << "   " << std::string(40, '-') << std::endl;
        
        std::cout << "   买盘（Bids）:" << std::endl;
        for (const auto& bid : depth["bids"]) {
            std::cout << "      " << std::setw(12) << bid[0] 
                      << "  |  " << bid[1] << std::endl;
        }
        std::cout << std::endl;
        
        // 测试7：获取K线数据
        std::cout << "7️⃣  获取K线数据（最近5根1小时K线）..." << std::endl;
        auto klines = api.get_klines("BTCUSDT", "1h", 0, 0, 5);
        
        std::cout << "   " << std::setw(20) << "时间" 
                  << std::setw(12) << "开盘价"
                  << std::setw(12) << "最高价"
                  << std::setw(12) << "最低价"
                  << std::setw(12) << "收盘价"
                  << std::setw(15) << "成交量" << std::endl;
        std::cout << "   " << std::string(80, '-') << std::endl;
        
        for (const auto& kline : klines) {
            int64_t timestamp = kline[0].get<int64_t>();
            time_t t = timestamp / 1000;
            char time_str[20];
            strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M", gmtime(&t));
            
            std::cout << "   " << std::setw(20) << time_str
                      << std::setw(12) << kline[1]  // 开盘价
                      << std::setw(12) << kline[2]  // 最高价
                      << std::setw(12) << kline[3]  // 最低价
                      << std::setw(12) << kline[4]  // 收盘价
                      << std::setw(15) << kline[5]  // 成交量
                      << std::endl;
        }
        std::cout << std::endl;
        
        // 测试8：账户信息（需要API密钥）
        if (!API_KEY.empty() && !SECRET_KEY.empty()) {
            std::cout << "8️⃣  获取账户信息..." << std::endl;
            
            try {
                auto account = api.get_account_info();
                std::cout << "   账户类型: " << account.value("accountType", "SPOT") << std::endl;
                std::cout << "   可以交易: " << (account.value("canTrade", false) ? "是" : "否") << std::endl;
                std::cout << "   可以提现: " << (account.value("canWithdraw", false) ? "是" : "否") << "\n" << std::endl;
                
                // 获取余额
                std::cout << "   账户余额（非零）:" << std::endl;
                auto balances = api.get_account_balance();
                
                bool has_balance = false;
                for (const auto& bal : balances) {
                    double free = std::stod(bal.free);
                    double locked = std::stod(bal.locked);
                    
                    if (free > 0 || locked > 0) {
                        std::cout << "      " << std::setw(8) << bal.asset
                                  << "  |  可用: " << std::setw(18) << bal.free
                                  << "  |  冻结: " << std::setw(18) << bal.locked
                                  << std::endl;
                        has_balance = true;
                    }
                }
                
                if (!has_balance) {
                    std::cout << "      （没有非零余额）" << std::endl;
                }
                
            } catch (const std::exception& e) {
                std::cout << "   ⚠️  需要有效的API密钥才能查询账户信息" << std::endl;
                std::cout << "   错误: " << e.what() << std::endl;
            }
        } else {
            std::cout << "8️⃣  跳过账户信息测试（未提供API密钥）" << std::endl;
        }
        
        // 提示信息
        std::cout << "\n========================================" << std::endl;
        std::cout << "  测试完成！" << std::endl;
        std::cout << "========================================" << std::endl;
        
        std::cout << "\n💡 提示：" << std::endl;
        std::cout << "   - 公开接口（行情数据）无需API密钥" << std::endl;
        std::cout << "   - 私有接口（账户、交易）需要API密钥" << std::endl;
        std::cout << "   - API密钥可在币安官网申请" << std::endl;
        std::cout << "   - 测试网API密钥：testnet.binance.vision" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 发生异常: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}

