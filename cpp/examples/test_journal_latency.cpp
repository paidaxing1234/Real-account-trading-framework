/**
 * Journal 延迟测试程序
 * 
 * 测试 C++ Writer → Python Reader 的端到端延迟
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <vector>
#include <algorithm>
#include <cmath>
#include <signal.h>

#include "../core/journal_protocol.h"
#include "../core/journal_writer.h"

using namespace trading::journal;
using namespace std::chrono;

// 全局标志：是否继续运行
volatile bool g_running = true;

void signal_handler(int signum) {
    std::cout << "\nReceived signal " << signum << ", stopping...\n";
    g_running = false;
}

// 统计信息
struct Stats {
    size_t total_events = 0;
    double total_time_sec = 0.0;
    std::vector<double> latencies_us;  // 微秒
    
    void print() const {
        std::cout << "\n========================================\n";
        std::cout << "         Performance Statistics\n";
        std::cout << "========================================\n";
        std::cout << "Total Events:  " << total_events << "\n";
        std::cout << "Total Time:    " << total_time_sec << " seconds\n";
        std::cout << "Throughput:    " << (total_events / total_time_sec) << " events/s\n";
        
        if (!latencies_us.empty()) {
            auto sorted = latencies_us;
            std::sort(sorted.begin(), sorted.end());
            
            double avg = 0;
            for (auto l : sorted) avg += l;
            avg /= sorted.size();
            
            double p50 = sorted[sorted.size() * 0.50];
            double p95 = sorted[sorted.size() * 0.95];
            double p99 = sorted[sorted.size() * 0.99];
            
            std::cout << "\nLatency (microseconds):\n";
            std::cout << "  Min:  " << sorted.front() << " μs\n";
            std::cout << "  Avg:  " << avg << " μs\n";
            std::cout << "  P50:  " << p50 << " μs\n";
            std::cout << "  P95:  " << p95 << " μs\n";
            std::cout << "  P99:  " << p99 << " μs\n";
            std::cout << "  Max:  " << sorted.back() << " μs\n";
        }
        std::cout << "========================================\n";
    }
};

int main(int argc, char* argv[]) {
    // 注册信号处理
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    std::cout << "========================================\n";
    std::cout << "  Journal Latency Test (C++ Writer)\n";
    std::cout << "========================================\n\n";
    
    // 解析参数
    std::string journal_path = "/tmp/trading_journal.dat";
    int num_events = 100000;
    int interval_us = 100;  // 发送间隔（微秒）
    
    if (argc > 1) journal_path = argv[1];
    if (argc > 2) num_events = std::stoi(argv[2]);
    if (argc > 3) interval_us = std::stoi(argv[3]);
    
    std::cout << "Configuration:\n";
    std::cout << "  Journal Path:   " << journal_path << "\n";
    std::cout << "  Number of Events: " << num_events << "\n";
    std::cout << "  Send Interval:  " << interval_us << " μs\n\n";
    
    try {
        // 创建 Journal Writer
        JournalWriter writer(journal_path, 128 * 1024 * 1024);  // 128MB
        
        std::cout << "Journal Writer created successfully.\n";
        std::cout << "Starting Python Reader in another terminal:\n";
        std::cout << "  python3 ../core/journal_reader.py " << journal_path << "\n\n";
        
        std::cout << "Press Enter to start sending events...\n";
        std::cin.get();
        
        // 开始发送
        std::cout << "Sending " << num_events << " Ticker events...\n\n";
        
        auto start_time = steady_clock::now();
        
        for (int i = 0; i < num_events && g_running; i++) {
            // 生成模拟数据
            char symbol[16];
            snprintf(symbol, sizeof(symbol), "BTC-USDT");
            
            double base_price = 50000.0;
            double price = base_price + (i % 100) * 10.0;
            double bid = price - 5.0;
            double ask = price + 5.0;
            double volume = 1000.0 + (i % 50) * 10.0;
            
            // 写入 Journal
            if (!writer.write_ticker(symbol, price, bid, ask, volume)) {
                std::cerr << "Journal full! Stopping...\n";
                break;
            }
            
            // 定期打印进度
            if ((i + 1) % 10000 == 0) {
                std::cout << "Sent " << (i + 1) << " events...\n";
            }
            
            // 控制发送速率
            if (interval_us > 0) {
                std::this_thread::sleep_for(microseconds(interval_us));
            }
        }
        
        auto end_time = steady_clock::now();
        auto elapsed = duration_cast<microseconds>(end_time - start_time).count();
        
        // 打印统计
        std::cout << "\n========================================\n";
        std::cout << "         Sending Statistics\n";
        std::cout << "========================================\n";
        std::cout << "Total Events:  " << num_events << "\n";
        std::cout << "Total Time:    " << (elapsed / 1e6) << " seconds\n";
        std::cout << "Throughput:    " << (num_events / (elapsed / 1e6)) << " events/s\n";
        std::cout << "Write Cursor:  " << writer.get_write_cursor() << " bytes\n";
        std::cout << "========================================\n\n";
        
        std::cout << "All events sent. Check Python Reader for latency stats.\n";
        std::cout << "Press Enter to exit...\n";
        std::cin.get();
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    
    return 0;
}

