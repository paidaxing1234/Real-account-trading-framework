/**
 * @file test_binance_batch_orders.cpp
 * @brief 测试 Binance 批量下单接口
 *
 * 编译:
 *   cd cpp/build && make test_binance_batch_orders
 *
 * 运行:
 *   ./test_binance_batch_orders
 */

#include <iostream>
#include <string>
#include <vector>
#include "../adapters/binance/binance_rest_api.h"

using namespace trading::binance;

int main() {
    std::cout << "========================================\n";
    std::cout << "  Binance 批量下单接口测试 (测试网)\n";
    std::cout << "========================================\n\n";

    // 测试网 API 密钥（从配置文件读取或硬编码测试）
    std::string api_key = "K3HOF3tv75HW6LqHaXl3kTyDt0gsSILT7Jst2l3wX5B5tLMetv3k9dasOKRxsX2M";
    std::string secret_key = "t29kSyEiiDYnvIAvx3ee0m7WYB6bOMCyhfqyuvuhfTRE1OpklnLV3KuCqfiP0ZMe";

    try {
        // 创建 Binance REST API 客户端（测试网）
        BinanceRestAPI api(api_key, secret_key, MarketType::FUTURES, true);

        std::cout << "[1] API 客户端创建成功\n";
        std::cout << "    Base URL: " << api.get_base_url() << "\n\n";

        // 测试获取账户余额
        std::cout << "[2] 测试获取账户余额...\n";
        auto balance = api.get_account_balance();
        for (const auto& asset : balance) {
            if (asset.contains("asset") && asset.contains("availableBalance")) {
                std::string asset_name = asset["asset"].get<std::string>();
                std::string avail = asset["availableBalance"].get<std::string>();
                if (std::stod(avail) > 0) {
                    std::cout << "    " << asset_name << ": " << avail << "\n";
                }
            }
        }
        std::cout << "\n";

        // 测试批量下单（使用很小的数量）
        std::cout << "[3] 测试批量下单...\n";

        std::vector<nlohmann::json> orders = {
            {
                {"symbol", "BTCUSDT"},
                {"side", "BUY"},
                {"type", "MARKET"},
                {"quantity", "0.001"},
                {"positionSide", "LONG"}
            },
            {
                {"symbol", "ETHUSDT"},
                {"side", "BUY"},
                {"type", "MARKET"},
                {"quantity", "0.01"},
                {"positionSide", "LONG"}
            }
        };

        std::cout << "    订单数量: " << orders.size() << "\n";
        for (size_t i = 0; i < orders.size(); ++i) {
            std::cout << "    订单 " << (i+1) << ": "
                      << orders[i]["symbol"].get<std::string>() << " "
                      << orders[i]["side"].get<std::string>() << " "
                      << orders[i]["quantity"].get<std::string>() << "\n";
        }
        std::cout << "\n";

        auto result = api.place_batch_orders(orders);

        std::cout << "[4] 批量下单结果:\n";
        std::cout << result.dump(2) << "\n\n";

        // 解析结果
        if (result.is_array()) {
            int success = 0, fail = 0;
            for (const auto& res : result) {
                if (res.contains("orderId")) {
                    success++;
                    std::cout << "    ✓ " << res.value("symbol", "")
                              << " 订单ID: " << res.value("orderId", 0) << "\n";
                } else if (res.contains("code")) {
                    fail++;
                    std::cout << "    ✗ 错误: " << res.value("msg", "Unknown") << "\n";
                }
            }
            std::cout << "\n    成功: " << success << ", 失败: " << fail << "\n";
        }

        std::cout << "\n========================================\n";
        std::cout << "  测试完成\n";
        std::cout << "========================================\n";

    } catch (const std::exception& e) {
        std::cerr << "\n[错误] " << e.what() << "\n";
        return 1;
    }

    return 0;
}
