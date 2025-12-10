/**
 * 精确延迟测试程序
 * 
 * 使用共享标志位测量真实的端到端延迟
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <vector>
#include <algorithm>
#include <fstream>

#include "../core/journal_protocol.h"
#include "../core/journal_writer.h"

using namespace trading::journal;
using namespace std::chrono;

// 共享标志文件（用于Python反馈）
const char* FEEDBACK_FILE = "/tmp/journal_feedback.txt";

int main() {
    std::cout << "========================================\n";
    std::cout << "  Precise Latency Test\n";
    std::cout << "========================================\n\n";
    
    const std::string journal_path = "/tmp/trading_journal.dat";
    const int num_samples = 1000;  // 采样1000次
    
    try {
        // 清理旧文件
        std::remove(journal_path.c_str());
        std::remove(FEEDBACK_FILE);
        
        // 创建Writer
        JournalWriter writer(journal_path);
        
        std::cout << "Waiting for Python Reader...\n";
        std::cout << "Please start: python3 test_latency_client.py\n\n";
        
        // 等待Python启动（检查反馈文件）
        while (!std::ifstream(FEEDBACK_FILE).good()) {
            std::this_thread::sleep_for(milliseconds(100));
        }
        
        std::cout << "Python Reader detected! Starting test...\n\n";
        std::this_thread::sleep_for(seconds(1));
        
        // 开始测试
        std::vector<int64_t> latencies_ns;
        
        for (int i = 0; i < num_samples; i++) {
            // 记录发送时间
            auto send_time = steady_clock::now();
            int64_t send_time_ns = duration_cast<nanoseconds>(
                send_time.time_since_epoch()
            ).count();
            
            // 写入Ticker（价格包含序号，用于验证）
            double price = 50000.0 + i;
            writer.write_ticker("BTC-USDT", price, price-5, price+5, 1000.0);
            
            // 等待Python反馈
            std::this_thread::sleep_for(microseconds(200));
            
            // 读取反馈时间
            std::ifstream feedback(FEEDBACK_FILE);
            std::string line;
            if (std::getline(feedback, line)) {
                int64_t recv_time_ns = std::stoll(line);
                int64_t latency_ns = recv_time_ns - send_time_ns;
                
                if (latency_ns > 0 && latency_ns < 1000000000) {  // < 1秒
                    latencies_ns.push_back(latency_ns);
                }
            }
            
            if ((i + 1) % 100 == 0) {
                std::cout << "Tested " << (i + 1) << " samples...\n";
            }
        }
        
        // 统计
        if (!latencies_ns.empty()) {
            std::sort(latencies_ns.begin(), latencies_ns.end());
            
            double avg = 0;
            for (auto l : latencies_ns) avg += l;
            avg /= latencies_ns.size();
            
            int64_t p50 = latencies_ns[latencies_ns.size() * 0.50];
            int64_t p95 = latencies_ns[latencies_ns.size() * 0.95];
            int64_t p99 = latencies_ns[latencies_ns.size() * 0.99];
            
            std::cout << "\n========================================\n";
            std::cout << "    End-to-End Latency Results\n";
            std::cout << "========================================\n";
            std::cout << "Samples:  " << latencies_ns.size() << "\n\n";
            
            std::cout << "Latency (nanoseconds):\n";
            std::cout << "  Min:  " << latencies_ns.front() << " ns\n";
            std::cout << "  Avg:  " << static_cast<int64_t>(avg) << " ns\n";
            std::cout << "  P50:  " << p50 << " ns\n";
            std::cout << "  P95:  " << p95 << " ns\n";
            std::cout << "  P99:  " << p99 << " ns\n";
            std::cout << "  Max:  " << latencies_ns.back() << " ns\n\n";
            
            std::cout << "Latency (microseconds):\n";
            std::cout << "  Min:  " << (latencies_ns.front() / 1000.0) << " μs\n";
            std::cout << "  Avg:  " << (avg / 1000.0) << " μs\n";
            std::cout << "  P50:  " << (p50 / 1000.0) << " μs\n";
            std::cout << "  P95:  " << (p95 / 1000.0) << " μs\n";
            std::cout << "  P99:  " << (p99 / 1000.0) << " μs\n";
            std::cout << "  Max:  " << (latencies_ns.back() / 1000.0) << " μs\n";
            std::cout << "========================================\n";
        }
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    
    return 0;
}

