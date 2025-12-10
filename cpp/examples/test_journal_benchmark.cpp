/**
 * Journal 性能基准测试
 * 
 * 测试纯写入性能（无Python Reader）
 */

#include <iostream>
#include <chrono>
#include <vector>
#include <algorithm>

#include "../core/journal_protocol.h"
#include "../core/journal_writer.h"

using namespace trading::journal;
using namespace std::chrono;

int main() {
    std::cout << "========================================\n";
    std::cout << "    Journal Write Benchmark\n";
    std::cout << "========================================\n\n";
    
    const std::string journal_path = "/tmp/benchmark_journal.dat";
    const int num_events = 1000000;  // 100万事件
    
    try {
        JournalWriter writer(journal_path, 128 * 1024 * 1024);
        
        std::cout << "Starting benchmark: " << num_events << " events\n\n";
        
        // 预热
        std::cout << "Warming up...\n";
        for (int i = 0; i < 1000; i++) {
            writer.write_ticker("BTC-USDT", 50000.0, 49995.0, 50005.0, 1000.0);
        }
        
        // 重置
        writer.reset();
        
        // 基准测试
        std::cout << "Running benchmark...\n";
        
        auto start = steady_clock::now();
        
        for (int i = 0; i < num_events; i++) {
            double price = 50000.0 + (i % 100) * 10.0;
            
            if (!writer.write_ticker("BTC-USDT", price, price-5, price+5, 1000.0)) {
                std::cerr << "Journal full at event " << i << "\n";
                break;
            }
            
            if ((i + 1) % 100000 == 0) {
                std::cout << "  " << (i + 1) << " events...\n";
            }
        }
        
        auto end = steady_clock::now();
        auto elapsed_ns = duration_cast<nanoseconds>(end - start).count();
        auto elapsed_sec = elapsed_ns / 1e9;
        
        // 统计
        double throughput = num_events / elapsed_sec;
        double avg_latency_ns = static_cast<double>(elapsed_ns) / num_events;
        
        std::cout << "\n========================================\n";
        std::cout << "         Benchmark Results\n";
        std::cout << "========================================\n";
        std::cout << "Total Events:      " << num_events << "\n";
        std::cout << "Total Time:        " << elapsed_sec << " seconds\n";
        std::cout << "Throughput:        " << throughput << " events/s\n";
        std::cout << "Avg Write Latency: " << avg_latency_ns << " ns\n";
        std::cout << "                   " << (avg_latency_ns / 1000.0) << " μs\n";
        std::cout << "========================================\n";
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    
    return 0;
}

