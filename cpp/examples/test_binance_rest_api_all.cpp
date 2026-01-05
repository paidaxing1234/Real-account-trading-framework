/**
 * @file test_binance_rest_api_all.cpp
 * @brief Binance REST API 完整测试 - 测试所有接口
 *
 * 测试内容：
 * 1. 市场数据接口（无需认证）
 * 2. 账户接口（需要认证）
 * 3. 交易接口（需要认证）
 * 4. 合约设置接口（需要认证）
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
    return prefix + std::to_string(ms % 1000000000);
}

// 打印分隔线
void print_section(const std::string& title) {
    std::cout << "\n" << std::string(50, '=') << "\n";
    std::cout << "  " << title << "\n";
    std::cout << std::string(50, '=') << "\n";
}

// 打印JSON（格式化）
void print_json(const nlohmann::json& j, int indent = 2) {
    std::cout << j.dump(indent) << "\n";
}

// ==================== 测试函数 ====================

// 1. 测试连接
bool test_connectivity(BinanceRestAPI& api) {
    std::cout << "\n[测试] test_connectivity()\n";
    try {
        bool ok = api.test_connectivity();
        std::cout << "  结果: " << (ok ? "✅ 成功" : "❌ 失败") << "\n";
        return ok;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 2. 获取服务器时间
bool test_server_time(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_server_time()\n";
    try {
        int64_t ts = api.get_server_time();
        std::cout << "  服务器时间: " << ts << " ms\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 3. 获取交易规则
bool test_exchange_info(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_exchange_info(\"BTCUSDT\")\n";
    try {
        auto info = api.get_exchange_info("BTCUSDT");
        if (info.contains("symbols") && !info["symbols"].empty()) {
            auto& sym = info["symbols"][0];
            std::cout << "  交易对: " << sym.value("symbol", "") << "\n";
            std::cout << "  状态: " << sym.value("status", "") << "\n";
            std::cout << "  结果: ✅ 成功\n";
            return true;
        }
        std::cout << "  结果: ❌ 无数据\n";
        return false;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 4. 获取深度
bool test_depth(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_depth(\"BTCUSDT\", 5)\n";
    try {
        auto depth = api.get_depth("BTCUSDT", 5);
        std::cout << "  买一: " << depth["bids"][0][0] << " @ " << depth["bids"][0][1] << "\n";
        std::cout << "  卖一: " << depth["asks"][0][0] << " @ " << depth["asks"][0][1] << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 5. 获取最新成交
bool test_recent_trades(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_recent_trades(\"BTCUSDT\", 3)\n";
    try {
        auto trades = api.get_recent_trades("BTCUSDT", 3);
        std::cout << "  成交数量: " << trades.size() << "\n";
        if (!trades.empty()) {
            std::cout << "  最新成交: " << trades[0]["price"] << " @ " << trades[0]["qty"] << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 6. 获取K线
bool test_klines(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_klines(\"BTCUSDT\", \"1h\", limit=3)\n";
    try {
        auto klines = api.get_klines("BTCUSDT", "1h", 0, 0, 3);
        std::cout << "  K线数量: " << klines.size() << "\n";
        if (!klines.empty()) {
            auto& k = klines[0];
            std::cout << "  最新K线: O=" << k[1] << " H=" << k[2] << " L=" << k[3] << " C=" << k[4] << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 7. 获取24小时行情
bool test_ticker_24hr(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_ticker_24hr(\"BTCUSDT\")\n";
    try {
        auto ticker = api.get_ticker_24hr("BTCUSDT");
        std::cout << "  交易对: " << ticker.value("symbol", "") << "\n";
        std::cout << "  最新价: " << ticker.value("lastPrice", "") << "\n";
        std::cout << "  24h涨跌: " << ticker.value("priceChangePercent", "") << "%\n";
        std::cout << "  24h成交量: " << ticker.value("volume", "") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 8. 获取最新价格
bool test_ticker_price(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_ticker_price(\"BTCUSDT\")\n";
    try {
        auto ticker = api.get_ticker_price("BTCUSDT");
        std::cout << "  交易对: " << ticker.value("symbol", "") << "\n";
        std::cout << "  价格: " << ticker.value("price", "") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 9. 获取资金费率（仅合约）
bool test_funding_rate(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_funding_rate(\"BTCUSDT\")\n";
    try {
        auto rates = api.get_funding_rate("BTCUSDT", 3);
        std::cout << "  记录数: " << rates.size() << "\n";
        if (!rates.empty()) {
            std::cout << "  最新费率: " << rates[0].value("fundingRate", "") << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 10. 获取账户余额
bool test_account_balance(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_account_balance()\n";
    try {
        auto balance = api.get_account_balance();
        if (balance.is_array()) {
            // 合约返回数组
            std::cout << "  资产数量: " << balance.size() << "\n";
            for (const auto& b : balance) {
                double bal = std::stod(b.value("balance", "0"));
                if (bal > 0) {
                    std::cout << "  " << b.value("asset", "") << ": " << bal << "\n";
                }
            }
        } else if (balance.contains("balances")) {
            // 现货返回对象
            std::cout << "  资产数量: " << balance["balances"].size() << "\n";
            for (const auto& b : balance["balances"]) {
                double free = std::stod(b.value("free", "0"));
                if (free > 0) {
                    std::cout << "  " << b.value("asset", "") << ": " << free << "\n";
                }
            }
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 11. 获取账户信息
bool test_account_info(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_account_info()\n";
    try {
        auto info = api.get_account_info();
        if (info.contains("totalWalletBalance")) {
            // 合约
            std::cout << "  总钱包余额: " << info.value("totalWalletBalance", "") << "\n";
            std::cout << "  可用余额: " << info.value("availableBalance", "") << "\n";
        } else if (info.contains("balances")) {
            // 现货
            std::cout << "  账户类型: " << info.value("accountType", "") << "\n";
            std::cout << "  资产数量: " << info["balances"].size() << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 12. 获取持仓（仅合约）
bool test_positions(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_positions()\n";
    try {
        auto positions = api.get_positions();
        std::cout << "  持仓数量: " << positions.size() << "\n";
        int count = 0;
        for (const auto& p : positions) {
            double amt = std::stod(p.value("positionAmt", "0"));
            if (amt != 0 && count < 3) {
                std::cout << "  " << p.value("symbol", "") << ": " << amt
                          << " (未实现盈亏: " << p.value("unRealizedProfit", "") << ")\n";
                count++;
            }
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 13. 获取持仓模式（仅合约）
bool test_position_mode(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_position_mode()\n";
    try {
        auto mode = api.get_position_mode();
        bool dual = mode.value("dualSidePosition", false);
        std::cout << "  持仓模式: " << (dual ? "双向持仓" : "单向持仓") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 14. 获取当前挂单
bool test_open_orders(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_open_orders(\"BTCUSDT\")\n";
    try {
        auto orders = api.get_open_orders("BTCUSDT");
        std::cout << "  挂单数量: " << orders.size() << "\n";
        for (const auto& o : orders) {
            std::cout << "  订单ID: " << o.value("orderId", 0)
                      << " " << o.value("side", "")
                      << " " << o.value("price", "")
                      << " @ " << o.value("origQty", "") << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 15. 获取所有订单
bool test_all_orders(BinanceRestAPI& api) {
    std::cout << "\n[测试] get_all_orders(\"BTCUSDT\", limit=5)\n";
    try {
        auto orders = api.get_all_orders("BTCUSDT", 0, 0, 5);
        std::cout << "  订单数量: " << orders.size() << "\n";
        for (const auto& o : orders) {
            std::cout << "  " << o.value("orderId", 0)
                      << " " << o.value("side", "")
                      << " " << o.value("status", "")
                      << " " << o.value("price", "") << "\n";
        }
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 16. 下单测试
bool test_place_order(BinanceRestAPI& api, int64_t& order_id) {
    std::cout << "\n[测试] place_order() - 限价单\n";
    try {
        // 获取当前价格
        auto ticker = api.get_ticker_price("BTCUSDT");
        double last_price = std::stod(ticker.value("price", "0"));

        // 远离市价下单（不会成交），价格取整到0.1精度
        double order_price = std::floor(last_price * 0.5 / 0.1) * 0.1;
        std::string qty = "0.003";
        std::string cid = gen_client_order_id("test");

        // 格式化价格字符串（1位小数）
        std::ostringstream price_ss;
        price_ss << std::fixed << std::setprecision(1) << order_price;

        std::cout << "  交易对: BTCUSDT\n";
        std::cout << "  方向: BUY\n";
        std::cout << "  价格: " << price_ss.str() << "\n";
        std::cout << "  数量: " << qty << "\n";
        std::cout << "  客户订单ID: " << cid << "\n";

        auto resp = api.place_order(
            "BTCUSDT",
            OrderSide::BUY,
            OrderType::LIMIT,
            qty,
            price_ss.str(),
            TimeInForce::GTC,
            PositionSide::LONG,  // 双向持仓模式需要指定LONG/SHORT
            cid
        );

        order_id = resp.value("orderId", (int64_t)0);
        std::cout << "  订单ID: " << order_id << "\n";
        std::cout << "  状态: " << resp.value("status", "") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 17. 查询订单
bool test_get_order(BinanceRestAPI& api, int64_t order_id) {
    std::cout << "\n[测试] get_order(\"BTCUSDT\", " << order_id << ")\n";
    try {
        auto order = api.get_order("BTCUSDT", order_id);
        std::cout << "  订单ID: " << order.value("orderId", 0) << "\n";
        std::cout << "  状态: " << order.value("status", "") << "\n";
        std::cout << "  方向: " << order.value("side", "") << "\n";
        std::cout << "  价格: " << order.value("price", "") << "\n";
        std::cout << "  数量: " << order.value("origQty", "") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 18. 撤销订单
bool test_cancel_order(BinanceRestAPI& api, int64_t order_id) {
    std::cout << "\n[测试] cancel_order(\"BTCUSDT\", " << order_id << ")\n";
    try {
        auto resp = api.cancel_order("BTCUSDT", order_id);
        std::cout << "  订单ID: " << resp.value("orderId", 0) << "\n";
        std::cout << "  状态: " << resp.value("status", "") << "\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 19. 修改杠杆（仅合约）
bool test_change_leverage(BinanceRestAPI& api) {
    std::cout << "\n[测试] change_leverage(\"BTCUSDT\", 10)\n";
    try {
        auto resp = api.change_leverage("BTCUSDT", 10);
        std::cout << "  交易对: " << resp.value("symbol", "") << "\n";
        std::cout << "  杠杆: " << resp.value("leverage", 0) << "x\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// 20. 创建listenKey
bool test_create_listen_key(BinanceRestAPI& api) {
    std::cout << "\n[测试] create_listen_key()\n";
    try {
        auto resp = api.create_listen_key();
        std::string key = resp.value("listenKey", "");
        std::cout << "  listenKey: " << key.substr(0, 20) << "...\n";
        std::cout << "  结果: ✅ 成功\n";
        return true;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        return false;
    }
}

// ==================== 主函数 ====================

int main(int argc, char* argv[]) {
    std::cout << "╔══════════════════════════════════════════════════╗\n";
    std::cout << "║     Binance REST API 完整测试                    ║\n";
    std::cout << "╚══════════════════════════════════════════════════╝\n";

    // 代理设置
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY") &&
        !std::getenv("all_proxy") && !std::getenv("ALL_PROXY")) {
        setenv("https_proxy", DEFAULT_PROXY, 1);
        std::cout << "\n[代理] 已设置: " << DEFAULT_PROXY << "\n";
    }

    // API密钥（从环境变量或命令行参数获取）
    std::string api_key = std::getenv("BINANCE_API_KEY") ? std::getenv("BINANCE_API_KEY") : "";
    std::string secret_key = std::getenv("BINANCE_SECRET_KEY") ? std::getenv("BINANCE_SECRET_KEY") : "";

    // 市场类型（默认U本位合约测试网）
    MarketType market_type = MarketType::FUTURES;
    bool is_testnet = true;

    // 解析命令行参数
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--spot") {
            market_type = MarketType::SPOT;
        } else if (arg == "--futures") {
            market_type = MarketType::FUTURES;
        } else if (arg == "--mainnet") {
            is_testnet = false;
        } else if (arg == "--testnet") {
            is_testnet = true;
        } else if (arg.find("--key=") == 0) {
            api_key = arg.substr(6);
        } else if (arg.find("--secret=") == 0) {
            secret_key = arg.substr(9);
        }
    }

    std::cout << "\n配置信息:\n";
    std::cout << "  市场类型: " << (market_type == MarketType::SPOT ? "现货" : "U本位合约") << "\n";
    std::cout << "  网络: " << (is_testnet ? "测试网" : "主网") << "\n";
    std::cout << "  API Key: " << (api_key.empty() ? "未设置" : api_key.substr(0, 8) + "...") << "\n";

    // 创建API客户端
    BinanceRestAPI api(api_key, secret_key, market_type, is_testnet);

    int passed = 0, failed = 0;

    // ==================== 公开接口测试（无需认证） ====================
    print_section("公开接口测试（无需认证）");

    if (test_connectivity(api)) passed++; else failed++;
    if (test_server_time(api)) passed++; else failed++;
    if (test_exchange_info(api)) passed++; else failed++;
    if (test_depth(api)) passed++; else failed++;
    if (test_recent_trades(api)) passed++; else failed++;
    if (test_klines(api)) passed++; else failed++;
    if (test_ticker_24hr(api)) passed++; else failed++;
    if (test_ticker_price(api)) passed++; else failed++;

    if (market_type != MarketType::SPOT) {
        if (test_funding_rate(api)) passed++; else failed++;
    }

    // ==================== 私有接口测试（需要认证） ====================
    if (!api_key.empty() && !secret_key.empty()) {
        print_section("私有接口测试（需要认证）");

        // 账户接口
        if (test_account_balance(api)) passed++; else failed++;
        if (test_account_info(api)) passed++; else failed++;
        if (test_open_orders(api)) passed++; else failed++;
        if (test_all_orders(api)) passed++; else failed++;
        if (test_create_listen_key(api)) passed++; else failed++;

        // 合约专用接口
        if (market_type != MarketType::SPOT) {
            if (test_positions(api)) passed++; else failed++;
            if (test_position_mode(api)) passed++; else failed++;
            if (test_change_leverage(api)) passed++; else failed++;
        }

        // 交易测试（可选）
        bool do_trade = std::getenv("BINANCE_DO_TRADE") != nullptr;
        if (do_trade) {
            print_section("交易接口测试");

            int64_t order_id = 0;
            if (test_place_order(api, order_id)) {
                passed++;

                std::this_thread::sleep_for(std::chrono::seconds(1));

                if (test_get_order(api, order_id)) passed++; else failed++;
                if (test_cancel_order(api, order_id)) passed++; else failed++;
            } else {
                failed++;
            }
        } else {
            std::cout << "\n[提示] 设置 BINANCE_DO_TRADE=1 启用交易测试\n";
        }
    } else {
        std::cout << "\n[提示] 设置 BINANCE_API_KEY 和 BINANCE_SECRET_KEY 启用私有接口测试\n";
    }

    // ==================== 测试结果 ====================
    print_section("测试结果");
    std::cout << "  ✅ 通过: " << passed << "\n";
    std::cout << "  ❌ 失败: " << failed << "\n";
    std::cout << "  总计: " << (passed + failed) << "\n";

    return failed > 0 ? 1 : 0;
}
