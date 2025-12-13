#!/usr/bin/env python3
"""
多策略并发基准测试运行器
========================

同时启动多个策略进程，测试 ZeroMQ 框架在并发场景下的延迟表现。

测试配置：
- 5 个策略同时运行
- 服务端每 100ms 推送一次行情（8KB）
- 共推送 1000 次

使用方法：
    # 启动 5 个策略
    python run_benchmark.py --num-strategies 5

    # 自定义配置
    python run_benchmark.py -n 5 --count 1000

前置条件：
    1. 先编译并启动 C++ 服务端
    2. 确保服务端配置为 100ms 间隔、8KB 消息、1000 条

作者: Sequence Framework
"""

import subprocess
import sys
import os
import time
import argparse
import json
from typing import List, Dict
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================

BENCHMARK_SCRIPT = os.path.join(os.path.dirname(__file__), "benchmark_latency.py")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


# ============================================================
# 进程管理
# ============================================================

class StrategyProcess:
    """策略进程"""
    
    def __init__(self, strategy_id: int, expected_count: int):
        self.strategy_id = strategy_id
        self.expected_count = expected_count
        self.process = None
        self.start_time = 0
    
    def start(self):
        cmd = [
            sys.executable,
            BENCHMARK_SCRIPT,
            "--id", str(self.strategy_id),
            "--count", str(self.expected_count)
        ]
        
        self.process = subprocess.Popen(cmd)
        self.start_time = time.time()
        
        print(f"[Runner] 启动策略 benchmark_{self.strategy_id}, PID: {self.process.pid}")
    
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def wait(self, timeout=None):
        if self.process:
            return self.process.wait(timeout=timeout)
    
    def terminate(self):
        if self.process and self.is_running():
            self.process.terminate()
            self.process.wait(timeout=5)


# ============================================================
# 测试运行器
# ============================================================

class BenchmarkRunner:
    """基准测试运行器"""
    
    def __init__(self, num_strategies: int, expected_count: int):
        self.num_strategies = num_strategies
        self.expected_count = expected_count
        self.processes: List[StrategyProcess] = []
        self.start_time = 0
        self.end_time = 0
        
        os.makedirs(REPORT_DIR, exist_ok=True)
    
    def run(self):
        print("\n" + "=" * 70)
        print("  ZeroMQ 多策略并发基准测试")
        print("=" * 70)
        print(f"\n测试配置:")
        print(f"  策略数量: {self.num_strategies}")
        print(f"  预期消息: {self.expected_count}")
        print(f"  消息大小: 8KB")
        print(f"  发送间隔: 100ms")
        print()
        
        # 检查服务端是否运行
        if not os.path.exists("/tmp/trading_md.ipc"):
            print("⚠️  警告: IPC 文件不存在，请确保服务端已启动")
            print("   运行: cd cpp/build && ./trading_server")
            print()
        
        self.start_time = time.time()
        
        # 启动所有策略（间隔启动，避免同时连接）
        print("[Runner] 启动策略进程...")
        for i in range(1, self.num_strategies + 1):
            sp = StrategyProcess(i, self.expected_count)
            sp.start()
            self.processes.append(sp)
            time.sleep(0.3)  # 间隔 300ms 启动
        
        print(f"\n[Runner] 已启动 {self.num_strategies} 个策略进程")
        print("[Runner] 等待测试完成...\n")
        print("-" * 70)
        
        # 监控进程
        try:
            self._monitor()
        except KeyboardInterrupt:
            print("\n[Runner] 收到中断信号，停止所有策略...")
            self._stop_all()
        
        self.end_time = time.time()
        
        # 等待文件写入
        time.sleep(2)
        
        # 生成汇总报告
        self._generate_summary()
    
    def _monitor(self):
        """监控进程"""
        while True:
            running = [p for p in self.processes if p.is_running()]
            
            if not running:
                print("\n[Runner] 所有策略已完成")
                break
            
            elapsed = time.time() - self.start_time
            print(f"\r[Runner] 运行中: {len(running)}/{self.num_strategies} | "
                  f"耗时: {elapsed:.0f}s", end="", flush=True)
            
            time.sleep(1)
    
    def _stop_all(self):
        """停止所有进程"""
        for p in self.processes:
            if p.is_running():
                p.terminate()
    
    def _generate_summary(self):
        """生成汇总报告"""
        print("\n" + "=" * 70)
        print("  多策略并发测试汇总报告")
        print("=" * 70)
        
        # 收集报告
        reports = []
        report_files = list(Path(REPORT_DIR).glob("benchmark_*.json"))
        
        # 只取最近的报告
        recent_time = time.time() - (self.end_time - self.start_time) - 120
        
        for f in sorted(report_files, key=lambda x: x.stat().st_mtime, reverse=True):
            if f.stat().st_mtime > recent_time:
                try:
                    with open(f, 'r') as fp:
                        reports.append(json.load(fp))
                except:
                    pass
        
        if not reports:
            print("\n⚠️  未找到报告文件")
            return
        
        print(f"\n收集到 {len(reports)} 份报告\n")
        
        # 汇总表格
        print(f"{'策略ID':<15} {'样本数':<10} {'平均(μs)':<12} {'P50(μs)':<12} {'P90(μs)':<12} {'P99(μs)':<12} {'最大(μs)':<12} {'异常%':<10}")
        print("-" * 95)
        
        all_means = []
        all_p99 = []
        all_max = []
        all_outlier_pct = []
        
        for r in reports:
            strategy_id = r.get("strategy_id", "unknown")
            lat = r.get("latency_timestamp", {})
            
            mean = lat.get("mean_us", 0)
            p50 = lat.get("p50_us", 0)
            p90 = lat.get("p90_us", 0)
            p99 = lat.get("p99_us", 0)
            max_lat = lat.get("max_us", 0)
            outlier_pct = lat.get("outlier_pct", 0)
            count = lat.get("count", 0)
            
            print(f"{strategy_id:<15} {count:<10} {mean:<12.2f} {p50:<12.2f} {p90:<12.2f} {p99:<12.2f} {max_lat:<12.2f} {outlier_pct:<10.2f}")
            
            if mean > 0:
                all_means.append(mean)
                all_p99.append(p99)
                all_max.append(max_lat)
                all_outlier_pct.append(outlier_pct)
        
        # 汇总统计
        if all_means:
            print("-" * 95)
            avg_mean = sum(all_means) / len(all_means)
            avg_p99 = sum(all_p99) / len(all_p99)
            max_p99 = max(all_p99)
            max_max = max(all_max)
            avg_outlier = sum(all_outlier_pct) / len(all_outlier_pct)
            
            print(f"{'汇总':<15} {'-':<10} {avg_mean:<12.2f} {'-':<12} {'-':<12} {avg_p99:<12.2f} {max_max:<12.2f} {avg_outlier:<10.2f}")
        
        # 评估结果
        print(f"\n{'='*70}")
        print("  评估结果")
        print("=" * 70)
        
        total_elapsed = self.end_time - self.start_time
        print(f"\n运行时间: {total_elapsed:.1f} 秒")
        print(f"策略数量: {len(reports)}")
        
        if all_p99:
            avg_p99 = sum(all_p99) / len(all_p99)
            max_p99 = max(all_p99)
            max_max = max(all_max)
            avg_outlier = sum(all_outlier_pct) / len(all_outlier_pct)
            
            print(f"\n延迟评估:")
            print(f"  平均 P99: {avg_p99:.2f} μs ({avg_p99/1000:.3f} ms)")
            print(f"  最差 P99: {max_p99:.2f} μs ({max_p99/1000:.3f} ms)")
            print(f"  最大延迟: {max_max:.2f} μs ({max_max/1000:.3f} ms)")
            print(f"  平均异常比例: {avg_outlier:.2f}%")
            
            print(f"\n最终判定:")
            
            # 判断是否满足 <1ms 要求
            if max_p99 < 1000 and max_max < 2000:
                print(f"  ✅ 所有策略 P99 < 1ms，最大值 < 2ms")
                print(f"  ✅ 框架满足低延迟要求")
            elif max_p99 < 1000:
                print(f"  ⚠️ P99 满足 < 1ms 要求")
                print(f"  ⚠️ 但存在个别异常值 ({max_max/1000:.2f}ms)")
                print(f"  建议: 可接受，但需监控生产环境")
            else:
                print(f"  ❌ P99 延迟 {max_p99:.0f}μs ≥ 1ms，不满足要求")
                print(f"  ❌ 最大延迟 {max_max:.0f}μs")
                print(f"  建议: 考虑使用共享内存方案")
        
        print("\n" + "=" * 70)
        
        # 保存汇总
        summary = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "num_strategies": self.num_strategies,
                "expected_count": self.expected_count
            },
            "results": {
                "total_elapsed": total_elapsed,
                "avg_mean_us": sum(all_means) / len(all_means) if all_means else 0,
                "avg_p99_us": sum(all_p99) / len(all_p99) if all_p99 else 0,
                "max_p99_us": max(all_p99) if all_p99 else 0,
                "max_latency_us": max(all_max) if all_max else 0,
                "avg_outlier_pct": sum(all_outlier_pct) / len(all_outlier_pct) if all_outlier_pct else 0
            },
            "individual_reports": reports
        }
        
        summary_file = os.path.join(REPORT_DIR, f"benchmark_summary_{int(time.time())}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n汇总报告: {summary_file}")


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="多策略并发基准测试")
    parser.add_argument("--num-strategies", "-n", type=int, default=5, 
                        help="策略数量 (默认: 5)")
    parser.add_argument("--count", "-c", type=int, default=1000, 
                        help="预期消息数量 (默认: 1000)")
    
    args = parser.parse_args()
    
    # 检查脚本是否存在
    if not os.path.exists(BENCHMARK_SCRIPT):
        print(f"错误: 找不到 {BENCHMARK_SCRIPT}")
        sys.exit(1)
    
    runner = BenchmarkRunner(
        num_strategies=args.num_strategies,
        expected_count=args.count
    )
    
    runner.run()


if __name__ == "__main__":
    main()

