/**
 * @file test_binance_futures_rest_order_testnet.cpp
 * @brief Binance U本位合约（FUTURES）测试网 - REST 下单测试（仿照 OKX）
 * 
 * 目标：
 * - 用测试网（demo-fapi.binance.com）下单、撤单、查单
 * - 最简风格：key 直接写代码里（仿照 test_okx_order.cpp）
 * 
 * ⚠️ 注意：
 * - 合约最小名义价值（notional）= 100 USDT
 * - 避免 -4164：确保 price × quantity ≥ 100
 */

#include "../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <iomanip>
#include <chrono>
#include <thread>

using namespace trading::binance;

// 默认代理
const char* DEFAULT_PROXY = "http://127.0.0.1:7890";

// 生成客户订单ID
static std::string gen_client_order_id(const std::string& prefix) {
    auto now = std::chrono::system_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count();
    // Binance 规则：^[\.A-Z\:/a-z0-9_-]{1,36}$
    return prefix + std::to_string(ms % 1000000000);
}

int main() {
    std::cout << "========================================\n";
    std::cout << "  Binance FUTURES REST 下单测试(Testnet)\n";
    std::cout << "========================================\n";

    // 代理设置（仿照 OKX）
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") &&
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置代理: " << DEFAULT_PROXY << "\n";
    }

    // ==================== 填入你的合约测试网 key ====================
    std::string api_key = "txMIDVQyFksbCVfDkgDQgmkxmy24zwKrsEffJqHadqX5wOB9o6YFiXVhMFN6h10q";
    std::string secret_key = "EiVtWX34yO9Xgb28eC2zwJ7jWPtW6Cwk39sse0axMrfIeeIP5DqpZczNwuprJMZp";

    if (api_key == "YOUR_FUTURES_TESTNET_API_KEY") {
        std::cerr << "\n❌ 请先填入合约测试网 API 密钥\n";
        std::cerr << "   文档：https://binance-docs.github.io/apidocs/futures/cn/\n";
        std::cerr << "   测试网：demo-fapi.binance.com\n";
        return 1;
    }

    std::cout << "\n配置信息:\n";
    std::cout << "  API Key: " << api_key.substr(0, 8) << "...\n";
    std::cout << "  网络: FUTURES Testnet (demo-fapi.binance.com)\n";
    std::cout << "  模式: 模拟交易\n";

    // 创建 API 客户端（U本位合约，测试网）
    BinanceRestAPI api(api_key, secret_key, MarketType::FUTURES, true);

    try {
        // 1) ping
        std::cout << "\n[1] 测试连接...\n";
        if (!api.test_connectivity()) {
            std::cerr << "❌ ping 失败\n";
            return 1;
        }
        std::cout << "✅ ping OK\n";

        // 2) 获取最新价
        std::cout << "\n[2] 获取 BTCUSDT 最新价...\n";
        auto ticker = api.get_ticker_price("BTCUSDT");
        double last_price = std::stod(ticker.value("price", "0"));
        std::cout << "  lastPrice: " << std::fixed << std::setprecision(2) << last_price << "\n";

        // 3) 下限价单（远离市价 + 满足最小名义价值 100 USDT）
        std::cout << "\n[3] 下限价单（GTC, 远离市价）...\n";
        
        // 计算：确保 price × quantity ≥ 100 USDT
        // 例如：price = last_price * 0.5（远离市价），quantity = 0.003
        // notional = 44000 * 0.003 = 132 USDT > 100 ✅
        double order_price = last_price * 0.5;  // 市价一半（不会成交）
        std::string qty = "0.3";  // 0.003 BTC
        
        std::string cid = gen_client_order_id("restfut");
        
        std::cout << "  symbol: BTCUSDT\n";
        std::cout << "  side: BUY\n";
        std::cout << "  type: LIMIT\n";
        std::cout << "  quantity: " << qty << "\n";
        std::cout << "  price: " << std::fixed << std::setprecision(1) << order_price << "\n";
        std::cout << "  notional: " << (order_price * std::stod(qty)) << " USDT (需≥100)\n";
        std::cout << "  positionSide: BOTH\n";
        std::cout << "  newClientOrderId: " << cid << "\n";

        auto order_resp = api.place_order(
            "BTCUSDT",
            OrderSide::BUY,
            OrderType::LIMIT,
            qty,
            std::to_string((int)order_price),  // BTCUSDT tick=0.1，这里取整数即可
            TimeInForce::GTC,
            PositionSide::LONG,
            cid
        );

        std::cout << "\n✅ 下单成功\n";
        std::cout << "  orderId: " << order_resp.value("orderId", 0) << "\n";
        std::cout << "  status: " << order_resp.value("status", "") << "\n";
        std::cout << "  clientOrderId: " << order_resp.value("clientOrderId", "") << "\n";

        int64_t order_id = order_resp.value("orderId", 0L);

        // 等待 1 秒
        std::this_thread::sleep_for(std::chrono::seconds(10));

        // 4) 查询订单
        std::cout << "\n[4] 查询订单（通过 orderId）...\n";
        auto query_resp = api.get_order("BTCUSDT", order_id);
        std::cout << "  orderId: " << query_resp.value("orderId", 0) << "\n";
        std::cout << "  status: " << query_resp.value("status", "") << "\n";
        std::cout << "  price: " << query_resp.value("price", "") << "\n";
        std::cout << "  origQty: " << query_resp.value("origQty", "") << "\n";
        std::cout << "  executedQty: " << query_resp.value("executedQty", "") << "\n";
        std::this_thread::sleep_for(std::chrono::seconds(10));
        // 5) 撤单
        std::cout << "\n[5] 撤单（通过 orderId）...\n";
        auto cancel_resp = api.cancel_order("BTCUSDT", order_id);
        std::cout << "  orderId: " << cancel_resp.value("orderId", 0) << "\n";
        std::cout << "  status: " << cancel_resp.value("status", "") << "\n";
        std::cout << "  clientOrderId: " << cancel_resp.value("clientOrderId", "") << "\n";
        std::cout << "✅ 撤单成功\n";

        std::cout << "\n========================================\n";
        std::cout << "  测试完成：下单 → 查单 → 撤单 全部成功\n";
        std::cout << "========================================\n";

    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << "\n";
        std::cerr << "\n💡 常见错误:\n";
        std::cerr << "  -2015: key/IP/权限不对（确认是合约测试网 demo-fapi 的 key）\n";
        std::cerr << "  -4164: notional too small（确保 price × quantity ≥ 100 USDT）\n";
        return 1;
    }

    return 0;
}

