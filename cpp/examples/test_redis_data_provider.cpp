/**
 * @file test_redis_data_provider.cpp
 * @brief 测试 Redis 数据提供者模块
 *
 * 功能：
 * 1. 测试 Redis 连接
 * 2. 测试从 Redis 查询 K 线数据
 * 3. 测试 API 回退功能（OKX 和 Binance）
 * 4. 测试 K 线聚合功能
 *
 * 编译：
 *   cd build && cmake .. && make test_redis_data_provider
 *
 * 运行：
 *   ./test_redis_data_provider
 *
 * @author Sequence Team
 * @date 2026-01
 */

#include <iostream>
#include <iomanip>
#include <chrono>
#include <ctime>
#include <string>

#include "server/managers/redis_data_provider.h"

using namespace trading::server;

// 时间戳转可读字符串
std::string timestamp_to_string(int64_t ts_ms) {
    time_t ts_sec = ts_ms / 1000;
    struct tm* tm_info = localtime(&ts_sec);
    char buffer[32];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", tm_info);
    return std::string(buffer);
}

// 打印 K 线数据
void print_kline(const KlineBar& bar) {
    std::cout << "  " << timestamp_to_string(bar.timestamp)
              << " | O:" << std::fixed << std::setprecision(2) << bar.open
              << " H:" << bar.high
              << " L:" << bar.low
              << " C:" << bar.close
              << " V:" << std::setprecision(4) << bar.volume
              << std::endl;
}

// 打印分隔线
void print_separator(const std::string& title = "") {
    std::cout << "\n========================================" << std::endl;
    if (!title.empty()) {
        std::cout << "  " << title << std::endl;
        std::cout << "========================================" << std::endl;
    }
}

int main(int argc, char* argv[]) {
    print_separator("Redis 数据提供者测试");

    // 解析命令行参数
    std::string redis_host = "127.0.0.1";
    int redis_port = 6379;
    std::string redis_password = "";
    std::string okx_api_key = "";
    std::string okx_secret_key = "";
    std::string okx_passphrase = "";
    std::string binance_api_key = "";
    std::string binance_secret_key = "";

    // 从环境变量读取配置
    if (const char* env = std::getenv("REDIS_HOST")) redis_host = env;
    if (const char* env = std::getenv("REDIS_PORT")) redis_port = std::stoi(env);
    if (const char* env = std::getenv("REDIS_PASSWORD")) redis_password = env;
    if (const char* env = std::getenv("OKX_API_KEY")) okx_api_key = env;
    if (const char* env = std::getenv("OKX_SECRET_KEY")) okx_secret_key = env;
    if (const char* env = std::getenv("OKX_PASSPHRASE")) okx_passphrase = env;
    if (const char* env = std::getenv("BINANCE_API_KEY")) binance_api_key = env;
    if (const char* env = std::getenv("BINANCE_SECRET_KEY")) binance_secret_key = env;

    std::cout << "\n配置信息:" << std::endl;
    std::cout << "  Redis: " << redis_host << ":" << redis_port << std::endl;
    std::cout << "  OKX API: " << (okx_api_key.empty() ? "未配置" : "已配置") << std::endl;
    std::cout << "  Binance API: " << (binance_api_key.empty() ? "未配置" : "已配置") << std::endl;

    // 创建 Redis 数据提供者
    RedisDataProvider provider;

    // 配置
    RedisProviderConfig config;
    config.host = redis_host;
    config.port = redis_port;
    config.password = redis_password;
    config.enable_api_fallback = true;
    config.okx_api_key = okx_api_key;
    config.okx_secret_key = okx_secret_key;
    config.okx_passphrase = okx_passphrase;
    config.okx_testnet = false;
    config.binance_api_key = binance_api_key;
    config.binance_secret_key = binance_secret_key;
    config.binance_testnet = false;

    provider.set_config(config);

    // ==================== 测试 1: Redis 连接 ====================
    print_separator("测试 1: Redis 连接");

    if (!provider.connect()) {
        std::cerr << "Redis 连接失败!" << std::endl;
        return 1;
    }
    std::cout << "Redis 连接成功!" << std::endl;

    // ==================== 测试 2: 获取可用交易对 ====================
    print_separator("测试 2: 获取可用交易对");

    auto symbols = provider.get_available_symbols();
    std::cout << "Redis 中共有 " << symbols.size() << " 个交易对" << std::endl;

    if (!symbols.empty()) {
        std::cout << "前 10 个交易对:" << std::endl;
        for (size_t i = 0; i < std::min(symbols.size(), (size_t)10); i++) {
            std::cout << "  " << (i + 1) << ". " << symbols[i] << std::endl;
        }
    }

    // 按交易所分类
    auto okx_symbols = provider.get_available_symbols("okx");
    auto binance_symbols = provider.get_available_symbols("binance");
    std::cout << "\nOKX 交易对: " << okx_symbols.size() << " 个" << std::endl;
    std::cout << "Binance 交易对: " << binance_symbols.size() << " 个" << std::endl;

    // ==================== 测试 3: 查询 Redis K 线数据 ====================
    print_separator("测试 3: 查询 Redis K 线数据");

    // 选择一个测试交易对
    std::string test_symbol = "BTC-USDT-SWAP";
    std::string test_exchange = "okx";

    if (!okx_symbols.empty()) {
        test_symbol = okx_symbols[0];
    } else if (!binance_symbols.empty()) {
        test_symbol = binance_symbols[0];
        test_exchange = "binance";
    }

    std::cout << "测试交易对: " << test_exchange << ":" << test_symbol << std::endl;

    // 获取数据时间范围
    auto time_range = provider.get_data_time_range(test_symbol, test_exchange, "1m");
    if (time_range.first > 0) {
        std::cout << "数据时间范围: " << timestamp_to_string(time_range.first)
                  << " ~ " << timestamp_to_string(time_range.second) << std::endl;
    } else {
        std::cout << "Redis 中暂无该交易对的数据" << std::endl;
    }

    // 获取 K 线数量
    int64_t kline_count = provider.get_kline_count(test_symbol, test_exchange, "1m");
    std::cout << "1m K 线数量: " << kline_count << " 条" << std::endl;

    // 查询最近 10 根 K 线
    std::cout << "\n最近 10 根 1m K 线:" << std::endl;
    auto latest_klines = provider.get_latest_klines(test_symbol, test_exchange, "1m", 10);
    for (const auto& bar : latest_klines) {
        print_kline(bar);
    }

    // ==================== 测试 4: K 线聚合 ====================
    print_separator("测试 4: K 线聚合 (1m -> 5m)");

    if (kline_count >= 5) {
        // 获取最近 1 小时的数据进行聚合测试
        auto now = std::chrono::system_clock::now();
        auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();
        auto start_time = end_time - 60 * 60 * 1000;  // 1 小时前

        auto aggregated = provider.get_klines(test_symbol, test_exchange, "5m", start_time, end_time);
        std::cout << "聚合后的 5m K 线数量: " << aggregated.size() << " 条" << std::endl;

        if (!aggregated.empty()) {
            std::cout << "\n最近 5 根 5m K 线:" << std::endl;
            size_t start_idx = aggregated.size() > 5 ? aggregated.size() - 5 : 0;
            for (size_t i = start_idx; i < aggregated.size(); i++) {
                print_kline(aggregated[i]);
            }
        }
    } else {
        std::cout << "Redis 中数据不足，跳过聚合测试" << std::endl;
    }

    // ==================== 测试 5: API 回退功能 (OKX) ====================
    print_separator("测试 5: API 回退功能 (OKX)");

    if (!okx_api_key.empty()) {
        std::cout << "测试从 OKX API 拉取历史数据..." << std::endl;

        // 请求 7 天前的数据（可能超出 Redis 保存范围）
        auto now = std::chrono::system_clock::now();
        auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();
        auto start_time = end_time - 7 * 24 * 60 * 60 * 1000LL;  // 7 天前

        auto klines = provider.get_klines("BTC-USDT-SWAP", "okx", "1H", start_time, end_time);
        std::cout << "获取到 " << klines.size() << " 条 1H K 线" << std::endl;

        if (!klines.empty()) {
            std::cout << "\n前 5 根 K 线:" << std::endl;
            for (size_t i = 0; i < std::min(klines.size(), (size_t)5); i++) {
                print_kline(klines[i]);
            }
            std::cout << "\n后 5 根 K 线:" << std::endl;
            size_t start_idx = klines.size() > 5 ? klines.size() - 5 : 0;
            for (size_t i = start_idx; i < klines.size(); i++) {
                print_kline(klines[i]);
            }
        }
    } else {
        std::cout << "OKX API 未配置，跳过此测试" << std::endl;
        std::cout << "请设置环境变量: OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE" << std::endl;
    }

    // ==================== 测试 6: API 回退功能 (Binance) ====================
    print_separator("测试 6: API 回退功能 (Binance)");

    if (!binance_api_key.empty()) {
        std::cout << "测试从 Binance API 拉取历史数据..." << std::endl;

        // 请求 7 天前的数据
        auto now = std::chrono::system_clock::now();
        auto end_time = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();
        auto start_time = end_time - 7 * 24 * 60 * 60 * 1000LL;  // 7 天前

        auto klines = provider.get_klines("BTCUSDT", "binance", "1H", start_time, end_time);
        std::cout << "获取到 " << klines.size() << " 条 1H K 线" << std::endl;

        if (!klines.empty()) {
            std::cout << "\n前 5 根 K 线:" << std::endl;
            for (size_t i = 0; i < std::min(klines.size(), (size_t)5); i++) {
                print_kline(klines[i]);
            }
            std::cout << "\n后 5 根 K 线:" << std::endl;
            size_t start_idx = klines.size() > 5 ? klines.size() - 5 : 0;
            for (size_t i = start_idx; i < klines.size(); i++) {
                print_kline(klines[i]);
            }
        }
    } else {
        std::cout << "Binance API 未配置，跳过此测试" << std::endl;
        std::cout << "请设置环境变量: BINANCE_API_KEY, BINANCE_SECRET_KEY" << std::endl;
    }

    // ==================== 测试 7: 按天数查询 ====================
    print_separator("测试 7: 按天数查询");

    if (kline_count > 0) {
        std::cout << "查询最近 1 天的 1m K 线..." << std::endl;
        auto day_klines = provider.get_klines_by_days(test_symbol, test_exchange, "1m", 1);
        std::cout << "获取到 " << day_klines.size() << " 条 K 线" << std::endl;

        if (!day_klines.empty()) {
            std::cout << "时间范围: " << timestamp_to_string(day_klines.front().timestamp)
                      << " ~ " << timestamp_to_string(day_klines.back().timestamp) << std::endl;
        }
    }

    // ==================== 统计信息 ====================
    print_separator("统计信息");

    std::cout << "查询次数: " << provider.get_query_count() << std::endl;
    std::cout << "错误次数: " << provider.get_error_count() << std::endl;

    // 断开连接
    provider.disconnect();

    print_separator("测试完成");

    return 0;
}
