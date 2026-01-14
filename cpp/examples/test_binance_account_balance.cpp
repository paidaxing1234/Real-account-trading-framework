/**
 * @file test_binance_account_balance.cpp
 * @brief 测试 Binance 账户余额查询 API
 *
 * 用于调试 GNN 策略中余额为 0 的问题
 *
 * 编译:
 * cd build && cmake .. && make test_binance_account_balance
 *
 * 运行:
 * ./test_binance_account_balance
 */

#include "../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <iomanip>
#include <cstdlib>

using namespace trading::binance;

void print_section(const std::string& title) {
    std::cout << "\n" << std::string(60, '=') << "\n";
    std::cout << "  " << title << "\n";
    std::cout << std::string(60, '=') << "\n";
}

void print_json(const nlohmann::json& j, int indent = 2) {
    std::cout << j.dump(indent) << "\n";
}

int main() {
    std::cout << "===== Binance 账户余额查询测试 =====\n\n";

    // 从环境变量获取 API 密钥
    const char* api_key = std::getenv("BINANCE_API_KEY");
    const char* secret_key = std::getenv("BINANCE_SECRET_KEY");

    if (!api_key || !secret_key) {
        std::cerr << "❌ 请设置环境变量:\n";
        std::cerr << "   export BINANCE_API_KEY=your_api_key\n";
        std::cerr << "   export BINANCE_SECRET_KEY=your_secret_key\n";
        return 1;
    }

    std::cout << "API Key: " << std::string(api_key).substr(0, 8) << "...\n";
    std::cout << "使用主网 (MarketType::FUTURES)\n";

    try {
        // 创建 API 实例 - U本位合约，主网
        BinanceRestAPI api(api_key, secret_key, MarketType::FUTURES, true);

        // ========== 测试1: 基础连接 ==========
        print_section("1. 测试连接");
        if (api.test_connectivity()) {
            std::cout << "✅ 连接成功\n";
        } else {
            std::cout << "❌ 连接失败\n";
            return 1;
        }

        // ========== 测试2: 获取服务器时间 ==========
        print_section("2. 服务器时间");
        int64_t server_time = api.get_server_time();
        std::cout << "服务器时间: " << server_time << " ms\n";

        // ========== 测试3: get_account_balance() ==========
        print_section("3. get_account_balance() - 账户余额");
        try {
            auto balance = api.get_account_balance();
            std::cout << "返回类型: " << (balance.is_array() ? "数组" : "对象") << "\n";
            std::cout << "完整响应:\n";
            print_json(balance);

            // 解析余额
            if (balance.is_array()) {
                std::cout << "\n有余额的资产:\n";
                for (const auto& b : balance) {
                    double bal = std::stod(b.value("balance", "0"));
                    double avail = std::stod(b.value("availableBalance", "0"));
                    if (bal > 0 || avail > 0) {
                        std::cout << "  " << b.value("asset", "")
                                  << ": balance=" << bal
                                  << ", available=" << avail << "\n";
                    }
                }
            }
        } catch (const std::exception& e) {
            std::cout << "❌ 异常: " << e.what() << "\n";
        }

        // ========== 测试4: get_account_info() ==========
        print_section("4. get_account_info() - 账户信息 (包含 assets)");
        try {
            auto info = api.get_account_info();

            // 打印关键字段
            std::cout << "totalWalletBalance: " << info.value("totalWalletBalance", "N/A") << "\n";
            std::cout << "availableBalance: " << info.value("availableBalance", "N/A") << "\n";
            std::cout << "totalUnrealizedProfit: " << info.value("totalUnrealizedProfit", "N/A") << "\n";

            // 检查 assets 字段
            if (info.contains("assets") && info["assets"].is_array()) {
                std::cout << "\nassets 数组大小: " << info["assets"].size() << "\n";
                std::cout << "\n有余额的 assets:\n";
                int count = 0;
                for (const auto& asset : info["assets"]) {
                    std::string ccy = asset.value("asset", "");
                    double wallet = std::stod(asset.value("walletBalance", "0"));
                    double avail = std::stod(asset.value("availableBalance", "0"));

                    if (wallet > 0 || avail > 0) {
                        std::cout << "  " << ccy << ":\n";
                        std::cout << "    walletBalance: " << wallet << "\n";
                        std::cout << "    availableBalance: " << avail << "\n";
                        std::cout << "    crossUnPnl: " << asset.value("crossUnPnl", "0") << "\n";
                        count++;
                    }
                }
                if (count == 0) {
                    std::cout << "  (无)\n";
                }
            } else {
                std::cout << "⚠️ 响应中没有 assets 字段\n";
                std::cout << "完整响应:\n";
                print_json(info);
            }

            // 检查 positions 字段
            if (info.contains("positions") && info["positions"].is_array()) {
                std::cout << "\npositions 数组大小: " << info["positions"].size() << "\n";
                std::cout << "\n有持仓的 positions:\n";
                int count = 0;
                for (const auto& pos : info["positions"]) {
                    double amt = std::stod(pos.value("positionAmt", "0"));
                    if (amt != 0 && count < 5) {
                        std::cout << "  " << pos.value("symbol", "") << ":\n";
                        std::cout << "    positionAmt: " << amt << "\n";
                        std::cout << "    entryPrice: " << pos.value("entryPrice", "0") << "\n";
                        std::cout << "    unrealizedProfit: " << pos.value("unrealizedProfit", "0") << "\n";
                        count++;
                    }
                }
                if (count == 0) {
                    std::cout << "  (无持仓)\n";
                }
            }

        } catch (const std::exception& e) {
            std::cout << "❌ 异常: " << e.what() << "\n";
        }

        // ========== 测试5: get_positions() ==========
       /* print_section("5. get_positions() - 持仓信息");
        try {
            auto positions = api.get_positions();
            std::cout << "返回类型: " << (positions.is_array() ? "数组" : "对象") << "\n";
            std::cout << "持仓总数: " << positions.size() << "\n";

            std::cout << "\n有持仓的交易对:\n";
            int count = 0;
            for (const auto& pos : positions) {
                double amt = std::stod(pos.value("positionAmt", "0"));
                if (amt != 0 && count < 10) {
                    std::cout << "  " << pos.value("symbol", "")
                              << " [" << pos.value("positionSide", "BOTH") << "]: "
                              << amt << " @ " << pos.value("entryPrice", "0")
                              << " (PnL: " << pos.value("unrealizedProfit", "0") << ")\n";
                    count++;
                }
            }
            if (count == 0) {
                std::cout << "  (无持仓)\n";
            }

        } catch (const std::exception& e) {
            std::cout << "❌ 异常: " << e.what() << "\n";
        }*/

        print_section("测试完成");
        std::cout << "✅ 所有测试执行完毕\n";

    } catch (const std::exception& e) {
        std::cerr << "❌ 致命错误: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
