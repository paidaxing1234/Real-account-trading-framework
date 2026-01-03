/**
 * @file test_binance_spot.cpp
 * @brief Binance 现货 REST API 测试程序（示例）
 *
 * 说明：
 * - 公开行情接口无需密钥
 * - 私有接口（账户等）需要 API_KEY/SECRET_KEY
 * - 可通过 BINANCE_TESTNET=1 使用测试网（模拟）
 */

#include "../adapters/binance/binance_rest_api.h"

#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>

using namespace trading::binance;

static bool env_truthy(const char* key) {
    const char* v = std::getenv(key);
    if (!v) return false;
    std::string s(v);
    for (auto& c : s) c = (char)std::tolower((unsigned char)c);
    return (s == "1" || s == "true" || s == "yes" || s == "on");
}

static std::string getenv_or_empty(const char* k) {
    const char* v = std::getenv(k);
    return (v && *v) ? std::string(v) : std::string();
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  Binance 现货 REST API 测试\n";
    std::cout << "========================================\n\n";

    const bool is_testnet = env_truthy("BINANCE_TESTNET");
    const std::string api_key = getenv_or_empty("BINANCE_API_KEY");
    const std::string secret_key = getenv_or_empty("BINANCE_SECRET_KEY");

    try {
        BinanceRestAPI api(api_key, secret_key, MarketType::SPOT, is_testnet);

        std::cout << "网络: " << (is_testnet ? "TESTNET(模拟)" : "MAINNET(实盘)") << "\n";

        std::cout << "\n1) 测试连接..." << std::endl;
        if (!api.test_connectivity()) {
            std::cout << "   ❌ 连接失败" << std::endl;
            return 1;
        }
        std::cout << "   ✅ 连接成功" << std::endl;

        std::cout << "\n2) 获取服务器时间..." << std::endl;
        std::cout << "   serverTime(ms): " << api.get_server_time() << std::endl;

        std::cout << "\n3) 获取 BTCUSDT 交易规则..." << std::endl;
        auto info = api.get_exchange_info("BTCUSDT");
        if (info.contains("symbols") && !info["symbols"].empty()) {
            auto s = info["symbols"][0];
            std::cout << "   symbol: " << s.value("symbol", "") << "\n";
            std::cout << "   status: " << s.value("status", "") << "\n";
            std::cout << "   base  : " << s.value("baseAsset", "") << "\n";
            std::cout << "   quote : " << s.value("quoteAsset", "") << "\n";
        }

        std::cout << "\n4) 获取最新价格..." << std::endl;
        auto price = api.get_ticker_price("BTCUSDT");
        std::cout << "   BTCUSDT: " << price.value("price", "") << std::endl;

        std::cout << "\n5) 获取24小时价格变动..." << std::endl;
        auto t24 = api.get_ticker_24hr("BTCUSDT");
        std::cout << "   high: " << t24.value("highPrice", "") << "\n";
        std::cout << "   low : " << t24.value("lowPrice", "") << "\n";
        std::cout << "   vol : " << t24.value("volume", "") << "\n";

        std::cout << "\n6) 账户/交易接口已跳过（仅保留已验证的市场数据接口）\n";

        std::cout << "\n========================================\n";
        std::cout << "  测试完成\n";
        std::cout << "========================================\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}


