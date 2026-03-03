/**
 * @file kline_8h_monitor.cpp
 * @brief 8小时K线聚合完成时间监控工具
 *
 * 功能：
 * - 连接Redis，扫描所有OKX和Binance USDT合约的8h K线key
 * - 使用Pipeline批量查询最新8h K线时间戳（最快方式）
 * - 检测新的8h K线出现，记录每个币种的完成时间
 * - 统计：第一根新8h K线完成时间、最后一根完成时间、总耗时
 *
 * 编译：
 *   cd cpp/tools && make kline_8h_monitor
 *
 * 运行：
 *   ./kline_8h_monitor [--poll-ms 200] [--timeout 600]
 */

#include <iostream>
#include <string>
#include <map>
#include <set>
#include <vector>
#include <atomic>
#include <chrono>
#include <csignal>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <thread>
#include <cstring>
#include <cstdlib>

#include <hiredis/hiredis.h>

using namespace std::chrono;

// ============================================================
// 全局控制
// ============================================================

std::atomic<bool> g_running{true};

void signal_handler(int) {
    g_running.store(false);
}

// ============================================================
// 配置
// ============================================================

struct MonitorConfig {
    std::string redis_host = "127.0.0.1";
    int redis_port = 6379;
    int poll_interval_ms = 200;   // 轮询间隔（毫秒）
    int timeout_seconds = 600;    // 超时时间（秒）
};

// ============================================================
// 工具函数
// ============================================================

std::string format_wall_time(const system_clock::time_point& tp) {
    auto t = system_clock::to_time_t(tp);
    std::tm tm = *std::localtime(&t);
    auto ms = duration_cast<milliseconds>(tp.time_since_epoch()) % 1000;
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%d %H:%M:%S") << "." << std::setw(3) << std::setfill('0') << ms.count();
    return oss.str();
}

std::string format_time_short(const system_clock::time_point& tp) {
    auto t = system_clock::to_time_t(tp);
    std::tm tm = *std::localtime(&t);
    auto ms = duration_cast<milliseconds>(tp.time_since_epoch()) % 1000;
    std::ostringstream oss;
    oss << std::put_time(&tm, "%H:%M:%S") << "." << std::setw(3) << std::setfill('0') << ms.count();
    return oss.str();
}

std::string format_kline_ts(int64_t ts_ms) {
    time_t t = ts_ms / 1000;
    std::tm tm = *std::localtime(&t);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%d %H:%M");
    return oss.str();
}

std::string format_duration_ms(int64_t ms) {
    if (ms < 1000) {
        return std::to_string(ms) + " ms";
    } else if (ms < 60000) {
        std::ostringstream oss;
        oss << std::fixed << std::setprecision(2) << (ms / 1000.0) << " 秒";
        return oss.str();
    } else {
        int64_t minutes = ms / 60000;
        int64_t secs = (ms % 60000) / 1000;
        std::ostringstream oss;
        oss << minutes << " 分 " << secs << " 秒";
        return oss.str();
    }
}

// 从Redis key中提取exchange
std::string extract_exchange(const std::string& key) {
    // key: kline:exchange:symbol:8h
    size_t p1 = key.find(':');
    if (p1 == std::string::npos) return "";
    size_t p2 = key.find(':', p1 + 1);
    if (p2 == std::string::npos) return "";
    return key.substr(p1 + 1, p2 - p1 - 1);
}

// 从Redis key中提取symbol
std::string extract_symbol(const std::string& key) {
    size_t p1 = key.find(':');
    if (p1 == std::string::npos) return "";
    size_t p2 = key.find(':', p1 + 1);
    if (p2 == std::string::npos) return "";
    size_t p3 = key.find(':', p2 + 1);
    if (p3 == std::string::npos) return "";
    return key.substr(p2 + 1, p3 - p2 - 1);
}

// 判断是否为USDT合约
bool is_usdt_contract(const std::string& exchange, const std::string& symbol) {
    if (exchange == "okx") {
        return symbol.find("-USDT-SWAP") != std::string::npos;
    } else if (exchange == "binance") {
        return symbol.length() > 4 && symbol.substr(symbol.length() - 4) == "USDT";
    }
    return false;
}

// 计算下一个8h边界时间戳（UTC: 00:00, 08:00, 16:00）
int64_t next_8h_boundary_ms() {
    auto now = system_clock::now();
    auto now_ms = duration_cast<milliseconds>(now.time_since_epoch()).count();

    // 8小时 = 28800000 毫秒
    const int64_t period_ms = 8LL * 3600 * 1000;

    // 对齐到8h边界
    int64_t current_boundary = (now_ms / period_ms) * period_ms;
    int64_t next_boundary = current_boundary + period_ms;

    return next_boundary;
}

int64_t current_8h_boundary_ms() {
    auto now = system_clock::now();
    auto now_ms = duration_cast<milliseconds>(now.time_since_epoch()).count();
    const int64_t period_ms = 8LL * 3600 * 1000;
    return (now_ms / period_ms) * period_ms;
}

// ============================================================
// 符号完成记录
// ============================================================

struct SymbolCompletion {
    std::string exchange;
    std::string symbol;
    std::string key;                         // Redis key
    int64_t baseline_ts;                     // 监控开始时的最新8h时间戳
    int64_t new_ts;                          // 新的8h时间戳
    system_clock::time_point completion_time; // 检测到新K线的时刻
    bool completed;                          // 是否已检测到新K线
};

// ============================================================
// 主监控器
// ============================================================

class Kline8hMonitor {
public:
    explicit Kline8hMonitor(const MonitorConfig& config) : config_(config), context_(nullptr) {}

    ~Kline8hMonitor() {
        if (context_) redisFree(context_);
    }

    bool init() {
        // 连接Redis
        context_ = redisConnect(config_.redis_host.c_str(), config_.redis_port);
        if (!context_ || context_->err) {
            std::cerr << "[错误] Redis连接失败";
            if (context_) std::cerr << ": " << context_->errstr;
            std::cerr << std::endl;
            return false;
        }
        std::cout << "[Redis] 已连接 " << config_.redis_host << ":" << config_.redis_port << std::endl;

        // 扫描所有8h key
        if (!scan_8h_keys()) {
            return false;
        }

        // 获取基线时间戳
        if (!fetch_baseline()) {
            return false;
        }

        return true;
    }

    void run() {
        auto expected_ts = current_8h_boundary_ms();
        auto next_ts = next_8h_boundary_ms();

        std::cout << "\n[监控] 当前8h边界: " << format_kline_ts(expected_ts) << std::endl;
        std::cout << "[监控] 下一个8h边界: " << format_kline_ts(next_ts) << std::endl;
        std::cout << "[监控] 轮询间隔: " << config_.poll_interval_ms << " ms" << std::endl;
        std::cout << "[监控] 超时时间: " << config_.timeout_seconds << " 秒" << std::endl;
        std::cout << "\n[监控] 开始监控，等待新的8h K线出现..." << std::endl;
        std::cout << "  按 Ctrl+C 停止\n" << std::endl;

        auto start_time = steady_clock::now();
        system_clock::time_point first_completion_wall;
        system_clock::time_point last_completion_wall;
        steady_clock::time_point first_completion_steady;
        steady_clock::time_point last_completion_steady;
        bool has_first = false;
        int completed_count = 0;
        int total_symbols = static_cast<int>(symbols_.size());
        int last_printed_count = 0;

        while (g_running.load()) {
            // 超时检查
            auto elapsed = duration_cast<seconds>(steady_clock::now() - start_time).count();
            if (elapsed >= config_.timeout_seconds) {
                std::cout << "\n[超时] 已等待 " << elapsed << " 秒，停止监控" << std::endl;
                break;
            }

            // Pipeline批量查询所有key的最新时间戳
            poll_new_klines();

            // 检查新完成的
            auto now_wall = system_clock::now();
            auto now_steady = steady_clock::now();

            for (auto& sym : symbols_) {
                if (sym.completed) continue;

                if (sym.new_ts > sym.baseline_ts) {
                    sym.completed = true;
                    sym.completion_time = now_wall;
                    completed_count++;

                    if (!has_first) {
                        has_first = true;
                        first_completion_wall = now_wall;
                        first_completion_steady = now_steady;

                        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
                        std::cout << "★ 第一根新8h K线出现!" << std::endl;
                        std::cout << "  币种: " << sym.exchange << ":" << sym.symbol << std::endl;
                        std::cout << "  新K线时间戳: " << format_kline_ts(sym.new_ts) << std::endl;
                        std::cout << "  检测时间: " << format_wall_time(now_wall) << std::endl;
                        std::cout << "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" << std::endl;
                    }

                    last_completion_wall = now_wall;
                    last_completion_steady = now_steady;
                }
            }

            // 进度打印（每增加一定数量或定期打印）
            if (has_first && completed_count != last_printed_count) {
                if (completed_count - last_printed_count >= 10 || completed_count == total_symbols) {
                    auto spread_ms = duration_cast<milliseconds>(now_steady - first_completion_steady).count();
                    std::cout << "[进度] " << completed_count << "/" << total_symbols
                              << " 个币种完成 (" << (completed_count * 100 / total_symbols) << "%)"
                              << " | 已用时: " << format_duration_ms(spread_ms)
                              << " | " << format_time_short(now_wall) << std::endl;
                    last_printed_count = completed_count;
                }
            }

            // 全部完成
            if (completed_count >= total_symbols) {
                std::cout << "\n[完成] 所有币种的8h K线均已更新!" << std::endl;
                break;
            }

            std::this_thread::sleep_for(milliseconds(config_.poll_interval_ms));
        }

        // 打印最终报告
        print_report(has_first, first_completion_wall, first_completion_steady,
                     last_completion_wall, last_completion_steady,
                     completed_count, total_symbols);
    }

private:
    bool scan_8h_keys() {
        // KEYS kline:*:8h 获取所有8h key
        redisReply* reply = (redisReply*)redisCommand(context_, "KEYS kline:*:8h");
        if (!reply || reply->type != REDIS_REPLY_ARRAY) {
            std::cerr << "[错误] 无法获取8h K线key" << std::endl;
            if (reply) freeReplyObject(reply);
            return false;
        }

        for (size_t i = 0; i < reply->elements; i++) {
            std::string key = reply->element[i]->str;
            std::string exchange = extract_exchange(key);
            std::string symbol = extract_symbol(key);

            if (exchange.empty() || symbol.empty()) continue;

            // 只处理USDT合约
            if (!is_usdt_contract(exchange, symbol)) continue;

            SymbolCompletion sc;
            sc.exchange = exchange;
            sc.symbol = symbol;
            sc.key = key;
            sc.baseline_ts = 0;
            sc.new_ts = 0;
            sc.completed = false;
            symbols_.push_back(std::move(sc));
        }
        freeReplyObject(reply);

        if (symbols_.empty()) {
            std::cerr << "[错误] Redis中没有找到任何USDT合约的8h K线数据" << std::endl;
            return false;
        }

        // 排序：Binance在前，OKX在后，字母排序
        std::sort(symbols_.begin(), symbols_.end(),
            [](const SymbolCompletion& a, const SymbolCompletion& b) {
                if (a.exchange != b.exchange) return a.exchange < b.exchange;
                return a.symbol < b.symbol;
            });

        // 统计
        int binance_count = 0, okx_count = 0;
        for (const auto& s : symbols_) {
            if (s.exchange == "binance") binance_count++;
            else if (s.exchange == "okx") okx_count++;
        }

        std::cout << "\n[扫描] 找到 " << symbols_.size() << " 个USDT合约8h K线" << std::endl;
        std::cout << "  Binance: " << binance_count << " 个" << std::endl;
        std::cout << "  OKX: " << okx_count << " 个" << std::endl;

        return true;
    }

    bool fetch_baseline() {
        // 使用Pipeline批量获取所有key的最新时间戳
        for (const auto& sym : symbols_) {
            redisAppendCommand(context_, "ZREVRANGE %s 0 0 WITHSCORES", sym.key.c_str());
        }

        int valid_count = 0;
        for (auto& sym : symbols_) {
            redisReply* reply = nullptr;
            if (redisGetReply(context_, (void**)&reply) != REDIS_OK) {
                if (reply) freeReplyObject(reply);
                continue;
            }

            if (reply && reply->type == REDIS_REPLY_ARRAY && reply->elements >= 2) {
                // elements[0] = value, elements[1] = score(timestamp)
                sym.baseline_ts = std::stoll(reply->element[1]->str);
                valid_count++;
            }
            if (reply) freeReplyObject(reply);
        }

        std::cout << "[基线] 已获取 " << valid_count << "/" << symbols_.size() << " 个币种的基线时间戳" << std::endl;

        // 打印一些示例基线
        int shown = 0;
        for (const auto& sym : symbols_) {
            if (sym.baseline_ts > 0 && shown < 3) {
                std::cout << "  示例: " << sym.exchange << ":" << sym.symbol
                          << " 最新8h: " << format_kline_ts(sym.baseline_ts) << std::endl;
                shown++;
            }
        }

        return valid_count > 0;
    }

    void poll_new_klines() {
        // 使用Pipeline批量查询 —— 一次RTT完成所有查询
        int pending = 0;
        for (const auto& sym : symbols_) {
            if (sym.completed) continue;
            redisAppendCommand(context_, "ZREVRANGE %s 0 0 WITHSCORES", sym.key.c_str());
            pending++;
        }

        // 收集响应
        int idx = 0;
        for (auto& sym : symbols_) {
            if (sym.completed) continue;

            redisReply* reply = nullptr;
            if (redisGetReply(context_, (void**)&reply) != REDIS_OK) {
                if (reply) freeReplyObject(reply);
                idx++;
                continue;
            }

            if (reply && reply->type == REDIS_REPLY_ARRAY && reply->elements >= 2) {
                int64_t latest_ts = std::stoll(reply->element[1]->str);
                sym.new_ts = latest_ts;
            }

            if (reply) freeReplyObject(reply);
            idx++;
        }
    }

    void print_report(bool has_first,
                      const system_clock::time_point& first_wall,
                      const steady_clock::time_point& first_steady,
                      const system_clock::time_point& last_wall,
                      const steady_clock::time_point& last_steady,
                      int completed_count, int total_symbols) {
        std::cout << "\n╔══════════════════════════════════════════════════════════╗" << std::endl;
        std::cout << "║          8小时K线聚合完成时间报告                        ║" << std::endl;
        std::cout << "╚══════════════════════════════════════════════════════════╝" << std::endl;

        if (!has_first) {
            std::cout << "\n  监控期间未检测到新的8h K线" << std::endl;
            std::cout << "\n  待监控币种: " << total_symbols << " 个" << std::endl;

            // 打印各币种当前最新时间戳
            std::cout << "\n  各币种当前最新8h K线时间戳:" << std::endl;
            int shown = 0;
            for (const auto& sym : symbols_) {
                if (shown >= 10) {
                    std::cout << "  ... 共 " << total_symbols << " 个" << std::endl;
                    break;
                }
                std::cout << "  " << sym.exchange << ":" << sym.symbol
                          << " -> " << format_kline_ts(sym.baseline_ts) << std::endl;
                shown++;
            }
        } else {
            int64_t total_spread_ms = duration_cast<milliseconds>(last_steady - first_steady).count();

            std::cout << "\n  完成情况: " << completed_count << "/" << total_symbols << " 个币种" << std::endl;
            std::cout << "\n  ┌──────────────────────────────────────────┐" << std::endl;
            std::cout << "  │ 第一根新8h K线完成时间: " << format_wall_time(first_wall) << " │" << std::endl;
            std::cout << "  │ 最后一根新8h K线完成时间: " << format_wall_time(last_wall) << " │" << std::endl;
            std::cout << "  │ 总耗时: " << std::setw(30) << std::left << format_duration_ms(total_spread_ms) << " │" << std::endl;
            std::cout << "  └──────────────────────────────────────────┘" << std::endl;

            // 按完成时间排序，打印每个交易所的统计
            std::cout << "\n  ── 按交易所分组 ──" << std::endl;

            // Binance统计
            int binance_done = 0, binance_total = 0;
            system_clock::time_point binance_first, binance_last;
            bool binance_has_first = false;

            for (const auto& sym : symbols_) {
                if (sym.exchange != "binance") continue;
                binance_total++;
                if (sym.completed) {
                    binance_done++;
                    if (!binance_has_first || sym.completion_time < binance_first) {
                        binance_first = sym.completion_time;
                        binance_has_first = true;
                    }
                    if (sym.completion_time > binance_last) {
                        binance_last = sym.completion_time;
                    }
                }
            }

            if (binance_total > 0) {
                std::cout << "\n  Binance: " << binance_done << "/" << binance_total << " 完成" << std::endl;
                if (binance_has_first) {
                    auto binance_spread = duration_cast<milliseconds>(binance_last - binance_first).count();
                    std::cout << "    首个完成: " << format_time_short(binance_first) << std::endl;
                    std::cout << "    最后完成: " << format_time_short(binance_last) << std::endl;
                    std::cout << "    耗时: " << format_duration_ms(binance_spread) << std::endl;
                }
            }

            // OKX统计
            int okx_done = 0, okx_total = 0;
            system_clock::time_point okx_first, okx_last;
            bool okx_has_first = false;

            for (const auto& sym : symbols_) {
                if (sym.exchange != "okx") continue;
                okx_total++;
                if (sym.completed) {
                    okx_done++;
                    if (!okx_has_first || sym.completion_time < okx_first) {
                        okx_first = sym.completion_time;
                        okx_has_first = true;
                    }
                    if (sym.completion_time > okx_last) {
                        okx_last = sym.completion_time;
                    }
                }
            }

            if (okx_total > 0) {
                std::cout << "\n  OKX: " << okx_done << "/" << okx_total << " 完成" << std::endl;
                if (okx_has_first) {
                    auto okx_spread = duration_cast<milliseconds>(okx_last - okx_first).count();
                    std::cout << "    首个完成: " << format_time_short(okx_first) << std::endl;
                    std::cout << "    最后完成: " << format_time_short(okx_last) << std::endl;
                    std::cout << "    耗时: " << format_duration_ms(okx_spread) << std::endl;
                }
            }

            // 未完成的币种
            if (completed_count < total_symbols) {
                std::cout << "\n  ── 未完成的币种 ──" << std::endl;
                int shown = 0;
                for (const auto& sym : symbols_) {
                    if (!sym.completed) {
                        std::cout << "  ✗ " << sym.exchange << ":" << sym.symbol
                                  << " (最新: " << format_kline_ts(sym.baseline_ts) << ")" << std::endl;
                        shown++;
                        if (shown >= 20) {
                            int remaining = total_symbols - completed_count - shown;
                            if (remaining > 0) {
                                std::cout << "  ... 还有 " << remaining << " 个未完成" << std::endl;
                            }
                            break;
                        }
                    }
                }
            }
        }

        std::cout << "\n══════════════════════════════════════════════════════════" << std::endl;
    }

    MonitorConfig config_;
    redisContext* context_;
    std::vector<SymbolCompletion> symbols_;
};

// ============================================================
// main
// ============================================================

int main(int argc, char* argv[]) {
    std::cout << "╔══════════════════════════════════════════════════════════╗" << std::endl;
    std::cout << "║       8小时K线聚合完成时间监控工具                       ║" << std::endl;
    std::cout << "╚══════════════════════════════════════════════════════════╝" << std::endl;
    std::cout << std::endl;

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    MonitorConfig config;

    // 解析命令行参数
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--poll-ms" && i + 1 < argc) {
            config.poll_interval_ms = std::atoi(argv[++i]);
        } else if (arg == "--timeout" && i + 1 < argc) {
            config.timeout_seconds = std::atoi(argv[++i]);
        } else if (arg == "--redis-host" && i + 1 < argc) {
            config.redis_host = argv[++i];
        } else if (arg == "--redis-port" && i + 1 < argc) {
            config.redis_port = std::atoi(argv[++i]);
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "用法: " << argv[0] << " [选项]" << std::endl;
            std::cout << "  --poll-ms <ms>       轮询间隔（默认200ms）" << std::endl;
            std::cout << "  --timeout <seconds>  超时时间（默认600秒）" << std::endl;
            std::cout << "  --redis-host <host>  Redis主机（默认127.0.0.1）" << std::endl;
            std::cout << "  --redis-port <port>  Redis端口（默认6379）" << std::endl;
            return 0;
        }
    }

    Kline8hMonitor monitor(config);
    if (!monitor.init()) {
        std::cerr << "[错误] 初始化失败" << std::endl;
        return 1;
    }

    monitor.run();
    return 0;
}
