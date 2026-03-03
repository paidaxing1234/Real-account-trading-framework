/**
 * @file kline_latency_monitor.cpp
 * @brief 1分钟K线接收延迟监测工具
 *
 * 功能：
 * - 订阅 ZMQ IPC 行情通道，被动接收 1m K线
 * - 记录每个 K线周期内"第一根币种到达"到"最后一根币种到达"的时间跨度
 * - 统计并输出：最小/最大/平均延迟、每周期币种数量
 * - 不写 Redis，纯观测
 *
 * 编译：
 *   g++ -O2 -std=c++17 kline_latency_monitor.cpp -lzmq -o kline_latency_monitor
 *
 * 运行：
 *   ./kline_latency_monitor
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
#include <numeric>
#include <algorithm>
#include <climits>
#include <thread>

#include <zmq.hpp>
#include <nlohmann/json.hpp>

using namespace std::chrono;
using json = nlohmann::json;

// ============================================================
// 全局控制
// ============================================================

std::atomic<bool> g_running{true};

void signal_handler(int) {
    g_running.store(false);
}

// ============================================================
// 工具函数
// ============================================================

// 格式化 system_clock 时间点为 HH:MM:SS.mmm
std::string format_time(const system_clock::time_point& tp) {
    auto t = system_clock::to_time_t(tp);
    std::tm tm = *std::localtime(&t);
    auto ms = duration_cast<milliseconds>(tp.time_since_epoch()) % 1000;
    std::ostringstream oss;
    oss << std::put_time(&tm, "%H:%M:%S") << "." << std::setw(3) << std::setfill('0') << ms.count();
    return oss.str();
}

// 格式化 kline 时间戳（ms）为 MM-DD HH:MM
std::string format_kline_ts(int64_t ts_ms) {
    time_t t = ts_ms / 1000;
    std::tm tm = *std::localtime(&t);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%m-%d %H:%M");
    return oss.str();
}

// ============================================================
// 每个 K线周期的统计数据
// ============================================================

struct PeriodRecord {
    int64_t kline_ts;                        // K线起始时间戳（ms）
    steady_clock::time_point first_arrival;  // 第一个币种到达时刻（精确计时）
    steady_clock::time_point last_arrival;   // 最后一个币种到达时刻
    system_clock::time_point first_wall;     // 第一个币种��达的真实时钟时间（用于显示）
    system_clock::time_point last_wall;      // 最后一个币种到达的真实时钟时间
    std::set<std::string> symbols;           // 已接收的币种集合
    bool finalized = false;                  // 是否已完成统计
};

// ============================================================
// 全局聚合统计
// ============================================================

struct AggStats {
    int total_periods = 0;
    int64_t min_spread_ms = INT64_MAX;
    int64_t max_spread_ms = 0;
    double sum_spread_ms = 0.0;
    int min_symbols = INT_MAX;
    int max_symbols = 0;

    void update(int64_t spread_ms, int symbol_count) {
        total_periods++;
        min_spread_ms = std::min(min_spread_ms, spread_ms);
        max_spread_ms = std::max(max_spread_ms, spread_ms);
        sum_spread_ms += spread_ms;
        min_symbols = std::min(min_symbols, symbol_count);
        max_symbols = std::max(max_symbols, symbol_count);
    }

    double avg_spread_ms() const {
        return total_periods > 0 ? sum_spread_ms / total_periods : 0.0;
    }
};

// ============================================================
// 主监测器
// ============================================================

class KlineLatencyMonitor {
public:
    KlineLatencyMonitor() : zmq_ctx_(1) {}

    bool init() {
        try {
            sub_ = std::make_unique<zmq::socket_t>(zmq_ctx_, zmq::socket_type::sub);
            sub_->connect("ipc:///tmp/seq_md.ipc");
            sub_->set(zmq::sockopt::subscribe, "");  // 订阅所有
            sub_->set(zmq::sockopt::rcvtimeo, 200);  // 200ms 超时，避免阻塞
            std::cout << "[ZMQ] 已连接: ipc:///tmp/seq_md.ipc\n";
            return true;
        } catch (const zmq::error_t& e) {
            std::cerr << "[ZMQ] 连接失败: " << e.what() << "\n";
            return false;
        }
    }

    void run() {
        std::cout << "[Monitor] 开始监测，等待1m K线数据...\n";
        std::cout << "  每个周期结束后将打印该分钟的延迟统计\n";
        std::cout << "  按 Ctrl+C 停止并打印汇总统计\n\n";

        auto last_print_time = steady_clock::now();

        while (g_running.load()) {
            zmq::message_t msg;
            try {
                auto result = sub_->recv(msg, zmq::recv_flags::dontwait);
                if (result.has_value()) {
                    on_message(std::string(static_cast<char*>(msg.data()), msg.size()));
                }
            } catch (const zmq::error_t& e) {
                if (e.num() != EAGAIN) {
                    std::cerr << "[ZMQ] 接收错误: " << e.what() << "\n";
                }
            }

            // 每 500ms 做一次"周期超时检查"：如果一个周期超过 5 秒没收到新数据，视为完成
            auto now = steady_clock::now();
            if (duration_cast<milliseconds>(now - last_print_time).count() >= 500) {
                last_print_time = now;
                check_stale_periods(now);
            }

            std::this_thread::sleep_for(microseconds(200));
        }

        // 程序退出时，强制完成所有尚未完成的周期
        std::cout << "\n[Monitor] 正在停止，强制完成剩余周期...\n";
        auto now = steady_clock::now();
        for (auto& [ts, rec] : periods_) {
            if (!rec.finalized) {
                finalize(rec, now);
            }
        }

        print_summary();
    }

private:
    void on_message(const std::string& raw) {
        // 处理 topic|json 格式
        std::string data_str = raw;
        size_t sep = raw.find('|');
        if (sep != std::string::npos) {
            data_str = raw.substr(sep + 1);
        }

        json data;
        try {
            data = json::parse(data_str);
        } catch (...) {
            return;
        }

        std::string type = data.value("type", "");
        std::string interval = data.value("interval", "");
        if (type != "kline" || interval != "1m") return;

        std::string symbol = data.value("symbol", "");
        int64_t kline_ts = data.value("timestamp", 0LL);
        if (symbol.empty() || kline_ts == 0) return;

        auto now_steady = steady_clock::now();
        auto now_wall = system_clock::now();

        auto& rec = periods_[kline_ts];
        bool is_new = rec.symbols.empty();

        if (is_new) {
            rec.kline_ts = kline_ts;
            rec.first_arrival = now_steady;
            rec.first_wall = now_wall;
            rec.last_arrival = now_steady;
            rec.last_wall = now_wall;

            // 打印"新周期开始"
            std::cout << "\n[" << format_kline_ts(kline_ts) << "] 新周期开始 "
                      << "首个币种: " << symbol
                      << " @ " << format_time(now_wall) << "\n";
        } else {
            // 更新最后到达时刻
            rec.last_arrival = now_steady;
            rec.last_wall = now_wall;
        }

        rec.symbols.insert(symbol);

        // 实时打印进度（每增加10个币种打印一次，避免刷屏）
        if (rec.symbols.size() % 10 == 0) {
            auto spread_ms = duration_cast<milliseconds>(rec.last_arrival - rec.first_arrival).count();
            std::cout << "  ... " << rec.symbols.size() << " 个币种已到达, 已用 " << spread_ms << " ms\n";
        }
    }

    // 超时检查：超过 stale_ms 没有新数据的周期视为完成
    void check_stale_periods(const steady_clock::time_point& now) {
        const int64_t stale_ms = 5000;  // 5秒无新数据 -> 视为完成

        for (auto& [ts, rec] : periods_) {
            if (rec.finalized) continue;
            auto idle_ms = duration_cast<milliseconds>(now - rec.last_arrival).count();
            if (idle_ms >= stale_ms) {
                finalize(rec, now);
            }
        }

        // 清理超过 10 分钟的旧记录，防止内存积累
        auto threshold = duration_cast<milliseconds>(now.time_since_epoch()).count() - 600000;
        for (auto it = periods_.begin(); it != periods_.end(); ) {
            if (it->second.finalized && it->first < threshold) {
                it = periods_.erase(it);
            } else {
                ++it;
            }
        }
    }

    void finalize(PeriodRecord& rec, const steady_clock::time_point& /*now*/) {
        rec.finalized = true;

        int64_t spread_ms = duration_cast<milliseconds>(rec.last_arrival - rec.first_arrival).count();
        int sym_count = static_cast<int>(rec.symbols.size());

        stats_.update(spread_ms, sym_count);

        // 打印该周期的完整统计
        std::cout << "========================================\n";
        std::cout << "周期 [" << format_kline_ts(rec.kline_ts) << "]\n";
        std::cout << "  首个币种到达: " << format_time(rec.first_wall) << "\n";
        std::cout << "  最后币种到达: " << format_time(rec.last_wall) << "\n";
        std::cout << "  延迟跨度:     " << spread_ms << " ms\n";
        std::cout << "  本周期币种数: " << sym_count << "\n";
        std::cout << "  [汇总] 已统计 " << stats_.total_periods << " 个周期"
                  << " | 最小: " << (stats_.min_spread_ms == INT64_MAX ? 0 : stats_.min_spread_ms) << " ms"
                  << " | 最大: " << stats_.max_spread_ms << " ms"
                  << " | 平均: " << std::fixed << std::setprecision(1) << stats_.avg_spread_ms() << " ms"
                  << "\n";
        std::cout << "========================================\n";
    }

    void print_summary() {
        std::cout << "\n\n========================================\n";
        std::cout << "    最终汇总统计\n";
        std::cout << "========================================\n";
        if (stats_.total_periods == 0) {
            std::cout << "  没有收到任何完整周期的数据\n";
        } else {
            std::cout << "  统计周期数:   " << stats_.total_periods << "\n";
            std::cout << "  最小延迟跨度: " << (stats_.min_spread_ms == INT64_MAX ? 0 : stats_.min_spread_ms) << " ms\n";
            std::cout << "  最大延迟跨度: " << stats_.max_spread_ms << " ms\n";
            std::cout << "  平均延迟跨度: " << std::fixed << std::setprecision(1) << stats_.avg_spread_ms() << " ms\n";
            std::cout << "  最少币种数:   " << (stats_.min_symbols == INT_MAX ? 0 : stats_.min_symbols) << "\n";
            std::cout << "  最多币种数:   " << stats_.max_symbols << "\n";
        }
        std::cout << "========================================\n";
    }

private:
    zmq::context_t zmq_ctx_;
    std::unique_ptr<zmq::socket_t> sub_;

    std::map<int64_t, PeriodRecord> periods_;  // kline_ts -> 记录
    AggStats stats_;
};

// ============================================================
// main
// ============================================================

int main() {
    std::cout << "========================================\n";
    std::cout << "  1分钟K线接收延迟监测工具\n";
    std::cout << "  测量：同一K线周期内，第一个到最后一个\n";
    std::cout << "        币种到达的时间跨度\n";
    std::cout << "========================================\n\n";

    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    KlineLatencyMonitor monitor;
    if (!monitor.init()) {
        std::cerr << "[错误] 初始化失败\n";
        return 1;
    }

    monitor.run();
    return 0;
}
