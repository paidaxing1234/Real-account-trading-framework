/**
 * @file test_binance_login_simple.cpp
 * @brief Binance API 登录测试 - 最简版本
 * 
 * 测试内容：
 * 1. 网络连接测试（无需认证）
 * 2. API Key 验证（需要认证）
 * 3. 账户余额查询（确认登录成功）
 * 
 * 使用方法：
 *   1. 修改下面的 API_KEY 和 SECRET_KEY
 *   2. 编译：make test_binance_login_simple
 *   3. 运行：./build/test_binance_login_simple
 * 
 * 测试网申请：https://testnet.binancefuture.com
 */

#include "../adapters/binance/binance_rest_api.h"
#include <iostream>
#include <iomanip>

using namespace trading::binance;

// ==================== 配置区域（修改这里） ====================

// 方法1：直接填入（测试用）
const std::string API_KEY = "";      // 填入你的测试网 API Key
const std::string SECRET_KEY = "";   // 填入你的测试网 Secret Key

// 方法2：使用环境变量（推荐）
// export BINANCE_API_KEY="xxx"
// export BINANCE_SECRET_KEY="xxx"

// 网络配置
const bool IS_TESTNET = true;                    // true=测试网, false=主网
const MarketType MARKET_TYPE = MarketType::FUTURES;  // FUTURES=U本位合约, SPOT=现货

// 代理配置（如果需要）
const char* PROXY = "http://127.0.0.1:7890";

// ==============================================================

int main() {
    std::cout << "╔══════════════════════════════════════════════════╗\n";
    std::cout << "║     Binance API 登录测试 (简易版)                ║\n";
    std::cout << "╚══════════════════════════════════════════════════╝\n\n";

    // 获取 API Key（优先使用环境变量）
    std::string api_key = API_KEY;
    std::string secret_key = SECRET_KEY;
    
    if (api_key.empty() && std::getenv("BINANCE_API_KEY")) {
        api_key = std::getenv("BINANCE_API_KEY");
    }
    if (secret_key.empty() && std::getenv("BINANCE_SECRET_KEY")) {
        secret_key = std::getenv("BINANCE_SECRET_KEY");
    }

    // 设置代理（如果未设置）
    if (!std::getenv("https_proxy") && !std::getenv("HTTPS_PROXY")) {
        setenv("https_proxy", PROXY, 1);
        std::cout << "[代理] 已设置: " << PROXY << "\n";
    }

    // 显示配置
    std::cout << "\n[配置信息]\n";
    std::cout << "  市场类型: " << (MARKET_TYPE == MarketType::FUTURES ? "U本位合约" : "现货") << "\n";
    std::cout << "  网络模式: " << (IS_TESTNET ? "测试网 ✓" : "主网 ⚠️") << "\n";
    std::cout << "  API Key:  " << (api_key.empty() ? "❌ 未设置" : api_key.substr(0, 12) + "...") << "\n";

    if (IS_TESTNET && MARKET_TYPE == MarketType::FUTURES) {
        std::cout << "  REST URL: https://testnet.binancefuture.com\n";
    }

    // 创建 API 客户端
    BinanceRestAPI api(api_key, secret_key, MARKET_TYPE, IS_TESTNET);

    int passed = 0, failed = 0;

    // ==================== 测试 1: 网络连接 ====================
    std::cout << "\n" << std::string(50, '─') << "\n";
    std::cout << "[测试 1] 网络连接测试（无需认证）\n";
    std::cout << std::string(50, '─') << "\n";

    try {
        bool ping_ok = api.test_connectivity();
        if (ping_ok) {
            std::cout << "  ✅ Ping 成功 - 网络连接正常\n";
            passed++;
        } else {
            std::cout << "  ❌ Ping 失败 - 检查网络/代理\n";
            failed++;
        }
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        failed++;
    }

    // ==================== 测试 2: 服务器时间 ====================
    std::cout << "\n" << std::string(50, '─') << "\n";
    std::cout << "[测试 2] 获取服务器时间（无需认证）\n";
    std::cout << std::string(50, '─') << "\n";

    try {
        int64_t server_time = api.get_server_time();
        std::cout << "  ✅ 服务器时间: " << server_time << " ms\n";
        
        // 计算时间差
        auto now = std::chrono::system_clock::now();
        auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()).count();
        int64_t diff = now_ms - server_time;
        std::cout << "  ✅ 本地时间差: " << diff << " ms ";
        if (std::abs(diff) < 1000) {
            std::cout << "(正常)\n";
        } else if (std::abs(diff) < 5000) {
            std::cout << "(可接受)\n";
        } else {
            std::cout << "(⚠️ 偏差较大，可能影响签名)\n";
        }
        passed++;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        failed++;
    }

    // ==================== 测试 3: 市场数据 ====================
    std::cout << "\n" << std::string(50, '─') << "\n";
    std::cout << "[测试 3] 获取 BTCUSDT 价格（无需认证）\n";
    std::cout << std::string(50, '─') << "\n";

    try {
        auto ticker = api.get_ticker_price("BTCUSDT");
        std::string price = ticker.value("price", "0");
        std::cout << "  ✅ BTCUSDT 价格: $" << price << "\n";
        passed++;
    } catch (const std::exception& e) {
        std::cout << "  ❌ 异常: " << e.what() << "\n";
        failed++;
    }

    // ==================== 需要认证的测试 ====================
    if (api_key.empty() || secret_key.empty()) {
        std::cout << "\n" << std::string(50, '═') << "\n";
        std::cout << "⚠️  API Key 未设置，跳过认证测试\n";
        std::cout << std::string(50, '═') << "\n";
        std::cout << "\n设置方法：\n";
        std::cout << "  1. 直接修改代码中的 API_KEY 和 SECRET_KEY\n";
        std::cout << "  2. 或设置环境变量：\n";
        std::cout << "     export BINANCE_API_KEY=\"你的API_KEY\"\n";
        std::cout << "     export BINANCE_SECRET_KEY=\"你的SECRET_KEY\"\n";
        std::cout << "\n测试网申请：https://testnet.binancefuture.com\n";
    } else {
        // ==================== 测试 4: 账户余额 ====================
        std::cout << "\n" << std::string(50, '─') << "\n";
        std::cout << "[测试 4] 获取账户余额（需要认证）🔐\n";
        std::cout << std::string(50, '─') << "\n";

        try {
            auto balance = api.get_account_balance();
            
            std::cout << "  ✅ API 认证成功！\n\n";
            
            if (balance.is_array()) {
                // 合约返回数组格式
                std::cout << "  资产列表:\n";
                int count = 0;
                for (const auto& b : balance) {
                    double bal = std::stod(b.value("balance", "0"));
                    double available = std::stod(b.value("availableBalance", "0"));
                    if (bal > 0 || available > 0) {
                        std::cout << "    " << b.value("asset", "") 
                                  << ": 余额=" << std::fixed << std::setprecision(4) << bal
                                  << ", 可用=" << available << "\n";
                        count++;
                    }
                }
                if (count == 0) {
                    std::cout << "    (无余额)\n";
                }
            } else if (balance.contains("balances")) {
                // 现货返回对象格式
                std::cout << "  资产列表:\n";
                for (const auto& b : balance["balances"]) {
                    double free = std::stod(b.value("free", "0"));
                    double locked = std::stod(b.value("locked", "0"));
                    if (free > 0 || locked > 0) {
                        std::cout << "    " << b.value("asset", "")
                                  << ": 可用=" << free << ", 冻结=" << locked << "\n";
                    }
                }
            }
            passed++;
        } catch (const std::exception& e) {
            std::cout << "  ❌ 认证失败: " << e.what() << "\n";
            std::cout << "\n  常见错误:\n";
            std::cout << "    -2015: API Key 无效或权限不足\n";
            std::cout << "    -1021: 时间戳差异过大\n";
            std::cout << "    -1022: 签名无效\n";
            failed++;
        }

        // ==================== 测试 5: 持仓模式 ====================
        if (MARKET_TYPE == MarketType::FUTURES) {
            std::cout << "\n" << std::string(50, '─') << "\n";
            std::cout << "[测试 5] 获取持仓模式（需要认证）🔐\n";
            std::cout << std::string(50, '─') << "\n";

            try {
                auto mode = api.get_position_mode();
                bool dual = mode.value("dualSidePosition", false);
                std::cout << "  ✅ 持仓模式: " << (dual ? "双向持仓" : "单向持仓") << "\n";
                passed++;
            } catch (const std::exception& e) {
                std::cout << "  ❌ 异常: " << e.what() << "\n";
                failed++;
            }
        }

        // ==================== 测试 6: 创建 listenKey ====================
        std::cout << "\n" << std::string(50, '─') << "\n";
        std::cout << "[测试 6] 创建 listenKey（需要认证）🔐\n";
        std::cout << std::string(50, '─') << "\n";

        try {
            auto resp = api.create_listen_key();
            std::string key = resp.value("listenKey", "");
            if (!key.empty()) {
                std::cout << "  ✅ listenKey: " << key.substr(0, 20) << "...\n";
                std::cout << "  ✅ WebSocket 用户数据流可用\n";
                passed++;
            } else {
                std::cout << "  ❌ 未获取到 listenKey\n";
                failed++;
            }
        } catch (const std::exception& e) {
            std::cout << "  ❌ 异常: " << e.what() << "\n";
            failed++;
        }
    }

    // ==================== 测试结果汇总 ====================
    std::cout << "\n" << std::string(50, '═') << "\n";
    std::cout << "  测试结果汇总\n";
    std::cout << std::string(50, '═') << "\n";
    std::cout << "  ✅ 通过: " << passed << "\n";
    std::cout << "  ❌ 失败: " << failed << "\n";
    
    if (failed == 0 && passed > 3) {
        std::cout << "\n  🎉 API 登录验证成功！可以进行交易操作。\n";
    } else if (passed >= 3 && api_key.empty()) {
        std::cout << "\n  ⚠️  网络正常，但未配置 API Key。\n";
    } else {
        std::cout << "\n  ⚠️  存在失败项，请检查配置。\n";
    }
    std::cout << std::string(50, '═') << "\n";

    return failed > 0 ? 1 : 0;
}

