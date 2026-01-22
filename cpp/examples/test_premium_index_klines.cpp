/**
 * @file test_premium_index_klines.cpp
 * @brief 测试币安溢价指数K线接口
 *
 * 测试 GET /fapi/v1/premiumIndexKlines 接口
 */

#include "../adapters/binance/binance_rest_api.h"

#include <iostream>
#include <iomanip>
#include <chrono>
#include <ctime>

using namespace trading::binance;

// 格式化时间戳（毫秒）为可读格式
std::string format_timestamp(int64_t ts_ms) {
    time_t ts = ts_ms / 1000;
    struct tm* tm_info = localtime(&ts);
    char buffer[32];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", tm_info);
    return std::string(buffer);
}

int main() {
    std::cout << "======================================================================\n";
    std::cout << "  币安溢价指数K线接口测试 (C++)\n";
    std::cout << "  GET /fapi/v1/premiumIndexKlines\n";
    std::cout << "======================================================================\n";

    try {
        // 创建 REST API 客户端（U本位合约，主网）
        BinanceRestAPI api("", "", MarketType::FUTURES, false);

        // 测试交易对
        std::vector<std::string> test_symbols = {"BTCUSDT", "ETHUSDT", "SOLUSDT"};

        // 测试周期
        std::vector<std::string> test_intervals = {"1m", "5m", "15m", "1h"};

        // ==================== 1. 基础功能测试 ====================
        std::cout << "\n1. 基础功能测试\n";
        std::cout << "----------------------------------------------------------------------\n";

        for (const auto& symbol : test_symbols) {
            std::cout << "\n交易对: " << symbol << std::endl;

            try {
                // 获取最近10根1分钟K线
                auto klines = api.get_premium_index_klines(symbol, "1m", 0, 0, 10);

                if (klines.is_array() && !klines.empty()) {
                    std::cout << "  获取到 " << klines.size() << " 根K线" << std::endl;

                    // 显示最新一根
                    auto& latest = klines.back();
                    int64_t open_time = latest[0].get<int64_t>();
                    std::string open_price = latest[1].get<std::string>();
                    std::string high_price = latest[2].get<std::string>();
                    std::string low_price = latest[3].get<std::string>();
                    std::string close_price = latest[4].get<std::string>();

                    std::cout << "  最新K线:" << std::endl;
                    std::cout << "    时间: " << format_timestamp(open_time) << std::endl;
                    std::cout << "    开盘: " << open_price << std::endl;
                    std::cout << "    最高: " << high_price << std::endl;
                    std::cout << "    最低: " << low_price << std::endl;
                    std::cout << "    收盘: " << close_price << std::endl;
                } else {
                    std::cout << "  无数据" << std::endl;
                }
            } catch (const std::exception& e) {
                std::cout << "  错误: " << e.what() << std::endl;
            }
        }

        // ==================== 2. 不同周期测试 ====================
        std::cout << "\n\n2. 不同周期测试\n";
        std::cout << "----------------------------------------------------------------------\n";

        std::string symbol = "BTCUSDT";
        std::cout << "\n交易对: " << symbol << std::endl;

        for (const auto& interval : test_intervals) {
            try {
                auto klines = api.get_premium_index_klines(symbol, interval, 0, 0, 5);

                if (klines.is_array() && !klines.empty()) {
                    auto& latest = klines.back();
                    int64_t open_time = latest[0].get<int64_t>();
                    std::string close_price = latest[4].get<std::string>();

                    std::cout << "  [" << std::setw(4) << interval << "] 最新: "
                              << format_timestamp(open_time) << " | 溢价指数: "
                              << close_price << std::endl;
                } else {
                    std::cout << "  [" << std::setw(4) << interval << "] 无数据" << std::endl;
                }
            } catch (const std::exception& e) {
                std::cout << "  [" << std::setw(4) << interval << "] 错误: " << e.what() << std::endl;
            }
        }

        // ==================== 3. 时间范围查询测试 ====================
        std::cout << "\n\n3. 时间范围查询测试\n";
        std::cout << "----------------------------------------------------------------------\n";

        // 查询过去1小时的数据
        auto now = std::chrono::system_clock::now();
        auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()
        ).count();
        int64_t end_time = now_ms;
        int64_t start_time = end_time - 60 * 60 * 1000;  // 1小时前

        std::cout << "\n查询时间范围:" << std::endl;
        std::cout << "  开始: " << format_timestamp(start_time) << std::endl;
        std::cout << "  结束: " << format_timestamp(end_time) << std::endl;

        try {
            auto klines = api.get_premium_index_klines("BTCUSDT", "1m", start_time, end_time, 100);

            if (klines.is_array() && !klines.empty()) {
                std::cout << "\n获取到 " << klines.size() << " 根K线" << std::endl;

                // 显示前3根
                std::cout << "\n前3根K线:" << std::endl;
                for (size_t i = 0; i < std::min(size_t(3), klines.size()); ++i) {
                    auto& k = klines[i];
                    int64_t open_time = k[0].get<int64_t>();
                    std::string close_price = k[4].get<std::string>();
                    std::cout << "  " << (i + 1) << ". " << format_timestamp(open_time)
                              << " | 溢价: " << close_price << std::endl;
                }

                // 显示后3根
                std::cout << "\n后3根K线:" << std::endl;
                size_t start_idx = klines.size() > 3 ? klines.size() - 3 : 0;
                for (size_t i = start_idx; i < klines.size(); ++i) {
                    auto& k = klines[i];
                    int64_t open_time = k[0].get<int64_t>();
                    std::string close_price = k[4].get<std::string>();
                    std::cout << "  " << (i + 1) << ". " << format_timestamp(open_time)
                              << " | 溢价: " << close_price << std::endl;
                }

                // 统计溢价指数
                double sum = 0.0, max_val = -1e9, min_val = 1e9;
                for (const auto& k : klines) {
                    double val = std::stod(k[4].get<std::string>());
                    sum += val;
                    max_val = std::max(max_val, val);
                    min_val = std::min(min_val, val);
                }
                double avg = sum / klines.size();

                std::cout << "\n溢价指数统计:" << std::endl;
                std::cout << std::fixed << std::setprecision(8);
                std::cout << "  平均值: " << avg << " (" << std::setprecision(4) << (avg * 100) << "%)" << std::endl;
                std::cout << std::setprecision(8);
                std::cout << "  最大值: " << max_val << " (" << std::setprecision(4) << (max_val * 100) << "%)" << std::endl;
                std::cout << std::setprecision(8);
                std::cout << "  最小值: " << min_val << " (" << std::setprecision(4) << (min_val * 100) << "%)" << std::endl;
            } else {
                std::cout << "无数据" << std::endl;
            }
        } catch (const std::exception& e) {
            std::cout << "错误: " << e.what() << std::endl;
        }

        // ==================== 4. 数据格式验证 ====================
        std::cout << "\n\n4. 数据格式验证\n";
        std::cout << "----------------------------------------------------------------------\n";

        try {
            auto klines = api.get_premium_index_klines("BTCUSDT", "1m", 0, 0, 1);

            if (klines.is_array() && !klines.empty()) {
                auto& raw = klines[0];
                std::cout << "\n原始数据格式 (共 " << raw.size() << " 个字段):" << std::endl;
                std::cout << "  [0] 开盘时间: " << raw[0] << " (" << format_timestamp(raw[0].get<int64_t>()) << ")" << std::endl;
                std::cout << "  [1] 开盘价:   " << raw[1] << std::endl;
                std::cout << "  [2] 最高价:   " << raw[2] << std::endl;
                std::cout << "  [3] 最低价:   " << raw[3] << std::endl;
                std::cout << "  [4] 收盘价:   " << raw[4] << std::endl;
                std::cout << "  [5] 忽略:     " << raw[5] << std::endl;
                std::cout << "  [6] 收盘时间: " << raw[6] << " (" << format_timestamp(raw[6].get<int64_t>()) << ")" << std::endl;
                std::cout << "  [7] 忽略:     " << raw[7] << std::endl;
                std::cout << "  [8] 忽略:     " << raw[8] << std::endl;
                std::cout << "  [9] 忽略:     " << raw[9] << std::endl;
                std::cout << "  [10] 忽略:    " << raw[10] << std::endl;
                std::cout << "  [11] 忽略:    " << raw[11] << std::endl;
            }
        } catch (const std::exception& e) {
            std::cout << "错误: " << e.what() << std::endl;
        }

        std::cout << "\n======================================================================\n";
        std::cout << "  测试完成\n";
        std::cout << "======================================================================\n";

        return 0;

    } catch (const std::exception& e) {
        std::cerr << "\n❌ 异常: " << e.what() << std::endl;
        return 1;
    }
}
